"""Support for device tracking of client router."""

import logging
import re
from typing import Any, Dict, List, Optional, Set

import attr

from homeassistant.components.device_tracker import (
    DOMAIN as DEVICE_TRACKER_DOMAIN,
    SOURCE_TYPE_ROUTER,
)
from homeassistant.components.device_tracker.config_entry import ScannerEntity
from homeassistant.const import (
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_HOST,
    HTTP_BAD_REQUEST,
)

from homeassistant.core import callback
from homeassistant.helpers import entity_registry
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import (
    CONF_ENCRYPTION_METHOD,
    CONF_TRACK_WIRELESS_CLIENTS,
    CONF_TRACK_WIRED_CLIENTS,
    DOMAIN,
)


_LOGGER = logging.getLogger(__name__)

_DEVICE_SCAN = f"{DEVICE_TRACKER_DOMAIN}/device_scan"


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up from config entry."""

    options = config_entry.options

    # Initialize already tracked entities
    tracked: Set[str] = set()
    registry = await entity_registry.async_get_registry(hass)
    known_entities: List[SagemcomScannerEntity] = []

    client = hass.data[DOMAIN][config_entry.entry_id]["client"]

    devices = await client.get_hosts(only_active=True)

    last_results = []

    for device in devices:

        if options.get(CONF_TRACK_WIRELESS_CLIENTS) == False:
            if device.interface_type == "WiFi":
                continue

        if options.get(CONF_TRACK_WIRED_CLIENTS) == False:
            if device.interface_type == "Ethernet":
                continue

        print(device)

        entity = SagemcomScannerEntity(device, config_entry.entry_id)
        last_results.append(entity)

    async_add_entities(last_results, update_before_add=True)


class SagemcomScannerEntity(ScannerEntity):
    """client router scanner entity."""

    def __init__(self, device, parent):
        """ Constructor """

        self._device = device
        self._device_state_attributes = {
            "ip_address": self._device.ip_address,
            "interface_type": self._device.interface_type,
            "device_type": self._device.user_device_type
            or self._device.detected_device_type,
            "address_source": self._device.address_source,
        }

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
            "name": self.name,
            "identifiers": {(DOMAIN, self.unique_id)},
            "via_device": (DOMAIN, self._via_device),
        }

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Get additional attributes related to entity state."""

        return self._device_state_attributes or {}
