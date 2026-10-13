"""Microsoft Agent Framework model execution for the grounded workflow."""

import asyncio
import os
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from agent_framework import Agent, Message
from agent_framework.openai import OpenAIChatCompletionClient, OpenAIChatCompletionOptions
import httpx2
from openai import AsyncAzureOpenAI, AsyncOpenAI


class CompassOpenAI(AsyncOpenAI):
    def __init__(self, *, auth_header: str, **kwargs: Any):
        self.compass_auth_header = auth_header
        super().__init__(**kwargs)

    @property
    def auth_headers(self) -> dict[str, str]:
        return {self.compass_auth_header: self.api_key}

    async def _prepare_request(self, request: httpx2.Request) -> None:
        await super()._prepare_request(request)
        request.headers.pop("Authorization", None)
        request.headers[self.compass_auth_header] = self.api_key


def model_provider() -> str:
    provider = os.getenv("MODEL_PROVIDER", "azure_openai").strip().lower()
    if provider not in {"azure_openai", "compass"}:
        raise ValueError("MODEL_PROVIDER must be azure_openai or compass")
    return provider


def compass_settings() -> tuple[str, str, str, str]:
    endpoint = os.getenv("COMPASS_ENDPOINT", "").strip()
    key = os.getenv("COMPASS_API_KEY", "").strip()
    header = os.getenv("COMPASS_AUTH_HEADER", "api-key").strip()
    parsed = urlsplit(endpoint)
    match = re.fullmatch(r"(.*/deployments/)([A-Za-z0-9_.-]+)/chat/completions", parsed.path)
    query = parse_qs(parsed.query)
    version = query.get("api-version", [])
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.fragment or parsed.port not in (None, 443)
            or not match or len(version) != 1 or set(query) != {"api-version"}):
        raise ValueError("COMPASS_ENDPOINT must be an HTTPS APIM deployments/<model>/chat/completions URL with api-version")
    if not key:
        raise ValueError("Compass requires COMPASS_API_KEY")
    if header not in {"api-key", "Ocp-Apim-Subscription-Key"}:
        raise ValueError("COMPASS_AUTH_HEADER must be api-key or Ocp-Apim-Subscription-Key")
    return endpoint, match.group(2), key, header


def azure_deployment(endpoint: str) -> tuple[str, str, str]:
    parsed = urlsplit(endpoint)
    match = re.fullmatch(r"/openai/deployments/([^/]+)/chat/completions", parsed.path)
    version = parse_qs(parsed.query).get("api-version", [])
    if (
        parsed.scheme != "https"
        or not (parsed.hostname or "").endswith(".openai.azure.com")
        or parsed.username or parsed.password or parsed.port or parsed.fragment
        or not match or len(version) != 1
    ):
        raise ValueError("Expected an Azure OpenAI deployment chat-completions URL with api-version")
    return f"https://{parsed.hostname}", unquote(match.group(1)), version[0]


async def run_model(
    endpoint: str,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: int,
    purpose: str,
) -> dict[str, Any]:
    if model_provider() == "compass":
        compass_endpoint, deployment, api_key, auth_header = compass_settings()
        parsed = urlsplit(compass_endpoint)
        base_url = f"https://{parsed.netloc}{parsed.path.removesuffix('chat/completions')}"
        transport = CompassOpenAI(
            base_url=base_url,
            api_key=api_key,
            auth_header=auth_header,
            default_query={"api-version": parse_qs(parsed.query)["api-version"][0]},
            max_retries=0,
            timeout=timeout,
        )
    else:
        resource, deployment, version = azure_deployment(endpoint)
        api_key = headers.get("api-key")
        bearer = headers.get("Authorization", "").removeprefix("Bearer ")
        if not api_key and not bearer:
            raise ValueError("Azure OpenAI authentication is required")
        transport = AsyncAzureOpenAI(
            azure_endpoint=resource,
            azure_deployment=deployment,
            api_version=version,
            api_key=api_key,
            azure_ad_token=bearer or None,
            max_retries=0,
            timeout=timeout,
        )
    messages = body["messages"]
    instructions = "\n\n".join(item["content"] for item in messages if item["role"] == "system")
    inputs = [Message(role=item["role"], contents=[item["content"]]) for item in messages if item["role"] != "system"]
    options: OpenAIChatCompletionOptions = {"store": False}
    if "response_format" in body:
        options["response_format"] = body["response_format"]
    options["max_tokens"] = body.get("max_completion_tokens", body.get("max_tokens", 1500))
    if "temperature" in body and not deployment.lower().startswith(("gpt-5", "o1", "o3", "o4")):
        options["temperature"] = body["temperature"]
    async with asyncio.timeout(timeout):
        async with transport:
            agent = Agent(
                client=OpenAIChatCompletionClient(model=deployment, async_client=transport),
                name=re.sub(r"[^a-z0-9_]+", "_", purpose.lower()),
                instructions=instructions,
            )
            response = await agent.run(inputs, options=options)
            return {"text": response.text}