"""Helpers to coordinate Sagemcom F@st updates."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import time

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

REST_ENDPOINT_INTERVALS = {
    "device": 300,
    "device_info": 300,
    "home": 300,
    "hosts": 60,
    "wan_status": 120,
    "wan_ipv4": 120,
    "lan_stats": 30,
    "wireless_24": 900,
    "wireless_5": 900,
    "wireless_legacy24": 900,
    "wireless_stats_24": 120,
    "wireless_stats_5": 120,
    "mesh": 300,
}


class SagemcomDataUpdateCoordinator(DataUpdateCoordinator):
    """Manage fetching Sagemcom router and host data."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        *,
        name: str,
        client: SagemcomClient,
        host: str,
        ssl: bool,
        rest_api: bool,
        update_interval: timedelta | None = None,
    ) -> None:
        """Initialise the coordinator."""

        super().__init__(
            hass,
            logger,
            name=name,
            update_interval=update_interval,
        )

        self.client = client
        self.logger = logger
        self.host = host
        self.ssl = ssl
        self.rest_api = rest_api
        self._previous_counters = {}
        self._last_traffic_update = None

        # Existing device-tracker data. Do not change this structure.
        self.hosts: dict[str, Device] = {}

        # Additional REST API data for sensors.
        self.router_data: dict = {}
        self._endpoint_last_fetched: dict[str, float] = {}

    async def _get_json(self, path: str) -> object | None:
        """Fetch one REST API endpoint.

        Individual endpoint failures are tolerated. This allows sensors
        from working endpoints to continue updating if another endpoint
        is unavailable.
        """

        scheme = "https" if self.ssl else "http"
        url = f"{scheme}://{self.host}{path}"

        try:
            async with self.client.session.get(url) as response:
                response.raise_for_status()
                return await response.json(content_type=None)

        except (ClientError, TimeoutError, ValueError) as exception:
            self.logger.debug(
                "Unable to retrieve router endpoint %s: %s",
                path,
                exception,
            )
            return None

    def _calculate_interface_rates(self, router_data):
        """Calculate interface traffic rates using actual elapsed time."""

        now = time.monotonic()

        if self._last_traffic_update is None:
            polling_interval = None
        else:
            polling_interval = now - self._last_traffic_update

        lan_stats = router_data.get("lan_stats", [])

        if isinstance(lan_stats, list):
            lan_stats = lan_stats[0] if lan_stats else {}

        interfaces = lan_stats.get("lan", {}).get("interfaces", [])

        rates = {}

        for interface in interfaces:
            role = str(interface.get("role", "")).lower()

            if role not in ("wan", "lan"):
                continue

            for direction in ("rx", "tx"):
                key = f"{role}_{direction}"
                rate_key = f"{key}_rate"

                try:
                    counter = int(interface[direction]["bytes"])
                except (KeyError, TypeError, ValueError):
                    rates[rate_key] = None
                    continue

                previous = self._previous_counters.get(key)

                if previous is None:
                    rates[rate_key] = None
                else:
                    previous_counter, previous_time = previous

                    elapsed = now - previous_time
                    difference = counter - previous_counter

                    if elapsed <= 0 or difference < 0:
                        rates[rate_key] = None
                    else:
                        rates[rate_key] = round(
                            difference * 8 / elapsed / 1_000_000,
                            3,
                        )

                self._previous_counters[key] = (counter, now)

        self._last_traffic_update = now

        rates["polling_interval"] = polling_interval

        return rates

    async def _async_update_router_data(self) -> None:
        """Retrieve additional FAST5598 REST API information."""

        endpoints = {
            "device": "/api/v1/device",
            "device_info": "/api/v1/deviceInfo",
            "home": "/api/v1/home",
            "hosts": "/api/v1/hosts",
            "wan_status": "/api/v1/wan/status",
            "wan_ipv4": "/api/v1/wan/ipv4",
            "lan_stats": "/api/v1/lan/stats",
            "wireless_24": "/api/v2/wireless/24",
            "wireless_5": "/api/v2/wireless/5",
            "wireless_legacy24": "/api/v2/wireless/legacy24",
            "wireless_stats_24": "/api/v2/wireless/stats/24",
            "wireless_stats_5": "/api/v2/wireless/stats/5",
            "mesh": "/api/v3/easymesh/meshdevices",
        }

        now = time.monotonic()

        due_endpoints = {
            key: path
            for key, path in endpoints.items()
            if (
                key not in self.router_data
                or now - self._endpoint_last_fetched.get(key, 0)
                >= REST_ENDPOINT_INTERVALS.get(key, 300)
            )
        }

        due_results = await asyncio.gather(
            *[self._get_json(path) for path in due_endpoints.values()],
            return_exceptions=True,
        )

        fresh_results = {}

        for (key, path), result in zip(
            due_endpoints.items(),
            due_results,
            strict=True,
        ):
            if isinstance(result, Exception):
                self.logger.debug(
                    "Error retrieving router data %s: %s",
                    key,
                    str(result)[:1500],
                )
                continue

            if result is not None:
                self.router_data[key] = result
                self._endpoint_last_fetched[key] = time.monotonic()
                fresh_results[key] = result

        # Combine wireless API responses into the structure
        # expected by the existing sensor definitions.
        wireless = {
            "radio": {},
            "ssid": {},
        }

        # Radio configuration from the dedicated wireless endpoints.
        for band in ("24", "5"):
            response = self.router_data.get(f"wireless_{band}")

            if not response:
                continue

            section = (
                response[0].get("wireless", {})
                if isinstance(response, list) and response
                else {}
            )

            radio = section.get("radio", {})
            ssid = section.get("ssid", {})

            if radio:
                wireless["radio"][band] = {
                    **radio,
                    "current_channel": radio.get("channel"),
                    "maxbitrate": radio.get("max_bit_rate"),
                    "htbw": ssid.get("htbw"),
                }

            if ssid:
                wireless["ssid"][band] = ssid

        # SSID status information from deviceInfo.
        device_info = self.router_data.get("device_info", [])

        if isinstance(device_info, list) and device_info:
            device_info = device_info[0]

        for item in device_info.get("wireless", []):
            if not isinstance(item, dict):
                continue

            for ssid_name, ssid_data in item.items():
                if isinstance(ssid_data, dict):
                    wireless["ssid"][ssid_name] = {
                        **wireless["ssid"].get(ssid_name, {}),
                        "ssid_status": ssid_data.get("ssidStatus"),
                    }

        self.router_data["wireless"] = wireless

        # Calculate traffic rates only when fresh LAN statistics arrive.
        fresh_lan_stats = fresh_results.get("lan_stats")

        if fresh_lan_stats is not None:
            self.router_data["traffic_rates"] = self._calculate_interface_rates(
                {"lan_stats": fresh_lan_stats}
            )

    async def _async_update_data(self) -> dict[str, Device]:
        """Update router and connected-host data."""

        try:
            async with asyncio.timeout(60):
                await self.client.login()

                try:
                    await asyncio.sleep(1)

                    # Preserve the original library-based host tracking.
                    hosts = await self.client.get_hosts(only_active=True)

                    # Additional data is specific to REST API routers.
                    if self.rest_api:
                        await self._async_update_router_data()

                finally:
                    await self.client.logout()

                # Mark previously known devices as inactive.
                for idx, host in self.hosts.items():
                    host.active = False
                    self.hosts[idx] = host

                # Update devices returned by the library.
                for host in hosts:
                    self.hosts[host.id] = host

                # IMPORTANT:
                # Return the original host dictionary. Existing device
                # tracker entities depend on this being coordinator.data.
                return self.hosts

        except InvalidSessionException as exception:
            raise UpdateFailed("Session is no longer valid") from exception

        except AccessRestrictionException as exception:
            raise ConfigEntryAuthFailed("Access restricted") from exception

        except (
            AuthenticationException,
            UnauthorizedException,
        ) as exception:
            raise ConfigEntryAuthFailed("Invalid credentials") from exception

        except (
            TimeoutError,
            ClientError,
            ConnectionError,
            LoginConnectionException,
            LoginTimeoutException,
        ) as exception:
            raise UpdateFailed("Failed to connect to the router") from exception

        except LoginRetryErrorException as exception:
            raise UpdateFailed(
                "Too many login attempts. Retrying later."
            ) from exception

        except MaximumSessionCountException as exception:
            raise UpdateFailed("Maximum session count reached") from exception

        except Exception as exception:
            self.logger.exception("Unexpected error updating Sagemcom router")
            raise UpdateFailed(
                f"Error communicating with API: {exception}"
            ) from exception
