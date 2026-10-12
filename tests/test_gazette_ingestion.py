import unittest
from unittest.mock import Mock, patch

from ingest_gazettes_foundry import (
    MANIFEST_PATH, KNOWLEDGE_BASE_NAME, SOURCE_NAME, SearchAPI, download_pdf, ensure_knowledge_base, file_name, knowledge_source,
    load_manifest, normalize_defaults, select_existing, validate_source_url,
)


class GazetteIngestionTests(unittest.TestCase):
    def test_manifest_is_exactly_eight_2026_issues(self):
        documents = load_manifest(MANIFEST_PATH)
        self.assertEqual([item["issue"] for item in documents], list(range(1, 9)))
        self.assertEqual(len({file_name(item) for item in documents}), 8)

    def test_other_years_and_hosts_are_rejected(self):
        valid = load_manifest(MANIFEST_PATH)[0]["url"]
        for invalid in [valid.replace("2026", "2025"), valid.replace("www.abudhabi.gov.ae", "localhost"), valid.replace("https:", "http:"), valid + "?url=http://localhost"]:
            with self.subTest(url=invalid), self.assertRaises(ValueError):
                validate_source_url(invalid)

    def test_unchanged_remote_file_is_reused(self):
        existing = {"fileName": "issue.pdf", "fileId": "file-1", "metadata": {"sha256": "hash"}}
        self.assertIs(select_existing([existing], "issue.pdf", "hash"), existing)
        self.assertIsNone(select_existing([], "issue.pdf", "hash"))

    def test_changed_duplicate_and_failed_files_stop_ingestion(self):
        existing = {"fileName": "issue.pdf", "metadata": {"sha256": "hash"}}
        for files, digest in [([existing], "changed"), ([existing, existing], "hash"), ([{**existing, "errorMessage": "failed"}], "hash")]:
            with self.subTest(files=files), self.assertRaises(RuntimeError):
                select_existing(files, "issue.pdf", digest)

    def test_embedding_target_is_explicit(self):
        definition = knowledge_source("https://dedicated.openai.azure.com/")
        self.assertEqual(definition["kind"], "file")
        self.assertEqual(definition["fileParameters"]["ingestionParameters"]["embeddingModel"]["azureOpenAIParameters"]["resourceUri"], "https://dedicated.openai.azure.com")

    def test_service_defaults_do_not_block_resumption(self):
        expected = knowledge_source("https://dedicated.openai.azure.com")["fileParameters"]["ingestionParameters"]
        actual = {**expected, "ingestionPermissionOptions": []}
        actual["embeddingModel"] = {"kind": "azureOpenAI", "azureOpenAIParameters": {
            **expected["embeddingModel"]["azureOpenAIParameters"], "apiKey": None, "authIdentity": None,
        }}
        self.assertEqual(normalize_defaults(actual), expected)
        actual["contentExtractionMode"] = "standard"
        self.assertNotEqual(normalize_defaults(actual), expected)

    @patch.dict("os.environ", {"SEARCH_KEY": "test-only"})
    def test_upload_timeout_and_no_automatic_write_retry(self):
        api = SearchAPI("https://dedicated.search.windows.net")
        retries = api.session.get_adapter(api.endpoint).max_retries
        self.assertNotIn("POST", retries.allowed_methods)
        self.assertIn("PUT", retries.allowed_methods)
        self.assertEqual(retries.read, 0)
        self.assertEqual(retries.status_forcelist, [429])
        api.session = Mock()
        api.session.request.return_value = Mock(ok=False, status_code=429, text="Throttled")
        with self.assertRaisesRegex(RuntimeError, "429"):
            api.request("POST", "knowledgesources/test/files", files={"content": b"pdf"})
        api.session.request.assert_called_once()
        self.assertEqual(api.session.request.call_args.kwargs["timeout"], (240, 240))

    def test_knowledge_base_only_references_2026_source(self):
        api = Mock()
        api.list_values.return_value = []
        ensure_knowledge_base(api)
        definition = api.request.call_args.kwargs["json"]
        self.assertEqual(definition["knowledgeSources"], [{"name": SOURCE_NAME}])
        self.assertEqual(definition["retrievalReasoningEffort"], {"kind": "minimal"})
        api.reset_mock()
        api.list_values.return_value = [{"name": KNOWLEDGE_BASE_NAME, "knowledgeSources": [{"name": "other-corpus"}]}]
        with self.assertRaisesRegex(RuntimeError, "unexpected sources"):
            ensure_knowledge_base(api)
        api.request.assert_not_called()

    def test_html_response_is_not_uploaded_as_pdf(self):
        response = Mock(is_redirect=False, headers={})
        response.iter_content.return_value = [b"<html>Access denied</html>"]
        session = Mock()
        session.get.return_value.__enter__ = Mock(return_value=response)
        session.get.return_value.__exit__ = Mock(return_value=False)
        with self.assertRaisesRegex(ValueError, "non-PDF"):
            download_pdf(session, load_manifest(MANIFEST_PATH)[0]["url"])


if __name__ == "__main__":
    unittest.main()