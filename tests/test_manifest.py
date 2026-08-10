"""Tests for the integration manifest dependencies."""

import json
from pathlib import Path


def test_manifest_api_requirement_matches_development() -> None:
    root = Path(__file__).parents[1]
    manifest = json.loads(
        (root / "custom_components/sagemcom_fast/manifest.json").read_text()
    )

    api_requirements = [
        requirement
        for requirement in manifest["requirements"]
        if requirement.startswith("sagemcom_api==")
    ]
    assert len(api_requirements) == 1

    development_requirements = {
        line.strip()
        for line in (root / "requirements.txt").read_text().splitlines()
        if line.strip() and not line.startswith("-r ")
    }
    assert api_requirements[0] in development_requirements
