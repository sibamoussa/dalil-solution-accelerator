import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "webapp"))
import main
from foundry_retrieval import adapt_response


class AgentPipelineTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(main, "_normalize_query_for_policy_search", side_effect=main._neutral_query_plan))
        self.stack.enter_context(patch.object(main, "GROUNDEDNESS_RETRY_ATTEMPTS", 0))
        payload = adapt_response({"references": [{
            "type": "file", "docName": "gazette-2026-ar-issue-01.pdf", "rerankerScore": 3.0,
            "sourceData": {"uid": "file-1_1", "snippet": "The decision approves the reconstitution of the board of directors of the cooperative society."},
        }]})
        self.search = self.stack.enter_context(patch.object(main, "_search_many", return_value=[payload]))
        self.synthesis = self.stack.enter_context(patch.object(main, "_synthesize", side_effect=lambda question, evidence, language, **kwargs: ({"answer": "The decision reconstitutes the board.", "evidence": [1], "reasoning": []}, evidence)))
        self.verification = self.stack.enter_context(patch.object(main, "_verify_groundedness", return_value={"verified": True}))

    def test_framework_pipeline_returns_allowlisted_citations(self):
        result = main.query_grounded_agent("What does the decision say about the board?")
        self.assertFalse(result["abstained"])
        self.assertEqual(result["sources"][0]["source_url"], "https://www.abudhabi.gov.ae/-/media/sites/adgov/gazettes/2026/ar/1st-arabic-2026.ashx")
        self.verification.assert_called_once()

    def test_low_confidence_stops_before_synthesis(self):
        self.search.return_value[0]["value"][0]["@search.rerankerScore"] = 0.1
        result = main.query_grounded_agent("What does the decision say?")
        self.assertTrue(result["abstained"])
        self.synthesis.assert_not_called()

    def test_invalid_citation_abstains(self):
        self.synthesis.side_effect = lambda question, evidence, language, **kwargs: ({"answer": "Unsupported", "evidence": [999]}, evidence)
        result = main.query_grounded_agent("What does the decision say?")
        self.assertTrue(result["abstained"])
        self.verification.assert_not_called()

    def test_failed_verification_returns_excerpts_not_generated_claim(self):
        self.verification.return_value = {"verified": False, "unsupported_rate": 1.0}
        result = main.query_grounded_agent("What does the decision say?")
        self.assertNotIn("The decision reconstitutes the board.", result["answer"])


class VerificationFailureTests(unittest.TestCase):
    def test_model_failure_cannot_skip_enabled_verification(self):
        evidence = [main.EvidenceItem(index=1, text="Evidence text", source_file="source.pdf", page_number=None, section_path=None, source_url=None, reranker_score=3, rrf_score=0.1)]
        with patch.object(main, "AOAI_FAST_ENDPOINT", "https://dedicated.openai.azure.com"), patch.object(main, "_fast_model_headers", return_value={"api-key": "test"}), patch.object(main, "_chat_completion", return_value=None):
            verdict = main._verify_groundedness("Answer", evidence, "Question", "en")
        self.assertFalse(verdict["verified"])
        self.assertFalse(verdict.get("skipped", False))


class ResponseLanguageTests(unittest.TestCase):
    def test_response_language_follows_english_question_and_overrides_arabic_evidence(self):
        state = main._prepare_request({"message": "Tell me about these policies.", "history": []})
        self.assertEqual(state["response_lang"], "en")

        evidence = [main.EvidenceItem(
            index=1,
            text="السياسات الحكومية والأمن السيبراني.",
            source_file="policy.pdf",
            page_number=None,
            section_path=None,
            source_url=None,
            reranker_score=3.0,
            rrf_score=0.1,
        )]
        requests = []

        def capture_request(*args, **kwargs):
            requests.append(args[2])
            return None

        with patch.object(main, "AOAI_USE_GENERATIVE_SYNTHESIS", True), \
             patch.object(main, "AOAI_CHAT_ENDPOINT", "https://example.openai.azure.com"), \
             patch.object(main, "_aoai_chat_headers", return_value={"api-key": "test"}), \
             patch.object(main, "_has_auth", return_value=True), \
             patch.object(main, "_chat_completion", side_effect=capture_request):
            main._synthesize(state["question"], evidence, state["response_lang"])

        self.assertIn("Answer entirely in English", requests[0]["messages"][0]["content"])
        self.assertIn("السياسات الحكومية والأمن السيبراني", requests[0]["messages"][1]["content"])

    def test_response_language_follows_arabic_question(self):
        state = main._prepare_request({"message": "ما هي هذه السياسات؟", "history": []})
        self.assertEqual(state["response_lang"], "ar")