"""The Sagemcom integration."""
import asyncio
import logging
from aiohttp.client import ClientTimeout
from aiohttp.client_exceptions import ClientError
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC

import voluptuous as vol

from homeassistant.const import (
    CONF_SOURCE,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_HOST,
)
from homeassistant.config_entries import ConfigEntry, SOURCE_REAUTH
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, discovery, service
from homeassistant.helpers import aiohttp_client
from .const import DOMAIN, CONF_ENCRYPTION_METHOD

from sagemcom_api.enums import EncryptionMethod
from sagemcom_api.exceptions import (
    AccessRestrictionException,
    AuthenticationException,
    LoginTimeoutException,
    UnauthorizedException,
)

from sagemcom_api.client import SagemcomClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["device_tracker"]

SERVICE_REBOOT = "reboot"


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Sagemcom component."""

    hass.data.setdefault(DOMAIN, {})

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Sagemcom from a config entry."""

    host = entry.data[CONF_HOST]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    encryption_method = entry.data[CONF_ENCRYPTION_METHOD]

    session = aiohttp_client.async_get_clientsession(hass)
    client = SagemcomClient(
        host, username, password, EncryptionMethod(encryption_method), session
    )

    try:
        await client.login()
    except AccessRestrictionException:
        _LOGGER.error("access_restricted")
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={CONF_SOURCE: SOURCE_REAUTH},
                data=entry.data,
            )
        )
        return False
    except (AuthenticationException, UnauthorizedException):
        _LOGGER.error("invalid_auth")
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={CONF_SOURCE: SOURCE_REAUTH},
                data=entry.data,
            )
        )
        return False
    except (TimeoutError, ClientError) as exception:
        _LOGGER.error("cannot_connect")
        raise ConfigEntryNotReady from exception
    except LoginTimeoutException:
        _LOGGER.error("login_timeout")
        return False
    except Exception as exception:  # pylint: disable=broad-except
        _LOGGER.exception(exception)
        return False

    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "devices": await client.get_hosts(only_active=True),
    }

    # Create gateway device in Home Assistant
    gateway = await client.get_device_info()
    device_registry = await hass.helpers.device_registry.async_get_registry()

    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(CONNECTION_NETWORK_MAC, gateway.mac_address)},
        identifiers={(DOMAIN, gateway.serial_number)},
        manufacturer=gateway.manufacturer,
        name=f"{gateway.manufacturer} {gateway.model_number}",
        model=gateway.model_name,
        sw_version=gateway.software_version,
    )

    # Register components
    for component in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    # Handle gateway device services
    async def async_command_reboot(call):
        """Handle reboot service call."""
        client.reboot()

    service.async_register_admin_service(
        hass, DOMAIN, SERVICE_REBOOT, async_command_reboot
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""

    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            ]
        )
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    # Temp
    hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
