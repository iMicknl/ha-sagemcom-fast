"""Tests for gateway binary sensor entities."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from sagemcom_api.models import DeviceInfo

from custom_components.sagemcom_fast.binary_sensor import (
    SagemcomFastWanConnectivityBinarySensor,
    async_setup_entry,
)
from custom_components.sagemcom_fast.const import DOMAIN
from custom_components.sagemcom_fast.snapshot import (
    GatewayCapabilities,
    GatewayCapability,
    GatewaySnapshot,
)


def _coordinator(*, supported: bool = True, status: str = "Up") -> SimpleNamespace:
    capabilities = (
        GatewayCapabilities(supported=frozenset({GatewayCapability.WAN_STATUS}))
        if supported
        else GatewayCapabilities()
    )
    metrics = {GatewayCapability.WAN_STATUS: status} if supported else {}
    return SimpleNamespace(
        data=GatewaySnapshot(
            gateway=DeviceInfo(mac_address="AA:BB:CC:DD:EE:00", serial_number="router"),
            capabilities=capabilities,
            metrics=metrics,
        ),
        last_update_success=True,
    )


def _setup_entities(
    coordinator: SimpleNamespace,
) -> list[SagemcomFastWanConnectivityBinarySensor]:
    entry = SimpleNamespace(entry_id="entry")
    hass = SimpleNamespace(
        data={DOMAIN: {entry.entry_id: SimpleNamespace(coordinator=coordinator)}}
    )
    entities: list[SagemcomFastWanConnectivityBinarySensor] = []
    asyncio.run(async_setup_entry(hass, entry, entities.extend))
    return entities


def test_setup_adds_wan_sensor_only_for_supported_gateways() -> None:
    assert len(_setup_entities(_coordinator())) == 1
    assert _setup_entities(_coordinator(supported=False)) == []


def test_wan_sensor_state_metadata_and_gateway_identity() -> None:
    sensor = _setup_entities(_coordinator())[0]

    assert sensor.is_on is True
    assert sensor.available is True
    assert sensor.device_class is BinarySensorDeviceClass.CONNECTIVITY
    assert sensor.unique_id == "router_wan_connectivity"
    assert sensor.device_info["identifiers"] == {(DOMAIN, "router")}


def test_wan_sensor_handles_disconnected_and_unknown_states() -> None:
    coordinator = _coordinator(status="Down")
    sensor = _setup_entities(coordinator)[0]

    assert sensor.is_on is False
    assert sensor.available is True

    coordinator.data = coordinator.data.with_metrics(
        {GatewayCapability.WAN_STATUS: "Unknown"}
    )

    assert sensor.is_on is None
    assert sensor.available is False
