"""Capability discovery and optional metric normalization."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import Final

from sagemcom_api.client import SagemcomClient
from sagemcom_api.exceptions import (
    AccessRestrictionException,
    UnknownException,
    UnknownPathException,
)

from .docsis import (
    DocsisDownstreamChannel,
    DocsisUpstreamChannel,
    parse_docsis_downstream_channels,
    parse_docsis_upstream_channels,
)
from .snapshot import GatewayCapabilities, GatewayCapability

CAPABILITY_XPATHS: Final[Mapping[GatewayCapability, str]] = {
    GatewayCapability.UPTIME: "Device/DeviceInfo/UpTime",
    GatewayCapability.WAN_STATUS: (
        "Device/IP/Interfaces/Interface[Alias='IP_DATA']/Status"
    ),
    GatewayCapability.DSL_DOWNSTREAM_RATE: (
        "Device/DSL/Channels/Channel[@uid='1']/DownstreamCurrRate"
    ),
    GatewayCapability.DSL_UPSTREAM_RATE: (
        "Device/DSL/Channels/Channel[@uid='1']/UpstreamCurrRate"
    ),
}

DOCSIS_COLLECTION_XPATHS: Final[Mapping[GatewayCapability, str]] = {
    GatewayCapability.DOCSIS_DOWNSTREAM_CHANNELS: (
        "Device/Docsis/CableModem/Downstreams"
    ),
    GatewayCapability.DOCSIS_UPSTREAM_CHANNELS: ("Device/Docsis/CableModem/Upstreams"),
}

_INTEGER_CAPABILITIES: Final[frozenset[GatewayCapability]] = frozenset(
    {
        GatewayCapability.UPTIME,
        GatewayCapability.DSL_DOWNSTREAM_RATE,
        GatewayCapability.DSL_UPSTREAM_RATE,
    }
)
_DSL_RATE_CAPABILITIES: Final[frozenset[GatewayCapability]] = frozenset(
    {
        GatewayCapability.DSL_DOWNSTREAM_RATE,
        GatewayCapability.DSL_UPSTREAM_RATE,
    }
)
_DSL_RATE_UNAVAILABLE: Final[int] = 2**32 - 1

_CONNECTED_WAN_STATUSES: Final[frozenset[str]] = frozenset(
    {"connected", "online", "up"}
)
_DISCONNECTED_WAN_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "disconnected",
        "dormant",
        "down",
        "error",
        "lowerlayerdown",
        "notpresent",
        "offline",
    }
)


@dataclass(frozen=True, slots=True)
class CapabilityDiscovery:
    """Capabilities and initial values confirmed by individual probes."""

    capabilities: GatewayCapabilities
    metrics: Mapping[GatewayCapability, object]
    docsis_downstream_channels: tuple[DocsisDownstreamChannel, ...] = ()
    docsis_upstream_channels: tuple[DocsisUpstreamChannel, ...] = ()


def _is_invalid_path_exception(exception: UnknownException) -> bool:
    """Recognize path errors not typed by the pinned API client."""
    if not exception.args or not isinstance(exception.args[0], Mapping):
        return False
    return exception.args[0].get("description") in {
        "XMO_INVALID_PATH_ERR",
        "XMO_UNKNOWN_PATH_ERR",
    }


def normalize_metric(capability: GatewayCapability, value: object) -> object:
    """Validate and normalize a raw optional metric value."""
    if capability in _INTEGER_CAPABILITIES:
        if isinstance(value, bool):
            raise ValueError(f"Invalid numeric value for {capability}: {value!r}")
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exception:
            raise ValueError(
                f"Invalid numeric value for {capability}: {value!r}"
            ) from exception
        if normalized < 0:
            raise ValueError(f"Invalid numeric value for {capability}: {value!r}")
        if capability in _DSL_RATE_CAPABILITIES and normalized == _DSL_RATE_UNAVAILABLE:
            raise ValueError(f"Unavailable numeric value for {capability}")
        return normalized

    if capability is GatewayCapability.WAN_STATUS:
        if not isinstance(value, str) or not (normalized := value.strip()):
            raise ValueError(f"Invalid status value for {capability}: {value!r}")
        return normalized

    raise ValueError(f"Unknown gateway capability: {capability}")


def wan_status_is_connected(value: object) -> bool | None:
    """Return connectivity for known WAN interface states."""
    if not isinstance(value, str):
        return None

    normalized = "".join(
        character for character in value.casefold() if character.isalnum()
    )
    if normalized in _CONNECTED_WAN_STATUSES:
        return True
    if normalized in _DISCONNECTED_WAN_STATUSES:
        return False
    return None


def metric_xpaths(
    capabilities: GatewayCapabilities,
) -> dict[GatewayCapability, str]:
    """Return paths for capabilities confirmed during discovery."""
    return {
        capability: xpath
        for capability, xpath in CAPABILITY_XPATHS.items()
        if capabilities.supports(capability)
    }


def normalize_metrics(
    values: Mapping[GatewayCapability, object],
) -> dict[GatewayCapability, object]:
    """Return valid values while omitting missing or malformed metrics."""
    metrics: dict[GatewayCapability, object] = {}
    for capability, value in values.items():
        try:
            metrics[capability] = normalize_metric(capability, value)
        except ValueError:
            continue
    return metrics


def _is_unavailable_metric(capability: GatewayCapability, value: object) -> bool:
    """Return whether a supported metric reports its standard unavailable value."""
    if capability not in _DSL_RATE_CAPABILITIES or isinstance(value, bool):
        return False
    try:
        return int(value) == _DSL_RATE_UNAVAILABLE
    except (TypeError, ValueError):
        return False


def prefer_metric_batch(
    *,
    sequential_ms: float,
    batch_ms: float,
    expected_values: int,
    decoded_values: int,
) -> bool:
    """Return whether a batch was complete and faster than sequential reads."""
    return (
        expected_values > 1
        and decoded_values == expected_values
        and batch_ms < sequential_ms
    )


async def async_discover_capabilities(
    client: SagemcomClient,
) -> CapabilityDiscovery:
    """Probe optional paths individually so one unsupported path cannot hide others."""
    supported: set[GatewayCapability] = set()
    metrics: dict[GatewayCapability, object] = {}
    sequential_ms = 0.0

    for capability, xpath in CAPABILITY_XPATHS.items():
        started = perf_counter()
        try:
            value = await client.get_value_by_xpath(xpath)
        except (AccessRestrictionException, UnknownPathException):
            continue
        except UnknownException as exception:
            if _is_invalid_path_exception(exception):
                continue
            raise

        try:
            metrics[capability] = normalize_metric(capability, value)
        except ValueError:
            if _is_unavailable_metric(capability, value):
                supported.add(capability)
            continue
        supported.add(capability)
        sequential_ms += (perf_counter() - started) * 1000

    batch_metrics = False
    if len(supported) > 1:
        xpaths = {capability: CAPABILITY_XPATHS[capability] for capability in supported}
        try:
            started = perf_counter()
            batch_values = await client.get_values_by_xpaths(xpaths)
            batch_ms = (perf_counter() - started) * 1000
        except Exception:  # pylint: disable=broad-except
            pass
        else:
            decoded_values = len(normalize_metrics(batch_values))
            batch_metrics = prefer_metric_batch(
                sequential_ms=sequential_ms,
                batch_ms=batch_ms,
                expected_values=len(supported),
                decoded_values=decoded_values,
            )

    downstream_channels: tuple[DocsisDownstreamChannel, ...] = ()
    upstream_channels: tuple[DocsisUpstreamChannel, ...] = ()
    for capability, xpath in DOCSIS_COLLECTION_XPATHS.items():
        try:
            value = await client.get_value_by_xpath(xpath)
        except (AccessRestrictionException, UnknownPathException):
            continue
        except UnknownException as exception:
            if _is_invalid_path_exception(exception):
                continue
            raise

        try:
            if capability is GatewayCapability.DOCSIS_DOWNSTREAM_CHANNELS:
                downstream_channels = parse_docsis_downstream_channels(value)
            else:
                upstream_channels = parse_docsis_upstream_channels(value)
        except ValueError:
            continue
        supported.add(capability)

    return CapabilityDiscovery(
        capabilities=GatewayCapabilities(
            supported=frozenset(supported),
            batch_metrics=batch_metrics,
        ),
        metrics=metrics,
        docsis_downstream_channels=downstream_channels,
        docsis_upstream_channels=upstream_channels,
    )
