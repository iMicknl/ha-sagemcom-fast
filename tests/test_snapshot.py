"""Tests for gateway snapshot and capability models."""

import pytest
from sagemcom_api.models import Device, DeviceInfo

from custom_components.sagemcom_fast.docsis import DocsisDownstreamChannel
from custom_components.sagemcom_fast.snapshot import (
    ActiveHostCounts,
    GatewayCapabilities,
    GatewayCapability,
    GatewaySnapshot,
    HostConnectionType,
    host_connection_type,
)


def test_capabilities_distinguish_supported_and_absent_features() -> None:
    capabilities = GatewayCapabilities(supported=frozenset({GatewayCapability.UPTIME}))

    assert capabilities.supports(GatewayCapability.UPTIME)
    assert not capabilities.supports(GatewayCapability.WAN_STATUS)


def test_host_update_does_not_mutate_the_previous_snapshot() -> None:
    gateway = DeviceInfo(mac_address="AA:BB:CC:DD:EE:00", serial_number="router")
    stale = Device(phys_address="AA:BB:CC:DD:EE:01", active=True)
    active = Device(phys_address="AA:BB:CC:DD:EE:02", active=True)
    snapshot = GatewaySnapshot(gateway=gateway, hosts={stale.id: stale})

    updated = snapshot.with_active_hosts([active])

    assert stale.active is True
    assert snapshot.hosts[stale.id].active is True
    assert updated.hosts[stale.id].active is False
    assert updated.hosts[active.id] is active
    assert updated.gateway is gateway


@pytest.mark.parametrize(
    ("interface_type", "expected"),
    [
        ("WiFi", HostConnectionType.WIRELESS),
        ("Wi-Fi", HostConnectionType.WIRELESS),
        ("WLAN", HostConnectionType.WIRELESS),
        ("Ethernet", HostConnectionType.WIRED),
        ("LAN", HostConnectionType.WIRED),
        ("MoCA", None),
        (None, None),
    ],
)
def test_host_connection_type_normalizes_only_known_labels(
    interface_type: str | None,
    expected: HostConnectionType | None,
) -> None:
    assert host_connection_type(interface_type) is expected


def test_active_host_counts_keep_unknown_interfaces_in_total_only() -> None:
    hosts = [
        Device(phys_address="AA:BB:CC:DD:EE:01", active=True, interface_type="WiFi"),
        Device(
            phys_address="AA:BB:CC:DD:EE:02",
            active=True,
            interface_type="Ethernet",
        ),
        Device(phys_address="AA:BB:CC:DD:EE:03", active=True, interface_type="MoCA"),
        Device(phys_address="AA:BB:CC:DD:EE:04", active=False, interface_type="WiFi"),
    ]
    snapshot = GatewaySnapshot(
        gateway=DeviceInfo(mac_address="AA:BB:CC:DD:EE:00"),
        hosts={host.id: host for host in hosts},
    )

    assert snapshot.active_host_counts == ActiveHostCounts(total=3, wired=1, wireless=1)


def test_docsis_channel_updates_do_not_mutate_previous_snapshot() -> None:
    snapshot = GatewaySnapshot(gateway=DeviceInfo(mac_address="AA:BB:CC:DD:EE:00"))
    channel = DocsisDownstreamChannel(
        uid=1,
        channel_id=10,
        lock_status=True,
        frequency=None,
        bandwidth=None,
        symbol_rate=None,
        modulation=None,
        snr=40.0,
        power_level=None,
        unerrored_codewords=None,
        correctable_codewords=None,
        uncorrectable_codewords=None,
    )

    updated = snapshot.with_docsis_channels((channel,), ())

    assert snapshot.docsis_downstream_channels == ()
    assert updated.docsis_downstream_channels == (channel,)
