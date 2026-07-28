"""Helpers to help coordinate updates."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Never

from aiohttp.client_exceptions import ClientError
import async_timeout
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from sagemcom_api.client import SagemcomClient
from sagemcom_api.exceptions import (
    AccessRestrictionException,
    AuthenticationException,
    BadRequestException,
    InvalidSessionException,
    LoginConnectionException,
    LoginRetryErrorException,
    LoginTimeoutException,
    MaximumSessionCountException,
    UnauthorizedException,
    UnsupportedHostException,
)
from sagemcom_api.models import Device, DeviceInfo as GatewayDeviceInfo

if TYPE_CHECKING:
    from . import SagemcomConfigEntry


class SagemcomDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Device]]):
    """Class to manage fetching Sagemcom data."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        *,
        config_entry: SagemcomConfigEntry,
        name: str,
        client: SagemcomClient,
        update_interval: timedelta | None = None,
    ) -> None:
        """Initialize update coordinator."""
        super().__init__(
            hass,
            logger,
            config_entry=config_entry,
            name=name,
            update_interval=update_interval,
        )
        self.data = {}
        self.hosts: dict[str, Device] = {}
        self.client = client
        self.gateway: GatewayDeviceInfo | None = None
        self.logger = logger

    async def _async_setup(self) -> None:
        """Fetch gateway metadata before the first hosts update."""
        try:
            try:
                await self.client.login()
                self.gateway = await self.client.get_device_info()
            except BaseException:
                await self._async_logout_after_failure()
                raise

            await self.client.logout()
        except asyncio.CancelledError:
            raise
        except Exception as exception:
            self._raise_for_error(exception)

    async def _async_logout_after_failure(self) -> None:
        """Log out without replacing an in-flight operation failure."""
        try:
            await self.client.logout()
        except Exception:
            self.logger.warning(
                "Failed to log out after gateway operation failed", exc_info=True
            )

    async def _async_update_data(self) -> dict[str, Device]:
        """Update hosts data."""
        try:
            async with async_timeout.timeout(25):
                try:
                    await self.client.login()
                    await asyncio.sleep(1)
                    hosts = await self.client.get_hosts(only_active=True)
                except BaseException:
                    await self._async_logout_after_failure()
                    raise

                await self.client.logout()

                for idx, host in self.hosts.items():
                    host.active = False
                    self.hosts[idx] = host
                for host in hosts:
                    self.hosts[host.id] = host

                return self.hosts
        except asyncio.CancelledError:
            raise
        except Exception as exception:
            self._raise_for_error(exception)

    @staticmethod
    def _raise_for_error(exception: Exception) -> Never:
        """Convert API errors to Home Assistant coordinator transitions."""
        if isinstance(exception, InvalidSessionException):
            raise UpdateFailed("Session is no longer valid") from exception
        if isinstance(exception, AccessRestrictionException):
            raise ConfigEntryAuthFailed("Access restricted") from exception
        if isinstance(exception, (AuthenticationException, UnauthorizedException)):
            raise ConfigEntryAuthFailed("Invalid credentials") from exception
        if isinstance(
            exception,
            (
                TimeoutError,
                ClientError,
                ConnectionError,
                LoginConnectionException,
                LoginTimeoutException,
            ),
        ):
            raise UpdateFailed("Failed to connect") from exception
        if isinstance(exception, LoginRetryErrorException):
            raise UpdateFailed(
                "Too many login attempts. Retrying later."
            ) from exception
        if isinstance(exception, MaximumSessionCountException):
            raise UpdateFailed("Maximum session count reached") from exception
        if isinstance(exception, UnsupportedHostException):
            raise UpdateFailed("Gateway API is unavailable") from exception
        if isinstance(exception, BadRequestException):
            raise UpdateFailed("Gateway rejected the request") from exception
        raise UpdateFailed("Unexpected error communicating with gateway") from exception
