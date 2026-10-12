"""Validated, non-secret customer configuration shared by runtime and setup."""

import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent.parent
if not (ROOT / "accelerator.json").exists():
    ROOT = Path(__file__).resolve().parent


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
    return config


def manifest_path(config: dict) -> Path:
    return ROOT / config["source"]["manifest"]