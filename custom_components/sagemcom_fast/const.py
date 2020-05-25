"""Constants for the Sagemcom integration."""
import logging
from sagemcom_api import EncryptionMethod

LOGGER = logging.getLogger(__package__)
DOMAIN = "sagemcom_fast"

CONF_ENCRYPTION_METHOD = 'encryption_method'
CONF_TRACK_WIRELESS_CLIENTS = 'track_wireless_clients'
CONF_TRACK_WIRED_CLIENTS = 'track_wired_clients'

DEFAULT_TRACK_WIRELESS_CLIENTS = True
DEFAULT_TRACK_WIRED_CLIENTS = True

ATTR_MANUFACTURER = "Sagemcom"

