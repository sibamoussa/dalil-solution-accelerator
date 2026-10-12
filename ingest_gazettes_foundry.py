"""Ingest the allowlisted 2026 gazettes through Foundry IQ file knowledge sources."""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from gazette_ocr import GazetteOCR, OCR_VERSION


API_VERSION = "2026-08-01-preview"
SOURCE_NAME = "dalil-gazettes-2026"
KNOWLEDGE_BASE_NAME = "dalil-policies-2026"
MAX_PDF_BYTES = 50 * 1024 * 1024
MANIFEST_PATH = Path(__file__).parent / "sources" / "gazettes-2026.json"


def validate_source_url(url: str) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "www.abudhabi.gov.ae"
        or not re.fullmatch(r"/-/media/sites/adgov/gazettes/2026/ar/[a-z0-9-]+\.ashx", parsed.path)
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Only allowlisted 2026 Arabic Abu Dhabi gazette URLs are permitted")
    return url


def load_manifest(path: Path) -> list[dict]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("year") != 2026 or manifest.get("language") != "ar":
        raise ValueError("Manifest must contain only Arabic gazettes from 2026")
    documents = manifest["documents"]
    if not documents or len(documents) > 200:
        raise ValueError("Manifest must contain between 1 and 200 documents")
    issues = set()
    urls = set()
    for document in documents:
        validate_source_url(document["url"])
        issue = document["issue"]
        if type(issue) is not int or not 1 <= issue <= 99 or issue in issues or document["url"] in urls:
            raise ValueError("Duplicate or invalid gazette issue")
        issues.add(issue)
        urls.add(document["url"])
    return documents


def file_name(document: dict) -> str:
    return f"gazette-2026-ar-issue-{document['issue']:02d}.pdf"


def download_pdf(session: requests.Session, url: str) -> bytes:
    for attempt in range(4):
        validate_source_url(url)
        with session.get(url, stream=True, allow_redirects=False, timeout=(15, 90)) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers["Location"])
                continue
            response.raise_for_status()
            if int(response.headers.get("Content-Length", "0")) > MAX_PDF_BYTES:
                raise ValueError("PDF exceeds the Basic-tier 50 MB file limit")
            payload = bytearray()
            for block in response.iter_content(64 * 1024):
                payload.extend(block)
                if len(payload) > MAX_PDF_BYTES:
                    raise ValueError("PDF exceeds the Basic-tier 50 MB file limit")
            if not payload.startswith(b"%PDF-"):
                raise ValueError("Source returned non-PDF content")
            return bytes(payload)
    raise ValueError("Too many redirects while downloading PDF")


class SearchAPI:
    def __init__(self, endpoint: str):
        parsed = urlsplit(endpoint)
        if parsed.scheme != "https" or not re.fullmatch(r"[a-z0-9-]+\.search\.windows\.net", parsed.netloc) or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("An explicit Azure AI Search HTTPS endpoint is required")
        self.endpoint = endpoint.rstrip("/")
        self.session = requests.Session()
        self.session.mount("https://", HTTPAdapter(max_retries=Retry(
            total=3, connect=0, read=0, other=0, status=3,
            allowed_methods=frozenset({"GET", "PUT"}), status_forcelist=[429],
            backoff_factor=5, respect_retry_after_header=True, raise_on_status=False,
        )))
        self.credential = None

    def request(self, method: str, path: str, **kwargs) -> dict:
        url = path if path.startswith("https://") else f"{self.endpoint}/{path}?api-version={API_VERSION}"
        if urlsplit(url).netloc != urlsplit(self.endpoint).netloc:
            raise ValueError("Refusing to send Search credentials to another host")
        key = os.getenv("SEARCH_KEY")
        if key:
            headers = {"api-key": key}
        else:
            if self.credential is None:
                from azure.identity import DefaultAzureCredential
                self.credential = DefaultAzureCredential()
            headers = {"Authorization": f"Bearer {self.credential.get_token('https://search.azure.com/.default').token}"}
        response = self.session.request(method, url, headers=headers, timeout=(240 if "files" in kwargs else 15, 240), allow_redirects=False, **kwargs)
        if not response.ok:
            raise RuntimeError(f"Search {method} failed (HTTP {response.status_code}): {response.text[:2000]}")
        return response.json() if response.content else {}

    def list_values(self, path: str) -> list[dict]:
        values = []
        visited = set()
        while path:
            if path in visited:
                raise RuntimeError("Repeated Search continuation link")
            visited.add(path)
            result = self.request("GET", path)
            values.extend(result.get("value", []))
            path = result.get("@odata.nextLink")
        return values


def knowledge_source(openai_endpoint: str) -> dict:
    parsed = urlsplit(openai_endpoint)
    if parsed.scheme != "https" or not re.fullmatch(r"[a-z0-9-]+\.openai\.azure\.com", parsed.netloc) or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("An explicit Azure OpenAI HTTPS endpoint is required")
    return {
        "name": SOURCE_NAME,
        "kind": "file",
        "description": "Arabic Abu Dhabi Official Gazette issues published in 2026 only. Historical legal text does not establish current legal validity.",
        "fileParameters": {"ingestionParameters": {
            "contentExtractionMode": "minimal",
            "embeddingModel": {"kind": "azureOpenAI", "azureOpenAIParameters": {
                "resourceUri": openai_endpoint.rstrip("/"),
                "deploymentId": "text-embedding-3-large",
                "modelName": "text-embedding-3-large",
            }},
        }},
    }


def ensure_knowledge_base(api: SearchAPI) -> None:
    definition = {
        "name": KNOWLEDGE_BASE_NAME,
        "description": "Public Arabic Abu Dhabi gazettes published in 2026 only.",
        "knowledgeSources": [{"name": SOURCE_NAME}],
        "outputMode": "extractiveData",
        "retrievalReasoningEffort": {"kind": "minimal"},
    }
    existing = next((item for item in api.list_values("knowledgebases") if item["name"] == KNOWLEDGE_BASE_NAME), None)
    if existing and {item["name"] for item in existing.get("knowledgeSources", [])} != {SOURCE_NAME}:
        raise RuntimeError("Knowledge base has unexpected sources; review before reuse")
    api.request("PUT", f"knowledgebases/{KNOWLEDGE_BASE_NAME}", json=definition)


def normalize_defaults(value):
    if isinstance(value, dict):
        return {key: normalize_defaults(item) for key, item in value.items() if item is not None and item != []}
    return value


def select_existing(files: list[dict], filename: str, digest: str) -> dict | None:
    matches = [item for item in files if item.get("fileName") == filename]
    if len(matches) > 1:
        raise RuntimeError(f"Duplicate remote files for {filename}; reconcile before retrying")
    if not matches:
        return None
    existing = matches[0]
    if existing.get("errorMessage"):
        raise RuntimeError(f"Remote extraction failed for {filename}: {existing['errorMessage']}")
    if existing.get("metadata", {}).get("sha256") != digest:
        raise RuntimeError(f"Content changed or hash unavailable for {filename}; explicit version review is required")
    return existing


def ingest(api: SearchAPI, documents: list[dict], openai_endpoint: str, apply: bool, ocr: GazetteOCR) -> list[dict]:
    definition = knowledge_source(openai_endpoint)
    sources = api.list_values("knowledgesources")
    existing_source = next((item for item in sources if item["name"] == SOURCE_NAME), None)
    if existing_source:
        parameters = existing_source.get("fileParameters", {}).get("ingestionParameters", {})
        if existing_source.get("kind") != "file" or normalize_defaults(parameters) != definition["fileParameters"]["ingestionParameters"]:
            raise RuntimeError("Existing knowledge source configuration differs; review it before reuse")
    if apply and not existing_source:
        api.request("PUT", f"knowledgesources/{SOURCE_NAME}", json=definition)
    files = api.list_values(f"knowledgesources/{SOURCE_NAME}/files") if apply or existing_source else []
    expected = {file_name(document) for document in documents}
    if any(item.get("fileName") not in expected for item in files):
        raise RuntimeError("Knowledge source contains files outside the manifest")
    results = []
    with requests.Session() as downloads:
        for document in documents:
            filename = file_name(document)
            payload = download_pdf(downloads, document["url"])
            digest = hashlib.sha256(payload).hexdigest()
            existing = select_existing(files, filename, digest)
            result = {"fileName": filename, "source_url": document["url"], "sha256": digest, "bytes": len(payload)}
            if existing and existing.get("metadata", {}).get("ocr_version") == OCR_VERSION:
                result.update(status="unchanged", fileId=existing["fileId"])
            elif apply:
                payload, ocr_metadata = ocr.searchable_pdf(payload)
                metadata = {"fileName": filename, "metadata": {
                    "sha256": digest, "source_url": document["url"],
                    "title": document["title"], "year": "2026", "language": "ar",
                    **ocr_metadata,
                }}
                method = "PUT" if existing else "POST"
                path = f"knowledgesources('{SOURCE_NAME}')/files('{quote(existing['fileId'], safe='')}')" if existing else f"knowledgesources/{SOURCE_NAME}/files"
                uploaded = api.request(method, path, files={
                    "metadata": (None, json.dumps(metadata), "application/json"),
                    "content": (filename, payload, "application/pdf"),
                })
                if uploaded.get("errorMessage") or not uploaded.get("fileId"):
                    raise RuntimeError(f"Upload not confirmed for {filename}: {uploaded}")
                result.update(status="updated" if existing else "uploaded", fileId=uploaded["fileId"], **ocr_metadata)
            else:
                result["status"] = "validated"
            results.append(result)
            print(json.dumps(result), flush=True)
    if apply:
        remote = api.list_values(f"knowledgesources/{SOURCE_NAME}/files")
        if len(remote) != len(documents) or {item.get("fileName") for item in remote} != expected:
            raise RuntimeError("Remote file inventory does not match the manifest")
        for result in results:
            verified = select_existing(remote, result["fileName"], result["sha256"])
            if not verified or verified.get("metadata", {}).get("ocr_version") != OCR_VERSION:
                raise RuntimeError("Remote file lacks verified OCR metadata")
        ensure_knowledge_base(api)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--search-endpoint", required=True)
    parser.add_argument("--openai-endpoint", required=True)
    parser.add_argument("--document-intelligence-endpoint", required=True)
    parser.add_argument("--apply", action="store_true", help="Create the file source and ingest; otherwise only validate")
    args = parser.parse_args()
    documents = load_manifest(args.manifest)
    results = ingest(SearchAPI(args.search_endpoint), documents, args.openai_endpoint, args.apply, GazetteOCR(args.document_intelligence_endpoint))
    print(f"Verified {len(results)} PDFs from 2026; apply={args.apply}.")


if __name__ == "__main__":
    main()