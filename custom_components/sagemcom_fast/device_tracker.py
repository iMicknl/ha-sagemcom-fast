"""Support for device tracking of client router."""
from __future__ import annotations

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import ScannerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from sagemcom_api.models import Device

from . import HomeAssistantSagemcomFastData
from .const import DOMAIN
from .coordinator import SagemcomDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up device tracker from config entry."""
    data: HomeAssistantSagemcomFastData = hass.data[DOMAIN][entry.entry_id]
    tracked: dict[str, SagemcomScannerEntity] = {}

    @callback
    def async_update_router() -> None:
        """Update the values of the router."""
        newly_discovered: list[SagemcomScannerEntity] = []
        for idx, device in data.coordinator.data.items():
            if idx not in tracked:
                tracked[idx] = SagemcomScannerEntity(
                    data.coordinator, idx, entry.entry_id
                )
                newly_discovered.append(tracked[idx])
        async_add_entities(newly_discovered)

    entry.async_on_unload(data.coordinator.async_add_listener(async_update_router))
    async_update_router()


class SagemcomScannerEntity(
    ScannerEntity, RestoreEntity, CoordinatorEntity[SagemcomDataUpdateCoordinator]
):
    """Sagemcom router scanner entity."""

    def __init__(
        self, coordinator: SagemcomDataUpdateCoordinator, idx: str, parent: str
    ) -> None:
        """Initialize the device."""
        super().__init__(coordinator)
        self._idx = idx
        self._via_device = parent

    @property
    def device(self) -> Device:
        """Return the device entity."""
        return self.coordinator.data[self._idx]

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return (
            self.device.name
            or self.device.user_friendly_name
            or self.device.mac_address
        )

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self.device.id

    @property
    def source_type(self) -> str:
        """Return the source type, eg gps or router, of the device."""
        return SourceType.ROUTER

    @property
    def is_connected(self) -> bool:
        """Get whether the entity is connected."""
        return self.device.active or False

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            connections={(CONNECTION_NETWORK_MAC, self.device.phys_address)},
            name=self.name,
            via_device=(DOMAIN, self._via_device),
        )

    @property
    def extra_state_attributes(self) -> dict[str, StateType]:
        """Return the state attributes of the device."""
        return {"interface_type": self.device.interface_type}

    @property
    def ip_address(self) -> str:
        """Return the primary ip address of the device."""
        return self.device.ip_address or None

    @property
    def mac_address(self) -> str:
        """Return the mac address of the device."""
        return self.device.phys_address

    @property
    def hostname(self) -> str:
        """Return hostname of the device."""
        return self.device.user_host_name or self.device.host_name
