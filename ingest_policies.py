"""Upload reviewed public policies to a dedicated Foundry IQ file source."""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "webapp"))
from accelerator_config import load_config
from source_manifest import documents
from policy_sources import PublicWebsite, extract
from ingest_gazettes_foundry import SearchAPI, knowledge_source, normalize_defaults, select_existing
from gazette_ocr import GazetteOCR, OCR_VERSION


EXTRACTION_VERSION = "policy-text-v1"


def ingest(config: dict, api: SearchAPI, openai_endpoint: str, ocr: GazetteOCR, apply: bool) -> list[dict]:
    resources = config["resources"]
    source_name = resources["knowledgeSource"]
    definition = knowledge_source(openai_endpoint)
    definition.update(name=source_name, description="Reviewed public policy documents. Publication does not establish current legal validity.")
    definition["fileParameters"]["ingestionParameters"]["embeddingModel"]["azureOpenAIParameters"]["deploymentId"] = resources["embeddingDeployment"]
    definition["fileParameters"]["ingestionParameters"]["embeddingModel"]["azureOpenAIParameters"]["modelName"] = resources["embeddingModel"]
    existing_source = next((item for item in api.list_values("knowledgesources") if item["name"] == source_name), None)
    if existing_source and (existing_source.get("kind") != "file" or normalize_defaults(existing_source.get("fileParameters", {}).get("ingestionParameters", {})) != definition["fileParameters"]["ingestionParameters"]):
        raise ValueError("Knowledge source configuration differs; review before reuse")
    manifest = documents(config)
    remote = api.list_values(f"knowledgesources/{source_name}/files") if existing_source else []
    if any(item.get("fileName") not in manifest for item in remote):
        raise ValueError("Remote source has documents outside this manifest; refusing to mix collections")
    if apply and not existing_source:
        api.request("PUT", f"knowledgesources/{source_name}", json=definition)
    website = PublicWebsite(config["source"])
    results = []
    for filename, document in manifest.items():
        raw, mime, final_url = website.fetch(document["url"])
        if final_url != document["url"]:
            raise ValueError("Document URL changed; rediscover and review the manifest")
        digest = hashlib.sha256(raw).hexdigest()
        if document.get("sha256") and document["sha256"] != digest:
            raise ValueError("Document content changed since discovery; review before ingesting")
        existing = select_existing(remote, filename, digest)
        kind, content, _ = extract(raw, mime, final_url)
        if filename.endswith(".pdf") != (kind == "pdf"):
            raise ValueError("Manifest filename does not match the downloaded format")
        version = OCR_VERSION if kind == "pdf" else EXTRACTION_VERSION
        metadata = {"sha256": digest, "source_url": final_url, "title": document["title"], "language": document.get("language", ""), "extraction_version": version}
        if existing and (existing.get("metadata", {}).get("extraction_version") == version or kind == "pdf" and existing.get("metadata", {}).get("ocr_version") == OCR_VERSION):
            results.append({"fileName": filename, "status": "unchanged", "fileId": existing["fileId"]})
            continue
        if existing:
            raise ValueError("Existing file has a different extraction version; explicit migration required")
        if not apply:
            results.append({"fileName": filename, "status": "validated"})
            continue
        if kind == "pdf":
            content, ocr_metadata = ocr.searchable_pdf(raw)
            metadata.update(ocr_metadata)
        uploaded = api.request("POST", f"knowledgesources/{source_name}/files", files={
            "metadata": (None, json.dumps({"fileName": filename, "metadata": metadata}), "application/json"),
            "content": (filename, content, "application/pdf" if kind == "pdf" else "text/plain"),
        })
        if not uploaded.get("fileId") or uploaded.get("errorMessage"):
            raise RuntimeError("Upload not confirmed; inspect remote inventory before retrying")
        results.append({"fileName": filename, "status": "uploaded", "fileId": uploaded["fileId"]})
    if apply:
        inventory = api.list_values(f"knowledgesources/{source_name}/files")
        if len(inventory) != len(manifest) or {item.get("fileName") for item in inventory} != set(manifest) or any(item.get("errorMessage") for item in inventory):
            raise RuntimeError("Uploaded source inventory is incomplete or has extraction errors")
        knowledge_base = resources["knowledgeBase"]
        existing = next((item for item in api.list_values("knowledgebases") if item["name"] == knowledge_base), None)
        if existing and {item["name"] for item in existing.get("knowledgeSources", [])} != {source_name}:
            raise ValueError("Knowledge base contains unexpected sources")
        api.request("PUT", f"knowledgebases/{knowledge_base}", json={"name": knowledge_base, "description": "Reviewed public policy documents", "knowledgeSources": [{"name": source_name}], "outputMode": "extractiveData", "retrievalReasoningEffort": {"kind": "minimal"}})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--search-endpoint", required=True)
    parser.add_argument("--openai-endpoint", required=True)
    parser.add_argument("--document-intelligence-endpoint", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.config:
        os.environ["ACCELERATOR_CONFIG"] = str(args.config.resolve())
    results = ingest(load_config(), SearchAPI(args.search_endpoint), args.openai_endpoint, GazetteOCR(args.document_intelligence_endpoint), args.apply)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()