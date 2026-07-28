"""Tests for Sagemcom F@st config entry migration."""

from dataclasses import replace
from typing import Any
from unittest.mock import Mock, patch

from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from sagemcom_api.enums import EncryptionMethod
from sagemcom_api.exceptions import AuthenticationException, LoginConnectionException
from sagemcom_api.models import DeviceInfo

from custom_components.sagemcom_fast import config_flow
from custom_components.sagemcom_fast.const import CONF_ENCRYPTION_METHOD

from .conftest import CONFIG_HOST_MARKER


@pytest.fixture
def legacy_entry(
    hass: HomeAssistant,
    flow_user_input: dict[str, Any],
) -> MockConfigEntry:
    """Return a version-1 entry identified by its connection host."""
    entry = MockConfigEntry(
        domain=config_flow.DOMAIN,
        entry_id="legacy-entry-id",
        title="Living room gateway",
        unique_id=CONFIG_HOST_MARKER,
        version=1,
        minor_version=1,
        data={
            **flow_user_input,
            CONF_ENCRYPTION_METHOD: EncryptionMethod.MD5,
        },
        options={CONF_SCAN_INTERVAL: 45},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def registry_entries(
    hass: HomeAssistant,
    legacy_entry: MockConfigEntry,
) -> tuple[dr.DeviceEntry, er.RegistryEntry]:
    """Return customized registries owned by the legacy config entry."""
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=legacy_entry.entry_id,
        identifiers={(config_flow.DOMAIN, "legacy-gateway-device")},
        manufacturer="Sagemcom",
        name="Gateway",
    )
    device = device_registry.async_update_device(
        device.id,
        name_by_user="Downstairs router",
    )
    assert device is not None

    entity_registry = er.async_get(hass)
    entity = entity_registry.async_get_or_create(
        "sensor",
        config_flow.DOMAIN,
        "legacy-entity-unique-id",
        config_entry=legacy_entry,
        device_id=device.id,
        original_name="Gateway status",
    )
    entity = entity_registry.async_update_entity(
        entity.entity_id,
        icon="mdi:router-wireless",
        name="Router health",
    )

    return device, entity


def _entry_state(entry: MockConfigEntry) -> dict[str, Any]:
    """Capture all config-entry fields migration is allowed to affect."""
    return {
        "entry_id": entry.entry_id,
        "title": entry.title,
        "unique_id": entry.unique_id,
        "version": entry.version,
        "minor_version": entry.minor_version,
        "data": dict(entry.data),
        "options": dict(entry.options),
    }


def _assert_registry_ownership(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    expected_device: dr.DeviceEntry,
    expected_entity: er.RegistryEntry,
) -> None:
    """Assert registry IDs, ownership, and user customization are unchanged."""
    device = dr.async_get(hass).async_get(expected_device.id)
    assert device is not None
    assert device.id == expected_device.id
    assert device.config_entries == {entry.entry_id}
    assert device.name_by_user == "Downstairs router"

    entity = er.async_get(hass).async_get(expected_entity.entity_id)
    assert entity is not None
    assert entity.entity_id == expected_entity.entity_id
    assert entity.unique_id == "legacy-entity-unique-id"
    assert entity.config_entry_id == entry.entry_id
    assert entity.device_id == device.id
    assert entity.name == "Router health"
    assert entity.icon == "mdi:router-wireless"


@pytest.mark.asyncio
async def test_migration_preserves_entry_and_registry_ownership(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    legacy_entry: MockConfigEntry,
    registry_entries: tuple[dr.DeviceEntry, er.RegistryEntry],
    gateway: DeviceInfo,
    sagemcom_client: Mock,
) -> None:
    """Migration must change only version metadata and authenticated identity."""
    original_state = _entry_state(legacy_entry)
    sagemcom_client.get_encryption_method.return_value = EncryptionMethod.MD5
    sagemcom_client.get_device_info.return_value = gateway

    with patch(
        "custom_components.sagemcom_fast.config_flow.SagemcomClient",
        return_value=sagemcom_client,
    ):
        result = await legacy_entry.async_migrate(hass)

    assert result is True
    assert hass.config_entries.async_get_entry(legacy_entry.entry_id) is legacy_entry
    assert legacy_entry.entry_id == original_state["entry_id"]
    assert legacy_entry.title == original_state["title"]
    assert legacy_entry.data == original_state["data"]
    assert legacy_entry.options == original_state["options"]
    assert legacy_entry.version == 2
    assert legacy_entry.minor_version == 1
    assert legacy_entry.unique_id == "mac:02:00:5e:30:00:03"
    _assert_registry_ownership(hass, legacy_entry, *registry_entries)
    sagemcom_client.logout.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        LoginConnectionException("gateway offline"),
        AuthenticationException("credentials rejected"),
    ],
)
async def test_migration_login_failure_is_atomic(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    legacy_entry: MockConfigEntry,
    registry_entries: tuple[dr.DeviceEntry, er.RegistryEntry],
    sagemcom_client: Mock,
    error: Exception,
) -> None:
    """Connection and authentication failures must leave the entry untouched."""
    original_state = _entry_state(legacy_entry)
    sagemcom_client.get_encryption_method.return_value = EncryptionMethod.MD5
    sagemcom_client.login.side_effect = error

    with patch(
        "custom_components.sagemcom_fast.config_flow.SagemcomClient",
        return_value=sagemcom_client,
    ):
        result = await legacy_entry.async_migrate(hass)

    assert result is False
    assert _entry_state(legacy_entry) == original_state
    assert hass.config_entries.async_entries(config_flow.DOMAIN) == [legacy_entry]
    _assert_registry_ownership(hass, legacy_entry, *registry_entries)
    sagemcom_client.logout.assert_not_awaited()


@pytest.mark.asyncio
async def test_migration_authenticated_failure_logs_out_without_mutation(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    legacy_entry: MockConfigEntry,
    registry_entries: tuple[dr.DeviceEntry, er.RegistryEntry],
    sagemcom_client: Mock,
) -> None:
    """Failure after login must log out and leave the entry untouched."""
    original_state = _entry_state(legacy_entry)
    sagemcom_client.get_encryption_method.return_value = EncryptionMethod.MD5
    sagemcom_client.get_device_info.side_effect = TimeoutError("gateway timed out")

    with patch(
        "custom_components.sagemcom_fast.config_flow.SagemcomClient",
        return_value=sagemcom_client,
    ):
        result = await legacy_entry.async_migrate(hass)

    assert result is False
    assert _entry_state(legacy_entry) == original_state
    _assert_registry_ownership(hass, legacy_entry, *registry_entries)
    sagemcom_client.logout.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_migration_missing_stable_identity_is_atomic(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    legacy_entry: MockConfigEntry,
    registry_entries: tuple[dr.DeviceEntry, er.RegistryEntry],
    gateway: DeviceInfo,
    sagemcom_client: Mock,
) -> None:
    """Migration must reject a gateway without an authenticated stable identity."""
    original_state = _entry_state(legacy_entry)
    sagemcom_client.get_encryption_method.return_value = EncryptionMethod.MD5
    sagemcom_client.get_device_info.return_value = replace(
        gateway,
        mac_address="",
        serial_number=None,
    )

    with patch(
        "custom_components.sagemcom_fast.config_flow.SagemcomClient",
        return_value=sagemcom_client,
    ):
        result = await legacy_entry.async_migrate(hass)

    assert result is False
    assert _entry_state(legacy_entry) == original_state
    _assert_registry_ownership(hass, legacy_entry, *registry_entries)
    sagemcom_client.logout.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_migration_identity_collision_is_atomic(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    legacy_entry: MockConfigEntry,
    registry_entries: tuple[dr.DeviceEntry, er.RegistryEntry],
    flow_user_input: dict[str, Any],
    gateway: DeviceInfo,
    sagemcom_client: Mock,
) -> None:
    """Migration must never overwrite or merge another identity owner."""
    target_owner = MockConfigEntry(
        domain=config_flow.DOMAIN,
        entry_id="stable-entry-id",
        title="Existing stable gateway",
        unique_id="mac:02:00:5e:30:00:03",
        version=2,
        minor_version=1,
        data={**flow_user_input, CONF_HOST: "other-gateway.example.invalid"},
        options={CONF_SCAN_INTERVAL: 60},
    )
    target_owner.add_to_hass(hass)
    original_legacy_state = _entry_state(legacy_entry)
    original_owner_state = _entry_state(target_owner)
    sagemcom_client.get_encryption_method.return_value = EncryptionMethod.MD5
    sagemcom_client.get_device_info.return_value = gateway

    with patch(
        "custom_components.sagemcom_fast.config_flow.SagemcomClient",
        return_value=sagemcom_client,
    ):
        result = await legacy_entry.async_migrate(hass)

    assert result is False
    assert _entry_state(legacy_entry) == original_legacy_state
    assert _entry_state(target_owner) == original_owner_state
    assert hass.config_entries.async_entries(config_flow.DOMAIN) == [
        legacy_entry,
        target_owner,
    ]
    _assert_registry_ownership(hass, legacy_entry, *registry_entries)
    sagemcom_client.logout.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_migration_uses_serial_identity_fallback(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    legacy_entry: MockConfigEntry,
    gateway: DeviceInfo,
    sagemcom_client: Mock,
) -> None:
    """Migration must support gateways that report only a stable serial."""
    sagemcom_client.get_encryption_method.return_value = EncryptionMethod.MD5
    sagemcom_client.get_device_info.return_value = replace(gateway, mac_address="")

    with patch(
        "custom_components.sagemcom_fast.config_flow.SagemcomClient",
        return_value=sagemcom_client,
    ):
        result = await legacy_entry.async_migrate(hass)

    assert result is True
    assert legacy_entry.version == 2
    assert (
        legacy_entry.unique_id
        == "serial:DIAGNOSTICS-GATEWAY-SERIAL-MARKER"
    )
