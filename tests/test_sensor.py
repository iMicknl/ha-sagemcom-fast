"""Tests for gateway sensor entities."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS,
    EntityCategory,
    UnitOfDataRate,
    UnitOfTime,
)
from sagemcom_api.models import Device, DeviceInfo

from custom_components.sagemcom_fast.const import DOMAIN
from custom_components.sagemcom_fast.docsis import (
    DocsisDownstreamChannel,
    DocsisUpstreamChannel,
)
from custom_components.sagemcom_fast.sensor import (
    DOCSIS_CODEWORD_UNIT,
    DOCSIS_POWER_UNIT,
    SagemcomFastDocsisSensor,
    SagemcomFastSensor,
    async_setup_entry,
)
from custom_components.sagemcom_fast.snapshot import (
    GatewayCapabilities,
    GatewayCapability,
    GatewaySnapshot,
)


def _coordinator(
    *, uptime: bool = True, dsl_rates: bool = False, docsis: bool = False
) -> SimpleNamespace:
    hosts = [
        Device(phys_address="AA:BB:CC:DD:EE:01", active=True, interface_type="WiFi"),
        Device(
            phys_address="AA:BB:CC:DD:EE:02",
            active=True,
            interface_type="Ethernet",
        ),
        Device(phys_address="AA:BB:CC:DD:EE:03", active=True, interface_type=None),
        Device(phys_address="AA:BB:CC:DD:EE:04", active=False, interface_type="WiFi"),
    ]
    supported = {GatewayCapability.UPTIME} if uptime else set()
    metrics = {GatewayCapability.UPTIME: 1234} if uptime else {}
    if dsl_rates:
        supported.update(
            {
                GatewayCapability.DSL_DOWNSTREAM_RATE,
                GatewayCapability.DSL_UPSTREAM_RATE,
            }
        )
        metrics.update(
            {
                GatewayCapability.DSL_DOWNSTREAM_RATE: 123456,
                GatewayCapability.DSL_UPSTREAM_RATE: 23456,
            }
        )
    downstream_channels = ()
    upstream_channels = ()
    if docsis:
        supported.update(
            {
                GatewayCapability.DOCSIS_DOWNSTREAM_CHANNELS,
                GatewayCapability.DOCSIS_UPSTREAM_CHANNELS,
            }
        )
        downstream_channels = (
            DocsisDownstreamChannel(
                uid=10,
                channel_id=6,
                lock_status=True,
                frequency=386000000.0,
                bandwidth=8000000,
                symbol_rate=6952,
                modulation="Qam256",
                snr=42.0,
                power_level=8.6,
                unerrored_codewords=1000,
                correctable_codewords=2,
                uncorrectable_codewords=0,
            ),
        )
        upstream_channels = (
            DocsisUpstreamChannel(
                uid=20,
                channel_id=1,
                lock_status=True,
                frequency=23800000.0,
                symbol_rate=5120,
                modulation="atdma",
                power_level=39.299999,
                frequency31=None,
                modulation31=None,
                profile_id31=None,
            ),
        )
    return SimpleNamespace(
        data=GatewaySnapshot(
            gateway=DeviceInfo(mac_address="AA:BB:CC:DD:EE:00", serial_number="router"),
            hosts={host.id: host for host in hosts},
            capabilities=GatewayCapabilities(supported=frozenset(supported)),
            metrics=metrics,
            docsis_downstream_channels=downstream_channels,
            docsis_upstream_channels=upstream_channels,
        ),
        last_update_success=True,
    )


def _setup_entities(coordinator: SimpleNamespace) -> list[SensorEntity]:
    entry = SimpleNamespace(entry_id="entry")
    hass = SimpleNamespace(
        data={DOMAIN: {entry.entry_id: SimpleNamespace(coordinator=coordinator)}}
    )
    entities: list[SensorEntity] = []
    asyncio.run(async_setup_entry(hass, entry, entities.extend))
    return entities


def test_sensor_setup_includes_only_supported_optional_metrics() -> None:
    supported_keys = {
        entity.entity_description.key for entity in _setup_entities(_coordinator())
    }
    assert supported_keys == {
        "uptime",
        "active_clients",
        "active_wired_clients",
        "active_wireless_clients",
    }
    assert {
        entity.entity_description.key
        for entity in _setup_entities(_coordinator(uptime=False))
    } == {
        "active_clients",
        "active_wired_clients",
        "active_wireless_clients",
    }


def test_sensor_values_and_gateway_identity_come_from_snapshot() -> None:
    entities = {
        entity.entity_description.key: entity
        for entity in _setup_entities(_coordinator())
    }

    assert entities["uptime"].native_value == 1234
    assert entities["active_clients"].native_value == 3
    assert entities["active_wired_clients"].native_value == 1
    assert entities["active_wireless_clients"].native_value == 1
    assert entities["uptime"].unique_id == "router_uptime"
    assert entities["uptime"].device_info["identifiers"] == {(DOMAIN, "router")}
    assert entities["uptime"].device_class is SensorDeviceClass.DURATION
    assert entities["uptime"].native_unit_of_measurement is UnitOfTime.SECONDS
    assert entities["uptime"].state_class is SensorStateClass.MEASUREMENT


def test_uptime_is_unavailable_when_latest_optional_read_failed() -> None:
    coordinator = _coordinator()
    uptime = next(
        entity
        for entity in _setup_entities(coordinator)
        if entity.entity_description.key == "uptime"
    )

    coordinator.data = coordinator.data.with_metrics({})

    assert uptime.native_value is None
    assert not uptime.available


def test_dsl_rate_sensors_use_kilobits_and_data_rate_semantics() -> None:
    entities = {
        entity.entity_description.key: entity
        for entity in _setup_entities(_coordinator(dsl_rates=True))
    }

    downstream = entities["dsl_downstream_rate"]
    upstream = entities["dsl_upstream_rate"]

    assert downstream.native_value == 123456
    assert upstream.native_value == 23456
    for entity in (downstream, upstream):
        assert entity.device_class is SensorDeviceClass.DATA_RATE
        assert entity.native_unit_of_measurement is UnitOfDataRate.KILOBITS_PER_SECOND
        assert entity.state_class is SensorStateClass.MEASUREMENT
        assert entity.entity_category is EntityCategory.DIAGNOSTIC


def test_dsl_rate_sensors_are_absent_when_unsupported() -> None:
    keys = {
        entity.entity_description.key
        for entity in _setup_entities(_coordinator(dsl_rates=False))
    }

    assert "dsl_downstream_rate" not in keys
    assert "dsl_upstream_rate" not in keys


def test_supported_dsl_rate_is_unavailable_after_a_failed_read() -> None:
    coordinator = _coordinator(dsl_rates=True)
    entities = {
        entity.entity_description.key: entity for entity in _setup_entities(coordinator)
    }
    coordinator.data = coordinator.data.with_metrics(
        {GatewayCapability.DSL_UPSTREAM_RATE: 23456}
    )

    assert entities["dsl_downstream_rate"].native_value is None
    assert not entities["dsl_downstream_rate"].available
    assert entities["dsl_upstream_rate"].native_value == 23456
    assert entities["dsl_upstream_rate"].available


def test_docsis_signal_sensors_use_validated_units_and_stable_uids() -> None:
    entities = {
        entity.entity_description.key: entity
        for entity in _setup_entities(_coordinator(docsis=True))
        if isinstance(entity, SagemcomFastDocsisSensor)
    }

    assert set(entities) == {
        "docsis_downstream_snr",
        "docsis_downstream_power",
        "docsis_upstream_power",
    }
    assert entities["docsis_downstream_snr"].native_value == 42.0
    assert entities["docsis_downstream_snr"].native_unit_of_measurement == (
        SIGNAL_STRENGTH_DECIBELS
    )
    assert (
        entities["docsis_downstream_snr"].device_class
        is SensorDeviceClass.SIGNAL_STRENGTH
    )
    assert entities["docsis_downstream_power"].native_value == 8.6
    assert (
        entities["docsis_downstream_power"].native_unit_of_measurement
        == DOCSIS_POWER_UNIT
    )
    assert entities["docsis_upstream_power"].native_value == 39.3
    assert not entities["docsis_upstream_power"].entity_registry_enabled_default
    assert entities["docsis_downstream_snr"].unique_id == (
        "router_docsis_downstream_snr_10"
    )
    assert entities["docsis_downstream_snr"].translation_placeholders == {
        "channel_id": "6",
        "frequency_mhz": "386",
    }
    assert entities["docsis_upstream_power"].translation_placeholders == {
        "channel_id": "1",
        "frequency_mhz": "23.8",
    }


def test_docsis_signal_sensor_is_unavailable_when_channel_unlocks() -> None:
    coordinator = _coordinator(docsis=True)
    upstream = next(
        entity
        for entity in _setup_entities(coordinator)
        if isinstance(entity, SagemcomFastDocsisSensor)
        and entity.entity_description.key == "docsis_upstream_power"
    )
    channel = coordinator.data.docsis_upstream_channels[0]
    coordinator.data = coordinator.data.with_docsis_channels(
        coordinator.data.docsis_downstream_channels,
        (replace(channel, lock_status=False),),
    )

    assert upstream.native_value is None
    assert not upstream.available


def test_docsis_aggregate_codeword_sensors_and_error_percentage() -> None:
    entities = {
        entity.entity_description.key: entity
        for entity in _setup_entities(_coordinator(docsis=True))
        if isinstance(entity, SagemcomFastSensor)
    }

    assert entities["docsis_unerrored_codewords"].native_value == 1000
    assert entities["docsis_corrected_codewords"].native_value == 2
    assert entities["docsis_uncorrectable_codewords"].native_value == 0
    assert entities["docsis_codeword_error_percentage"].native_value == round(
        2 / 1002 * 100, 8
    )
    assert (
        entities["docsis_unerrored_codewords"].native_unit_of_measurement
        == DOCSIS_CODEWORD_UNIT
    )
    assert (
        entities["docsis_codeword_error_percentage"].native_unit_of_measurement
        == PERCENTAGE
    )
    assert entities["docsis_unerrored_codewords"].available
    assert entities["docsis_codeword_error_percentage"].available


def test_docsis_aggregate_codeword_sensors_require_all_channels_locked() -> None:
    coordinator = _coordinator(docsis=True)
    corrected = next(
        entity
        for entity in _setup_entities(coordinator)
        if isinstance(entity, SagemcomFastSensor)
        and entity.entity_description.key == "docsis_corrected_codewords"
    )
    channel = coordinator.data.docsis_downstream_channels[0]
    coordinator.data = coordinator.data.with_docsis_channels(
        (replace(channel, lock_status=False),),
        coordinator.data.docsis_upstream_channels,
    )

    assert corrected.native_value is None
    assert not corrected.available
