"""Support for device tracking of client router."""

from datetime import timedelta
import logging
from typing import Dict, Optional

import async_timeout
from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import ScannerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from sagemcom_api.client import SagemcomClient
from sagemcom_api.models import Device

from . import HomeAssistantSagemcomFastData
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up from config entry."""
    data: HomeAssistantSagemcomFastData = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        SagemcomScannerEntity(data.coordinator, idx)
        for idx, device in data.coordinator.data.items()
    )


class SagemcomDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Sagemcom data."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        *,
        name: str,
        client: SagemcomClient,
        update_interval: Optional[timedelta] = None,
    ):
        """Initialize update coordinator."""
        super().__init__(
            hass,
            logger,
            name=name,
            update_interval=update_interval,
        )
        self.data = {}
        self.hosts: Dict[str, Device] = {}
        self._client = client

    async def _async_update_data(self) -> Dict[str, Device]:
        """Update hosts data."""
        async with async_timeout.timeout(10):
            try:
                await self._client.login()
                hosts = await self._client.get_hosts(only_active=True)
            finally:
                await self._client.logout()

            # Mark all device as non-active
            for idx, host in self.hosts.items():
                host.active = False
                self.hosts[idx] = host
            for host in hosts:
                self.hosts[host.id] = host

            return self.hosts


class SagemcomScannerEntity(ScannerEntity, RestoreEntity, CoordinatorEntity):
    """Sagemcom router scanner entity."""

    def __init__(self, coordinator, idx):
        """Initialize the device."""
        super().__init__(coordinator)
        self._idx = idx

        self._attr_unique_id = self.device.id
        self._attr_name = (
            self.device.name
            or self.device.user_friendly_name
            or self.device.mac_address
        )

    @property
    def device(self):
        """Return the device entity."""
        return self.coordinator.data[self._idx]

    @property
    def source_type(self) -> str:
        """Return the source type, eg gps or router, of the device."""
        return SourceType.ROUTER

    @property
    def is_connected(self) -> bool:
        """Get whether the entity is connected."""
        return self.device.active or False

    @property
    def device_info(self):
        """Return the device info."""
        return {
            "name": self.name,
            "identifiers": {(DOMAIN, self.unique_id)},
            "via_device": (DOMAIN, self._via_device),
        }

    @property
    def extra_state_attributes(self) -> dict[str, StateType]:
        """Return the state attributes of the device."""
        attr: dict[str, StateType] = {"interface_type": self.device.interface_type}

        return attr

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
