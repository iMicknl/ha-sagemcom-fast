"""Diagnostics support for Sagemcom F@st."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SSL, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from . import HomeAssistantSagemcomFastData
from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return privacy-safe diagnostics from cached integration state."""
    entry_data: HomeAssistantSagemcomFastData = hass.data[DOMAIN][entry.entry_id]
    hosts = entry_data.coordinator.hosts
    integration_version = (await async_get_integration(hass, DOMAIN)).version
    update_interval = entry_data.coordinator.update_interval

    return {
        "integration": {
            "domain": DOMAIN,
            "version": str(integration_version) if integration_version else None,
        },
        "configuration": {
            "ssl": entry.data[CONF_SSL],
            "verify_ssl": entry.data[CONF_VERIFY_SSL],
        },
        "coordinator": {
            "last_update_success": entry_data.coordinator.last_update_success,
            "update_interval_seconds": (
                update_interval.total_seconds() if update_interval is not None else None
            ),
        },
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
