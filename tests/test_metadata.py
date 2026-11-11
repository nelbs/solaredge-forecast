"""Keep the shipped integration manifest and localized forms consistent."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "solaredge_forecast"


def paths(value, prefix=""):
    return {
        path
        for key, child in value.items()
        for path in (
            paths(child, prefix + key + ".")
            if isinstance(child, dict)
            else [prefix + key]
        )
    }


def test_translation_fields_match_canonical_strings():
    canonical = json.loads((INTEGRATION / "strings.json").read_text(encoding="utf-8"))
    for translation in (INTEGRATION / "translations").glob("*.json"):
        translated = json.loads(translation.read_text(encoding="utf-8"))
        assert paths(translated) == paths(canonical), translation.name
        assert (
            "{authorization_url}"
            in translated["config"]["step"]["authorize"]["description"]
        )
        assert "account key" not in translated["config"]["step"]["user"]["data"]


def test_metadata_pins_v2_and_minimum_supported_home_assistant():
    manifest = json.loads((INTEGRATION / "manifest.json").read_text())
    hacs = json.loads((ROOT / "hacs.json").read_text())
    assert manifest["requirements"] == ["solaredge==3.3.0"]
    assert manifest["version"] == "2.0.1-beta.1"
    assert hacs["homeassistant"] == "2026.11.0"
