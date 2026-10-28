"""Tests for transient gateway session and connection failures."""

from datetime import timedelta
import logging
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from sagemcom_api.exceptions import (
    InvalidSessionException,
    LoginConnectionException,
    LoginTimeoutException,
)

from custom_components.sagemcom_fast.const import DOMAIN, LOGGER
from custom_components.sagemcom_fast.coordinator import SagemcomDataUpdateCoordinator


def _coordinator(
    hass: HomeAssistant, config_entry: MockConfigEntry, sagemcom_client: Mock
) -> SagemcomDataUpdateCoordinator:
    return SagemcomDataUpdateCoordinator(
        hass,
        LOGGER,
        config_entry=config_entry,
        name="sagemcom_hosts",
        client=sagemcom_client,
        update_interval=timedelta(seconds=30),
    )


@pytest.mark.parametrize("failure_point", ["login", "get_hosts", "logout"])
async def test_update_invalid_session_is_transient(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    sagemcom_client: Mock,
    failure_point: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An invalid session after the library retry must not require reauth."""
    error = InvalidSessionException("session expired")
    getattr(sagemcom_client, failure_point).side_effect = error
    sagemcom_client.get_hosts.return_value = []

    with (
        patch(
            "custom_components.sagemcom_fast.coordinator.asyncio.sleep",
            new=AsyncMock(),
        ),
        caplog.at_level(logging.ERROR, logger=LOGGER.name),
        pytest.raises(UpdateFailed, match="Session is no longer valid") as raised,
    ):
        await _coordinator(hass, config_entry, sagemcom_client)._async_update_data()

    assert raised.value.__cause__ is error
    assert not caplog.records


@pytest.mark.parametrize("error_type", [LoginConnectionException, LoginTimeoutException])
async def test_update_login_connection_failure_is_transient(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    sagemcom_client: Mock,
    error_type: type[Exception],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Login connectivity failures must not log a traceback on every poll."""
    sagemcom_client.login.side_effect = error_type("router offline")

    with (
        caplog.at_level(logging.ERROR, logger=LOGGER.name),
        pytest.raises(UpdateFailed, match="Failed to connect"),
    ):
        await _coordinator(hass, config_entry, sagemcom_client)._async_update_data()

    assert not caplog.records


async def _async_setup(
    hass: HomeAssistant, config_entry: MockConfigEntry, sagemcom_client: Mock
) -> None:
    config_entry.add_to_hass(hass)
    with patch(
        "custom_components.sagemcom_fast.api.SagemcomClient",
        return_value=sagemcom_client,
    ):
        assert not await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.parametrize("failure_point", ["login", "get_device_info", "logout"])
async def test_setup_invalid_session_retries_setup(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    config_entry: MockConfigEntry,
    sagemcom_client: Mock,
    failure_point: str,
) -> None:
    """An invalid session during setup must retry instead of starting reauth."""
    getattr(sagemcom_client, failure_point).side_effect = InvalidSessionException(
        "session expired"
    )

    await _async_setup(hass, config_entry, sagemcom_client)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)


@pytest.mark.parametrize("error_type", [LoginConnectionException, LoginTimeoutException])
async def test_setup_login_connection_failure_retries_setup(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    config_entry: MockConfigEntry,
    sagemcom_client: Mock,
    error_type: type[Exception],
) -> None:
    """An unreachable router at startup must not leave the entry failed."""
    sagemcom_client.login.side_effect = error_type("router offline")

    await _async_setup(hass, config_entry, sagemcom_client)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
