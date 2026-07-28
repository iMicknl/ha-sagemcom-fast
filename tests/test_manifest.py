"""Tests for the integration manifest dependencies."""

import json
from pathlib import Path


def test_manifest_uses_released_api_runtime_fix() -> None:
    """Keep Home Assistant's runtime API dependency aligned with development."""
    root = Path(__file__).parents[1]
    manifest = json.loads(
        (root / "custom_components/sagemcom_fast/manifest.json").read_text()
    )

    requirement = next(
        item
        for item in manifest["requirements"]
        if item.startswith("sagemcom_api==")
    )

    assert requirement == "sagemcom_api==1.5.0"
    assert "sagemcom_api==1.5.0" in (root / "requirements.txt").read_text().splitlines()
