import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from policy_sources import discover, extract, public_addresses, validate_url
from accelerator_config import load_config
from docx import Document


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.config["source"].update(website="https://example.org/policies", allowedHosts=["example.org"], pathPrefixes=["/policies"])

    def test_rejects_unsafe_destinations(self):
        for url in ("http://example.org/policies", "https://example.org.evil.test/policies", "https://user@example.org/policies", "https://example.org/private", "https://example.org/policies/../secret"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url, self.config["source"])
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("127.0.0.1", 443))]), self.assertRaises(ValueError):
            public_addresses("example.org")

    def test_docx_and_html_extraction(self):
        document = Document()
        document.add_paragraph("A customer policy")
        stream = io.BytesIO()
        document.save(stream)
        kind, payload, _ = extract(stream.getvalue(), "application/octet-stream", "https://example.org/policies/a.docx")
        self.assertEqual((kind, payload), ("docx", b"A customer policy"))
        kind, payload, _ = extract(b"<title>Policy</title><nav>Ignore me</nav><main>Policy content</main><script>bad()</script>", "text/html", "https://example.org/policies")
        self.assertEqual((kind, payload), ("html", b"Policy content"))

    def test_bounded_discovery_uses_exact_manifest(self):
        class Website:
            def fetch(self, url):
                if url.endswith(".pdf"):
                    return b"%PDF-test", "application/pdf", url
                return b'<main><a href="/policies/a.pdf">Policy</a><a href="https://evil.test/a.pdf">Other</a></main>', "text/html", url
        result = discover(self.config, Website())
        self.assertEqual(len(result["documents"]), 1)
        self.assertEqual(result["documents"][0]["url"], "https://example.org/policies/a.pdf")