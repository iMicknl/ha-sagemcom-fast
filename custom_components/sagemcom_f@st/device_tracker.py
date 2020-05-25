"""Support for device tracking of Sagemcom router."""

import logging
import re
from typing import Any, Dict, List, Optional, Set

import attr

from homeassistant.components.device_tracker import (
    DOMAIN as DEVICE_TRACKER_DOMAIN,
    SOURCE_TYPE_ROUTER,
)
from homeassistant.components.device_tracker.config_entry import ScannerEntity
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_HOST, HTTP_BAD_REQUEST

from homeassistant.core import callback
from homeassistant.helpers import entity_registry
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import CONF_ENCRYPTION_METHOD, DOMAIN

from sagemcom_api import SagemcomClient, EncryptionMethod

_LOGGER = logging.getLogger(__name__)

_DEVICE_SCAN = f"{DEVICE_TRACKER_DOMAIN}/device_scan"


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up from config entry."""

    # Grab hosts list once to examine whether the initial fetch has got some data for
    # us, i.e. if wlan host list is supported. Only set up a subscription and proceed
    # with adding and tracking entities if it is.
    # router = hass.data[DOMAIN].routers[config_entry.data[CONF_URL]]
    # try:
    #     _ = router.data[KEY_WLAN_HOST_LIST]["Hosts"]["Host"]
    # except KeyError:
    #     _LOGGER.debug("%s[%s][%s] not in data", KEY_WLAN_HOST_LIST, "Hosts", "Host")
    #     return

    host = config_entry.data[CONF_HOST]
    username = config_entry.data[CONF_USERNAME]
    password = config_entry.data[CONF_PASSWORD]
    encryption_method = config_entry.data[CONF_ENCRYPTION_METHOD]

    # Initialize already tracked entities
    tracked: Set[str] = set()
    registry = await entity_registry.async_get_registry(hass)
    known_entities: List[SagemcomScannerEntity] = []

    sagemcom = SagemcomClient(host, username, password, encryption_method)

    data = await sagemcom.get_hosts()
    devices = sagemcom.parse_devices(data, True)
    last_results = []

    for device in devices:

        # if device.interface is not "WiFi":
        #     continue

        entity = SagemcomScannerEntity(device)
        print(entity)
        last_results.append(entity)

    # for entity in registry.entities.values():
    #     if (
    #         entity.domain == DEVICE_TRACKER_DOMAIN
    #         and entity.config_entry_id == config_entry.entry_id
    #     ):
    #         tracked.add(entity.unique_id)
    #         known_entities.append(
    #             SagemcomScannerEntity(entity.unique_id.partition("-")[2])
    #         )
    async_add_entities(last_results, update_before_add=True)

    # Tell parent router to poll hosts list to gather new devices
    # router.subscriptions[KEY_WLAN_HOST_LIST].add(_DEVICE_SCAN)

    # async def _async_maybe_add_new_entities(url: str) -> None:
    #     """Add new entities if the update signal comes from our router."""
    #     if url == router.url:
    #         async_add_new_entities(hass, url, async_add_entities, tracked)

    # Register to handle router data updates
    # disconnect_dispatcher = async_dispatcher_connect(
    #     hass, UPDATE_SIGNAL, _async_maybe_add_new_entities
    # )
    # router.unload_handlers.append(disconnect_dispatcher)

    # Add new entities from initial scan
    # async_add_new_entities(hass, router.url, async_add_entities, tracked)


# @callback
# def async_add_new_entities(hass, router_url, async_add_entities, tracked):
#     """Add new entities that are not already being tracked."""
#     router = hass.data[DOMAIN].routers[router_url]
#     try:
#         hosts = router.data[KEY_WLAN_HOST_LIST]["Hosts"]["Host"]
#     except KeyError:
#         _LOGGER.debug("%s[%s][%s] not in data", KEY_WLAN_HOST_LIST, "Hosts", "Host")
#         return

#     new_entities = []
#     for host in (x for x in hosts if x.get("MacAddress")):
#         entity = SagemcomScannerEntity(router, host["MacAddress"])
#         if entity.unique_id in tracked:
#             continue
#         tracked.add(entity.unique_id)
#         new_entities.append(entity)
#     async_add_entities(new_entities, True)


# @attr.s
class SagemcomScannerEntity(ScannerEntity):
    """Sagemcom router scanner entity."""

    def __init__(self, device):
        """ Constructor """

        self._device = device
        self._device_state_attributes = {
            "ip_address": self._device.ip_address,
            "interface_type": self._device.interface,
            "device_type": self._device.detected_device_type
        }

        super().__init__()

    @property
    def name(self) -> str:
        return self._device.name or self._device.user_friendly_name or self._device.mac_address

    @property
    def icon(self) -> Optional[str]:
        """Return the icon to use in the frontend, if any."""
        if self._device.detected_device_type is "Smartphone":
            return "mdi:cellphone"

        return None

    @property
    def unique_id(self) -> str:
        return self._device.mac_address

    @property
    def source_type(self) -> str:
        """Return the source type, eg gps or router, of the device."""
        return SOURCE_TYPE_ROUTER

    @property
    def is_connected(self) -> bool:
        """Get whether the entity is connected."""
        return self._device.active

    @property
    def device_info(self):
        """Return the device info."""
        return {
            "name": self._device.name,
            "identifiers": {(DOMAIN, self._device.mac_address)},
            "via_device": (DOMAIN, "D8:A7:56:F5:01:83")
            # "manufacturer": "TEST",
            # "model": "MODEL",
        }

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Get additional attributes related to entity state."""

        # return self._device
        return self._device_state_attributes or {}