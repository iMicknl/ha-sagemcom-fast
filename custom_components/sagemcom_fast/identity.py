"""Stable identity helpers for Sagemcom gateways."""

from sagemcom_api.models import DeviceInfo as GatewayDeviceInfo


def gateway_unique_id(gateway: GatewayDeviceInfo) -> str:
    """Return the most stable available gateway identifier."""
    if serial_number := getattr(gateway, "serial_number", None):
        if normalized_serial := serial_number.strip():
            return normalized_serial

    return gateway.mac_address.upper()
