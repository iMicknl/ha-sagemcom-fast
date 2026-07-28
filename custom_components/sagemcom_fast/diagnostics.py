"""Diagnostics support for Sagemcom F@st."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import HomeAssistantSagemcomFastData
from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return privacy-safe diagnostics from cached integration state."""
    entry_data: HomeAssistantSagemcomFastData = hass.data[DOMAIN][entry.entry_id]
    hosts = entry_data.coordinator.hosts

    return {
        "integration": {"domain": DOMAIN},
        "gateway": {
            "manufacturer": entry_data.gateway.manufacturer,
            "model": entry_data.gateway.model_name,
            "software_version": entry_data.gateway.software_version,
        },
        "clients": {
            "active": sum(host.active is True for host in hosts.values()),
            "known": len(hosts),
        },
    }
