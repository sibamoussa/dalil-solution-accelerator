import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "webapp"))
from accelerator_config import load_config, manifest_path


class ConfigurationTests(unittest.TestCase):
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