"""Helpers to help coordinate updates."""
from __future__ import annotations

from datetime import timedelta
import logging

import async_timeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from sagemcom_api.client import SagemcomClient
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
        self.client = client

    async def _async_update_data(self) -> dict[str, Device]:
        """Update hosts data."""
        try:
            async with async_timeout.timeout(10):
                try:
                    await self.client.login()
                    hosts = await self.client.get_hosts(only_active=True)
                finally:
                    await self.client.logout()

                """Mark all device as non-active."""
                for idx, host in self.hosts.items():
                    host.active = False
                    self.hosts[idx] = host
                for host in hosts:
                    self.hosts[host.id] = host

                return self.hosts
        except Exception as exception:
            raise UpdateFailed(f"Error communicating with API: {exception}")
