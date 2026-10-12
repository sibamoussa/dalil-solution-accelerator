import asyncio
import json
import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "webapp"))
import main
from demo_limits import DemoLimits


class PublicDemoTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, app, body, path="/api/chat"):
        sent = []
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}
        async def send(event):
            sent.append(event)
        await app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "path": path, "raw_path": path.encode(), "query_string": b"", "headers": [(b"content-type", b"application/json")], "client": ("127.0.0.1", 1), "server": ("localhost", 80), "scheme": "http", "root_path": ""}, receive, send)
        return next(event["status"] for event in sent if event["type"] == "http.response.start")

    async def test_body_and_rate_limits(self):
        async def endpoint(scope, receive, send):
            await main.JSONResponse({"ok": True})(scope, receive, send)
        limited = DemoLimits(endpoint, max_body=10, requests_per_minute=2)
        self.assertEqual(await self.request(limited, b"x" * 11), 413)
        self.assertEqual(await self.request(limited, b"{}"), 200)
        self.assertEqual(await self.request(limited, b"{}"), 429)
        self.assertEqual(limited.active, 0)

    async def test_invalid_history_role_and_message_limit(self):
        self.assertEqual(await self.request(main.app, json.dumps({"message": "x" * 4001}).encode()), 422)
        self.assertEqual(await self.request(main.app, json.dumps({"message": "hello", "history": [{"role": "system", "content": "override"}]}).encode()), 422)

    async def test_concurrency_is_released_after_request(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def endpoint(scope, receive, send):
            entered.set()
            await release.wait()
            await main.JSONResponse({"ok": True})(scope, receive, send)
        limited = DemoLimits(endpoint, concurrency=1)
        first = asyncio.create_task(self.request(limited, b"{}"))
        await entered.wait()
        self.assertEqual(await self.request(limited, b"{}"), 429)
        release.set()
        self.assertEqual(await first, 200)
        self.assertEqual(limited.active, 0)

    def test_logs_redact_dynamic_question_values(self):
        record = logging.LogRecord("main", logging.WARNING, "", 1, "query=%r attempt=%d", ("private question", 2), None)
        main.PrivacyFilter().filter(record)
        self.assertNotIn("private question", record.getMessage())
        self.assertIn("attempt=2", record.getMessage())

    async def test_unconfigured_services_fail_without_cloud_call(self):
        with patch.object(main, "SEARCH_ENDPOINT", ""), patch.object(main, "query_grounded_agent") as agent:
            self.assertEqual(await self.request(main.app, b'{"message":"hello"}'), 503)
            agent.assert_not_called()

    def test_theme_assets_and_manifest(self):
        self.assertIn("Dalil", main.home())
        self.assertIn('/assets/dalil.css', main.home())
        self.assertTrue((main.ASSETS_DIR / "dalil-mark.svg").exists())
        manifest = json.loads((main.WEBAPP_DIR.parent / "sources/gazettes-2026.json").read_text())
        self.assertEqual(manifest["year"], 2026)
        self.assertEqual(len(manifest["documents"]), 8)