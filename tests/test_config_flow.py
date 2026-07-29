"""Tests for the Sagemcom F@st config flow."""

from dataclasses import replace
from typing import Any
from unittest.mock import ANY, AsyncMock, Mock, patch

from aiohttp import ClientError
from homeassistant.config_entries import SOURCE_USER
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


async def _start_reauth_flow(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> dict[str, Any]:
    """Start reauthentication through the linked config entry API."""
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry,
        unique_id="mac:02:00:5e:30:00:03",
    )
    config_entry.async_start_reauth(hass)
    await hass.async_block_till_done()

    [progress] = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    return await hass.config_entries.flow.async_configure(progress["flow_id"])


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
async def test_user_flow_creates_entry_with_validated_data_and_stable_identity(
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
    assert result["result"].unique_id == "mac:02:00:5e:30:00:03"
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


@pytest.mark.parametrize(
    ("serial_number", "mac_address", "expected_unique_id"),
    [
        (
            GATEWAY_SERIAL_MARKER,
            "02-00-5E-30-00-03",
            "mac:02:00:5e:30:00:03",
        ),
        (GATEWAY_SERIAL_MARKER, "", f"serial:{GATEWAY_SERIAL_MARKER}"),
        ("02:00:5e:30:00:03", "", "serial:02:00:5e:30:00:03"),
        ("  ", "  ", None),
    ],
)
def test_gateway_identity_precedence_and_normalization(
    serial_number: str | None,
    mac_address: str | None,
    expected_unique_id: str | None,
) -> None:
    """Gateway identity must prefer normalized MAC without namespace collisions."""
    assert (
        config_flow.gateway_unique_id(
            serial_number=serial_number,
            mac_address=mac_address,
        )
        == expected_unique_id
    )


@pytest.mark.asyncio
async def test_user_flow_uses_serial_identity_fallback(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    flow_user_input: dict[str, Any],
    gateway: DeviceInfo,
    sagemcom_client: Mock,
) -> None:
    """A non-empty serial must identify a gateway without a reported MAC."""
    sagemcom_client.get_encryption_method.return_value = EncryptionMethod.MD5
    sagemcom_client.get_device_info.return_value = replace(gateway, mac_address="")

    with (
        patch(
            "custom_components.sagemcom_fast.config_flow.SagemcomClient",
            return_value=sagemcom_client,
        ),
        patch(
            "custom_components.sagemcom_fast.async_setup_entry",
            new=AsyncMock(return_value=True),
        ),
    ):
        result = await _configure_user_flow(hass, flow_user_input)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == f"serial:{GATEWAY_SERIAL_MARKER}"


@pytest.mark.asyncio
async def test_user_flow_rejects_missing_gateway_identity(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    flow_user_input: dict[str, Any],
    gateway: DeviceInfo,
    sagemcom_client: Mock,
) -> None:
    """Setup must not create an entry without a proven physical identity."""
    sagemcom_client.get_encryption_method.return_value = EncryptionMethod.MD5
    sagemcom_client.get_device_info.return_value = replace(
        gateway,
        mac_address="",
        serial_number=None,
    )

    with (
        patch(
            "custom_components.sagemcom_fast.config_flow.SagemcomClient",
            return_value=sagemcom_client,
        ),
        patch(
            "custom_components.sagemcom_fast.async_setup_entry",
            new=AsyncMock(return_value=True),
        ),
    ):
        result = await _configure_user_flow(hass, flow_user_input)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "unknown"}
    assert hass.config_entries.async_entries(DOMAIN) == []
    sagemcom_client.logout.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "submitted_host",
    [
        "existing-host-marker.example.invalid",
        "changed-host-marker.example.invalid",
    ],
)
async def test_manual_duplicate_identity_aborts_without_host_mutation(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    flow_user_input: dict[str, Any],
    gateway: DeviceInfo,
    sagemcom_client: Mock,
    submitted_host: str,
) -> None:
    """Manual setup must not duplicate or relocate an existing router entry."""
    existing_host = "existing-host-marker.example.invalid"
    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="mac:02:00:5e:30:00:03",
        data={**flow_user_input, CONF_HOST: existing_host},
    )
    existing_entry.add_to_hass(hass)
    flow_user_input[CONF_HOST] = submitted_host
    sagemcom_client.get_encryption_method.return_value = EncryptionMethod.MD5
    sagemcom_client.get_device_info.return_value = gateway

    with (
        patch(
            "custom_components.sagemcom_fast.config_flow.SagemcomClient",
            return_value=sagemcom_client,
        ),
        patch(
            "custom_components.sagemcom_fast.async_setup_entry",
            new=AsyncMock(return_value=True),
        ),
    ):
        result = await _configure_user_flow(hass, flow_user_input)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert existing_entry.data[CONF_HOST] == existing_host
    assert hass.config_entries.async_entries(DOMAIN) == [existing_entry]


@pytest.mark.asyncio
async def test_distinct_gateway_identity_values_create_distinct_entries(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    flow_user_input: dict[str, Any],
    gateway: DeviceInfo,
    sagemcom_client: Mock,
) -> None:
    """A configured router must not block setup of a different router."""
    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="mac:02:00:5e:40:00:04",
        data={**flow_user_input, CONF_HOST: "other-host-marker.example.invalid"},
    )
    existing_entry.add_to_hass(hass)
    sagemcom_client.get_encryption_method.return_value = EncryptionMethod.MD5
    sagemcom_client.get_device_info.return_value = gateway

    with (
        patch(
            "custom_components.sagemcom_fast.config_flow.SagemcomClient",
            return_value=sagemcom_client,
        ),
        patch(
            "custom_components.sagemcom_fast.async_setup_entry",
            new=AsyncMock(return_value=True),
        ),
    ):
        result = await _configure_user_flow(hass, flow_user_input)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "mac:02:00:5e:30:00:03"
    assert {entry.unique_id for entry in hass.config_entries.async_entries(DOMAIN)} == {
        "mac:02:00:5e:30:00:03",
        "mac:02:00:5e:40:00:04",
    }


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


@pytest.mark.asyncio
async def test_reauth_shows_linked_confirmation_form(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    config_entry: MockConfigEntry,
) -> None:
    """A config entry must start a credential-only reauthentication form."""
    result = await _start_reauth_flow(hass, config_entry)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {}
    assert set(result["data_schema"].schema) == {CONF_USERNAME, CONF_PASSWORD}
    [progress] = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert progress["context"]["entry_id"] == config_entry.entry_id


@pytest.mark.asyncio
async def test_reauth_rejects_invalid_credentials_without_mutating_entry(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    config_entry: MockConfigEntry,
    sagemcom_client: Mock,
) -> None:
    """Invalid replacement credentials must leave the linked entry untouched."""
    original_data = dict(config_entry.data)
    original_options = dict(config_entry.options)
    sagemcom_client.get_encryption_method.return_value = EncryptionMethod.SHA512
    sagemcom_client.login.side_effect = AuthenticationException(
        "invalid credentials"
    )

    result = await _start_reauth_flow(hass, config_entry)
    with (
        patch(
            "custom_components.sagemcom_fast.config_flow.SagemcomClient",
            return_value=sagemcom_client,
        ),
        patch.object(
            hass.config_entries,
            "async_reload",
            new=AsyncMock(return_value=True),
        ) as async_reload,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "replacement-user",
                CONF_PASSWORD: "replacement-password",
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "invalid_auth"}
    assert config_entry.data == original_data
    assert config_entry.options == original_options
    async_reload.assert_not_awaited()
    sagemcom_client.get_device_info.assert_not_awaited()
    sagemcom_client.logout.assert_not_awaited()


@pytest.mark.asyncio
async def test_reauth_reports_connection_failure_without_mutating_entry(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    config_entry: MockConfigEntry,
    sagemcom_client: Mock,
) -> None:
    """Connection failure must keep the existing credentials and connection data."""
    original_data = dict(config_entry.data)
    sagemcom_client.get_encryption_method.return_value = EncryptionMethod.SHA512
    sagemcom_client.login.side_effect = LoginConnectionException("offline")

    result = await _start_reauth_flow(hass, config_entry)
    with (
        patch(
            "custom_components.sagemcom_fast.config_flow.SagemcomClient",
            return_value=sagemcom_client,
        ),
        patch.object(
            hass.config_entries,
            "async_reload",
            new=AsyncMock(return_value=True),
        ) as async_reload,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "replacement-user",
                CONF_PASSWORD: "replacement-password",
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "cannot_connect"}
    assert config_entry.data == original_data
    async_reload.assert_not_awaited()
    sagemcom_client.logout.assert_not_awaited()


@pytest.mark.asyncio
async def test_reauth_updates_only_credentials_and_encryption_then_reloads_once(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    config_entry: MockConfigEntry,
    gateway: DeviceInfo,
    sagemcom_client: Mock,
) -> None:
    """Successful reauthentication must preserve entry identity and connection data."""
    original_entry_id = config_entry.entry_id
    original_title = config_entry.title
    original_options = dict(config_entry.options)
    original_version = config_entry.version
    original_minor_version = config_entry.minor_version
    new_credentials = {
        CONF_USERNAME: "replacement-user",
        CONF_PASSWORD: "replacement-password",
    }
    sagemcom_client.get_encryption_method.return_value = EncryptionMethod.SHA512
    sagemcom_client.get_device_info.return_value = gateway

    result = await _start_reauth_flow(hass, config_entry)
    with (
        patch(
            "custom_components.sagemcom_fast.config_flow.SagemcomClient",
            return_value=sagemcom_client,
        ) as client_class,
        patch.object(
            hass.config_entries,
            "async_reload",
            new=AsyncMock(return_value=True),
        ) as async_reload,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            new_credentials,
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.entry_id == original_entry_id
    assert config_entry.title == original_title
    assert config_entry.unique_id == "mac:02:00:5e:30:00:03"
    assert config_entry.version == original_version
    assert config_entry.minor_version == original_minor_version
    assert config_entry.options == original_options
    assert config_entry.data == {
        CONF_HOST: CONFIG_HOST_MARKER,
        **new_credentials,
        CONF_SSL: True,
        CONF_VERIFY_SSL: True,
        CONF_ENCRYPTION_METHOD: EncryptionMethod.SHA512,
    }
    assert hass.config_entries.async_entries(DOMAIN) == [config_entry]
    client_class.assert_called_once_with(
        host=CONFIG_HOST_MARKER,
        username="replacement-user",
        password="replacement-password",
        session=ANY,
        ssl=True,
    )
    async_reload.assert_awaited_once_with(config_entry.entry_id)
    sagemcom_client.logout.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_reauth_rejects_valid_credentials_for_a_different_router(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    config_entry: MockConfigEntry,
    gateway: DeviceInfo,
    sagemcom_client: Mock,
) -> None:
    """Reauthentication must not switch an entry to a different physical router."""
    original_data = dict(config_entry.data)
    sagemcom_client.get_encryption_method.return_value = EncryptionMethod.SHA512
    sagemcom_client.get_device_info.return_value = replace(
        gateway,
        mac_address="02:00:5E:40:00:04",
    )

    result = await _start_reauth_flow(hass, config_entry)
    with (
        patch(
            "custom_components.sagemcom_fast.config_flow.SagemcomClient",
            return_value=sagemcom_client,
        ),
        patch.object(
            hass.config_entries,
            "async_reload",
            new=AsyncMock(return_value=True),
        ) as async_reload,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "replacement-user",
                CONF_PASSWORD: "replacement-password",
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
    assert config_entry.data == original_data
    assert config_entry.unique_id == "mac:02:00:5e:30:00:03"
    assert hass.config_entries.async_entries(DOMAIN) == [config_entry]
    async_reload.assert_not_awaited()
    sagemcom_client.logout.assert_awaited_once_with()
