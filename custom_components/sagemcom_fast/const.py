"""Constants for the Sagemcom integration."""
from __future__ import annotations

import logging
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "sagemcom_fast"
LOGGER: logging.Logger = logging.getLogger(__package__)

PLATFORMS: list[Platform] = [
    Platform.DEVICE_TRACKER,
]

CONF_ENCRYPTION_METHOD = "encryption_method"
CONF_TRACK_WIRELESS_CLIENTS = "track_wireless_clients"
CONF_TRACK_WIRED_CLIENTS = "track_wired_clients"

DEFAULT_TRACK_WIRELESS_CLIENTS = True
DEFAULT_TRACK_WIRED_CLIENTS = True

ATTR_MANUFACTURER = "Sagemcom"

MIN_SCAN_INTERVAL = 10
DEFAULT_SCAN_INTERVAL = 10
