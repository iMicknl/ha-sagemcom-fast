"""Provides diagnostics for Overkiz."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import HomeAssistantSagemcomFastData
from .const import DOMAIN, LOGGER


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    entry_data: HomeAssistantSagemcomFastData = hass.data[DOMAIN][entry.entry_id]
    client = entry_data.coordinator.client

    full_dump = None
    try:
        await client.login()
        full_dump = await client.get_value_by_xpath("*")
    except Exception as exception:  # pylint: disable=broad-except
        LOGGER.exception(exception)

        return False
    finally:
        await client.logout()

    data = {"raw": full_dump}

    return data
