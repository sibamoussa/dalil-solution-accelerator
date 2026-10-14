import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "webapp"))
from accelerator_config import apply_runtime_settings, load_config, manifest_path, runtime_settings


class ConfigurationTests(unittest.TestCase):
    def test_profile_alone_selects_compass_at_application_startup(self):
        config = load_config()
        config["runtime"].update(MODEL_PROVIDER="compass", COMPASS_ENDPOINT="https://gateway.example/openai/deployments/model/chat/completions?api-version=2024-10-21", SEARCH_TOP_K=11)
        environment = os.environ.copy()
        for name in config["runtime"]:
            environment.pop(name, None)
        environment["COMPASS_API_KEY"] = "test-only"
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "webapp")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            environment["ACCELERATOR_CONFIG"] = str(path)
            result = subprocess.run([sys.executable, "-c", "import main; assert main.MODEL_PROVIDER == 'compass'; assert main.SEARCH_TOP_K == 11; assert main.AOAI_CHAT_ENDPOINT.startswith('https://gateway.example/')"], env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_runtime_profile_applies_defaults_and_preserves_explicit_environment(self):
        config = {"runtime": {"MODEL_PROVIDER": "compass", "SEARCH_TOP_K": 12, "GROUNDEDNESS_CHECK_ENABLED": True}}
        with patch.dict(os.environ, {"SEARCH_TOP_K": "8"}, clear=True):
            apply_runtime_settings(config)
            self.assertEqual(os.environ["MODEL_PROVIDER"], "compass")
            self.assertEqual(os.environ["SEARCH_TOP_K"], "8")
            self.assertEqual(os.environ["GROUNDEDNESS_CHECK_ENABLED"], "true")

    def test_runtime_profile_rejects_secrets_and_unknown_settings(self):
        for name in ("COMPASS_API_KEY", "SEARCH_KEY", "TYPO_SETTING"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                runtime_settings({"runtime": {name: "not-a-real-secret"}})

    def test_runtime_types_and_endpoint_credentials_are_rejected(self):
        for runtime in ({"SEARCH_TOP_K": -1}, {"GROUNDEDNESS_CHECK_ENABLED": "yes"}, {"COMPASS_ENDPOINT": "https://gateway.example/chat?api-key=secret"}):
            with self.subTest(runtime=runtime), self.assertRaises(ValueError):
                runtime_settings({"runtime": runtime})

    def test_url_only_customer_profile_keeps_existing_names_separate(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from configure_accelerator import customer_config
        config = customer_config("https://policies.example.org/policies")
        self.assertEqual(config["source"]["allowedHosts"], ["policies.example.org"])
        self.assertNotEqual(config["resources"]["applicationName"], load_config()["resources"]["applicationName"])
        self.assertEqual(config["branding"], load_config()["branding"])

    def test_existing_profile_is_preserved(self):
        config = load_config()
        self.assertEqual(config["resources"]["knowledgeBase"], "dalil-policies-2026")
        self.assertEqual(len(json.loads(manifest_path(config).read_text())["documents"]), 8)
        self.assertNotIn("subscription", config["resources"])

    def test_rejects_unsafe_configuration(self):
        original = load_config()
        cases = [
            ("source", "website", "http://localhost/private"),
            ("source", "manifest", "sources/../../secrets.json"),
            ("source", "maxDocuments", 1000),
            ("resources", "applicationName", "INVALID"),
            ("branding", "logo", "https://example.org/logo.svg"),
            ("branding", "accentColor", "red; background: url(x)"),
            ("history", "retentionDays", 0),
            ("resources", "chatModelCapacity", 0),
            ("resources", "chatModelSku", "arbitrary"),
            ("resources", "chatDeployment", "../external"),
            ("runtime", "COMPASS_API_KEY", "test-only"),
            ("runtime", "SEARCH_TOP_K", -1),
            ("deployment", "localPort", 80),
            ("deployment", "localPort", True),
            ("deployment", "unknown", "value"),
            ("deployment", "subscription", 123),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            for section, key, value in cases:
                with self.subTest(key=key):
                    config = copy.deepcopy(original)
                    config[section][key] = value
                    path.write_text(json.dumps(config), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_config(path)