"""Fusion and deduplication of Azure AI Search results across query variations.

A single question is issued as several query variations (the raw question, a
normalized form, model-generated alternates). This module merges those result
sets with Reciprocal Rank Fusion, keeps one copy of each chunk, and caps how
many chunks any one source document may contribute.
"""

import hashlib
from typing import Any

# Allow at most this many chunks per source document, so one long policy cannot
# crowd out every other document in the evidence set.
MAX_CHUNKS_PER_DOC = 4

# Standard RRF rank offset. Larger values flatten the contribution of top ranks.
K_RRF = 60


def _get_chunk_id(item: dict[str, Any]) -> str:
    """Return a stable identity for a chunk.

    Prefers the index's own ``id``; falls back to hashing the content, then the
    title/page pair, for indexes that predate the ``id`` field.
    """
    if item.get("id"):
        return str(item["id"])

    content = item.get("content")
    if content:
        return hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()

    fallback = f"{item.get('title', '')}#{item.get('page', '')}"
    return hashlib.sha256(fallback.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _reranker_score(item: dict[str, Any]) -> float:
    score = item.get("@search.rerankerScore")
    if score is None:
        score = item.get("@search.score")
    try:
        return float(score or 0.0)
    except (TypeError, ValueError):
        return 0.0


def fuse_and_dedupe(
    result_sets: list[dict[str, Any]],
    max_per_doc: int = MAX_CHUNKS_PER_DOC,
) -> list[dict[str, Any]]:
    """Merge search result sets into one ranked, deduplicated chunk list.

    A chunk's RRF score is the sum of ``1 / (K_RRF + rank)`` over every query
    that returned it, so chunks several variations agree on rank highest. Where
    the same chunk comes back with different reranker scores, the best one is
    kept -- a chunk is only as irrelevant as its worst-matching query makes it
    look.

    Args:
        result_sets: Azure AI Search payloads, each with a ``value`` list.
        max_per_doc: Maximum chunks retained per ``source_file``.

    Returns:
        Chunks sorted by RRF score then reranker score, each carrying an added
        ``rrf_score`` and a normalized ``@search.rerankerScore``.
    """
    if not result_sets:
        return []

    for payload in result_sets:
        if not isinstance(payload, dict):
            raise ValueError("Each result set must be a dictionary")
        if not isinstance(payload.get("value"), list):
            raise ValueError("Each result set must have a 'value' list")

    merged: dict[str, dict[str, Any]] = {}
    for payload in result_sets:
        for rank, item in enumerate(payload["value"], start=1):
            chunk_id = _get_chunk_id(item)
            contribution = 1.0 / (K_RRF + rank)

            existing = merged.get(chunk_id)
            if existing is None:
                merged[chunk_id] = {
                    **item,
                    "rrf_score": contribution,
                    "@search.rerankerScore": _reranker_score(item),
                }
                continue

            existing["rrf_score"] += contribution
            # Keep the strongest reranker verdict this chunk earned.
            existing["@search.rerankerScore"] = max(
                existing["@search.rerankerScore"], _reranker_score(item)
            )
            # Keep any caption a later result set supplied.
            if not existing.get("@search.captions") and item.get("@search.captions"):
                existing["@search.captions"] = item["@search.captions"]

    ranked = sorted(
        merged.values(),
        key=lambda doc: (doc["rrf_score"], doc["@search.rerankerScore"]),
        reverse=True,
    )

    chunks_per_doc: dict[str, int] = {}
    final_docs: list[dict[str, Any]] = []
    for doc in ranked:
        source_file = doc.get("source_file") or "unknown"
        if chunks_per_doc.get(source_file, 0) >= max_per_doc:
            continue
        chunks_per_doc[source_file] = chunks_per_doc.get(source_file, 0) + 1
        final_docs.append(doc)

    return final_docs
