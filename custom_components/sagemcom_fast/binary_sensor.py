"""Gateway binary sensors for Sagemcom F@st routers."""

from __future__ import annotations

from typing import override

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import HomeAssistantSagemcomFastData
from .capabilities import wan_status_is_connected
from .const import DOMAIN
from .coordinator import SagemcomDataUpdateCoordinator
from .identity import gateway_unique_id
from .snapshot import GatewayCapability

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors supported by this gateway."""
    data: HomeAssistantSagemcomFastData = hass.data[DOMAIN][entry.entry_id]
    if not data.coordinator.data.capabilities.supports(GatewayCapability.WAN_STATUS):
        return

    async_add_entities([SagemcomFastWanConnectivityBinarySensor(data.coordinator)])


class SagemcomFastWanConnectivityBinarySensor(
    CoordinatorEntity[SagemcomDataUpdateCoordinator], BinarySensorEntity
):
    """Represent whether the gateway WAN interface is connected."""

    _attr_has_entity_name = True
    _attr_translation_key = "wan_connectivity"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: SagemcomDataUpdateCoordinator) -> None:
        """Initialize the WAN connectivity sensor."""
        super().__init__(coordinator)
        self._gateway_id = gateway_unique_id(coordinator.data.gateway)
        self._attr_unique_id = f"{self._gateway_id}_wan_connectivity"

    @property
    @override
    def is_on(self) -> bool | None:
        """Return whether the latest WAN status is connected."""
        return wan_status_is_connected(
            self.coordinator.data.metrics.get(GatewayCapability.WAN_STATUS)
        )

    @property
    @override
    def available(self) -> bool:
        """Return whether a recognized WAN status is available."""
        return super().available and self.is_on is not None

    @property
    @override
    def device_info(self) -> DeviceInfo:
        """Attach the binary sensor to the gateway device."""
        return DeviceInfo(identifiers={(DOMAIN, self._gateway_id)})
