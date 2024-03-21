"""Support for Sagencom F@st buttons."""
from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from sagemcom_api.client import SagemcomClient
from sagemcom_api.models import DeviceInfo as GatewayDeviceInfo

from . import HomeAssistantSagemcomFastData
from .const import DOMAIN, LOGGER


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Sagemcom F@st button from a config entry."""
    data: HomeAssistantSagemcomFastData = hass.data[DOMAIN][entry.entry_id]
    entities: list[ButtonEntity] = []
    entities.append(SagemcomFastRebootButton(data.gateway, data.coordinator.client))

    async_add_entities(entities)


class SagemcomFastRebootButton(ButtonEntity):
    """Representation of an Sagemcom F@st Button."""

    _attr_has_entity_name = True
    _attr_name = "Reboot"
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, gateway: GatewayDeviceInfo, client: SagemcomClient) -> None:
        """Initialize the button."""
        self.gateway = gateway
        self.client = client
        self._attr_unique_id = f"{self.gateway.serial_number}_reboot"

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self.client.login()
            await self.client.reboot()
        except Exception as exception:  # pylint: disable=broad-except
            LOGGER.exception(exception)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.gateway.serial_number)},
        )
