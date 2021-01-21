"""Support for device tracking of client router."""

import logging
from typing import Any, Dict, List, Optional, Set, Counter
from homeassistant.components.device_tracker import (
    DOMAIN as DEVICE_TRACKER_DOMAIN,
    SOURCE_TYPE_ROUTER,
)
from homeassistant.components.device_tracker.config_entry import ScannerEntity

from homeassistant.core import callback
from homeassistant.helpers import entity_registry
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_TRACK_WIRELESS_CLIENTS,
    CONF_TRACK_WIRED_CLIENTS,
    DOMAIN,
)


_LOGGER = logging.getLogger(__name__)

_DEVICE_SCAN = f"{DEVICE_TRACKER_DOMAIN}/device_scan"


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up from config entry."""

    # Initialize already tracked entities
    # known_entities: List[SagemcomScannerEntity] = []
    entities = []

    client = hass.data[DOMAIN][config_entry.entry_id]["client"]

    # existing_devices = hass.data[DOMAIN][config_entry.entry_id]["devices"]
    # for device in existing_devices:
    #     device.active = False
    #     # entity = SagemcomScannerEntity(device, config_entry.entry_id)
    #     entities.append(device)

    new_devices = await client.get_hosts(only_active=True)

    for device in new_devices:
        entity = SagemcomScannerEntity(device, config_entry.entry_id)
        entities.append(entity)

    async_add_entities(entities, update_before_add=True)


class SagemcomScannerEntity(ScannerEntity, RestoreEntity):
    """Sagemcom router scanner entity."""

    def __init__(self, device, parent):
        """ Constructor """

        self._device = device
        self._via_device = parent

        super().__init__()

    @property
    def name(self) -> str:
        return (
            self._device.name
            or self._device.user_friendly_name
            or self._device.mac_address
        )

    @property
    def unique_id(self) -> str:
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
