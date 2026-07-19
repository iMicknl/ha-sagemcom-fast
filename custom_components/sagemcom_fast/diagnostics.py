"""Diagnostics support for Sagemcom F@st."""

from __future__ import annotations

from collections import Counter
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from . import HomeAssistantSagemcomFastData
from .const import DOMAIN

TO_REDACT = {CONF_HOST, CONF_PASSWORD, CONF_USERNAME}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    entry_data: HomeAssistantSagemcomFastData = hass.data[DOMAIN][entry.entry_id]
    coordinator = entry_data.coordinator
    snapshot = coordinator.data
    active_hosts = [host for host in snapshot.hosts.values() if host.active]
    interface_counts = Counter(
        host.interface_type or "unknown" for host in active_hosts
    )

    return {
        "config_entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "gateway": {
            "manufacturer": snapshot.gateway.manufacturer,
            "model_name": snapshot.gateway.model_name,
            "model_number": snapshot.gateway.model_number,
            "software_version": snapshot.gateway.software_version,
            "hardware_version": snapshot.gateway.hardware_version,
            "api_version": snapshot.gateway.api_version,
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "known_hosts": len(snapshot.hosts),
            "active_hosts": len(active_hosts),
            "active_interface_counts": dict(interface_counts),
            "docsis_downstream_channels": len(snapshot.docsis_downstream_channels),
            "docsis_downstream_locked": sum(
                channel.lock_status for channel in snapshot.docsis_downstream_channels
            ),
            "docsis_upstream_channels": len(snapshot.docsis_upstream_channels),
            "docsis_upstream_locked": sum(
                channel.lock_status for channel in snapshot.docsis_upstream_channels
            ),
        },
    }
