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
    LoginRetryErrorException,
    LoginTimeoutException,
    MaximumSessionCountException,
    UnauthorizedException,
)
from sagemcom_api.models import Device, DeviceInfo as GatewayDeviceInfo

from .api import SagemcomApi
from .capabilities import (
    DOCSIS_COLLECTION_XPATHS,
    async_discover_capabilities,
    metric_xpaths,
    normalize_metric,
    normalize_metrics,
)
from .docsis import (
    DocsisDownstreamChannel,
    DocsisUpstreamChannel,
    parse_docsis_downstream_channels,
    parse_docsis_upstream_channels,
)
from .snapshot import GatewayCapability, GatewaySnapshot


class SagemcomDataUpdateCoordinator(DataUpdateCoordinator[GatewaySnapshot]):
    """Class to manage fetching Sagemcom data."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        *,
        name: str,
        client: SagemcomClient,
        gateway: GatewayDeviceInfo,
        update_interval: timedelta | None = None,
    ):
        """Initialize update coordinator."""
        super().__init__(
            hass,
            logger,
            name=name,
            update_interval=update_interval,
        )
        self.data = GatewaySnapshot(gateway=gateway)
        self.api = SagemcomApi(client)
        self.logger = logger

    async def async_discover_capabilities(self) -> None:
        """Discover optional gateway paths without making setup depend on them."""
        try:
            async with asyncio.timeout(25):
                discovery = await self.api.async_call(async_discover_capabilities)
        except Exception:  # pylint: disable=broad-except
            self.logger.warning(
                "Optional gateway capability discovery failed",
                exc_info=True,
            )
            return

        self.data = self.data.with_capabilities(
            discovery.capabilities,
            discovery.metrics,
            docsis_downstream_channels=discovery.docsis_downstream_channels,
            docsis_upstream_channels=discovery.docsis_upstream_channels,
        )

    async def _async_update_data(self) -> GatewaySnapshot:
        """Update the gateway snapshot."""
        try:
            async with asyncio.timeout(25):

                async def _get_snapshot_values(
                    client: SagemcomClient,
                ) -> tuple[
                    list[Device],
                    dict,
                    tuple[DocsisDownstreamChannel, ...],
                    tuple[DocsisUpstreamChannel, ...],
                ]:
                    hosts = await client.get_hosts(only_active=True)
                    xpaths = metric_xpaths(self.data.capabilities)
                    metrics = {}
                    if xpaths and self.data.capabilities.batch_metrics:
                        try:
                            values = await client.get_values_by_xpaths(xpaths)
                        except Exception:  # pylint: disable=broad-except
                            self.logger.warning(
                                "Optional gateway metric batch failed",
                                exc_info=True,
                            )
                        else:
                            metrics = normalize_metrics(values)
                    else:
                        for capability, xpath in xpaths.items():
                            try:
                                value = await client.get_value_by_xpath(xpath)
                                metrics[capability] = normalize_metric(
                                    capability, value
                                )
                            except Exception:  # pylint: disable=broad-except
                                self.logger.warning(
                                    "Optional gateway metric %s failed",
                                    capability,
                                    exc_info=True,
                                )

                    downstream: tuple[DocsisDownstreamChannel, ...] = ()
                    upstream: tuple[DocsisUpstreamChannel, ...] = ()
                    for capability, xpath in DOCSIS_COLLECTION_XPATHS.items():
                        if not self.data.capabilities.supports(capability):
                            continue
                        try:
                            value = await client.get_value_by_xpath(xpath)
                            if (
                                capability
                                is GatewayCapability.DOCSIS_DOWNSTREAM_CHANNELS
                            ):
                                downstream = parse_docsis_downstream_channels(value)
                            else:
                                upstream = parse_docsis_upstream_channels(value)
                        except Exception:  # pylint: disable=broad-except
                            self.logger.warning(
                                "Optional gateway DOCSIS collection %s failed",
                                capability,
                                exc_info=True,
                            )
                    return hosts, metrics, downstream, upstream

                hosts, metrics, downstream, upstream = await self.api.async_call(
                    _get_snapshot_values
                )

                return (
                    self.data.with_active_hosts(hosts)
                    .with_metrics(metrics)
                    .with_docsis_channels(downstream, upstream)
                )
        except AccessRestrictionException as exception:
            raise ConfigEntryAuthFailed("Access restricted") from exception
        except (AuthenticationException, UnauthorizedException) as exception:
            raise ConfigEntryAuthFailed("Invalid credentials") from exception
        except (
            TimeoutError,
            ClientError,
            ConnectionError,
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
