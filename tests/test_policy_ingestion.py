import hashlib
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingest_policies import ingest
from accelerator_config import load_config


class PolicyIngestionTests(unittest.TestCase):
    def test_html_dry_run_does_not_write_or_ocr(self):
        api, ocr = Mock(), Mock()
        api.list_values.return_value = []
        payload = b"<main>Customer leave policy</main>"
        url = "https://example.org/policy"
        manifest = {"policy.txt": {"url": url, "title": "Leave", "sha256": hashlib.sha256(payload).hexdigest()}}
        with patch("ingest_policies.documents", return_value=manifest), patch("ingest_policies.PublicWebsite") as website:
            website.return_value.fetch.return_value = (payload, "text/html", url)
            result = ingest(load_config(), api, "https://customer.openai.azure.com", ocr, False)
            self.assertEqual(result[0]["status"], "validated")
            api.request.assert_not_called()
            ocr.searchable_pdf.assert_not_called()
            manifest["policy.txt"]["sha256"] = "changed"
            with self.assertRaisesRegex(ValueError, "changed since discovery"):
                ingest(load_config(), api, "https://customer.openai.azure.com", ocr, False)