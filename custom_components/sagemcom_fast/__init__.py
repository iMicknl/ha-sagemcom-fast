"""The Sagemcom F@st integration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from aiohttp.client_exceptions import ClientError
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import aiohttp_client, device_registry
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from sagemcom_api.client import SagemcomClient
from sagemcom_api.enums import EncryptionMethod
from sagemcom_api.exceptions import (
    AccessRestrictionException,
    AuthenticationException,
    MaximumSessionCountException,
    UnauthorizedException,
)
from sagemcom_api.models import DeviceInfo as GatewayDeviceInfo

from .const import (
    CONF_ENCRYPTION_METHOD,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGGER,
    PLATFORMS,
)
from .coordinator import SagemcomDataUpdateCoordinator


@dataclass
class HomeAssistantSagemcomFastData:
    """SagemcomFast data stored in the Home Assistant data object."""

    coordinator: SagemcomDataUpdateCoordinator
    gateway: GatewayDeviceInfo


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Sagemcom F@st from a config entry."""
    host = entry.data[CONF_HOST]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    encryption_method = entry.data[CONF_ENCRYPTION_METHOD]
    ssl = entry.data[CONF_SSL]
    verify_ssl = entry.data[CONF_VERIFY_SSL]

    session = aiohttp_client.async_get_clientsession(hass, verify_ssl=verify_ssl)
    client = SagemcomClient(
        host,
        username,
        password,
        EncryptionMethod(encryption_method),
        session,
        ssl=ssl,
    )

    try:
        await client.login()
    except AccessRestrictionException as exception:
        LOGGER.error("Access restricted")
        raise ConfigEntryAuthFailed("Access restricted") from exception
    except (AuthenticationException, UnauthorizedException) as exception:
        LOGGER.error("Invalid_auth")
        raise ConfigEntryAuthFailed("Invalid credentials") from exception
    except (TimeoutError, ClientError) as exception:
        LOGGER.error("Failed to connect")
        raise ConfigEntryNotReady("Failed to connect") from exception
    except MaximumSessionCountException as exception:
        LOGGER.error("Maximum session count reached")
        raise ConfigEntryNotReady("Maximum session count reached") from exception
    except Exception as exception:  # pylint: disable=broad-except
        LOGGER.exception(exception)
        return False

    try:
        gateway = await client.get_device_info()
    finally:
        await client.logout()

    update_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    coordinator = SagemcomDataUpdateCoordinator(
        hass,
        LOGGER,
        name="sagemcom_hosts",
        client=client,
        update_interval=timedelta(seconds=update_interval),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = HomeAssistantSagemcomFastData(
        coordinator=coordinator, gateway=gateway
    )

    # Create gateway device in Home Assistant
    dev_registry = device_registry.async_get(hass)

    dev_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(CONNECTION_NETWORK_MAC, gateway.mac_address)},
        identifiers={(DOMAIN, gateway.serial_number)},
        manufacturer=gateway.manufacturer,
        name=f"{gateway.manufacturer} {gateway.model_number}",
        model=gateway.model_name,
        sw_version=gateway.software_version,
        configuration_url=f"{'https' if ssl else 'http'}://{host}",
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update when entry options update."""
    if entry.options[CONF_SCAN_INTERVAL]:
        data: HomeAssistantSagemcomFastData = hass.data[DOMAIN][entry.entry_id]
        data.coordinator.update_interval = timedelta(
            seconds=entry.options[CONF_SCAN_INTERVAL]
        )

        await data.coordinator.async_refresh()
