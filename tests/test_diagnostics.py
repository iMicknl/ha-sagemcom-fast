"""Tests for Sagemcom F@st diagnostics."""

import json
from unittest.mock import Mock

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import pytest

from custom_components.sagemcom_fast.const import DOMAIN
from custom_components.sagemcom_fast.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import SENSITIVE_MARKERS


@pytest.mark.asyncio
async def test_diagnostics_reports_cached_gateway_and_client_summary(
    hass: HomeAssistant, loaded_entry: ConfigEntry
) -> None:
    """Diagnostics must describe cached integration state without raw gateway data."""
    diagnostics = await async_get_config_entry_diagnostics(hass, loaded_entry)

    assert diagnostics["integration"] == {"domain": DOMAIN}
    assert diagnostics["gateway"] == {
        "manufacturer": "Sagemcom",
        "model": "F@st 5366 TN",
        "software_version": "8.22.1",
    }
    assert diagnostics["clients"] == {"active": 1, "known": 2}


@pytest.mark.asyncio
@pytest.mark.parametrize("marker", SENSITIVE_MARKERS)
async def test_diagnostics_excludes_credential_and_network_markers(
    hass: HomeAssistant, loaded_entry: ConfigEntry, marker: str
) -> None:
    """Diagnostics must never expose credentials or gateway network details."""
    diagnostics = await async_get_config_entry_diagnostics(hass, loaded_entry)

    assert marker not in json.dumps(diagnostics, default=str, sort_keys=True)


@pytest.mark.asyncio
async def test_diagnostics_does_not_reauthenticate_or_query_gateway(
    hass: HomeAssistant, loaded_entry: ConfigEntry, sagemcom_client: Mock
) -> None:
    """Diagnostics must use cached runtime state rather than gateway I/O."""
    await async_get_config_entry_diagnostics(hass, loaded_entry)

    sagemcom_client.login.assert_not_awaited()
    sagemcom_client.get_value_by_xpath.assert_not_awaited()
    sagemcom_client.logout.assert_not_awaited()
