"""Tests for the privacy-safe contributor profile collector."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from sagemcom_api.exceptions import UnknownPathException
from sagemcom_api.models import DeviceInfo

from scripts import router_profile


class FakeClient:
    """Return sensitive-looking values so their exclusion can be verified."""

    def __init__(self) -> None:
        self.host = "192.168.1.1"
        self.username = "private-admin"
        self.password = "private-password"
        self.downstream = [
            {
                "uid": 8675309,
                "channel_id": 6,
                "lock_status": True,
                "frequency": 386000000.0,
                "SNR": 42.0,
                "power_level": 8.6,
                "private_note": "secret-channel-value",
            }
        ]
        self.upstream = [
            {
                "uid": 7654321,
                "channel_id": 1,
                "lock_status": True,
                "frequency": 23800000.0,
                "power_level": 39.3,
            }
        ]

    async def get_device_info(self) -> DeviceInfo:
        return DeviceInfo(
            mac_address="AA:BB:CC:DD:EE:FF",
            serial_number="private-router-serial",
            manufacturer="Sagemcom",
            model_name="FAST3896_MAGYAR",
            model_number="FAST3896",
            software_version="FAST3896_MAGYAR_sw23.83.19.23e",
            hardware_version="4.0",
            api_version="API-private-router-serial",
        )

    async def get_value_by_xpath(self, xpath: str) -> object:
        metrics = {
            router_profile.METRIC_XPATHS["uptime"]: 272567,
            router_profile.METRIC_XPATHS["wan_status"]: "online-private-token",
            router_profile.METRIC_XPATHS["dsl_downstream_rate"]: 123456,
            router_profile.METRIC_XPATHS["dsl_upstream_rate"]: 23456,
        }
        if xpath in metrics:
            return metrics[xpath]
        if xpath == router_profile.DOCSIS_COLLECTIONS["downstream"][0]:
            return self.downstream
        if xpath == router_profile.DOCSIS_COLLECTIONS["upstream"][0]:
            return self.upstream
        if "8675309" in xpath:
            return {
                "downstream": {
                    **self.downstream[0],
                    "address": "192.168.1.10",
                }
            }
        if "7654321" in xpath:
            return {
                "upstream": {
                    **self.upstream[0],
                    "address": "AA:BB:CC:DD:EE:01",
                }
            }
        raise UnknownPathException()

    async def get_values_by_xpaths(self, xpaths: dict[str, str]) -> dict:
        return {
            name: await self.get_value_by_xpath(xpath) for name, xpath in xpaths.items()
        }


def test_profile_excludes_credentials_addresses_identifiers_and_raw_values() -> None:
    """Only allowlisted metadata and response schemas may be serialized."""
    profile = asyncio.run(
        router_profile.async_collect_profile(
            FakeClient(),
            authentication_method="SHA512",
            benchmark_runs=1,
        )
    )
    serialized = json.dumps(profile, sort_keys=True)

    for private_value in (
        "AA:BB:CC:DD:EE:FF",
        "AA:BB:CC:DD:EE:01",
        "192.168.1.10",
        "private-router-serial",
        "private-admin",
        "private-password",
        "online-private-token",
        "secret-channel-value",
        "8675309",
        "7654321",
        "386000000",
        "23800000",
        "123456",
        "23456",
    ):
        assert private_value not in serialized

    assert "mac_address" not in profile["gateway"]
    assert "serial_number" not in profile["gateway"]
    assert profile["gateway"]["model_name"] == "FAST3896_MAGYAR"
    assert profile["gateway"]["api_version"] == "<redacted>"
    assert profile["capabilities"]["wan_status"] == {
        "status": "supported",
        "available": True,
        "value_type": "str",
        "connected": None,
    }
    downstream_shape = profile["schema_probes"]["docsis_downstreams"]["shape"]
    assert downstream_shape["count"] == 1
    assert downstream_shape["locked_count"] == 1
    assert downstream_shape["item_fields"]["SNR"] == "float"
    assert profile["docsis_indexed_path_probes"]["downstream"][
        "path_template"
    ].endswith("[@uid='<collection uid>']")


def test_shape_summary_does_not_copy_identifier_mapping_keys() -> None:
    """Keyed dictionaries may report counts and field types, not their keys."""
    shape = router_profile._value_shape(
        {
            "AA:BB:CC:DD:EE:FF": {
                "ip_address": "192.168.1.10",
                "active": True,
            }
        }
    )

    assert shape == {
        "type": "keyed_dict",
        "count": 1,
        "item_type": "dict",
        "item_fields": {"active": "bool", "ip_address": "str"},
    }
    assert "AA:BB:CC:DD:EE:FF" not in json.dumps(shape)


def test_safe_error_drops_arbitrary_router_messages() -> None:
    """Exception text is not shareable unless it is a protocol error token."""
    assert router_profile._safe_error(
        RuntimeError(
            {
                "code": 16777242,
                "description": "private failure at 192.168.1.1",
            }
        )
    ) == {"exception": "RuntimeError", "code": 16777242}
    assert router_profile._safe_error(
        RuntimeError(
            {
                "code": 16777242,
                "description": "XMO_INVALID_PATH_ERR",
            }
        )
    ) == {
        "exception": "RuntimeError",
        "code": 16777242,
        "description": "XMO_INVALID_PATH_ERR",
    }


def test_gateway_labels_reject_embedded_addresses() -> None:
    """Even allowlisted metadata fields are redacted when address-like."""
    assert router_profile._safe_label("firmware-AA:BB:CC:DD:EE:FF") == ("<redacted>")
    assert router_profile._safe_label("served-by-192.168.1.1") == "<redacted>"


def test_profile_output_refuses_to_replace_a_file(tmp_path: Path) -> None:
    """A contributor profile should not overwrite a previous report silently."""
    output = tmp_path / "sagemcom-profile.json"
    router_profile._write_profile({"safe": True}, output, overwrite=False)

    assert json.loads(output.read_text(encoding="utf-8")) == {"safe": True}
    with pytest.raises(FileExistsError):
        router_profile._write_profile({"safe": False}, output, overwrite=False)


def test_cli_never_accepts_a_password_argument() -> None:
    """Passwords must come from a hidden prompt or an environment variable."""
    option_strings = {
        option
        for action in router_profile._parser()._actions
        for option in action.option_strings
    }
    assert "--password" not in option_strings
