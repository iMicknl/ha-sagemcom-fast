"""Support for device tracking of client router."""

import logging
from typing import Any, Dict

from homeassistant.components.device_tracker import SOURCE_TYPE_ROUTER
from homeassistant.components.device_tracker.config_entry import ScannerEntity
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up from config entry."""

    # TODO Handle status of disconnected devices
    entities = []
    client = hass.data[DOMAIN][config_entry.entry_id]["client"]

    new_devices = await client.get_hosts(only_active=True)

    for device in new_devices:
        entity = SagemcomScannerEntity(device, config_entry.entry_id)
        entities.append(entity)

    async_add_entities(entities, update_before_add=True)


class SagemcomScannerEntity(ScannerEntity, RestoreEntity):
    """Sagemcom router scanner entity."""

    def __init__(self, device, parent):
        """Initialize the device."""
        self._device = device
        self._via_device = parent

        super().__init__()

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return (
            self._device.name
            or self._device.user_friendly_name
            or self._device.mac_address
        )

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._device.id

    @property
    def source_type(self) -> str:
        """Return the source type, eg gps or router, of the device."""
        return SOURCE_TYPE_ROUTER

    @property
    def is_connected(self) -> bool:
        """Get whether the entity is connected."""
        return self._device.active or False

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
        attr = {"interface_type": self._device.interface_type}

        return attr

    @property
    def ip_address(self) -> str:
        """Return the primary ip address of the device."""
        return self._device.ip_address or None

    @property
    def mac_address(self) -> str:
        """Return the mac address of the device."""
        return self._device.phys_address

    @property
    def hostname(self) -> str:
        """Return hostname of the device."""
        return self._device.user_host_name or self._device.host_name
