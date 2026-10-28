"""Tests for gateway behaviour introduced by sagemcom_api 1.6."""

import logging
from unittest.mock import Mock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from sagemcom_api.models import DeviceInfo

from custom_components.sagemcom_fast.const import DOMAIN

from .conftest import GATEWAY_MAC_MARKER


async def _async_setup(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    sagemcom_client: Mock,
    gateway: DeviceInfo,
) -> None:
    sagemcom_client.get_device_info.return_value = gateway
    sagemcom_client.get_hosts.return_value = []
    config_entry.add_to_hass(hass)
    with patch(
        "custom_components.sagemcom_fast.SagemcomClient",
        return_value=sagemcom_client,
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED


def _gateway_device(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> dr.DeviceEntry:
    (device,) = dr.async_entries_for_config_entry(
        dr.async_get(hass), config_entry.entry_id
    )
    return device


async def test_setup_without_serial_number_uses_mac_address(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    config_entry: MockConfigEntry,
    sagemcom_client: Mock,
) -> None:
    """Gateways reporting only leaf values must still get a stable identity."""
    gateway = DeviceInfo(mac_address=GATEWAY_MAC_MARKER)

    await _async_setup(hass, config_entry, sagemcom_client, gateway)

    device = _gateway_device(hass, config_entry)
    assert device.identifiers == {(DOMAIN, GATEWAY_MAC_MARKER)}
    assert device.name == "Sagemcom F@st"
    assert er.async_get(hass).async_get_entity_id(
        "button", DOMAIN, f"{GATEWAY_MAC_MARKER}_reboot"
    )


async def test_setup_keeps_serial_number_identity(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    config_entry: MockConfigEntry,
    sagemcom_client: Mock,
    gateway: DeviceInfo,
) -> None:
    """Existing gateways must keep their serial-number based identity."""
    await _async_setup(hass, config_entry, sagemcom_client, gateway)

    device = _gateway_device(hass, config_entry)
    assert device.identifiers == {(DOMAIN, gateway.serial_number)}
    assert device.name == f"{gateway.manufacturer} {gateway.model_number}"


@pytest.mark.parametrize(
    ("reboot_error", "logs_error"),
    [(ConnectionError("router went down"), False), (ValueError("boom"), True)],
)
async def test_reboot_dropped_connection_is_not_an_error(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    config_entry: MockConfigEntry,
    sagemcom_client: Mock,
    gateway: DeviceInfo,
    caplog: pytest.LogCaptureFixture,
    reboot_error: Exception,
    logs_error: bool,
) -> None:
    """A connection dropped by a rebooting router must not be logged as an error."""
    await _async_setup(hass, config_entry, sagemcom_client, gateway)
    sagemcom_client.reboot.side_effect = reboot_error
    entity_id = er.async_get(hass).async_get_entity_id(
        "button", DOMAIN, f"{gateway.serial_number}_reboot"
    )

    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )

    sagemcom_client.reboot.assert_awaited_once()
    assert any(r.levelno >= logging.ERROR for r in caplog.records) is logs_error
