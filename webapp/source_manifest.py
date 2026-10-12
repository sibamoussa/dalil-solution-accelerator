"""The reviewed manifest is the authority for displayed source URLs."""

import json
import re
from urllib.parse import unquote, urlsplit

from accelerator_config import load_config, manifest_path


def documents(config: dict | None = None) -> dict:
    config = config or load_config()
    manifest = json.loads(manifest_path(config).read_text(encoding="utf-8"))
    result = {}
    urls = set()
    for item in manifest["documents"]:
        filename = item.get("fileName")
        if not filename and manifest.get("year") == 2026 and manifest.get("language") == "ar":
            filename = f"gazette-2026-ar-issue-{int(item['issue']):02d}.pdf"
        if not filename or not re.fullmatch(r"[a-zA-Z0-9_-]+\.(?:pdf|txt)", filename):
            raise ValueError("Invalid source manifest filename")
        parsed = urlsplit(item["url"])
        if parsed.scheme != "https" or parsed.hostname not in config["source"]["allowedHosts"] or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError("Manifest source is not on an allowed HTTPS host")
        path = unquote(parsed.path)
        if "\\" in path or any(part in (".", "..") for part in path.split("/")) or not any(path.startswith(prefix) for prefix in config["source"]["pathPrefixes"]):
            raise ValueError("Manifest source is outside configured paths")
        if filename in result or item["url"] in urls:
            raise ValueError("Duplicate manifest source")
        if not isinstance(item.get("title"), str) or not item["title"].strip():
            raise ValueError("Manifest source needs a title")
        result[filename] = {**item, "language": item.get("language", manifest.get("language", ""))}
        urls.add(item["url"])
    if not 1 <= len(result) <= config["source"]["maxDocuments"]:
        raise ValueError("Manifest document count exceeds configured limits")
    return result