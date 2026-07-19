"""Gateway sensors for Sagemcom F@st routers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS,
    EntityCategory,
    UnitOfDataRate,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import HomeAssistantSagemcomFastData
from .const import DOMAIN
from .coordinator import SagemcomDataUpdateCoordinator
from .docsis import DocsisDownstreamChannel, DocsisUpstreamChannel
from .identity import gateway_unique_id
from .snapshot import GatewayCapability, GatewaySnapshot

PARALLEL_UPDATES = 0
DOCSIS_POWER_UNIT = "dBmV"
DOCSIS_CODEWORD_UNIT = "codewords"

DocsisChannel = DocsisDownstreamChannel | DocsisUpstreamChannel


def _format_frequency_mhz(frequency: float | None) -> str:
    """Format a DOCSIS frequency in MHz without unnecessary trailing zeros."""
    if frequency is None:
        return "?"
    return f"{frequency / 1_000_000:.3f}".rstrip("0").rstrip(".")


def _uptime(snapshot: GatewaySnapshot) -> int | None:
    """Return normalized uptime seconds when the latest read succeeded."""
    value = snapshot.metrics.get(GatewayCapability.UPTIME)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _integer_metric(
    snapshot: GatewaySnapshot, capability: GatewayCapability
) -> int | None:
    """Return a normalized integer metric when the latest read succeeded."""
    value = snapshot.metrics.get(capability)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _downstream_codeword_totals(
    snapshot: GatewaySnapshot,
) -> tuple[int, int, int] | None:
    """Return complete totals for the currently locked downstream channels."""
    channels = snapshot.docsis_downstream_channels
    if not channels or any(not channel.lock_status for channel in channels):
        return None

    unerrored = 0
    correctable = 0
    uncorrectable = 0
    for channel in channels:
        if (
            channel.unerrored_codewords is None
            or channel.correctable_codewords is None
            or channel.uncorrectable_codewords is None
        ):
            return None
        unerrored += channel.unerrored_codewords
        correctable += channel.correctable_codewords
        uncorrectable += channel.uncorrectable_codewords
    return unerrored, correctable, uncorrectable


def _downstream_codeword_total(snapshot: GatewaySnapshot, index: int) -> int | None:
    """Return one aggregate downstream codeword counter."""
    totals = _downstream_codeword_totals(snapshot)
    return totals[index] if totals is not None else None


def _downstream_codeword_error_percentage(
    snapshot: GatewaySnapshot,
) -> float | None:
    """Return the cumulative corrected plus uncorrectable codeword percentage."""
    totals = _downstream_codeword_totals(snapshot)
    if totals is None or (all_codewords := sum(totals)) == 0:
        return None
    return round((totals[1] + totals[2]) / all_codewords * 100, 8)


@dataclass(frozen=True, kw_only=True)
class SagemcomFastSensorEntityDescription(SensorEntityDescription):
    """Describe a Sagemcom gateway sensor."""

    value_fn: Callable[[GatewaySnapshot], StateType]
    capability: GatewayCapability | None = None


@dataclass(frozen=True, kw_only=True)
class SagemcomFastDocsisSensorEntityDescription(SensorEntityDescription):
    """Describe a per-channel DOCSIS sensor."""

    capability: GatewayCapability
    value_fn: Callable[[DocsisChannel], float | None]


SENSORS: tuple[SagemcomFastSensorEntityDescription, ...] = (
    SagemcomFastSensorEntityDescription(
        key="uptime",
        translation_key="uptime",
        icon="mdi:timer-outline",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        capability=GatewayCapability.UPTIME,
        value_fn=_uptime,
    ),
    SagemcomFastSensorEntityDescription(
        key="active_clients",
        translation_key="active_clients",
        icon="mdi:devices",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snapshot: snapshot.active_host_counts.total,
    ),
    SagemcomFastSensorEntityDescription(
        key="active_wired_clients",
        translation_key="active_wired_clients",
        icon="mdi:lan",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snapshot: snapshot.active_host_counts.wired,
    ),
    SagemcomFastSensorEntityDescription(
        key="active_wireless_clients",
        translation_key="active_wireless_clients",
        icon="mdi:wifi",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snapshot: snapshot.active_host_counts.wireless,
    ),
    SagemcomFastSensorEntityDescription(
        key="dsl_downstream_rate",
        translation_key="dsl_downstream_rate",
        icon="mdi:download-network-outline",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        capability=GatewayCapability.DSL_DOWNSTREAM_RATE,
        value_fn=lambda snapshot: _integer_metric(
            snapshot, GatewayCapability.DSL_DOWNSTREAM_RATE
        ),
    ),
    SagemcomFastSensorEntityDescription(
        key="dsl_upstream_rate",
        translation_key="dsl_upstream_rate",
        icon="mdi:upload-network-outline",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        capability=GatewayCapability.DSL_UPSTREAM_RATE,
        value_fn=lambda snapshot: _integer_metric(
            snapshot, GatewayCapability.DSL_UPSTREAM_RATE
        ),
    ),
    SagemcomFastSensorEntityDescription(
        key="docsis_unerrored_codewords",
        translation_key="docsis_unerrored_codewords",
        icon="mdi:check-circle-outline",
        native_unit_of_measurement=DOCSIS_CODEWORD_UNIT,
        entity_category=EntityCategory.DIAGNOSTIC,
        capability=GatewayCapability.DOCSIS_DOWNSTREAM_CHANNELS,
        value_fn=lambda snapshot: _downstream_codeword_total(snapshot, 0),
    ),
    SagemcomFastSensorEntityDescription(
        key="docsis_corrected_codewords",
        translation_key="docsis_corrected_codewords",
        icon="mdi:wrench-check-outline",
        native_unit_of_measurement=DOCSIS_CODEWORD_UNIT,
        entity_category=EntityCategory.DIAGNOSTIC,
        capability=GatewayCapability.DOCSIS_DOWNSTREAM_CHANNELS,
        value_fn=lambda snapshot: _downstream_codeword_total(snapshot, 1),
    ),
    SagemcomFastSensorEntityDescription(
        key="docsis_uncorrectable_codewords",
        translation_key="docsis_uncorrectable_codewords",
        icon="mdi:alert-circle-outline",
        native_unit_of_measurement=DOCSIS_CODEWORD_UNIT,
        entity_category=EntityCategory.DIAGNOSTIC,
        capability=GatewayCapability.DOCSIS_DOWNSTREAM_CHANNELS,
        value_fn=lambda snapshot: _downstream_codeword_total(snapshot, 2),
    ),
    SagemcomFastSensorEntityDescription(
        key="docsis_codeword_error_percentage",
        translation_key="docsis_codeword_error_percentage",
        icon="mdi:percent-outline",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=5,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        capability=GatewayCapability.DOCSIS_DOWNSTREAM_CHANNELS,
        value_fn=_downstream_codeword_error_percentage,
    ),
)

DOCSIS_SENSORS: tuple[SagemcomFastDocsisSensorEntityDescription, ...] = (
    SagemcomFastDocsisSensorEntityDescription(
        key="docsis_downstream_snr",
        translation_key="docsis_downstream_snr",
        icon="mdi:signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        capability=GatewayCapability.DOCSIS_DOWNSTREAM_CHANNELS,
        value_fn=lambda channel: (
            channel.snr if isinstance(channel, DocsisDownstreamChannel) else None
        ),
    ),
    SagemcomFastDocsisSensorEntityDescription(
        key="docsis_downstream_power",
        translation_key="docsis_downstream_power",
        icon="mdi:sine-wave",
        native_unit_of_measurement=DOCSIS_POWER_UNIT,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        capability=GatewayCapability.DOCSIS_DOWNSTREAM_CHANNELS,
        value_fn=lambda channel: (
            channel.power_level
            if isinstance(channel, DocsisDownstreamChannel)
            else None
        ),
    ),
    SagemcomFastDocsisSensorEntityDescription(
        key="docsis_upstream_power",
        translation_key="docsis_upstream_power",
        icon="mdi:sine-wave",
        native_unit_of_measurement=DOCSIS_POWER_UNIT,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        capability=GatewayCapability.DOCSIS_UPSTREAM_CHANNELS,
        value_fn=lambda channel: (
            channel.power_level if isinstance(channel, DocsisUpstreamChannel) else None
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors supported by this gateway."""
    data: HomeAssistantSagemcomFastData = hass.data[DOMAIN][entry.entry_id]
    snapshot = data.coordinator.data
    capabilities = snapshot.capabilities
    descriptions = (
        description
        for description in SENSORS
        if description.capability is None
        or capabilities.supports(description.capability)
    )
    entities: list[SensorEntity] = list(
        SagemcomFastSensor(data.coordinator, description)
        for description in descriptions
    )
    for description in DOCSIS_SENSORS:
        if not capabilities.supports(description.capability):
            continue
        channels: tuple[DocsisChannel, ...] = (
            snapshot.docsis_downstream_channels
            if description.capability is GatewayCapability.DOCSIS_DOWNSTREAM_CHANNELS
            else snapshot.docsis_upstream_channels
        )
        entities.extend(
            SagemcomFastDocsisSensor(data.coordinator, description, channel)
            for channel in channels
            if description.value_fn(channel) is not None
        )
    async_add_entities(entities)


class SagemcomFastSensor(
    CoordinatorEntity[SagemcomDataUpdateCoordinator], SensorEntity
):
    """A sensor backed by the shared gateway snapshot."""

    _attr_has_entity_name = True
    entity_description: SagemcomFastSensorEntityDescription

    def __init__(
        self,
        coordinator: SagemcomDataUpdateCoordinator,
        description: SagemcomFastSensorEntityDescription,
    ) -> None:
        """Initialize a gateway sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._gateway_id = gateway_unique_id(coordinator.data.gateway)
        self._attr_unique_id = f"{self._gateway_id}_{description.key}"

    @property
    @override
    def native_value(self) -> StateType:
        """Return the latest snapshot value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    @override
    def available(self) -> bool:
        """Return whether the coordinator and optional metric are available."""
        capability = self.entity_description.capability
        if capability is GatewayCapability.DOCSIS_DOWNSTREAM_CHANNELS:
            return super().available and self.native_value is not None
        return super().available and (
            capability is None or capability in self.coordinator.data.metrics
        )

    @property
    @override
    def device_info(self) -> DeviceInfo:
        """Attach the sensor to the gateway device."""
        return DeviceInfo(identifiers={(DOMAIN, self._gateway_id)})


class SagemcomFastDocsisSensor(
    CoordinatorEntity[SagemcomDataUpdateCoordinator], SensorEntity
):
    """A disabled-by-default sensor for one DOCSIS channel field."""

    _attr_has_entity_name = True
    entity_description: SagemcomFastDocsisSensorEntityDescription

    def __init__(
        self,
        coordinator: SagemcomDataUpdateCoordinator,
        description: SagemcomFastDocsisSensorEntityDescription,
        channel: DocsisChannel,
    ) -> None:
        """Initialize a DOCSIS channel sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._gateway_id = gateway_unique_id(coordinator.data.gateway)
        self._channel_uid = channel.uid
        self._attr_unique_id = (
            f"{self._gateway_id}_{description.key}_{self._channel_uid}"
        )
        self._attr_translation_placeholders = {
            "channel_id": str(channel.channel_id),
            "frequency_mhz": _format_frequency_mhz(channel.frequency),
        }

    def _channel(self) -> DocsisChannel | None:
        """Return the current channel matching this entity's stable UID."""
        channels: tuple[DocsisChannel, ...] = (
            self.coordinator.data.docsis_downstream_channels
            if self.entity_description.capability
            is GatewayCapability.DOCSIS_DOWNSTREAM_CHANNELS
            else self.coordinator.data.docsis_upstream_channels
        )
        return next(
            (channel for channel in channels if channel.uid == self._channel_uid),
            None,
        )

    @property
    @override
    def native_value(self) -> StateType:
        """Return a rounded signal value for a currently locked channel."""
        channel = self._channel()
        if channel is None or not channel.lock_status:
            return None
        value = self.entity_description.value_fn(channel)
        return round(value, 1) if value is not None else None

    @property
    @override
    def available(self) -> bool:
        """Return whether the channel remains locked with a valid value."""
        return super().available and self.native_value is not None

    @property
    @override
    def device_info(self) -> DeviceInfo:
        """Attach the sensor to the gateway device."""
        return DeviceInfo(identifiers={(DOMAIN, self._gateway_id)})
