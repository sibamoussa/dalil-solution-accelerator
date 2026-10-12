import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "webapp"))
from foundry_retrieval import adapt_response, public_source_url, retrieve, source_documents


class FoundryRetrievalTests(unittest.TestCase):
    def reference(self):
        return {"type": "file", "docName": "gazette-2026-ar-issue-01.pdf", "rerankerScore": 2.9,
                "sourceData": {"uid": "file-1_2", "snippet": "Grounding text"}}

    def test_maps_chunk_and_public_citation_without_inventing_page(self):
        hit = adapt_response({"references": [self.reference()]})["value"][0]
        self.assertEqual(hit["id"], "file-1_2")
        self.assertEqual(hit["content"], "Grounding text")
        self.assertEqual(hit["@search.rerankerScore"], 2.9)
        self.assertIsNone(hit["page"])
        self.assertEqual(public_source_url(hit["source_path"]), source_documents()[hit["source_file"]]["url"])

    def test_unknown_source_missing_grounding_and_activity_errors_fail(self):
        for payload in [
            {"references": [{**self.reference(), "docName": "2025.pdf"}]},
            {"references": [{**self.reference(), "sourceData": {}}]},
            {"activity": [{"error": {"message": "failed"}}]},
        ]:
            with self.subTest(payload=payload), self.assertRaises((ValueError, RuntimeError)):
                adapt_response(payload)
        self.assertIsNone(public_source_url("https://untrusted.example/document.pdf"))

    def test_retrieve_requires_complete_response_and_file_source(self):
        session = Mock()
        response = session.post.return_value
        response.status_code = 200
        response.json.return_value = {"references": [self.reference()]}
        self.assertEqual(len(retrieve(session, "https://dedicated.search.windows.net", "kb", {}, "query", 8, 30)["value"]), 1)
        params = session.post.call_args.kwargs["json"]["knowledgeSourceParams"][0]
        self.assertEqual(params["kind"], "file")
        self.assertTrue(params["failOnError"])
        response.status_code = 206
        with self.assertRaises(RuntimeError):
            retrieve(session, "https://dedicated.search.windows.net", "kb", {}, "query", 8, 30)

    def test_app_routes_to_foundry_and_surfaces_failures(self):
        import main
        with patch.object(main, "FOUNDRY_KNOWLEDGE_BASE", "kb"), patch.object(main, "SEARCH_ENDPOINT", "https://dedicated.search.windows.net"), patch.object(main, "_search_headers", return_value={}), patch.object(main, "retrieve_foundry", return_value={"value": []}) as adapter:
            self.assertEqual(main._search_many(["question"], 8, None, False), [{"value": []}])
            adapter.assert_called_once()
            adapter.side_effect = RuntimeError("unavailable")
            with self.assertRaises(main.HTTPException) as failure:
                main._search_many(["question"], 8, None, False)
            self.assertEqual(failure.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()