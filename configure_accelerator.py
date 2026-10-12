"""Create a customer profile from a public policy website without changing Dalil."""

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).parent / "webapp"))
from accelerator_config import load_config


def customer_config(website: str, name: str = "policies") -> dict:
    config = load_config(Path(__file__).parent / "accelerator.json")
    parsed = urlsplit(website)
    config["source"].update(website=website, allowedHosts=[parsed.hostname], pathPrefixes=["/"], manifest=f"sources/{name}.json")
    config["resources"].update(applicationName=name, knowledgeSource=f"{name}-documents", knowledgeBase=f"{name}-policies")
    config["history"]["database"] = name
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--website", required=True)
    parser.add_argument("--name", default="policies")
    parser.add_argument("--output", type=Path, default=Path("customer.json"))
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists. Edit that profile or choose another output; existing setup is never overwritten.")
    config = customer_config(args.website, args.name)
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as directory:
        validation = Path(directory) / "config.json"
        validation.write_text(json.dumps(config), encoding="utf-8")
        load_config(validation)
    args.output.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"Created {args.output}. Review source discovery before ingesting; customize branding in this same file.")


if __name__ == "__main__":
    main()