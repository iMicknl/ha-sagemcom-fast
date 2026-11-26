"""Support for Sagemcom F@st guest WiFi switches."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import HomeAssistantSagemcomFastData
from .const import DOMAIN
from .coordinator import SagemcomDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the guest WiFi switches from a config entry."""
    data: HomeAssistantSagemcomFastData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        SagemcomGuestWifiSwitch(data.coordinator, uid, data.gateway.serial_number)
        for uid in data.coordinator.guest_wifi
    )


class SagemcomGuestWifiSwitch(
    CoordinatorEntity[SagemcomDataUpdateCoordinator], SwitchEntity
):
    """Guest WiFi network of one radio band."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:wifi"

    def __init__(
        self, coordinator: SagemcomDataUpdateCoordinator, uid: int, serial: str
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._uid = uid
        self._attr_name = f"Guest WiFi {coordinator.guest_wifi[uid]['band'] or uid}"
        self._attr_unique_id = f"{serial}_guest_wifi_{uid}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, serial)})

    @property
    def available(self) -> bool:
        """Return if the SSID was in the last update."""
        return super().available and self._uid in self.coordinator.guest_wifi

    @property
    def is_on(self) -> bool:
        """Return if the guest network is enabled."""
        return self.coordinator.guest_wifi[self._uid]["enable"]

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the guest network."""
        await self._async_set_enable(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the guest network."""
        await self._async_set_enable(False)

    async def _async_set_enable(self, enable: bool) -> None:
        client = self.coordinator.client
        try:
            await client.login()
            try:
                await client.set_value_by_xpath(
                    f"Device/WiFi/SSIDs/SSID[@uid='{self._uid}']/Enable",
                    "true" if enable else "false",
                )
            finally:
                await client.logout()
        except Exception as exception:  # pylint: disable=broad-except
            raise HomeAssistantError(
                f"Failed to turn {'on' if enable else 'off'} {self.name}"
            ) from exception

        # The router applies it with a delay, so show it now and let the next poll confirm.
        self.coordinator.guest_wifi[self._uid]["enable"] = enable
        self.async_write_ha_state()
