"""Shared fixtures for Sagemcom F@st diagnostics tests."""

from datetime import timedelta
from typing import Any
from unittest.mock import Mock

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

from custom_components.sagemcom_fast import SagemcomRuntimeData
from custom_components.sagemcom_fast.const import CONF_ENCRYPTION_METHOD, DOMAIN
from custom_components.sagemcom_fast.coordinator import SagemcomDataUpdateCoordinator

CONFIG_HOST_MARKER = "config-host-marker.example.invalid"
CONFIG_USERNAME_MARKER = "diagnostics-username-marker"
CONFIG_PASSWORD_MARKER = "diagnostics-password-marker"
MANAGEMENT_URL_MARKER = "https://management-url-marker.example.invalid/api"
ACTIVE_CLIENT_IP_MARKER = "192.0.2.101"
ACTIVE_CLIENT_MAC_MARKER = "02:00:5E:10:00:01"
KNOWN_CLIENT_IP_MARKER = "192.0.2.202"
KNOWN_CLIENT_MAC_MARKER = "02:00:5E:20:00:02"
GATEWAY_SERIAL_MARKER = "DIAGNOSTICS-GATEWAY-SERIAL-MARKER"
GATEWAY_MAC_MARKER = "02:00:5E:30:00:03"
PROVISIONING_CODE_MARKER = "diagnostics-provisioning-code-marker"
CLID_MARKER = "diagnostics-clid-marker"

SENSITIVE_MARKERS = (
    CONFIG_HOST_MARKER,
    CONFIG_USERNAME_MARKER,
    CONFIG_PASSWORD_MARKER,
    MANAGEMENT_URL_MARKER,
    ACTIVE_CLIENT_IP_MARKER,
    ACTIVE_CLIENT_MAC_MARKER,
    KNOWN_CLIENT_IP_MARKER,
    KNOWN_CLIENT_MAC_MARKER,
    GATEWAY_SERIAL_MARKER,
    GATEWAY_MAC_MARKER,
    PROVISIONING_CODE_MARKER,
    CLID_MARKER,
)


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a realistic Sagemcom F@st configuration entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id="diagnostics-entry-id",
        title="Sagemcom F@st gateway",
        data={
            CONF_HOST: CONFIG_HOST_MARKER,
            CONF_USERNAME: CONFIG_USERNAME_MARKER,
            CONF_PASSWORD: CONFIG_PASSWORD_MARKER,
            CONF_SSL: True,
            CONF_VERIFY_SSL: True,
            CONF_ENCRYPTION_METHOD: "MD5",
        },
        options={CONF_SCAN_INTERVAL: 30},
    )


@pytest.fixture
def flow_user_input() -> dict[str, Any]:
    """Return complete user input for a Sagemcom F@st config flow."""
    return {
        CONF_HOST: CONFIG_HOST_MARKER,
        CONF_USERNAME: CONFIG_USERNAME_MARKER,
        CONF_PASSWORD: CONFIG_PASSWORD_MARKER,
        CONF_SSL: True,
        CONF_VERIFY_SSL: True,
    }


@pytest.fixture
def sagemcom_client() -> Mock:
    """Return the network client without permitting diagnostics I/O."""
    client = Mock(spec=SagemcomClient)
    client.get_value_by_xpath.return_value = {
        "ManagementServer": {"URL": MANAGEMENT_URL_MARKER},
        "Device": {
            "Host": CONFIG_HOST_MARKER,
            "Password": CONFIG_PASSWORD_MARKER,
            "Username": CONFIG_USERNAME_MARKER,
            "Gateway": {
                "CLID": CLID_MARKER,
                "MACAddress": GATEWAY_MAC_MARKER,
                "ProvisioningCode": PROVISIONING_CODE_MARKER,
                "SerialNumber": GATEWAY_SERIAL_MARKER,
            },
            "Hosts": [
                {
                    "IPAddress": ACTIVE_CLIENT_IP_MARKER,
                    "PhysAddress": ACTIVE_CLIENT_MAC_MARKER,
                },
                {
                    "IPAddress": KNOWN_CLIENT_IP_MARKER,
                    "PhysAddress": KNOWN_CLIENT_MAC_MARKER,
                },
            ],
        },
    }
    return client


@pytest.fixture
def coordinator(sagemcom_client: Mock) -> Mock:
    """Return current coordinator data for one active and one known client."""
    coordinator = Mock(spec=SagemcomDataUpdateCoordinator)
    coordinator.client = sagemcom_client
    coordinator.last_update_success = True
    coordinator.update_interval = timedelta(seconds=30)
    coordinator.hosts = {
        ACTIVE_CLIENT_MAC_MARKER: Device(
            uid=1,
            alias="Laptop",
            phys_address=ACTIVE_CLIENT_MAC_MARKER,
            ip_address=ACTIVE_CLIENT_IP_MARKER,
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
            ipv4_addresses=[ACTIVE_CLIENT_IP_MARKER],
            ipv6_addresses=[],
            device_type_association=None,
        ),
        KNOWN_CLIENT_MAC_MARKER: Device(
            uid=2,
            alias="Phone",
            phys_address=KNOWN_CLIENT_MAC_MARKER,
            ip_address=KNOWN_CLIENT_IP_MARKER,
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
            ipv4_addresses=[KNOWN_CLIENT_IP_MARKER],
            ipv6_addresses=[],
            device_type_association=None,
        ),
    }
    return coordinator


@pytest.fixture
def gateway() -> DeviceInfo:
    """Return the gateway metadata retained after integration setup."""
    return DeviceInfo(
        mac_address=GATEWAY_MAC_MARKER,
        serial_number=GATEWAY_SERIAL_MARKER,
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
        provisioning_code=PROVISIONING_CODE_MARKER,
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
        CLID=CLID_MARKER,
        flush_device_log=False,
        locations="NL",
        api_version="1.0",
    )


@pytest.fixture
def loaded_entry(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    config_entry: MockConfigEntry,
    coordinator: Mock,
    gateway: DeviceInfo,
) -> MockConfigEntry:
    """Load the current integration runtime-data shape into Home Assistant."""
    config_entry.add_to_hass(hass)
    config_entry.runtime_data = SagemcomRuntimeData(
        coordinator=coordinator, gateway=gateway
    )
    return config_entry
