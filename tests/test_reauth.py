"""Tests for reauthenticating a router after its credentials changed."""

from contextlib import contextmanager
from unittest.mock import AsyncMock, Mock, patch

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from sagemcom_api.enums import EncryptionMethod
from sagemcom_api.exceptions import AuthenticationException

from custom_components.sagemcom_fast.const import CONF_ENCRYPTION_METHOD, DOMAIN

from .conftest import CONFIG_HOST_MARKER, CONFIG_USERNAME_MARKER


@contextmanager
def _patch_clients(sagemcom_client: Mock):
    """Route both the detection and the entry-style client to one mock."""
    with (
        patch(
            "custom_components.sagemcom_fast.config_flow.SagemcomClient",
            return_value=sagemcom_client,
        ),
        patch(
            "custom_components.sagemcom_fast.api.SagemcomClient",
            return_value=sagemcom_client,
        ),
    ):
        yield


async def test_setup_auth_failure_starts_reauth_flow(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    config_entry: MockConfigEntry,
    sagemcom_client: Mock,
) -> None:
    """Rejected credentials at setup must lead to a usable reauth form."""
    sagemcom_client.login.side_effect = AuthenticationException("wrong password")
    config_entry.add_to_hass(hass)

    with _patch_clients(sagemcom_client):
        assert not await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    (flow,) = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flow["context"]["source"] == config_entries.SOURCE_REAUTH
    assert flow["step_id"] == "reauth_confirm"


async def test_reauth_updates_credentials_and_reloads(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    config_entry: MockConfigEntry,
    sagemcom_client: Mock,
) -> None:
    """Valid replacement credentials must be stored with the detected method."""
    config_entry.add_to_hass(hass)
    sagemcom_client.get_encryption_method.return_value = EncryptionMethod.SHA512
    result = await config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with (
        _patch_clients(sagemcom_client),
        patch(
            "custom_components.sagemcom_fast.async_setup_entry",
            new=AsyncMock(return_value=True),
        ) as setup_entry,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "new-user", CONF_PASSWORD: "new-password"},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_USERNAME] == "new-user"
    assert config_entry.data[CONF_PASSWORD] == "new-password"
    assert config_entry.data[CONF_ENCRYPTION_METHOD] == EncryptionMethod.SHA512
    assert config_entry.data[CONF_HOST] == CONFIG_HOST_MARKER
    setup_entry.assert_awaited_once()


@pytest.mark.parametrize(
    ("detected", "login_error"),
    [
        (None, None),
        (EncryptionMethod.MD5, AuthenticationException("wrong password")),
    ],
)
async def test_reauth_rejected_credentials_show_invalid_auth(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    config_entry: MockConfigEntry,
    sagemcom_client: Mock,
    detected: EncryptionMethod | None,
    login_error: Exception | None,
) -> None:
    """Rejected credentials must keep the form open and the entry unchanged."""
    config_entry.add_to_hass(hass)
    original_data = dict(config_entry.data)
    sagemcom_client.get_encryption_method.return_value = detected
    sagemcom_client.login.side_effect = login_error
    result = await config_entry.start_reauth_flow(hass)

    with _patch_clients(sagemcom_client):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: CONFIG_USERNAME_MARKER, CONF_PASSWORD: "still-wrong"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "invalid_auth"}
    assert dict(config_entry.data) == original_data


async def test_user_flow_stores_blank_password(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    sagemcom_client: Mock,
) -> None:
    """A router without a password must not create an entry setup can't read."""
    sagemcom_client.get_encryption_method.return_value = EncryptionMethod.MD5
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with (
        _patch_clients(sagemcom_client),
        patch(
            "custom_components.sagemcom_fast.async_setup_entry",
            new=AsyncMock(return_value=True),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.0.2.1",
                CONF_USERNAME: "admin",
                CONF_SSL: False,
                CONF_VERIFY_SSL: False,
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PASSWORD] == ""
