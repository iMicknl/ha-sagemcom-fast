"""Support for device tracking of client router."""

import logging
from datetime import timedelta
from typing import Any, Dict, Optional
import async_timeout

from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.components.device_tracker import SOURCE_TYPE_ROUTER
from homeassistant.components.device_tracker.config_entry import ScannerEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
    UpdateFailed,
)

from sagemcom_api.client import SagemcomClient
from sagemcom_api.models import Device

from .const import DOMAIN
from .config_flow import SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up from config entry."""

    # TODO Handle status of disconnected devices
    entities = []
    client = hass.data[DOMAIN][config_entry.entry_id]["client"]
    update_interval=config_entry.options.get(CONF_SCAN_INTERVAL)
    if update_interval is None:
        update_interval = SCAN_INTERVAL
    _LOGGER.debug("Update Interval {}".format(update_interval))

    coordinator = SagecomDataUpdateCoordinator(
        hass,
        _LOGGER,
        name="sagem_com",
        client=client,
        update_interval=update_interval,
    )
    await coordinator.async_refresh()

    async_add_entities(
        SagemcomScannerEntity(coordinator, idx, config_entry.entry_id) for idx, device in coordinator.data.items()
    )

class SagecomDataUpdateCoordinator(DataUpdateCoordinator):
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
        try:
            async with async_timeout.timeout(10):
                hosts = await self._client.get_hosts(only_active=True)
                """Mark all device as non-active"""
                for idx, host in self.hosts.items():
                    host.active = False
                    self.hosts[idx] = host
                for host in hosts:
                    self.hosts[host.id] = host
                return self.hosts
        except Exception as exception:
            raise UpdateFailed(f"Error communicating with API: {exception}")


class SagemcomScannerEntity(ScannerEntity, RestoreEntity, CoordinatorEntity):
    """Sagemcom router scanner entity."""

    def __init__(self, coordinator, idx, parent):
        """Initialize the device."""
        super().__init__(coordinator)
        self._idx = idx
        self._via_device = parent

    @property
    def device(self):
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
        return SOURCE_TYPE_ROUTER

    @property
    def is_connected(self) -> bool:
        """Get whether the entity is connected."""
        return self.device.active or False

    @property
    def device_info(self):
        """Return the device info."""
        return {
            "default_name": self.name,
            "identifiers": {(DOMAIN, self.unique_id)},
            "via_device": (DOMAIN, self._via_device),
        }

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes of the device."""
        attr = {"interface_type": self.device.interface_type}

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
