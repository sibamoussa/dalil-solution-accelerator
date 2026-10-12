"""Create searchable PDFs with the dedicated Document Intelligence Read model."""

import re
from urllib.parse import urlsplit


OCR_VERSION = "document-intelligence-read-2024-11-30-pdf"


class GazetteOCR:
    def __init__(self, endpoint: str):
        parsed = urlsplit(endpoint)
        if parsed.scheme != "https" or not re.fullmatch(r"[a-z0-9-]+\.cognitiveservices\.azure\.com", parsed.netloc) or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("An explicit Document Intelligence HTTPS endpoint is required")
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.identity import DefaultAzureCredential
        self.client = DocumentIntelligenceClient(endpoint, DefaultAzureCredential(), api_version="2024-11-30")

    def searchable_pdf(self, payload: bytes) -> tuple[bytes, dict]:
        poller = self.client.begin_analyze_document(
            "prebuilt-read", body=payload, content_type="application/pdf", output=["pdf"],
            polling_interval=5,
        )
        result = poller.result(timeout=1800)
        if not result.pages or not result.content:
            raise RuntimeError("OCR returned no pages or text")
        result_id = poller.details["operation_id"]
        converted = bytearray()
        for block in self.client.get_analyze_result_pdf("prebuilt-read", result_id):
            converted.extend(block)
            if len(converted) > 50 * 1024 * 1024:
                raise ValueError("Searchable PDF exceeds the 50 MB Search limit")
        if not converted.startswith(b"%PDF-"):
            raise ValueError("OCR returned invalid PDF output")
        return bytes(converted), {
            "ocr_version": OCR_VERSION,
            "ocr_pages": str(len(result.pages)),
            "ocr_characters": str(len(result.content)),
        }