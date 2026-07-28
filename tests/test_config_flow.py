"""Tests for the Sagemcom F@st config flow."""

from typing import Any
from unittest.mock import ANY, AsyncMock, Mock, patch

from aiohttp import ClientError
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from sagemcom_api.enums import EncryptionMethod
from sagemcom_api.exceptions import (
    AccessRestrictionException,
    AuthenticationException,
    LoginConnectionException,
    LoginRetryErrorException,
    LoginTimeoutException,
    MaximumSessionCountException,
    UnsupportedHostException,
)
from sagemcom_api.models import DeviceInfo

from custom_components.sagemcom_fast import config_flow
from custom_components.sagemcom_fast.const import CONF_ENCRYPTION_METHOD, DOMAIN

from .conftest import (
    CONFIG_HOST_MARKER,
    CONFIG_PASSWORD_MARKER,
    CONFIG_USERNAME_MARKER,
    GATEWAY_MAC_MARKER,
    GATEWAY_SERIAL_MARKER,
)


async def _configure_user_flow(
    hass: HomeAssistant,
    user_input: dict[str, Any],
) -> dict[str, Any]:
    """Start and submit a user config flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )


@pytest.mark.asyncio
async def test_user_form(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """The initial user step must show the setup form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


@pytest.mark.asyncio
async def test_user_flow_creates_entry_with_validated_data(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    flow_user_input: dict[str, Any],
    gateway: DeviceInfo,
    sagemcom_client: Mock,
) -> None:
    """Successful setup must use normalized data from gateway validation."""
    sagemcom_client.get_encryption_method.return_value = EncryptionMethod.MD5
    sagemcom_client.get_device_info.return_value = gateway

    with (
        patch(
            "custom_components.sagemcom_fast.config_flow.SagemcomClient",
            return_value=sagemcom_client,
        ) as client_class,
        patch(
            "custom_components.sagemcom_fast.async_setup_entry",
            new=AsyncMock(return_value=True),
        ),
    ):
        result = await _configure_user_flow(hass, flow_user_input)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == CONFIG_HOST_MARKER
    assert result["data"] == {
        **flow_user_input,
        CONF_ENCRYPTION_METHOD: EncryptionMethod.MD5,
    }
    assert result["result"].unique_id == CONFIG_HOST_MARKER
    client_class.assert_called_once_with(
        host=CONFIG_HOST_MARKER,
        username=CONFIG_USERNAME_MARKER,
        password=CONFIG_PASSWORD_MARKER,
        session=ANY,
        ssl=True,
    )
    sagemcom_client.login.assert_awaited_once_with()
    sagemcom_client.get_device_info.assert_awaited_once_with()
    sagemcom_client.logout.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_error"),
    [
        (AccessRestrictionException("restricted"), "access_restricted"),
        (AuthenticationException("invalid credentials"), "invalid_auth"),
        (TimeoutError("timed out"), "cannot_connect"),
        (ClientError("client error"), "cannot_connect"),
        (ConnectionError("offline"), "cannot_connect"),
        (LoginConnectionException("login connection failed"), "cannot_connect"),
        (LoginTimeoutException("login timed out"), "login_timeout"),
        (MaximumSessionCountException("sessions exhausted"), "maximum_session_count"),
        (LoginRetryErrorException("retry later"), "login_retry_error"),
        (RuntimeError("unexpected"), "unknown"),
    ],
)
async def test_user_flow_maps_login_errors(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    flow_user_input: dict[str, Any],
    sagemcom_client: Mock,
    error: Exception,
    expected_error: str,
) -> None:
    """Login failures must return the matching user-facing form error."""
    sagemcom_client.get_encryption_method.return_value = EncryptionMethod.MD5
    sagemcom_client.login.side_effect = error

    with patch(
        "custom_components.sagemcom_fast.config_flow.SagemcomClient",
        return_value=sagemcom_client,
    ):
        result = await _configure_user_flow(hass, flow_user_input)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": expected_error}
    sagemcom_client.get_device_info.assert_not_awaited()
    sagemcom_client.logout.assert_not_awaited()


@pytest.mark.asyncio
async def test_user_flow_maps_unsupported_host(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    flow_user_input: dict[str, Any],
    sagemcom_client: Mock,
) -> None:
    """Endpoint probing failure must return the unsupported-host error."""
    sagemcom_client.get_encryption_method.side_effect = UnsupportedHostException(
        "unsupported"
    )

    with patch(
        "custom_components.sagemcom_fast.config_flow.SagemcomClient",
        return_value=sagemcom_client,
    ):
        result = await _configure_user_flow(hass, flow_user_input)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "unsupported_host"}
    sagemcom_client.login.assert_not_awaited()
    sagemcom_client.logout.assert_not_awaited()


@pytest.mark.asyncio
async def test_user_flow_logs_out_when_gateway_info_fails(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    flow_user_input: dict[str, Any],
    sagemcom_client: Mock,
) -> None:
    """Gateway metadata failure must not leak an authenticated session."""
    sagemcom_client.get_encryption_method.return_value = EncryptionMethod.MD5
    sagemcom_client.get_device_info.side_effect = RuntimeError("gateway info failed")

    with patch(
        "custom_components.sagemcom_fast.config_flow.SagemcomClient",
        return_value=sagemcom_client,
    ):
        result = await _configure_user_flow(hass, flow_user_input)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "unknown"}
    sagemcom_client.login.assert_awaited_once_with()
    sagemcom_client.logout.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_validation_result_contains_gateway_identity(
    hass: HomeAssistant,
    flow_user_input: dict[str, Any],
    gateway: DeviceInfo,
    sagemcom_client: Mock,
) -> None:
    """Validation must return typed data and stable gateway identity."""
    sagemcom_client.get_encryption_method.return_value = EncryptionMethod.MD5
    sagemcom_client.get_device_info.return_value = gateway
    original_input = flow_user_input.copy()

    with patch(
        "custom_components.sagemcom_fast.config_flow.SagemcomClient",
        return_value=sagemcom_client,
    ):
        result = await config_flow.async_validate_input(hass, flow_user_input)

    assert result.title == CONFIG_HOST_MARKER
    assert result.data == {
        **flow_user_input,
        CONF_ENCRYPTION_METHOD: EncryptionMethod.MD5,
    }
    assert result.serial_number == GATEWAY_SERIAL_MARKER
    assert result.mac_address == GATEWAY_MAC_MARKER
    assert flow_user_input == original_input


@pytest.mark.asyncio
async def test_validation_result_normalizes_optional_credentials(
    hass: HomeAssistant,
    flow_user_input: dict[str, Any],
    gateway: DeviceInfo,
    sagemcom_client: Mock,
) -> None:
    """Validation must persist the credential defaults used by runtime setup."""
    flow_user_input.pop(CONF_USERNAME)
    flow_user_input.pop(CONF_PASSWORD)
    sagemcom_client.get_encryption_method.return_value = EncryptionMethod.MD5
    sagemcom_client.get_device_info.return_value = gateway

    with patch(
        "custom_components.sagemcom_fast.config_flow.SagemcomClient",
        return_value=sagemcom_client,
    ) as client_class:
        result = await config_flow.async_validate_input(hass, flow_user_input)

    assert result.data[CONF_USERNAME] == ""
    assert result.data[CONF_PASSWORD] == ""
    client_class.assert_called_once_with(
        host=CONFIG_HOST_MARKER,
        username="",
        password="",
        session=ANY,
        ssl=True,
    )
