"""The Sagemcom integration."""
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
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import aiohttp_client, service
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from sagemcom_api.client import SagemcomClient
from sagemcom_api.enums import EncryptionMethod
from sagemcom_api.exceptions import (
    AccessRestrictionException,
    AuthenticationException,
    LoginTimeoutException,
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
from .device_tracker import SagemcomDataUpdateCoordinator

SERVICE_REBOOT = "reboot"


@dataclass
class HomeAssistantSagemcomFastData:
    """Nest Protect data stored in the Home Assistant data object."""

    coordinator: SagemcomDataUpdateCoordinator
    gateway: GatewayDeviceInfo | None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up Sagemcom from a config entry."""
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
        raise ConfigEntryAuthFailed("Access Restricted") from exception
    except (AuthenticationException, UnauthorizedException) as exception:
        raise ConfigEntryAuthFailed("Invalid Authentication") from exception
    except (TimeoutError, ClientError) as exception:
        raise ConfigEntryNotReady("Failed to connect") from exception
    except MaximumSessionCountException as exception:
        raise ConfigEntryNotReady("Maximum session count reached") from exception
    except LoginTimeoutException:
        LOGGER.error("Request timed-out")
        return False
    except Exception as exception:  # pylint: disable=broad-except
        LOGGER.exception(exception)
        return False

    update_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    coordinator = SagemcomDataUpdateCoordinator(
        hass,
        LOGGER,
        name="sagemcom_hosts",
        client=client,
        update_interval=timedelta(seconds=update_interval),
    )

    await coordinator.async_config_entry_first_refresh()

    # Many users face issues while retrieving Device Info
    # So don't make this fail the start-up
    gateway = None

    try:
        gateway = await client.get_device_info()

        # Create gateway device in Home Assistant
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
    except Exception as exception:  # pylint: disable=broad-except
        LOGGER.exception(exception)
    finally:
        await client.logout()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = HomeAssistantSagemcomFastData(
        coordinator=coordinator, gateway=gateway
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    # Handle gateway device services
    # TODO move to button entity
    async def async_command_reboot(call: ServiceCall) -> None:
        """Handle reboot service call."""
        await client.reboot()

    service.async_register_admin_service(
        hass, DOMAIN, SERVICE_REBOOT, async_command_reboot
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle an options update."""
    await hass.config_entries.async_reload(entry.entry_id)
