"""Provides diagnostics for Sagemcom F@st."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

# from . import HomeAssistantSagemcomFastData
# from .const import DOMAIN

TO_REDACT = []


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    # entry_data: HomeAssistantSagemcomFastData = hass.data[DOMAIN][entry.entry_id]

    data = {
        "device_info": {},
    }

    return async_redact_data(data, TO_REDACT)


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Return diagnostics for a device entry."""
    # entry_data: HomeAssistantSagemcomFastData = hass.data[DOMAIN][entry.entry_id]

    data = {
        "device": {
            "controllable_name": device.hw_version,
            "firmware": device.sw_version,
            "model": device.model,
        },
        "app_launch": {},
    }

    return async_redact_data(data, TO_REDACT)
