import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from gazette_ocr import GazetteOCR, OCR_VERSION


class GazetteOCRTests(unittest.TestCase):
    def test_searchable_pdf_and_coverage_metadata(self):
        ocr = GazetteOCR.__new__(GazetteOCR)
        ocr.client = Mock()
        poller = ocr.client.begin_analyze_document.return_value
        poller.result.return_value = SimpleNamespace(pages=[1, 2], content="recognized text")
        poller.details = {"operation_id": "result-id"}
        ocr.client.get_analyze_result_pdf.return_value = [b"%PDF-", b"converted"]
        payload, metadata = ocr.searchable_pdf(b"%PDF-original")
        self.assertEqual(payload, b"%PDF-converted")
        self.assertEqual(metadata["ocr_pages"], "2")
        self.assertEqual(metadata["ocr_version"], OCR_VERSION)
        self.assertEqual(ocr.client.begin_analyze_document.call_args.kwargs["output"], ["pdf"])
        ocr.client.get_analyze_result_pdf.return_value = [b"not pdf"]
        with self.assertRaisesRegex(ValueError, "invalid PDF"):
            ocr.searchable_pdf(b"%PDF-original")


if __name__ == "__main__":
    unittest.main()