"""Shared fixtures for Sagemcom F@st diagnostics tests."""

from unittest.mock import AsyncMock, Mock

from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from sagemcom_api.client import SagemcomClient
from sagemcom_api.models import Device, DeviceInfo

from custom_components.sagemcom_fast import HomeAssistantSagemcomFastData
from custom_components.sagemcom_fast.const import CONF_ENCRYPTION_METHOD, DOMAIN
from custom_components.sagemcom_fast.coordinator import SagemcomDataUpdateCoordinator

SENSITIVE_MARKERS = (
    "gateway.example.invalid",
    "diagnostics-user-marker",
    "diagnostics-password-marker",
    "https://gateway.example.invalid/management",
)


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a realistic Sagemcom F@st configuration entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id="diagnostics-entry-id",
        title="Sagemcom F@st gateway",
        data={
            CONF_HOST: SENSITIVE_MARKERS[0],
            CONF_USERNAME: SENSITIVE_MARKERS[1],
            CONF_PASSWORD: SENSITIVE_MARKERS[2],
            CONF_SSL: True,
            CONF_VERIFY_SSL: True,
            CONF_ENCRYPTION_METHOD: "AES",
        },
        options={CONF_SCAN_INTERVAL: 30},
    )


@pytest.fixture
def sagemcom_client() -> Mock:
    """Return the network client without permitting diagnostics I/O."""
    client = Mock(spec=SagemcomClient)
    client.login = AsyncMock()
    client.logout = AsyncMock()
    client.get_value_by_xpath = AsyncMock(
        return_value={
            "ManagementServer": {"URL": SENSITIVE_MARKERS[3]},
            "Device": {
                "Host": SENSITIVE_MARKERS[0],
                "Password": SENSITIVE_MARKERS[2],
                "Username": SENSITIVE_MARKERS[1],
            },
        }
    )
    return client


@pytest.fixture
def coordinator(sagemcom_client: Mock) -> Mock:
    """Return current coordinator data for one active and one known client."""
    coordinator = Mock(spec=SagemcomDataUpdateCoordinator)
    coordinator.client = sagemcom_client
    coordinator.hosts = {
        "AA:BB:CC:DD:EE:01": Device(
            uid=1,
            alias="Laptop",
            phys_address="AA:BB:CC:DD:EE:01",
            ip_address="192.0.2.10",
            address_source="DHCP",
            dhcp_client="Laptop",
            lease_time_remaining=1800,
            associated_device=None,
            layer1_interface="WiFi",
            layer3_interface="IP",
            vendor_class_id=None,
            client_id=None,
            user_class_id=None,
            host_name="laptop",
            active=True,
            lease_start=1_700_000_000,
            lease_duration=3600,
            interface_type="WiFi",
            detected_device_type="Computer",
            active_last_change=1_700_000_000,
            user_friendly_name="Laptop",
            user_host_name="Laptop",
            user_device_type="Computer",
            icon=None,
            room=None,
            blacklist_enable=False,
            blacklisted=False,
            unblock_hours_count=0,
            blacklist_status=False,
            blacklisted_according_to_schedule=False,
            blacklisted_schedule=[],
            hidden=False,
            options=[],
            vendor_class_idv6=None,
            ipv4_addresses=["192.0.2.10"],
            ipv6_addresses=[],
            device_type_association=None,
        ),
        "AA:BB:CC:DD:EE:02": Device(
            uid=2,
            alias="Phone",
            phys_address="AA:BB:CC:DD:EE:02",
            ip_address="192.0.2.11",
            address_source="DHCP",
            dhcp_client="Phone",
            lease_time_remaining=0,
            associated_device=None,
            layer1_interface="WiFi",
            layer3_interface="IP",
            vendor_class_id=None,
            client_id=None,
            user_class_id=None,
            host_name="phone",
            active=False,
            lease_start=1_699_000_000,
            lease_duration=3600,
            interface_type="WiFi",
            detected_device_type="Phone",
            active_last_change=1_699_000_000,
            user_friendly_name="Phone",
            user_host_name="Phone",
            user_device_type="Phone",
            icon=None,
            room=None,
            blacklist_enable=False,
            blacklisted=False,
            unblock_hours_count=0,
            blacklist_status=False,
            blacklisted_according_to_schedule=False,
            blacklisted_schedule=[],
            hidden=False,
            options=[],
            vendor_class_idv6=None,
            ipv4_addresses=["192.0.2.11"],
            ipv6_addresses=[],
            device_type_association=None,
        ),
    }
    return coordinator


@pytest.fixture
def gateway() -> DeviceInfo:
    """Return the gateway metadata retained after integration setup."""
    return DeviceInfo(
        mac_address="AA:BB:CC:DD:EE:FF",
        serial_number="SF5366TN-123456789",
        manufacturer="Sagemcom",
        model_name="F@st 5366 TN",
        model_number="5366TN",
        software_version="8.22.1",
        hardware_version="1.0",
        bootloader_version="1.2",
        device_category="InternetGatewayDevice",
        manufacturer_oui="AABBCC",
        product_class="SagemcomFst5366",
        description="Sagemcom F@st gateway",
        additional_hardware_version="1.0",
        additional_software_version="8.22.1",
        external_firmware_version="8.22.1",
        internal_firmware_version="8.22.1",
        gui_firmware_version="8.22.1",
        guiapi_version=1.0,
        provisioning_code="diagnostics-provisioning-marker",
        up_time=86_400,
        first_use_date="2024-01-01",
        mode="router",
        country="NL",
        reboot_count=1,
        nodes_to_restore="",
        router_name="Sagemcom F@st gateway",
        reboot_status=0.0,
        reset_status=0.0,
        update_status=0.0,
        SNMP=False,
        first_connection=False,
        build_date="2024-01-01",
        spec_version="1.0",
        CLID="clid",
        flush_device_log=False,
        locations="NL",
        api_version="1.0",
    )


@pytest.fixture
def loaded_entry(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    coordinator: Mock,
    gateway: DeviceInfo,
) -> MockConfigEntry:
    """Load the current integration runtime-data shape into Home Assistant."""
    config_entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = (
        HomeAssistantSagemcomFastData(coordinator=coordinator, gateway=gateway)
    )
    return config_entry
