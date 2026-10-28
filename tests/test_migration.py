"""Tests for adopting a stable router identity on legacy config entries."""

from collections.abc import Iterator
from dataclasses import replace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from sagemcom_api.enums import EncryptionMethod
from sagemcom_api.exceptions import AuthenticationException, LoginConnectionException
from sagemcom_api.models import DeviceInfo

from custom_components.sagemcom_fast import config_flow
from custom_components.sagemcom_fast.const import (
    CONF_ENCRYPTION_METHOD,
    CONFIG_ENTRY_MINOR_VERSION,
    DOMAIN,
)

from .conftest import CONFIG_HOST_MARKER

STABLE_UNIQUE_ID = "mac:02:00:5e:30:00:03"


@pytest.fixture
def legacy_entry(
    hass: HomeAssistant,
    flow_user_input: dict[str, Any],
) -> MockConfigEntry:
    """Return an entry created by a release that used the host as unique ID."""
    entry = MockConfigEntry(
        domain=DOMAIN,
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
        identifiers={(DOMAIN, "legacy-gateway-device")},
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
        "device_tracker",
        DOMAIN,
        "legacy-entity-unique-id",
        config_entry=legacy_entry,
        device_id=device.id,
        original_name="Phone",
    )
    entity = entity_registry.async_update_entity(
        entity.entity_id,
        icon="mdi:cellphone",
        name="My phone",
    )

    return device, entity


@pytest.fixture
def patched_gateway(
    sagemcom_client: Mock, gateway: DeviceInfo
) -> Iterator[Mock]:
    """Route setup and config flows to the mocked gateway client."""
    sagemcom_client.get_encryption_method.return_value = EncryptionMethod.MD5
    sagemcom_client.get_device_info.return_value = gateway
    sagemcom_client.get_hosts.return_value = []
    with (
        patch(
            "custom_components.sagemcom_fast.SagemcomClient",
            return_value=sagemcom_client,
        ),
        patch(
            "custom_components.sagemcom_fast.config_flow.SagemcomClient",
            return_value=sagemcom_client,
        ),
        patch(
            "custom_components.sagemcom_fast.coordinator.asyncio.sleep",
            new=AsyncMock(),
        ),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            new=AsyncMock(),
        ),
    ):
        yield sagemcom_client


def _entry_state(entry: MockConfigEntry) -> dict[str, Any]:
    """Capture the config entry fields identity adoption may affect."""
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
    assert device.config_entry_id == entry.entry_id
    assert device.name_by_user == "Downstairs router"

    entity = er.async_get(hass).async_get(expected_entity.entity_id)
    assert entity is not None
    assert entity.unique_id == "legacy-entity-unique-id"
    assert entity.config_entry_id == entry.entry_id
    assert entity.device_id == device.id
    assert entity.name == "My phone"
    assert entity.icon == "mdi:cellphone"


def test_config_entry_major_version_is_downgrade_safe() -> None:
    """Earlier releases reject entries whose major version exceeds theirs."""
    assert config_flow.ConfigFlow.VERSION == 1


async def test_setup_adopts_gateway_identity(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    legacy_entry: MockConfigEntry,
    registry_entries: tuple[dr.DeviceEntry, er.RegistryEntry],
    patched_gateway: Mock,
) -> None:
    """Setup must change only the unique ID and minor version."""
    original_state = _entry_state(legacy_entry)

    assert await hass.config_entries.async_setup(legacy_entry.entry_id)

    assert legacy_entry.state is ConfigEntryState.LOADED
    assert _entry_state(legacy_entry) == {
        **original_state,
        "unique_id": STABLE_UNIQUE_ID,
        "minor_version": CONFIG_ENTRY_MINOR_VERSION,
    }
    _assert_registry_ownership(hass, legacy_entry, *registry_entries)


async def test_unreachable_router_retries_and_adopts_identity_later(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    legacy_entry: MockConfigEntry,
    registry_entries: tuple[dr.DeviceEntry, er.RegistryEntry],
    patched_gateway: Mock,
) -> None:
    """An offline router at startup must not leave the entry permanently failed."""
    original_state = _entry_state(legacy_entry)
    patched_gateway.login.side_effect = LoginConnectionException("router offline")

    assert not await hass.config_entries.async_setup(legacy_entry.entry_id)

    assert legacy_entry.state is ConfigEntryState.SETUP_RETRY
    assert _entry_state(legacy_entry) == original_state

    patched_gateway.login.side_effect = None
    assert await hass.config_entries.async_reload(legacy_entry.entry_id)

    assert legacy_entry.state is ConfigEntryState.LOADED
    assert legacy_entry.unique_id == STABLE_UNIQUE_ID
    _assert_registry_ownership(hass, legacy_entry, *registry_entries)


async def test_rejected_credentials_can_be_fixed_by_reauth(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    legacy_entry: MockConfigEntry,
    patched_gateway: Mock,
) -> None:
    """Reauth must accept a legacy entry whose unique ID is still its host."""
    patched_gateway.login.side_effect = AuthenticationException("rejected")

    assert not await hass.config_entries.async_setup(legacy_entry.entry_id)
    await hass.async_block_till_done()

    assert legacy_entry.state is ConfigEntryState.SETUP_ERROR
    [flow] = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flow["context"]["source"] == SOURCE_REAUTH

    patched_gateway.login.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {CONF_USERNAME: "replacement-user", CONF_PASSWORD: "replacement-password"},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert legacy_entry.state is ConfigEntryState.LOADED
    assert legacy_entry.data[CONF_USERNAME] == "replacement-user"
    assert legacy_entry.unique_id == STABLE_UNIQUE_ID


async def test_identity_owned_by_another_entry_keeps_legacy_identity(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    legacy_entry: MockConfigEntry,
    registry_entries: tuple[dr.DeviceEntry, er.RegistryEntry],
    flow_user_input: dict[str, Any],
    patched_gateway: Mock,
) -> None:
    """A duplicate entry for the same router must keep working unchanged."""
    owner = MockConfigEntry(
        domain=DOMAIN,
        entry_id="stable-entry-id",
        unique_id=STABLE_UNIQUE_ID,
        version=1,
        minor_version=CONFIG_ENTRY_MINOR_VERSION,
        data={**flow_user_input, CONF_HOST: "other-host.example.invalid"},
    )
    owner.add_to_hass(hass)
    original_legacy_state = _entry_state(legacy_entry)
    original_owner_state = _entry_state(owner)

    assert await hass.config_entries.async_setup(legacy_entry.entry_id)

    assert legacy_entry.state is ConfigEntryState.LOADED
    assert _entry_state(legacy_entry) == original_legacy_state
    assert _entry_state(owner) == original_owner_state
    _assert_registry_ownership(hass, legacy_entry, *registry_entries)


async def test_serial_identity_fallback(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    legacy_entry: MockConfigEntry,
    gateway: DeviceInfo,
    patched_gateway: Mock,
) -> None:
    """Routers that report only a serial number must still get a stable ID."""
    patched_gateway.get_device_info.return_value = replace(gateway, mac_address="")

    assert await hass.config_entries.async_setup(legacy_entry.entry_id)

    assert legacy_entry.unique_id == "serial:DIAGNOSTICS-GATEWAY-SERIAL-MARKER"
    assert legacy_entry.minor_version == CONFIG_ENTRY_MINOR_VERSION


async def test_missing_identity_keeps_legacy_identity(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    legacy_entry: MockConfigEntry,
    gateway: DeviceInfo,
    patched_gateway: Mock,
) -> None:
    """A router without MAC or serial must keep loading with its host ID."""
    original_state = _entry_state(legacy_entry)
    patched_gateway.get_device_info.return_value = replace(
        gateway, mac_address="", serial_number=""
    )

    assert await hass.config_entries.async_setup(legacy_entry.entry_id)

    assert legacy_entry.state is ConfigEntryState.LOADED
    assert _entry_state(legacy_entry) == original_state
