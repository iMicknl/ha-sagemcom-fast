"""Tests for stable gateway identity."""

import pytest
from sagemcom_api.models import DeviceInfo

from custom_components.sagemcom_fast.identity import gateway_unique_id


@pytest.mark.parametrize(
    ("gateway", "expected"),
    [
        (
            DeviceInfo(mac_address="aa:bb:cc:dd:ee:ff", serial_number=" serial "),
            "serial",
        ),
        (DeviceInfo(mac_address="aa:bb:cc:dd:ee:ff"), "AA:BB:CC:DD:EE:FF"),
    ],
)
def test_gateway_unique_id(gateway: DeviceInfo, expected: str) -> None:
    assert gateway_unique_id(gateway) == expected
