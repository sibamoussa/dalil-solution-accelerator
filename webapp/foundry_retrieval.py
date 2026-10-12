"""Adapt the public 2026 Foundry IQ corpus to the application's evidence schema."""

from functools import lru_cache
from urllib.parse import quote
from accelerator_config import load_config
from source_manifest import documents


API_VERSION = "2026-08-01-preview"
SOURCE_NAME = load_config()["resources"]["knowledgeSource"]


@lru_cache(maxsize=1)
def source_documents() -> dict:
    return documents()


def public_source_url(source_path: str) -> str | None:
    return next((item["url"] for item in source_documents().values() if item["url"] == source_path), None)


def adapt_response(payload: dict) -> dict:
    if any(activity.get("error") for activity in payload.get("activity", [])):
        raise RuntimeError("Foundry IQ returned a failed retrieval activity")
    documents = source_documents()
    hits = []
    for reference in payload.get("references", []):
        data = reference.get("sourceData") or {}
        filename = reference.get("docName")
        if reference.get("type") != "file" or filename not in documents:
            raise ValueError("Foundry IQ returned a source outside the approved manifest")
        if not data.get("uid") or not data.get("snippet"):
            raise ValueError("Foundry IQ reference lacks grounding text or chunk identity")
        document = documents[filename]
        hits.append({
            "id": data["uid"], "chunk_id": data["uid"],
            "content": data["snippet"], "title": document["title"],
            "source_file": filename, "source_path": document["url"],
            "language": document.get("language", ""), "page": None,
            "@search.rerankerScore": reference.get("rerankerScore", 0),
        })
    return {"value": hits}


def retrieve(session, endpoint: str, knowledge_base: str, headers: dict, query: str, top_k: int, timeout: int) -> dict:
    response = session.post(
        f"{endpoint.rstrip('/')}/knowledgebases/{quote(knowledge_base, safe='')}/retrieve?api-version={API_VERSION}",
        headers=headers,
        json={
            "intents": [{"type": "semantic", "search": query}],
            "knowledgeSourceParams": [{
                "knowledgeSourceName": SOURCE_NAME, "kind": "file",
                "includeReferences": True, "includeReferenceSourceData": True,
                "alwaysQuerySource": True, "failOnError": True,
            }],
            "includeActivity": True, "maxOutputDocuments": top_k,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    if response.status_code != 200:
        raise RuntimeError(f"Foundry IQ retrieval incomplete: HTTP {response.status_code}")
    return adapt_response(response.json())