"""Validated, non-secret customer configuration shared by runtime and setup."""

import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit


ROOT = Path(__file__).resolve().parent.parent
if not (ROOT / "accelerator.json").exists():
    ROOT = Path(__file__).resolve().parent

RUNTIME_SETTINGS = {
    "MODEL_PROVIDER", "COMPASS_ENDPOINT", "COMPASS_AUTH_HEADER", "SEARCH_ENDPOINT",
    "AOAI_CHAT_ENDPOINT", "AOAI_FAST_ENDPOINT", "COSMOS_ENDPOINT", "HISTORY_ENABLED",
    "SEARCH_TOP_K", "SEARCH_TIMEOUT_SECONDS", "MAX_CHUNKS_PER_DOCUMENT",
    "SUMMARY_MAX_POINTS", "SUMMARY_MAX_CITATIONS", "MATCH_RESPONSE_LANGUAGE_TO_QUESTION",
    "AOAI_USE_GENERATIVE_SYNTHESIS", "AOAI_CHAT_TIMEOUT_SECONDS", "AOAI_FAST_TIMEOUT_SECONDS",
    "AOAI_SYNTHESIS_MAX_COMPLETION_TOKENS", "AOAI_SYNTHESIS_TEMPERATURE",
    "AOAI_SYNTHESIS_EVIDENCE_TOKEN_BUDGET", "MAX_EVIDENCE_ITEMS", "MIN_EVIDENCE_WORDS",
    "QUERY_CONTEXTUALIZATION_ENABLED", "CONTEXTUALIZATION_HISTORY_TURNS",
    "QUERY_NORMALIZATION_ENABLED", "ANSWERABILITY_THRESHOLD", "GROUNDEDNESS_CHECK_ENABLED",
    "GROUNDEDNESS_CHECK_TIMEOUT_SECONDS", "GROUNDEDNESS_UNSUPPORTED_THRESHOLD",
    "GROUNDEDNESS_RETRY_ATTEMPTS", "SYNTHESIS_RETRY_STRICT_MODE",
}


def runtime_settings(config: dict) -> dict[str, str]:
    runtime = config.get("runtime", {})
    if not isinstance(runtime, dict):
        raise ValueError("runtime must be an object of non-secret environment settings")
    values = {}
    for name, value in runtime.items():
        if name not in RUNTIME_SETTINGS:
            raise ValueError(f"Unsupported or secret runtime setting: {name}")
        if not isinstance(value, (str, bool, int, float)) or value is None:
            raise ValueError(f"Invalid runtime value: {name}")
        values[name] = str(value).lower() if isinstance(value, bool) else str(value)
    if values.get("MODEL_PROVIDER", "azure_openai") not in {"azure_openai", "compass"}:
        raise ValueError("runtime.MODEL_PROVIDER must be azure_openai or compass")
    if values.get("COMPASS_AUTH_HEADER", "api-key") not in {"api-key", "Ocp-Apim-Subscription-Key"}:
        raise ValueError("Invalid runtime.COMPASS_AUTH_HEADER")
    for name, value in runtime.items():
        if name.endswith("ENABLED") or name in {"MATCH_RESPONSE_LANGUAGE_TO_QUESTION", "AOAI_USE_GENERATIVE_SYNTHESIS", "SYNTHESIS_RETRY_STRICT_MODE"}:
            if type(value) is not bool:
                raise ValueError(f"runtime.{name} must be a JSON boolean")
        if name.endswith("SECONDS") or name in {"SEARCH_TOP_K", "MAX_CHUNKS_PER_DOCUMENT", "MAX_EVIDENCE_ITEMS", "MIN_EVIDENCE_WORDS", "SUMMARY_MAX_POINTS", "SUMMARY_MAX_CITATIONS", "CONTEXTUALIZATION_HISTORY_TURNS", "AOAI_SYNTHESIS_MAX_COMPLETION_TOKENS", "AOAI_SYNTHESIS_EVIDENCE_TOKEN_BUDGET"}:
            if type(value) is not int or not 1 <= value <= 100000:
                raise ValueError(f"runtime.{name} must be a positive bounded integer")
    for name, value in values.items():
        if name.endswith("ENDPOINT") and value:
            parsed = urlsplit(value)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
                raise ValueError(f"runtime.{name} must be an HTTPS endpoint without embedded credentials")
            if set(dict(parse_qsl(parsed.query))) - {"api-version"}:
                raise ValueError(f"runtime.{name} may only include an api-version query parameter")
    return values


def apply_runtime_settings(config: dict) -> None:
    for name, value in runtime_settings(config).items():
        os.environ.setdefault(name, value)


def load_config(path: Path | None = None) -> dict:
    config_path = path or Path(os.environ.get("ACCELERATOR_CONFIG", ROOT / "accelerator.json"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("schemaVersion") != 1:
        raise ValueError("Unsupported accelerator configuration schema")
    source = config["source"]
    website = urlsplit(source["website"])
    if website.scheme != "https" or not website.hostname or website.username or website.password or website.port not in (None, 443):
        raise ValueError("Source website must be a public HTTPS URL")
    if website.hostname not in source["allowedHosts"]:
        raise ValueError("Source website must be in allowedHosts")
    for host in source["allowedHosts"]:
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host) or "." not in host:
            raise ValueError("Allowed hosts must be fully qualified hostnames")
    for key, maximum in (("maxDocuments", 200), ("maxPages", 100)):
        if type(source[key]) is not int or not 1 <= source[key] <= maximum:
            raise ValueError(f"{key} must be between 1 and {maximum}")
    manifest = Path(source["manifest"])
    if manifest.is_absolute() or ".." in manifest.parts or not source["manifest"].startswith("sources/"):
        raise ValueError("Manifest must be relative to sources/")
    if not source.get("pathPrefixes") or any(not prefix.startswith("/") or ".." in prefix for prefix in source["pathPrefixes"]):
        raise ValueError("Source pathPrefixes must be absolute URL paths")
    resources = config["resources"]
    for key in ("applicationName", "environmentName", "knowledgeSource", "knowledgeBase"):
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,39}", resources[key]):
            raise ValueError(f"Invalid resource name: {key}")
    if len(resources["applicationName"]) > 10 or len(resources["environmentName"]) > 8:
        raise ValueError("Application/environment names exceed Azure naming limits")
    for key in ("chatDeployment", "embeddingDeployment"):
        if not isinstance(resources[key], str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9-]{0,63}", resources[key]):
            raise ValueError(f"Invalid deployment name: {key}")
    for key in ("chatModel", "chatModelVersion", "embeddingModel", "embeddingModelVersion"):
        if not isinstance(resources[key], str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}", resources[key]):
            raise ValueError(f"Invalid model setting: {key}")
    for key in ("chatModelCapacity", "embeddingModelCapacity"):
        if type(resources[key]) is not int or not 1 <= resources[key] <= 10000:
            raise ValueError(f"{key} must be between 1 and 10000")
    if resources["chatModelSku"] not in ("GlobalStandard", "Standard", "GlobalProvisionedManaged", "ProvisionedManaged"):
        raise ValueError("Unsupported chat deployment SKU")
    if resources["embeddingModelSku"] not in ("Standard", "GlobalStandard", "ProvisionedManaged", "GlobalProvisionedManaged"):
        raise ValueError("Unsupported embedding deployment SKU")
    if resources["location"] != "uaenorth":
        raise ValueError("This accelerator currently deploys in UAE North")
    branding = config["branding"]
    for key in ("title", "organization", "shortName"):
        if not isinstance(branding[key], str) or not 1 <= len(branding[key]) <= 100:
            raise ValueError(f"Invalid branding value: {key}")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", branding["accentColor"]):
        raise ValueError("accentColor must be a six-digit hex color")
    if not re.fullmatch(r"/assets/[a-zA-Z0-9_/-]+\.(?:svg|png|jpg|webp)", branding["logo"]) or ".." in branding["logo"]:
        raise ValueError("Logo must be a local image under /assets/")
    history = config["history"]
    if type(history["enabled"]) is not bool or type(history["retentionDays"]) is not int or not 1 <= history["retentionDays"] <= 365:
        raise ValueError("History requires a boolean enabled flag and 1-365 retention days")
    for key in ("database", "container"):
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,39}", history[key]):
            raise ValueError(f"Invalid Cosmos {key} name")
            runtime_settings(config)
            deployment = config.get("deployment", {})
            if not isinstance(deployment, dict) or set(deployment) - {"subscription", "resourceGroup", "containerApp", "registry", "localPort", "cosmosRegion"}:
                raise ValueError("Unsupported deployment configuration")
            port = deployment.get("localPort", 8767)
            if type(port) is not int or not 1024 <= port <= 65535:
                raise ValueError("deployment.localPort must be between 1024 and 65535")
    return config


def manifest_path(config: dict) -> Path:
    return ROOT / config["source"]["manifest"]