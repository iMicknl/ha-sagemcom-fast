"""Tests for the guest WiFi switches."""

from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
import pytest
from sagemcom_api.exceptions import AccessRestrictionException

from custom_components.sagemcom_fast.const import LOGGER
from custom_components.sagemcom_fast.coordinator import SagemcomDataUpdateCoordinator
from custom_components.sagemcom_fast.switch import SagemcomGuestWifiSwitch

# Decamelized shape returned by get_values_by_xpaths.
WIFI = {
    "radios": [
        {"uid": 1, "operating_frequency_band": "2.4GHz"},
        {"uid": 2, "operating_frequency_band": "5GHz"},
    ],
    "ssids": [
        {
            "uid": 1,
            "alias": "WL_PRIV",
            "enable": True,
            "lower_layers": "Device/WiFi/Radios/Radio[@uid='1']",
        },
        {
            "uid": 2,
            "alias": "WL_GUEST",
            "enable": True,
            "lower_layers": "Device/WiFi/Radios/Radio[@uid='1']",
        },
        {
            "uid": 3,
            "alias": "WL_GUEST_5G",
            "enable": False,
            "lower_layers": "Device/WiFi/Radios/Radio[@uid='2']",
        },
    ],
}


async def _update(hass: HomeAssistant, client: Mock) -> SagemcomDataUpdateCoordinator:
    coordinator = SagemcomDataUpdateCoordinator(
        hass, LOGGER, name="test", client=client, update_interval=timedelta(seconds=30)
    )
    client.get_hosts.return_value = []
    with patch(
        "custom_components.sagemcom_fast.coordinator.asyncio.sleep", new=AsyncMock()
    ):
        await coordinator._async_update_data()
    return coordinator


async def test_guest_ssids_found_per_band(
    hass: HomeAssistant, sagemcom_client: Mock
) -> None:
    """Only guest SSIDs are kept, labelled with their radio band."""
    sagemcom_client.get_values_by_xpaths.return_value = WIFI

    coordinator = await _update(hass, sagemcom_client)

    assert coordinator.guest_wifi == {
        2: {"enable": True, "band": "2.4GHz"},
        3: {"enable": False, "band": "5GHz"},
    }


async def test_guest_wifi_error_keeps_host_tracking(
    hass: HomeAssistant, sagemcom_client: Mock
) -> None:
    """A router refusing the WiFi tree must not fail the update or start reauth."""
    sagemcom_client.get_values_by_xpaths.side_effect = AccessRestrictionException("no")

    coordinator = await _update(hass, sagemcom_client)

    assert coordinator.guest_wifi == {}


async def test_switch_toggles_ssid(hass: HomeAssistant, sagemcom_client: Mock) -> None:
    """Turning off writes the SSID Enable flag and shows the new state at once."""
    sagemcom_client.get_values_by_xpaths.return_value = WIFI
    coordinator = await _update(hass, sagemcom_client)
    switch = SagemcomGuestWifiSwitch(coordinator, 2, "SERIAL")
    switch.async_write_ha_state = Mock()

    assert switch.name == "Guest WiFi 2.4GHz"
    assert switch.is_on

    await switch.async_turn_off()

    sagemcom_client.set_value_by_xpath.assert_awaited_once_with(
        "Device/WiFi/SSIDs/SSID[@uid='2']/Enable", "false"
    )
    sagemcom_client.logout.assert_awaited()
    assert not switch.is_on

    sagemcom_client.set_value_by_xpath.side_effect = AccessRestrictionException("no")
    with pytest.raises(HomeAssistantError):
        await switch.async_turn_on()
    assert not switch.is_on
