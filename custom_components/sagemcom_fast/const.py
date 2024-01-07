"""Constants for the Sagemcom F@st integration."""
from __future__ import annotations

import logging
from typing import Final

from homeassistant.const import Platform

LOGGER: logging.Logger = logging.getLogger(__package__)

DOMAIN: Final = "sagemcom_fast"

CONF_ENCRYPTION_METHOD: Final = "encryption_method"
CONF_TRACK_WIRELESS_CLIENTS: Final = "track_wireless_clients"
CONF_TRACK_WIRED_CLIENTS: Final = "track_wired_clients"

DEFAULT_TRACK_WIRELESS_CLIENTS: Final = True
DEFAULT_TRACK_WIRED_CLIENTS: Final = True

ATTR_MANUFACTURER: Final = "Sagemcom"

MIN_SCAN_INTERVAL: Final = 10
DEFAULT_SCAN_INTERVAL: Final = 10

PLATFORMS: list[Platform] = [Platform.DEVICE_TRACKER, Platform.BUTTON]
