"""Helpers to help coordinate updates."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

from aiohttp.client_exceptions import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from sagemcom_api.client import SagemcomClient
from sagemcom_api.exceptions import (
    AccessRestrictionException,
    AuthenticationException,
    InvalidSessionException,
    LoginConnectionException,
    LoginRetryErrorException,
    LoginTimeoutException,
    MaximumSessionCountException,
    UnauthorizedException,
)
from sagemcom_api.models import Device


class SagemcomDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Sagemcom data."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        *,
        name: str,
        client: SagemcomClient,
        update_interval: timedelta | None = None,
    ):
        """Initialize update coordinator."""
        super().__init__(
            hass,
            logger,
            name=name,
            update_interval=update_interval,
        )
        self.data = {}
        self.hosts: dict[str, Device] = {}
        # SSID uid -> {"enable": bool, "band": "2.4GHz" | "5GHz" | None}
        self.guest_wifi: dict[int, dict] = {}
        self.client = client
        self.logger = logger

    async def _async_get_guest_wifi(self) -> dict[int, dict]:
        """Return the guest SSIDs, or nothing when the router does not expose them."""
        try:
            data = await self.client.get_values_by_xpaths(
                {"ssids": "Device/WiFi/SSIDs", "radios": "Device/WiFi/Radios"},
                ignore_unknown_paths=True,
            )
            bands = {
                f"Device/WiFi/Radios/Radio[@uid='{radio['uid']}']": radio.get(
                    "operating_frequency_band"
                )
                for radio in data["radios"] or []
            }
            # shortcut: guest SSIDs are found by "guest" in their alias, add an
            # explicit uid option if a router names them differently.
            return {
                ssid["uid"]: {
                    "enable": bool(ssid.get("enable")),
                    "band": bands.get(ssid.get("lower_layers")),
                }
                for ssid in data["ssids"] or []
                if "guest" in str(ssid.get("alias", "")).lower()
            }
        except Exception as exception:
            self.logger.debug("Guest WiFi not available: %s", exception)
            return {}

    async def _async_update_data(self) -> dict[str, Device]:
        """Update hosts data."""
        try:
            async with asyncio.timeout(25):
                try:
                    await self.client.login()
                    await asyncio.sleep(1)
                    hosts = await self.client.get_hosts(only_active=True)
                    self.guest_wifi = await self._async_get_guest_wifi()
                finally:
                    await self.client.logout()

                """Mark all device as non-active."""
                for idx, host in self.hosts.items():
                    host.active = False
                    self.hosts[idx] = host
                for host in hosts:
                    self.hosts[host.id] = host

                return self.hosts
        # An expired session is transient and must not trigger reauth.
        except InvalidSessionException as exception:
            raise UpdateFailed("Session is no longer valid") from exception
        except AccessRestrictionException as exception:
            raise ConfigEntryAuthFailed("Access restricted") from exception
        except (AuthenticationException, UnauthorizedException) as exception:
            raise ConfigEntryAuthFailed("Invalid credentials") from exception
        except (
            TimeoutError,
            ClientError,
            ConnectionError,
            LoginConnectionException,
            LoginTimeoutException,
        ) as exception:
            raise UpdateFailed("Failed to connect") from exception
        except LoginRetryErrorException as exception:
            raise UpdateFailed(
                "Too many login attempts. Retrying later."
            ) from exception
        except MaximumSessionCountException as exception:
            raise UpdateFailed("Maximum session count reached") from exception
        except Exception as exception:
            self.logger.exception(exception)
            raise UpdateFailed(f"Error communicating with API: {str(exception)}")
