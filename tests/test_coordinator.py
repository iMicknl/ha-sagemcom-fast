"""Tests for the Sagemcom F@st data update coordinator."""

from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

from aiohttp.client_exceptions import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import CoordinatorEntity, UpdateFailed
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from sagemcom_api.exceptions import (
    AccessRestrictionException,
    AuthenticationException,
    BadRequestException,
    InvalidSessionException,
    LoginConnectionException,
    LoginRetryErrorException,
    LoginTimeoutException,
    MaximumSessionCountException,
    UnauthorizedException,
    UnsupportedHostException,
)
from sagemcom_api.models import DeviceInfo

from custom_components.sagemcom_fast.const import LOGGER
from custom_components.sagemcom_fast.coordinator import SagemcomDataUpdateCoordinator


def test_coordinator_owns_explicit_config_entry(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    sagemcom_client: Mock,
) -> None:
    """Coordinator construction must not depend on an active setup context."""
    coordinator = SagemcomDataUpdateCoordinator(
        hass,
        LOGGER,
        config_entry=config_entry,
        name="sagemcom_hosts",
        client=sagemcom_client,
        update_interval=timedelta(seconds=30),
    )

    assert coordinator.config_entry is config_entry


@pytest.mark.asyncio
async def test_setup_fetches_gateway_once(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    config_entry: MockConfigEntry,
    sagemcom_client: Mock,
    gateway: DeviceInfo,
) -> None:
    """Gateway discovery must run once before normal host refreshes."""
    config_entry.add_to_hass(hass)
    sagemcom_client.get_device_info.return_value = gateway
    sagemcom_client.get_hosts.return_value = []

    with (
        patch(
            "custom_components.sagemcom_fast.SagemcomClient",
            return_value=sagemcom_client,
        ),
        patch(
            "custom_components.sagemcom_fast.coordinator.asyncio.sleep",
            new=AsyncMock(),
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new=AsyncMock(),
        ),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await config_entry.runtime_data.coordinator.async_refresh()

    assert config_entry.runtime_data.coordinator.gateway is gateway
    sagemcom_client.get_device_info.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_point", ["login", "get_device_info"])
async def test_setup_preserves_primary_error_when_logout_also_fails(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    sagemcom_client: Mock,
    failure_point: str,
) -> None:
    """Cleanup must run without replacing the gateway setup failure."""
    coordinator = SagemcomDataUpdateCoordinator(
        hass,
        LOGGER,
        config_entry=config_entry,
        name="sagemcom_hosts",
        client=sagemcom_client,
        update_interval=timedelta(seconds=30),
    )
    primary_error = RuntimeError(f"{failure_point} failed")
    cleanup_error = RuntimeError("logout failed")
    getattr(sagemcom_client, failure_point).side_effect = primary_error
    sagemcom_client.logout.side_effect = cleanup_error

    with pytest.raises(UpdateFailed) as raised:
        await coordinator._async_setup()

    assert raised.value.__cause__ is primary_error
    sagemcom_client.logout.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["setup", "update"])
@pytest.mark.parametrize(
    ("error_type", "expected_type"),
    [
        (AccessRestrictionException, ConfigEntryAuthFailed),
        (AuthenticationException, ConfigEntryAuthFailed),
        (UnauthorizedException, ConfigEntryAuthFailed),
        (ClientError, UpdateFailed),
        (ConnectionError, UpdateFailed),
        (TimeoutError, UpdateFailed),
        (LoginConnectionException, UpdateFailed),
        (LoginTimeoutException, UpdateFailed),
        (LoginRetryErrorException, UpdateFailed),
        (MaximumSessionCountException, UpdateFailed),
        (InvalidSessionException, UpdateFailed),
        (UnsupportedHostException, UpdateFailed),
        (BadRequestException, UpdateFailed),
        (RuntimeError, UpdateFailed),
    ],
)
async def test_error_classification_preserves_cause(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    sagemcom_client: Mock,
    operation: str,
    error_type: type[Exception],
    expected_type: type[Exception],
) -> None:
    """Known and unknown failures must retain their typed HA transition."""
    coordinator = SagemcomDataUpdateCoordinator(
        hass,
        LOGGER,
        config_entry=config_entry,
        name="sagemcom_hosts",
        client=sagemcom_client,
        update_interval=timedelta(seconds=30),
    )
    original_error = error_type("router failure")
    sagemcom_client.login.side_effect = original_error

    with pytest.raises(expected_type) as raised:
        if operation == "setup":
            await coordinator._async_setup()
        else:
            await coordinator._async_update_data()

    assert raised.value.__cause__ is original_error
    sagemcom_client.logout.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_update_preserves_primary_error_when_logout_also_fails(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    sagemcom_client: Mock,
) -> None:
    """Polling cleanup must not replace the operation failure."""
    coordinator = SagemcomDataUpdateCoordinator(
        hass,
        LOGGER,
        config_entry=config_entry,
        name="sagemcom_hosts",
        client=sagemcom_client,
        update_interval=timedelta(seconds=30),
    )
    primary_error = RuntimeError("hosts failed")
    sagemcom_client.get_hosts.side_effect = primary_error
    sagemcom_client.logout.side_effect = RuntimeError("logout failed")

    with (
        patch(
            "custom_components.sagemcom_fast.coordinator.asyncio.sleep",
            new=AsyncMock(),
        ),
        pytest.raises(UpdateFailed) as raised,
    ):
        await coordinator._async_update_data()

    assert raised.value.__cause__ is primary_error
    sagemcom_client.logout.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_update_error_recovers_on_later_refresh(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    sagemcom_client: Mock,
) -> None:
    """Coordinator availability must recover after a transient failure."""
    coordinator = SagemcomDataUpdateCoordinator(
        hass,
        LOGGER,
        config_entry=config_entry,
        name="sagemcom_hosts",
        client=sagemcom_client,
        update_interval=timedelta(seconds=30),
    )
    original_error = ConnectionError("router offline")
    sagemcom_client.login.side_effect = [original_error, None]
    sagemcom_client.get_hosts.return_value = []
    entity = CoordinatorEntity(coordinator)

    assert entity.available is True

    with patch(
        "custom_components.sagemcom_fast.coordinator.asyncio.sleep",
        new=AsyncMock(),
    ):
        await coordinator.async_refresh()
        assert coordinator.last_update_success is False
        assert isinstance(coordinator.last_exception, UpdateFailed)
        assert coordinator.last_exception.__cause__ is original_error
        assert entity.available is False

        await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    assert entity.available is True
    assert coordinator.data == {}
