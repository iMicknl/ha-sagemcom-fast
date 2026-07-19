"""Tests for integration setup helpers."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.const import CONF_SCAN_INTERVAL
import pytest

from custom_components.sagemcom_fast import update_listener
from custom_components.sagemcom_fast.const import DEFAULT_SCAN_INTERVAL, DOMAIN


@pytest.mark.parametrize("options", [{}, {CONF_SCAN_INTERVAL: 30}])
def test_options_update_refreshes_with_a_valid_interval(options: dict) -> None:
    coordinator = SimpleNamespace(update_interval=None, async_refresh=AsyncMock())
    entry = SimpleNamespace(entry_id="entry", options=options)
    hass = SimpleNamespace(
        data={DOMAIN: {entry.entry_id: SimpleNamespace(coordinator=coordinator)}}
    )

    asyncio.run(update_listener(hass, entry))

    expected = options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    assert coordinator.update_interval == timedelta(seconds=expected)
    coordinator.async_refresh.assert_awaited_once()
