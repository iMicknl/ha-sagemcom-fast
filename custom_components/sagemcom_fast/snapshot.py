"""Home-Assistant-independent gateway snapshot models."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import copy
from dataclasses import dataclass, field, replace
from enum import StrEnum

from sagemcom_api.models import Device, DeviceInfo as GatewayDeviceInfo

from .docsis import DocsisDownstreamChannel, DocsisUpstreamChannel


class GatewayCapability(StrEnum):
    """Semantic optional features reported by a gateway."""

    UPTIME = "uptime"
    WAN_STATUS = "wan_status"
    DSL_DOWNSTREAM_RATE = "dsl_downstream_rate"
    DSL_UPSTREAM_RATE = "dsl_upstream_rate"
    DOCSIS_DOWNSTREAM_CHANNELS = "docsis_downstream_channels"
    DOCSIS_UPSTREAM_CHANNELS = "docsis_upstream_channels"


class HostConnectionType(StrEnum):
    """Normalized host connection types used by aggregate sensors."""

    WIRED = "wired"
    WIRELESS = "wireless"


@dataclass(frozen=True, slots=True)
class ActiveHostCounts:
    """Counts of active hosts by recognized connection type."""

    total: int = 0
    wired: int = 0
    wireless: int = 0


def host_connection_type(interface_type: str | None) -> HostConnectionType | None:
    """Normalize common API interface labels without guessing unknown types."""
    if not interface_type:
        return None

    normalized = "".join(
        character for character in interface_type.casefold() if character.isalnum()
    )
    if normalized in {"wifi", "wlan", "wireless"}:
        return HostConnectionType.WIRELESS
    if normalized in {"ethernet", "eth", "lan", "wired"}:
        return HostConnectionType.WIRED
    return None


@dataclass(frozen=True, slots=True)
class GatewayCapabilities:
    """Optional features confirmed to be readable on a gateway."""

    supported: frozenset[GatewayCapability] = field(default_factory=frozenset)
    batch_metrics: bool = False

    def supports(self, capability: GatewayCapability) -> bool:
        """Return whether a capability was confirmed during discovery."""
        return capability in self.supported


@dataclass(frozen=True, slots=True)
class GatewaySnapshot:
    """A consistent view of gateway metadata, hosts, and optional metrics."""

    gateway: GatewayDeviceInfo
    hosts: Mapping[str, Device] = field(default_factory=dict)
    capabilities: GatewayCapabilities = field(default_factory=GatewayCapabilities)
    metrics: Mapping[GatewayCapability, object] = field(default_factory=dict)
    docsis_downstream_channels: tuple[DocsisDownstreamChannel, ...] = ()
    docsis_upstream_channels: tuple[DocsisUpstreamChannel, ...] = ()

    @property
    def active_host_counts(self) -> ActiveHostCounts:
        """Return active host totals without counting unknown types as wired."""
        total = 0
        wired = 0
        wireless = 0
        for host in self.hosts.values():
            if not host.active:
                continue
            total += 1
            connection_type = host_connection_type(host.interface_type)
            if connection_type is HostConnectionType.WIRED:
                wired += 1
            elif connection_type is HostConnectionType.WIRELESS:
                wireless += 1
        return ActiveHostCounts(total=total, wired=wired, wireless=wireless)

    def with_active_hosts(self, active_hosts: Iterable[Device]) -> GatewaySnapshot:
        """Return a new snapshot with absent known hosts marked disconnected."""
        hosts: dict[str, Device] = {}
        for host_id, host in self.hosts.items():
            disconnected_host = copy(host)
            disconnected_host.active = False
            hosts[host_id] = disconnected_host

        for host in active_hosts:
            hosts[host.id] = host

        return replace(self, hosts=hosts)

    def with_capabilities(
        self,
        capabilities: GatewayCapabilities,
        metrics: Mapping[GatewayCapability, object],
        *,
        docsis_downstream_channels: tuple[DocsisDownstreamChannel, ...] = (),
        docsis_upstream_channels: tuple[DocsisUpstreamChannel, ...] = (),
    ) -> GatewaySnapshot:
        """Return a new snapshot containing discovered optional features."""
        return replace(
            self,
            capabilities=capabilities,
            metrics=dict(metrics),
            docsis_downstream_channels=docsis_downstream_channels,
            docsis_upstream_channels=docsis_upstream_channels,
        )

    def with_metrics(
        self, metrics: Mapping[GatewayCapability, object]
    ) -> GatewaySnapshot:
        """Return a new snapshot with the latest optional metric values."""
        return replace(self, metrics=dict(metrics))

    def with_docsis_channels(
        self,
        downstream: tuple[DocsisDownstreamChannel, ...],
        upstream: tuple[DocsisUpstreamChannel, ...],
    ) -> GatewaySnapshot:
        """Return a new snapshot with the latest validated DOCSIS collections."""
        return replace(
            self,
            docsis_downstream_channels=downstream,
            docsis_upstream_channels=upstream,
        )
