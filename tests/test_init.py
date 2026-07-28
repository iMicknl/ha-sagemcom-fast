"""Tests for Sagemcom F@st config entry setup."""

from unittest.mock import AsyncMock, Mock, patch

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from sagemcom_api.models import DeviceInfo

from custom_components.sagemcom_fast import SagemcomRuntimeData
from custom_components.sagemcom_fast.const import DOMAIN
from custom_components.sagemcom_fast.coordinator import SagemcomDataUpdateCoordinator


@pytest.mark.asyncio
async def test_setup_stores_typed_runtime_data_on_entry(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    config_entry: MockConfigEntry,
    sagemcom_client: Mock,
    gateway: DeviceInfo,
) -> None:
    """Setup must make the config entry the sole owner of runtime state."""
    config_entry.add_to_hass(hass)
    sagemcom_client.get_device_info.return_value = gateway
    sagemcom_client.get_hosts.return_value = []

    with (
        patch(
            "custom_components.sagemcom_fast.SagemcomClient",
            return_value=sagemcom_client,
        ),
        patch(
            "custom_components.sagemcom_fast.coordinator.asyncio.sleep",
            new=AsyncMock(),
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new=AsyncMock(),
        ),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)

    assert isinstance(config_entry.runtime_data, SagemcomRuntimeData)
    assert isinstance(
        config_entry.runtime_data.coordinator, SagemcomDataUpdateCoordinator
    )
    assert config_entry.runtime_data.gateway is gateway
    assert config_entry.entry_id not in hass.data.get(DOMAIN, {})


@pytest.mark.asyncio
async def test_unload_does_not_require_domain_data(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    config_entry: MockConfigEntry,
    sagemcom_client: Mock,
    gateway: DeviceInfo,
) -> None:
    """Unload must delegate platform cleanup without using hass.data."""
    config_entry.add_to_hass(hass)
    sagemcom_client.get_device_info.return_value = gateway
    sagemcom_client.get_hosts.return_value = []

    with (
        patch(
            "custom_components.sagemcom_fast.SagemcomClient",
            return_value=sagemcom_client,
        ),
        patch(
            "custom_components.sagemcom_fast.coordinator.asyncio.sleep",
            new=AsyncMock(),
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new=AsyncMock(),
        ),
        patch.object(
            hass.config_entries,
            "async_unload_platforms",
            new=AsyncMock(return_value=True),
        ) as unload_platforms,
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        hass.data.pop(DOMAIN, None)

        assert await hass.config_entries.async_unload(config_entry.entry_id)

    unload_platforms.assert_awaited_once()
