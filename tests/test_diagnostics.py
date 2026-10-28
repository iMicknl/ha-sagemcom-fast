"""Tests for Sagemcom F@st diagnostics."""

import json
from pathlib import Path
from unittest.mock import Mock

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import pytest

from custom_components.sagemcom_fast.const import DOMAIN
from custom_components.sagemcom_fast.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import SENSITIVE_MARKERS

MANIFEST_VERSION = json.loads(
    (
        Path(__file__).parents[1] / "custom_components/sagemcom_fast/manifest.json"
    ).read_text()
)["version"]


@pytest.mark.asyncio
async def test_diagnostics_returns_only_whitelisted_cached_summary(
    hass: HomeAssistant, loaded_entry: ConfigEntry
) -> None:
    """Diagnostics must contain only the approved cached summary fields."""
    diagnostics = await async_get_config_entry_diagnostics(hass, loaded_entry)

    assert diagnostics == {
        "integration": {"domain": DOMAIN, "version": MANIFEST_VERSION},
        "configuration": {
            "ssl": True,
            "verify_ssl": True,
            "encryption_method": "MD5",
        },
        "coordinator": {
            "last_update_success": True,
            "update_interval_seconds": 30.0,
        },
        "gateway": {
            "manufacturer": "Sagemcom",
            "model": "F@st 5366 TN",
            "software_version": "8.22.1",
        },
        "clients": {"active": 1, "known": 2},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("marker", SENSITIVE_MARKERS)
async def test_diagnostics_excludes_all_identifying_fixture_data(
    hass: HomeAssistant, loaded_entry: ConfigEntry, marker: str
) -> None:
    """Diagnostics must never expose credentials, identifiers, or network data."""
    diagnostics = await async_get_config_entry_diagnostics(hass, loaded_entry)

    assert marker not in json.dumps(diagnostics, default=str, sort_keys=True)


@pytest.mark.asyncio
async def test_diagnostics_makes_no_client_calls(
    hass: HomeAssistant, loaded_entry: ConfigEntry, sagemcom_client: Mock
) -> None:
    """Diagnostics must use cached runtime state rather than gateway I/O."""
    await async_get_config_entry_diagnostics(hass, loaded_entry)

    assert sagemcom_client.mock_calls == []
