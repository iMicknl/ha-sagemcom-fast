"""Support for Sagemcom F@st buttons."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from sagemcom_api.models import DeviceInfo as GatewayDeviceInfo

from . import HomeAssistantSagemcomFastData
from .api import SagemcomApi
from .const import DOMAIN, LOGGER
from .identity import gateway_unique_id


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Sagemcom F@st button from a config entry."""
    data: HomeAssistantSagemcomFastData = hass.data[DOMAIN][entry.entry_id]
    entities: list[ButtonEntity] = []
    entities.append(
        SagemcomFastRebootButton(data.coordinator.data.gateway, data.coordinator.api)
    )

    async_add_entities(entities)


class SagemcomFastRebootButton(ButtonEntity):
    """Representation of a Sagemcom F@st button."""

    _attr_has_entity_name = True
    _attr_translation_key = "reboot"
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, gateway: GatewayDeviceInfo, api: SagemcomApi) -> None:
        """Initialize the button."""
        self.gateway = gateway
        self.api = api
        self._attr_unique_id = f"{gateway_unique_id(self.gateway)}_reboot"

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self.api.async_terminal_call(lambda client: client.reboot())
        except Exception as exception:  # pylint: disable=broad-except
            LOGGER.exception(exception)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, gateway_unique_id(self.gateway))},
        )
