import copy
import hashlib
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "webapp"))
from azure.cosmos.exceptions import CosmosResourceNotFoundError, CosmosHttpResponseError
from conversation_history import HistoryStore, available, router
from fastapi import FastAPI
from fastapi.testclient import TestClient


class Container:
    def __init__(self):
        self.items = {}

    def read_item(self, item, partition_key):
        if partition_key not in self.items:
            raise CosmosResourceNotFoundError(status_code=404)
        return copy.deepcopy(self.items[partition_key])

    def create_item(self, body):
        self.items[body["owner"]] = {**copy.deepcopy(body), "_etag": "1"}

    def replace_item(self, item, body, etag, match_condition):
        if self.items[body["owner"]]["_etag"] != etag:
            raise CosmosHttpResponseError(status_code=412)
        self.items[body["owner"]] = {**copy.deepcopy(body), "_etag": str(int(etag) + 1)}


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.container = Container()
        self.store = HistoryStore(self.container, 30)

    def test_off_is_default_and_stale_save_cannot_override_off_or_delete(self):
        self.assertFalse(self.store.save("browser-a", None, "question", "answer", "old"))
        self.assertFalse(self.container.items)
        self.store.set_enabled("browser-a", True)
        generation = self.store.read("browser-a")["generation"]
        conversation = self.store.save("browser-a", None, "question", "answer", generation)
        self.assertTrue(conversation)
        self.assertEqual(self.store.read("browser-b")["conversations"], [])
        self.store.set_enabled("browser-a", False)
        self.assertFalse(self.store.save("browser-a", conversation, "private", "answer", generation))
        self.store.delete("browser-a")
        self.assertEqual(self.store.read("browser-a")["conversations"], [])

    def test_api_cookie_isolation_and_csrf(self):
        app = FastAPI()
        app.include_router(router)
        with patch("conversation_history.available", return_value=True), patch("conversation_history.store", return_value=self.store):
            first, other = TestClient(app, base_url="https://testserver"), TestClient(app, base_url="https://testserver")
            self.assertFalse(first.get("/api/history").json()["enabled"])
            self.assertEqual(first.post("/api/history/preference", json={"enabled": True}).status_code, 403)
            enabled = first.post("/api/history/preference", json={"enabled": True}, headers={"X-Dalil-Request": "1"})
            self.assertIn("HttpOnly", enabled.headers["set-cookie"])
            self.assertIn("Secure", enabled.headers["set-cookie"])
            self.assertIn("SameSite=strict", enabled.headers["set-cookie"])
            self.assertTrue(first.get("/api/history").json()["enabled"])
            browser = hashlib.sha256(first.cookies.get("dalil_history").encode()).hexdigest()
            generation = self.store.read(browser)["generation"]
            identifier = self.store.save(browser, None, "Private question", "Private answer", generation)
            self.assertEqual(first.get(f"/api/history/{identifier}").status_code, 200)
            self.assertEqual(other.get(f"/api/history/{identifier}").status_code, 404)
            self.assertFalse(other.get("/api/history").json()["enabled"])
            self.assertEqual(other.get("/api/history/not-mine").status_code, 404)

    def test_deployment_flag_can_disable_history_even_with_cosmos_configured(self):
        with patch("conversation_history.load_config", return_value={"history": {"enabled": True}}):
            with patch.dict(os.environ, {"COSMOS_ENDPOINT": "https://example.documents.azure.com", "HISTORY_ENABLED": "false"}):
                self.assertFalse(available())
            with patch.dict(os.environ, {"COSMOS_ENDPOINT": "https://example.documents.azure.com", "HISTORY_ENABLED": "true"}):
                self.assertTrue(available())

    def test_chat_off_never_opens_database(self):
        import main
        from starlette.requests import Request
        request = Request({"type": "http", "headers": []})
        with patch.object(main, "SEARCH_ENDPOINT", "configured"), patch.object(main, "AOAI_CHAT_ENDPOINT", "configured"), patch.object(main, "query_grounded_agent", return_value={"answer": "Policy answer"}), patch("conversation_history.store") as database:
            result = main.chat(main.ChatRequest(message="Question"), request)
            database.assert_not_called()
            self.assertIn(b'"history_saved":false', result.body)