import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx2
from openai import AsyncAzureOpenAI

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "webapp"))
from agent_runtime import CompassOpenAI, azure_deployment, compass_settings, model_provider, run_model


class AgentRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_compass_preserves_schema_model_and_auth_header(self):
        for header in ("api-key", "Ocp-Apim-Subscription-Key"):
            with self.subTest(header=header):
                captured = []
                def respond(request):
                    captured.append(request)
                    return httpx2.Response(200, json={
                        "id": "test", "object": "chat.completion", "created": 0, "model": "custom-model",
                        "choices": [{"index": 0, "message": {"role": "assistant", "content": '{"answer":"grounded"}'}, "finish_reason": "stop"}],
                    })
                http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(respond))
                transport = CompassOpenAI(base_url="https://compass.example/openai/deployments/custom-model/", api_key="test-only", auth_header=header, default_query={"api-version": "2024-10-21"}, http_client=http_client)
                body = {"messages": [{"role": "user", "content": "Question"}], "response_format": {"type": "json_object"}}
                with patch.dict(os.environ, {"MODEL_PROVIDER": "compass", "COMPASS_ENDPOINT": "https://compass.example/openai/deployments/custom-model/chat/completions?api-version=2024-10-21", "COMPASS_API_KEY": "test-only", "COMPASS_AUTH_HEADER": header}), patch("agent_runtime.CompassOpenAI", return_value=transport) as factory, patch("agent_runtime.AsyncAzureOpenAI") as azure:
                    result = await run_model("unused", {}, body, 5, "Synthesis")
                azure.assert_not_called()
                self.assertEqual(result["text"], '{"answer":"grounded"}')
                self.assertEqual(str(captured[0].url), "https://compass.example/openai/deployments/custom-model/chat/completions?api-version=2024-10-21")
                self.assertEqual(factory.call_args.kwargs["auth_header"], header)
                self.assertEqual(factory.call_args.kwargs["default_query"], {"api-version": "2024-10-21"})
                self.assertEqual(json.loads(captured[0].content)["model"], "custom-model")
                self.assertEqual(json.loads(captured[0].content)["response_format"], body["response_format"])
                self.assertEqual(captured[0].headers[header], "test-only")
                self.assertNotIn("Authorization", captured[0].headers)
                self.assertTrue(http_client.is_closed)

    def test_invalid_compass_configuration_fails_closed(self):
        with patch.dict(os.environ, {"MODEL_PROVIDER": "unknown"}):
            with self.assertRaises(ValueError):
                model_provider()
        for url in ("http://compass.example/v1", "https://user:pass@compass.example/v1", "https://compass.example/v1?key=value"):
            with patch.dict(os.environ, {"COMPASS_ENDPOINT": url, "COMPASS_API_KEY": "test-only"}), self.assertRaises(ValueError):
                compass_settings()

    def test_compass_application_auth_never_requests_an_azure_model_token(self):
        import main
        for header in ("api-key", "Ocp-Apim-Subscription-Key"):
            with self.subTest(header=header), patch.object(main, "MODEL_PROVIDER", "compass"), patch.object(main, "compass_settings", return_value=("https://compass.example/openai/deployments/model/chat/completions?api-version=1", "model", "test-only", header)), patch.object(main, "_aoai_bearer_token") as azure_token:
                self.assertEqual(main._aoai_chat_headers(), {header: "test-only"})
                self.assertEqual(main._fast_model_headers(), {header: "test-only"})
                self.assertTrue(main._has_auth(main._fast_model_headers()))
                azure_token.assert_not_called()

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