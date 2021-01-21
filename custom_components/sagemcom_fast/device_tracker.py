"""Support for device tracking of client router."""

import logging
from typing import Any, Dict, List, Optional, Set

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

    options = config_entry.options

    # Initialize already tracked entities
    # tracked: Set[str] = set()
    # registry = await entity_registry.async_get_registry(hass)
    # known_entities: List[SagemcomScannerEntity] = []
    last_results = []

    client = hass.data[DOMAIN][config_entry.entry_id]["client"]
    devices = await client.get_hosts(only_active=True)

    entity_registry = await hass.helpers.entity_registry.async_get_registry()
    for entity in entity_registry.entities.values():
        if (
            entity.config_entry_id != config_entry.entry_id
            or "-" not in entity.unique_id
        ):
            continue

        mac = ""
        if entity.domain == "device_tracker":
            mac = entity.unique_id.split("-", 1)[0]

            # if mac in self.api.clients or mac not in self.api.clients_all:
            # continue

        print(client)

        # client = self.api.clients_all[mac]
        # self.api.clients.process_raw([client.raw])
        _LOGGER.debug(
            "Restore disconnected client %s (%s)",
            entity.entity_id,
            client.mac,
        )

    for device in devices:

        if options.get(CONF_TRACK_WIRELESS_CLIENTS) == False:
            if device.interface_type == "WiFi":
                continue

        if options.get(CONF_TRACK_WIRED_CLIENTS) == False:
            if device.interface_type == "Ethernet":
                continue

        # print(device)

        entity = SagemcomScannerEntity(device, config_entry.entry_id)
        last_results.append(entity)

    async_add_entities(last_results, update_before_add=True)


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
