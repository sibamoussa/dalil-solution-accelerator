"""Microsoft Agent Framework model execution for the grounded workflow."""

import asyncio
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from agent_framework import Agent, Message
from agent_framework.openai import OpenAIChatCompletionClient, OpenAIChatCompletionOptions
from openai import AsyncAzureOpenAI


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
    resource, deployment, version = azure_deployment(endpoint)
    api_key = headers.get("api-key")
    bearer = headers.get("Authorization", "").removeprefix("Bearer ")
    if not api_key and not bearer:
        raise ValueError("Azure OpenAI authentication is required")
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
        async with AsyncAzureOpenAI(
            azure_endpoint=resource,
            azure_deployment=deployment,
            api_version=version,
            api_key=api_key,
            azure_ad_token=bearer or None,
            max_retries=0,
            timeout=timeout,
        ) as transport:
            agent = Agent(
                client=OpenAIChatCompletionClient(model=deployment, async_client=transport),
                name=re.sub(r"[^a-z0-9_]+", "_", purpose.lower()),
                instructions=instructions,
            )
            response = await agent.run(inputs, options=options)
            return {"text": response.text}