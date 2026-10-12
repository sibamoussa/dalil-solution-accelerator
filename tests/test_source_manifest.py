import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "webapp"))
from accelerator_config import load_config
from source_manifest import documents
from foundry_retrieval import adapt_response


class ManifestTests(unittest.TestCase):
    def test_customer_html_source_and_unknown_reference(self):
        config = load_config()
        config["source"].update(allowedHosts=["policies.example.org"], pathPrefixes=["/policy/"])
        document = {"fileName": "customer-policy.txt", "url": "https://policies.example.org/policy/leave", "title": "Leave policy", "language": "en"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps({"documents": [document]}), encoding="utf-8")
            with patch("source_manifest.manifest_path", return_value=path):
                manifest = documents(config)
            with patch("foundry_retrieval.source_documents", return_value=manifest):
                payload = {"references": [{"type": "file", "docName": "customer-policy.txt", "sourceData": {"uid": "chunk-1", "snippet": "Employees have annual leave."}}]}
                hit = adapt_response(payload)["value"][0]
                self.assertEqual(hit["source_path"], document["url"])
                self.assertEqual(hit["language"], "en")
                payload["references"][0]["docName"] = "unapproved.txt"
                with self.assertRaises(ValueError):
                    adapt_response(payload)