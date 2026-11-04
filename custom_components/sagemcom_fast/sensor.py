
"""Sensors for Sagemcom F@st routers."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfInformation,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import HomeAssistantSagemcomFastData
from .const import DOMAIN
from .coordinator import SagemcomDataUpdateCoordinator


def _unwrap(value: Any) -> Any:
    """Unwrap the common Sagemcom API list response."""
    if isinstance(value, list):
        return value[0] if value else {}
    return value


def _get_section(data: dict, key: str) -> dict:
    """Get a top-level API section."""
    return _unwrap(data.get(key)) or {}


def _number(value: Any) -> float | None:
    """Convert a router value to a number."""
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        match = re.search(r"-?\d+(?:\.\d+)?", str(value))
        return float(match.group()) if match else None


def _integer(value: Any) -> int | None:
    """Convert a router value to an integer."""
    number = _number(value)
    return int(number) if number is not None else None


def _device_info(data: dict) -> dict:
    """Return the device information object."""
    section = _get_section(data, "device_info")
    return section if isinstance(section, dict) else {}


def _device(data: dict) -> dict:
    """Return the device object from the device endpoint."""
    section = _get_section(data, "device")

    if not isinstance(section, dict):
        return {}

    device = section.get("device", section)
    return device if isinstance(device, dict) else {}


def _wireless_info(data: dict) -> dict:
    """Return the wireless information object."""
    section = _get_section(data, "wireless")

    if not isinstance(section, dict):
        return {}

    wireless = section.get("wireless", section)
    return wireless if isinstance(wireless, dict) else {}


def _radio(data: dict, band: str) -> dict:
    """Return radio information for one band."""
    radios = _wireless_info(data).get("radio", {}) or {}
    return radios.get(band, {}) or {}


def _usb_device_count(data: dict) -> int | None:
    """Count connected USB devices."""
    section = _get_section(data, "home")

    if not isinstance(section, dict):
        return None

    devices = section.get("usbListDevice")

    if devices is None:
        return None

    return len(devices)


def _lan_interfaces(data: dict) -> list[dict]:
    """Return LAN interface statistics."""
    section = _get_section(data, "lan_stats")
    lan = section.get("lan", section)

    if not isinstance(lan, dict):
        return []

    return lan.get("interfaces", []) or []


def _lan_ipv4_address(data):
    """Return the router's LAN IPv4 address."""
    return _device_info(data).get("localIpv4Address")


def _mesh_info(data: dict) -> dict:
    """Return the mesh gateway information."""
    section = _get_section(data, "mesh")
    devices = section.get("meshDevices", []) or []

    if not devices:
        return {}

    return devices[0]


def _hosts(data: dict) -> list[dict]:
    """Return the router's raw host list."""
    section = _get_section(data, "hosts")

    if not isinstance(section, dict):
        return []

    hosts = section.get("hosts", section)

    if not isinstance(hosts, dict):
        return []

    return hosts.get("list", []) or []


def _connected_host_count(data: dict) -> int:
    """Count all hosts reported by the router."""
    return len(_hosts(data))


def _active_host_count(data: dict) -> int:
    """Count active hosts reported by the router."""
    return sum(
        1 for host in _hosts(data)
        if host.get("active") is True
        or str(host.get("active", "")).lower() in ("true", "1", "yes")
    )


def _inactive_host_count(data: dict) -> int:
    """Count inactive hosts reported by the router."""
    return sum(
        1 for host in _hosts(data)
        if host.get("active") is False
        or str(host.get("active", "")).lower() in ("false", "0", "no")
    )


def _total_interface_counter(
    data: dict,
    counter: str,
    field: str,
) -> int | None:
    """Sum a counter across LAN interfaces only."""
    values = [
        _integer(interface.get(counter, {}).get(field))
        for interface in _lan_interfaces(data)
        if (
            str(interface.get("role", "")).upper() == "LAN"
            and isinstance(interface.get(counter), dict)
        )
    ]

    valid = [value for value in values if value is not None]

    return sum(valid) if valid else None

def _lan_status(data: dict) -> str | None:
    """Return a summary of LAN interface status."""
    statuses = [
        str(interface.get("status"))
        for interface in _lan_interfaces(data)
        if interface.get("status") is not None
    ]

    if not statuses:
        return None

    return "Up" if any(s.upper() == "UP" for s in statuses) else "Down"


def _uptime(data: dict) -> int | None:
    """Return router uptime in seconds."""
    value = _device_info(data).get("uptimeSystem")

    if value is None:
        value = _device(data).get("uptime")

    return _integer(value)


def _wifi_channel(data: dict, band: str) -> int | None:
    """Return the current Wi-Fi channel."""
    return _integer(_radio(data, band).get("current_channel"))


def _wifi_width(data: dict, band: str) -> int | None:
    """Return Wi-Fi channel width in MHz."""
    return _integer(_radio(data, band).get("htbw"))


def _wifi_bitrate(data: dict, band: str) -> float | None:
    """Return Wi-Fi maximum bitrate in Mbps."""
    return _number(_radio(data, band).get("maxbitrate"))


def _wifi_radio_status(data, band):
    """Return the operational status of a Wi-Fi radio."""
    radio = _wireless_info(data).get("radio", {}).get(band, {})

    if not radio:
        return None

    if not radio.get("enable", False):
        return "Disabled"

    return radio.get("state", "Unknown")


def _wan_ipv4_info(data):
    """Return WAN IPv4 information."""
    wan_ipv4 = _get_section(data, "wan_ipv4")
    return wan_ipv4.get("wan", {}).get("ipv4", {})


def _wan_connection_time(data):
    """Return WAN connection uptime in seconds."""
    wan = _wan_ipv4_info(data)
    uptime = wan.get("uptime")

    if uptime is None:
        return None

    try:
        return int(uptime)
    except (ValueError, TypeError):
        return None


def _wan_ipv4_address(data):
    """Return the WAN IPv4 address."""
    wan = _wan_ipv4_info(data)
    return wan.get("address")


def _wan_bitrate(data):
    """Return the negotiated WAN Ethernet link speed in Mbps."""
    for interface in _lan_interfaces(data):
        if (
            str(interface.get("role", "")).upper() == "WAN"
            and str(interface.get("status", "")).upper() == "UP"
        ):
            bitrate = interface.get("curbitrate")

            try:
                return int(bitrate)
            except (ValueError, TypeError):
                return None

    return None


def _wifi_ssid_status(data, ssid):
    """Return the status of a specific Wi-Fi SSID."""
    wireless = _wireless_info(data)
    ssid_info = wireless.get("ssid", {}).get(ssid, {})

    if not ssid_info:
        return None

    if not ssid_info.get("enable", False):
        return "Disabled"

    status = ssid_info.get("ssid_status")

    if status:
        return status.capitalize()

    return ssid_info.get("ap_status", "Unknown").capitalize()

@dataclass(frozen=True, kw_only=True)
class SagemcomSensorDescription(SensorEntityDescription):
    """Describe a Sagemcom sensor."""

    value_fn: Callable[[dict], Any]


SENSORS: tuple[SagemcomSensorDescription, ...] = (
    # Router system information.
    SagemcomSensorDescription(
        key="uptime",
        name="Router uptime",
        icon="mdi:timer-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_uptime,
    ),
    SagemcomSensorDescription(
        key="cpu_load",
        name="CPU load",
        icon="mdi:chip",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _number(_device_info(d).get("cpuLoad")),
    ),
    SagemcomSensorDescription(
        key="firmware",
        name="Firmware version",
        icon="mdi:package-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _device_info(d).get("softwareVersion"),
    ),
    SagemcomSensorDescription(
        key="kernel",
        name="Kernel version",
        icon="mdi:linux",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _device_info(d).get("kernelVersion"),
    ),
    SagemcomSensorDescription(
        key="reboot_count",
        name="Router reboot count",
        icon="mdi:restart",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: _integer(_device(d).get("numberofboots")),
    ),
    SagemcomSensorDescription(
        key="temperature",
        name="Router temperature",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _number(
            _device(d).get("temperature", {}).get("current")
        ),
    ),

    #Memory Sensors
    SagemcomSensorDescription(
        key="memory_total",
        name="Total memory",
        icon="mdi:memory",
        native_unit_of_measurement="MiB",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: (
        _device_info(d).get("totalMemory", 0) / 1024
        if _device_info(d).get("totalMemory") is not None
        else None
        ),
    ),
    SagemcomSensorDescription(
        key="memory_free",
        name="Free memory",
        icon="mdi:memory",
        native_unit_of_measurement=UnitOfInformation.KILOBYTES,
        value_fn=lambda d: _integer(_device_info(d).get("freeMemory")),
    ),
    SagemcomSensorDescription(
        key="memory_cached",
        name="Cached memory",
        icon="mdi:memory",
        native_unit_of_measurement=UnitOfInformation.KILOBYTES,
        value_fn=lambda d: _integer(_device_info(d).get("cachedMemory")),
    ),
    #Flash Storage
    SagemcomSensorDescription(
        key="flash_total",
        name="Total flash memory",
        icon="mdi:harddisk",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfInformation.KILOBYTES,
        value_fn=lambda d: _integer(_device_info(d).get("totalFlashMemory")),
    ),
    SagemcomSensorDescription(
        key="flash_free",
        name="Free flash memory",
        icon="mdi:harddisk",
        native_unit_of_measurement=UnitOfInformation.KILOBYTES,
        value_fn=lambda d: _integer(_device_info(d).get("freeFlashMemory")),
    ),

    # LAN interface counters.
    SagemcomSensorDescription(
        key="lan_status",
        name="LAN interface status",
        icon="mdi:ethernet",
        value_fn=_lan_status,
    ),

    # LAN IPv4 address
    SagemcomSensorDescription(
        key="lan_ipv4_address",
        name="LAN IPv4 Address",
        icon="mdi:ip-network",
        value_fn=lambda d: _lan_ipv4_address(d),
    ),
    SagemcomSensorDescription(
        key="lan_rx_bytes",
        name="LAN received",
        icon="mdi:download-network",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: _total_interface_counter(d, "rx", "bytes"),
    ),
    SagemcomSensorDescription(
        key="lan_tx_bytes",
        name="LAN transmitted",
        icon="mdi:upload-network",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: _total_interface_counter(d, "tx", "bytes"),
    ),
    SagemcomSensorDescription(
        key="lan_rx_errors",
        name="LAN receive errors",
        icon="mdi:alert-circle-outline",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: _total_interface_counter(d, "rx", "packetserrors"),
    ),
    SagemcomSensorDescription(
        key="lan_tx_errors",
        name="LAN transmit errors",
        icon="mdi:alert-circle-outline",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: _total_interface_counter(d, "tx", "packetserrors"),
    ),
    SagemcomSensorDescription(
        key="lan_rx_discards",
        name="LAN receive discards",
        icon="mdi:alert-circle-outline",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: _total_interface_counter(d, "rx", "packetsdiscards"),
    ),
    SagemcomSensorDescription(
        key="lan_tx_discards",
        name="LAN transmit discards",
        icon="mdi:alert-circle-outline",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: _total_interface_counter(d, "tx", "packetsdiscards"),
    ),
    # WAN.
    SagemcomSensorDescription(
        key="wan_status",
        name="WAN connection",
        icon="mdi:wan",
        value_fn=lambda d: _get_section(d, "wan_status").get("status"),
    ),

    # WAN connection uptime
    SagemcomSensorDescription(
        key="wan_connection_time",
        name="WAN Connection Time",
        icon="mdi:timer-outline",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        value_fn=lambda d: _wan_connection_time(d),
    ),

    # WAN Ethernet link speed
    SagemcomSensorDescription(
        key="wan_bitrate",
        name="WAN Link Bitrate",
        icon="mdi:speedometer",
        native_unit_of_measurement="Mbit/s",
        value_fn=lambda d: _wan_bitrate(d),
    ),

    # WAN IPv4 address
    SagemcomSensorDescription(
        key="wan_ipv4_address",
        name="WAN IPv4 Address",
        icon="mdi:ip-network",
        value_fn=lambda d: _wan_ipv4_address(d),
    ),
    # Network traffic rates
    SagemcomSensorDescription(
        key="wan_rx_rate",
        name="WAN Download Rate",
        icon="mdi:download-network",
        native_unit_of_measurement="Mbit/s",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("traffic_rates", {}).get("wan_rx_rate"),
    ),
    SagemcomSensorDescription(
        key="wan_tx_rate",
        name="WAN Upload Rate",
        icon="mdi:upload-network",
        native_unit_of_measurement="Mbit/s",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("traffic_rates", {}).get("wan_tx_rate"),
    ),
    # Connected hosts.
    SagemcomSensorDescription(
        key="connected_hosts",
        name="Connected devices",
        icon="mdi:devices",
        native_unit_of_measurement="devices",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_connected_host_count,
    ),
    SagemcomSensorDescription(
        key="active_hosts",
        name="Active router hosts",
        icon="mdi:lan-connect",
        native_unit_of_measurement="devices",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_active_host_count,
    ),
    SagemcomSensorDescription(
        key="inactive_hosts",
        name="Inactive router hosts",
        icon="mdi:lan-disconnect",
        native_unit_of_measurement="devices",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_inactive_host_count,
    ),

    # Connected USB device count
    SagemcomSensorDescription(
        key="usb_devices",
        name="Connected USB devices",
        icon="mdi:usb",
        native_unit_of_measurement="devices",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_usb_device_count,
    ),

    # Wifi - for both 2.4GHz and 5GHz: Split into Radio, SSID, guest and private
    # 2.4 GHz radio
    SagemcomSensorDescription(
        key="wifi_24_radio_status",
        name="Wi-Fi 2.4 GHz Radio Status",
        icon="mdi:radio-tower",
        value_fn=lambda d: _wifi_radio_status(d, "24"),
    ),
    SagemcomSensorDescription(
        key="wifi_24_channel",
        name="2.4 GHz Wi-Fi channel",
        icon="mdi:wifi",
        value_fn=lambda d: _wifi_channel(d, "24"),
    ),
    SagemcomSensorDescription(
        key="wifi_24_width",
        name="2.4 GHz Wi-Fi channel width",
        icon="mdi:wifi",
        native_unit_of_measurement="MHz",
        value_fn=lambda d: _wifi_width(d, "24"),
    ),
    SagemcomSensorDescription(
        key="wifi_24_max_bitrate",
        name="2.4 GHz Wi-Fi maximum bitrate",
        icon="mdi:speedometer",
        native_unit_of_measurement="Mbps",
        value_fn=lambda d: _wifi_bitrate(d, "24"),
    ),

    # 2.4 GHz private SSID
    SagemcomSensorDescription(
        key="wifi_24_private_status",
        name="Wi-Fi 2.4 GHz Private Status",
        icon="mdi:wifi",
        value_fn=lambda d: _wifi_ssid_status(d, "24"),
    ),
    # 2.4 GHz guest SSID
    SagemcomSensorDescription(
        key="wifi_24_guest_status",
        name="Wi-Fi 2.4 GHz Guest Status",
        icon="mdi:wifi-star",
        value_fn=lambda d: _wifi_ssid_status(d, "guest24"),
    ),
    # 5 GHz wireless radio.
    SagemcomSensorDescription(
        key="wifi_5_radio_status",
        name="Wi-Fi 5 GHz Radio Status",
        icon="mdi:radio-tower",
        value_fn=lambda d: _wifi_radio_status(d, "5"),
    ),
    SagemcomSensorDescription(
        key="wifi_5_channel",
        name="5 GHz Wi-Fi channel",
        icon="mdi:wifi",
        value_fn=lambda d: _wifi_channel(d, "5"),
    ),
    SagemcomSensorDescription(
        key="wifi_5_width",
        name="5 GHz Wi-Fi channel width",
        icon="mdi:wifi",
        native_unit_of_measurement="MHz",
        value_fn=lambda d: _wifi_width(d, "5"),
    ),
    SagemcomSensorDescription(
        key="wifi_5_max_bitrate",
        name="5 GHz Wi-Fi maximum bitrate",
        icon="mdi:speedometer",
        native_unit_of_measurement="Mbps",
        value_fn=lambda d: _wifi_bitrate(d, "5"),
    ),

      # 5 GHz private SSID
    SagemcomSensorDescription(
        key="wifi_5_private_status",
        name="Wi-Fi 5 GHz Private Status",
        icon="mdi:wifi",
        value_fn=lambda d: _wifi_ssid_status(d, "5"),
    ),

     # 5 GHz guest SSID
    SagemcomSensorDescription(
        key="wifi_5_guest_status",
        name="Wi-Fi 5 GHz Guest Status",
        icon="mdi:wifi-star",
        value_fn=lambda d: _wifi_ssid_status(d, "guest5"),
    ),

    # Wifi Mesh
    # Mesh.
    SagemcomSensorDescription(
        key="mesh_backhaul_quality",
        name="Mesh backhaul quality",
        icon="mdi:access-point-network",
        value_fn=lambda d: (
            _mesh_info(d).get("backhaul", {}).get("linkQuality")
        ),
    ),
    SagemcomSensorDescription(
        key="mesh_backhaul_type",
        name="Mesh backhaul type",
        icon="mdi:access-point-network",
        value_fn=lambda d: (
            _mesh_info(d).get("backhaul", {}).get("linkType")
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sagemcom F@st sensors."""

    data: HomeAssistantSagemcomFastData = (
        hass.data[DOMAIN][entry.entry_id]
    )

    async_add_entities(
        SagemcomFastSensor(
            data.coordinator,
            data.gateway,
            description,
        )
        for description in SENSORS
    )


class SagemcomFastSensor(
    CoordinatorEntity[SagemcomDataUpdateCoordinator],
    SensorEntity,
):
    """Representation of a Sagemcom F@st sensor."""

    entity_description: SagemcomSensorDescription

    _attr_has_entity_name = True

    # Keep all new sensors disabled until explicitly enabled.
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: SagemcomDataUpdateCoordinator,
        gateway,
        description: SagemcomSensorDescription,
    ) -> None:
        """Initialise the sensor."""

        super().__init__(coordinator)

        self.entity_description = description
        self.gateway = gateway

        self._attr_unique_id = (
            f"{gateway.serial_number}_{description.key}"
        )

    @property
    def native_value(self):
        """Return the sensor value."""

        return self.entity_description.value_fn(
            self.coordinator.router_data
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Link the sensor to the router device."""
        device = _device_info(self.coordinator.router_data)

        return DeviceInfo(
            identifiers={
                (DOMAIN, self.gateway.serial_number)
            },
            manufacturer=device.get("manufacturer", "Sagemcom"),
            model=device.get("productClass", "FAST5598"),
            name="Sagemcom FAST5598",
            sw_version=device.get("softwareVersion"),
            hw_version=device.get("hardwareVersion"),
            serial_number=device.get("serialnumber"),
            configuration_url="http://192.168.0.1",
        )