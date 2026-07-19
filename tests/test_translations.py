"""Tests for integration translation resources."""

from __future__ import annotations

import json
from pathlib import Path
import re

COMPONENT_PATH = Path(__file__).parents[1] / "custom_components" / "sagemcom_fast"
TRANSLATION_PATH = COMPONENT_PATH / "translations"
PLACEHOLDER_PATTERN = re.compile(r"{([a-z0-9_]+)}")


def _load_json(path: Path) -> dict:
    """Load one translation resource."""
    return json.loads(path.read_text(encoding="utf-8"))


def _leaf_paths(value: object, prefix: str = "") -> dict[str, str]:
    """Return the string leaves in a nested translation mapping."""
    if isinstance(value, dict):
        leaves: dict[str, str] = {}
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else key
            leaves.update(_leaf_paths(child, child_prefix))
        return leaves
    assert isinstance(value, str), f"Translation value at {prefix} is not text"
    return {prefix: value}


def test_translation_files_match_source_keys_and_placeholders() -> None:
    """Ensure every shipped language remains complete and renderable."""
    source = _leaf_paths(_load_json(COMPONENT_PATH / "strings.json"))

    for language in ("en", "hu"):
        translated = _leaf_paths(_load_json(TRANSLATION_PATH / f"{language}.json"))
        assert translated.keys() == source.keys()
        for key, source_text in source.items():
            assert PLACEHOLDER_PATTERN.findall(translated[key]) == (
                PLACEHOLDER_PATTERN.findall(source_text)
            ), key
