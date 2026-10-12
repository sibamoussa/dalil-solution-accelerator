"""Opt-in browser-owned history; no control-plane access or database keys."""

import hashlib
import json
import os
import re
import secrets
import time
import uuid
from functools import lru_cache

from azure.core import MatchConditions
from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceNotFoundError
from azure.identity import AzureCliCredential, ManagedIdentityCredential
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StrictBool

from accelerator_config import load_config


router = APIRouter(prefix="/api/history")
COOKIE = "dalil_history"


def available() -> bool:
    enabled = os.getenv("HISTORY_ENABLED", "true").lower() == "true"
    return enabled and load_config()["history"]["enabled"] and bool(os.getenv("COSMOS_ENDPOINT"))


def owner(request: Request) -> str | None:
    token = request.cookies.get(COOKIE, "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        return None
    return hashlib.sha256(token.encode()).hexdigest()


def require_browser_request(request: Request) -> None:
    if request.headers.get("X-Dalil-Request") != "1" or request.headers.get("Sec-Fetch-Site") == "cross-site":
        raise HTTPException(403, "A same-origin application request is required.")


class HistoryStore:
    def __init__(self, container, retention_days: int):
        self.container = container
        self.ttl = retention_days * 86400

    def read(self, browser: str) -> dict:
        try:
            state = self.container.read_item("history", partition_key=browser)
        except CosmosResourceNotFoundError:
            return {"id": "history", "owner": browser, "enabled": False, "conversations": [], "ttl": self.ttl}
        cutoff = time.time() - self.ttl
        state["conversations"] = [item for item in state["conversations"] if item["updated"] > cutoff]
        return state

    def change(self, browser: str, mutate):
        for attempt in range(3):
            state = self.read(browser)
            result = mutate(state)
            if result is False:
                return False
            etag = state.pop("_etag", None)
            body = {key: value for key, value in state.items() if not key.startswith("_")}
            body["ttl"] = self.ttl
            try:
                if etag:
                    self.container.replace_item("history", body, etag=etag, match_condition=MatchConditions.IfNotModified)
                else:
                    self.container.create_item(body)
                return result
            except CosmosHttpResponseError as error:
                if error.status_code not in (409, 412):
                    raise
        raise RuntimeError("Concurrent history updates; retry the action")

    def set_enabled(self, browser: str, enabled: bool):
        def mutate(state):
            state["enabled"] = enabled
            state["generation"] = uuid.uuid4().hex
        self.change(browser, mutate)

    def save(self, browser: str, conversation_id: str | None, question: str, answer: str, generation: str) -> str | bool:
        new_id = uuid.uuid4().hex
        def mutate(state):
            if not state["enabled"] or state.get("generation") != generation:
                return False
            conversation = next((item for item in state["conversations"] if item["id"] == conversation_id), None)
            if conversation_id and conversation is None:
                return False
            if conversation is None:
                conversation = {"id": new_id, "title": question[:80], "messages": []}
                state["conversations"].append(conversation)
            conversation["messages"].extend([{"role": "user", "content": question[:4000]}, {"role": "assistant", "content": answer[:4000]}])
            conversation["messages"] = conversation["messages"][-20:]
            conversation["updated"] = time.time()
            state["conversations"] = sorted(state["conversations"], key=lambda item: item["updated"], reverse=True)[:10]
            while len(json.dumps(state).encode("utf-8")) > 900000:
                if len(state["conversations"]) > 1:
                    state["conversations"].pop()
                else:
                    conversation["messages"] = conversation["messages"][2:]
            return conversation["id"]
        return self.change(browser, mutate)

    def delete(self, browser: str, conversation_id: str | None = None):
        def mutate(state):
            state["conversations"] = [item for item in state["conversations"] if conversation_id and item["id"] != conversation_id]
            state["generation"] = uuid.uuid4().hex
        self.change(browser, mutate)


@lru_cache(maxsize=1)
def store() -> HistoryStore:
    if not available():
        raise HTTPException(503, "Conversation history is not configured.")
    endpoint = os.environ["COSMOS_ENDPOINT"]
    if not re.fullmatch(r"https://[a-z0-9-]+\.documents\.azure\.com(?::443)?/?", endpoint):
        raise ValueError("An Azure Cosmos DB HTTPS endpoint is required")
    client_id = os.getenv("AZURE_CLIENT_ID")
    credential = ManagedIdentityCredential(client_id=client_id) if client_id else AzureCliCredential()
    config = load_config()["history"]
    client = CosmosClient(endpoint, credential=credential, connection_timeout=10, timeout=15, retry_total=2, logging_enable=False)
    return HistoryStore(client.get_database_client(config["database"]).get_container_client(config["container"]), config["retentionDays"])


def response(payload: dict) -> JSONResponse:
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


def safely(operation):
    try:
        return operation()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Conversation history is temporarily unavailable.") from None


@router.get("")
def list_history(request: Request):
    browser = owner(request)
    if not available() or not browser:
        return response({"available": available(), "enabled": False, "conversations": []})
    state = safely(lambda: store().read(browser))
    return response({"available": True, "enabled": state["enabled"], "conversations": [{key: item[key] for key in ("id", "title", "updated")} for item in state["conversations"]]})


class Preference(BaseModel):
    enabled: StrictBool


@router.post("/preference")
def preference(preference: Preference, request: Request):
    require_browser_request(request)
    token = request.cookies.get(COOKIE, "")
    if not owner(request):
        token = secrets.token_urlsafe(32)
    browser = hashlib.sha256(token.encode()).hexdigest()
    safely(lambda: store().set_enabled(browser, preference.enabled))
    result = response({"enabled": preference.enabled})
    secure = request.url.hostname not in ("localhost", "127.0.0.1", "::1") or request.url.scheme == "https"
    result.set_cookie(COOKIE, token, max_age=load_config()["history"]["retentionDays"] * 86400, httponly=True, secure=secure, samesite="strict", path="/")
    return result


@router.get("/{conversation_id}")
def load_history(conversation_id: str, request: Request):
    browser = owner(request)
    if not browser:
        raise HTTPException(404, "Conversation not found.")
    state = safely(lambda: store().read(browser))
    item = next((item for item in state["conversations"] if item["id"] == conversation_id), None)
    if item is None:
        raise HTTPException(404, "Conversation not found.")
    return response(item)


@router.delete("")
@router.delete("/{conversation_id}")
def delete_history(request: Request, conversation_id: str | None = None):
    require_browser_request(request)
    browser = owner(request)
    if browser:
        safely(lambda: store().delete(browser, conversation_id))
    return response({"deleted": True})