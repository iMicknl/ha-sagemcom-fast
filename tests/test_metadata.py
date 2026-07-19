"""Tests for contribution metadata."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
COMPONENT_PATH = ROOT / "custom_components" / "sagemcom_fast"


def test_runtime_requirements_match_manifest() -> None:
    """Keep local development and Home Assistant runtime pins synchronized."""
    requirements = [
        line
        for raw_line in (ROOT / "requirements.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if (line := raw_line.strip()) and not line.startswith("#")
    ]
    manifest = json.loads(
        (COMPONENT_PATH / "manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["requirements"] == requirements
