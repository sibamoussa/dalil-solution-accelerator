import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx2
from openai import AsyncAzureOpenAI

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "webapp"))
from agent_runtime import azure_deployment, run_model


class AgentRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_framework_agent_preserves_schema_and_azure_routing(self):
        captured = []

        def respond(request):
            captured.append(request)
            return httpx2.Response(200, json={
                "id": "test", "object": "chat.completion", "created": 0, "model": "gpt-5-1",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": '{"answer":"grounded"}'}, "finish_reason": "stop"}],
            })

        http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(respond))
        transport = AsyncAzureOpenAI(azure_endpoint="https://dedicated.openai.azure.com", api_version="2024-12-01-preview", api_key="test-only", http_client=http_client)
        body = {"messages": [{"role": "system", "content": "Use only evidence."}, {"role": "user", "content": "Question"}], "max_completion_tokens": 256, "temperature": 0, "response_format": {"type": "json_object"}}
        with patch("agent_runtime.AsyncAzureOpenAI", return_value=transport) as factory:
            result = await run_model("https://dedicated.openai.azure.com/openai/deployments/gpt-5-1/chat/completions?api-version=2024-12-01-preview", {"Authorization": "Bearer test-token"}, body, 5, "Synthesis")
        self.assertEqual(result, {"text": '{"answer":"grounded"}'})
        self.assertEqual(factory.call_args.kwargs["azure_ad_token"], "test-token")
        self.assertTrue(http_client.is_closed)
        request = captured[0]
        self.assertEqual(request.url.host, "dedicated.openai.azure.com")
        sent = json.loads(request.content)
        self.assertEqual(sent["response_format"], body["response_format"])
        self.assertEqual(sent["max_completion_tokens"], 256)
        self.assertNotIn("temperature", sent)
        self.assertFalse(sent["store"])
        self.assertEqual([item["content"] for item in sent["messages"]], ["Use only evidence.", "Question"])

    def test_non_azure_or_ambiguous_endpoints_are_rejected(self):
        for endpoint in ["http://dedicated.openai.azure.com", "https://attacker.example/openai/deployments/model/chat/completions?api-version=1", "https://dedicated.openai.azure.com/openai/deployments/model/chat/completions"]:
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                azure_deployment(endpoint)