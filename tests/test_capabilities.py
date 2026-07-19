"""Tests for optional gateway capability discovery and metrics."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from sagemcom_api.exceptions import (
    AccessRestrictionException,
    UnknownException,
    UnknownPathException,
)

from custom_components.sagemcom_fast.capabilities import (
    CAPABILITY_XPATHS,
    DOCSIS_COLLECTION_XPATHS,
    async_discover_capabilities,
    metric_xpaths,
    normalize_metrics,
    prefer_metric_batch,
    wan_status_is_connected,
)
from custom_components.sagemcom_fast.snapshot import (
    GatewayCapabilities,
    GatewayCapability,
)


class FakeClient:
    """Return a configured value or exception for each XPath."""

    def __init__(
        self,
        responses: dict[str, object],
        batch_responses: dict[GatewayCapability, object] | None = None,
    ) -> None:
        self.responses = responses
        self.batch_responses = batch_responses or {}
        self.calls: list[str] = []

    async def get_value_by_xpath(self, xpath: str) -> object:
        self.calls.append(xpath)
        response = self.responses.get(xpath, UnknownPathException())
        if isinstance(response, Exception):
            raise response
        return response

    async def get_values_by_xpaths(self, _xpaths: dict) -> dict:
        return self.batch_responses


def test_discovery_probes_paths_individually_and_skips_unsupported_values() -> None:
    client = FakeClient(
        {
            CAPABILITY_XPATHS[GatewayCapability.UPTIME]: "3600",
            CAPABILITY_XPATHS[
                GatewayCapability.WAN_STATUS
            ]: AccessRestrictionException(),
            CAPABILITY_XPATHS[
                GatewayCapability.DSL_DOWNSTREAM_RATE
            ]: UnknownPathException(),
            CAPABILITY_XPATHS[GatewayCapability.DSL_UPSTREAM_RATE]: "malformed",
        }
    )

    result = asyncio.run(async_discover_capabilities(client))

    assert client.calls == [
        *CAPABILITY_XPATHS.values(),
        *DOCSIS_COLLECTION_XPATHS.values(),
    ]
    assert result.capabilities.supported == frozenset({GatewayCapability.UPTIME})
    assert result.metrics == {GatewayCapability.UPTIME: 3600}


def test_discovery_propagates_systemic_failures() -> None:
    client = FakeClient(
        {
            CAPABILITY_XPATHS[GatewayCapability.UPTIME]: ConnectionError(
                "router unavailable"
            )
        }
    )

    with pytest.raises(ConnectionError, match="router unavailable"):
        asyncio.run(async_discover_capabilities(client))


def test_discovery_parses_supported_docsis_collections() -> None:
    client = FakeClient(
        {
            DOCSIS_COLLECTION_XPATHS[GatewayCapability.DOCSIS_DOWNSTREAM_CHANNELS]: [
                {
                    "uid": 1,
                    "channel_id": 10,
                    "lock_status": True,
                    "SNR": 39.5,
                }
            ],
            DOCSIS_COLLECTION_XPATHS[GatewayCapability.DOCSIS_UPSTREAM_CHANNELS]: {
                "malformed": True
            },
        }
    )

    result = asyncio.run(async_discover_capabilities(client))

    assert result.capabilities.supported == frozenset(
        {GatewayCapability.DOCSIS_DOWNSTREAM_CHANNELS}
    )
    assert result.docsis_downstream_channels[0].channel_id == 10
    assert result.docsis_downstream_channels[0].snr == 39.5
    assert result.docsis_upstream_channels == ()


def test_discovery_treats_untyped_invalid_path_as_unsupported() -> None:
    client = FakeClient(
        {
            DOCSIS_COLLECTION_XPATHS[
                GatewayCapability.DOCSIS_DOWNSTREAM_CHANNELS
            ]: UnknownException(
                {
                    "code": 16777242,
                    "description": "XMO_INVALID_PATH_ERR",
                }
            )
        }
    )

    result = asyncio.run(async_discover_capabilities(client))

    assert result.capabilities.supported == frozenset()


def test_discovery_disables_an_incomplete_batch() -> None:
    client = FakeClient(
        {
            CAPABILITY_XPATHS[GatewayCapability.UPTIME]: 3600,
            CAPABILITY_XPATHS[GatewayCapability.WAN_STATUS]: "Up",
            CAPABILITY_XPATHS[
                GatewayCapability.DSL_DOWNSTREAM_RATE
            ]: UnknownPathException(),
            CAPABILITY_XPATHS[
                GatewayCapability.DSL_UPSTREAM_RATE
            ]: UnknownPathException(),
        },
        {
            GatewayCapability.UPTIME: 3600,
            GatewayCapability.WAN_STATUS: None,
        },
    )

    result = asyncio.run(async_discover_capabilities(client))

    assert result.capabilities.supported == frozenset(
        {GatewayCapability.UPTIME, GatewayCapability.WAN_STATUS}
    )
    assert not result.capabilities.batch_metrics


def test_metric_batch_contains_only_confirmed_paths() -> None:
    capabilities = GatewayCapabilities(
        supported=frozenset({GatewayCapability.UPTIME, GatewayCapability.WAN_STATUS})
    )

    assert metric_xpaths(capabilities) == {
        GatewayCapability.UPTIME: CAPABILITY_XPATHS[GatewayCapability.UPTIME],
        GatewayCapability.WAN_STATUS: CAPABILITY_XPATHS[GatewayCapability.WAN_STATUS],
    }


def test_metric_normalization_omits_missing_and_malformed_values() -> None:
    values = {
        GatewayCapability.UPTIME: "7200",
        GatewayCapability.WAN_STATUS: " ",
        GatewayCapability.DSL_DOWNSTREAM_RATE: None,
        GatewayCapability.DSL_UPSTREAM_RATE: 2**32 - 1,
    }

    assert normalize_metrics(values) == {GatewayCapability.UPTIME: 7200}


def test_discovery_keeps_dsl_capability_with_unavailable_standard_value() -> None:
    client = FakeClient(
        {
            CAPABILITY_XPATHS[GatewayCapability.UPTIME]: UnknownPathException(),
            CAPABILITY_XPATHS[GatewayCapability.WAN_STATUS]: UnknownPathException(),
            CAPABILITY_XPATHS[GatewayCapability.DSL_DOWNSTREAM_RATE]: 2**32 - 1,
            CAPABILITY_XPATHS[
                GatewayCapability.DSL_UPSTREAM_RATE
            ]: UnknownPathException(),
        }
    )

    result = asyncio.run(async_discover_capabilities(client))

    assert result.capabilities.supported == frozenset(
        {GatewayCapability.DSL_DOWNSTREAM_RATE}
    )
    assert result.metrics == {}


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("Up", True),
        (" connected ", True),
        ("Down", False),
        ("LowerLayerDown", False),
        ("NotPresent", False),
        ("Unknown", None),
        ("vendor-specific", None),
        (None, None),
    ],
)
def test_wan_status_normalization(
    status: object,
    expected: bool | None,
) -> None:
    assert wan_status_is_connected(status) is expected


@pytest.mark.parametrize(
    ("sequential_ms", "batch_ms", "decoded_values", "expected"),
    [
        (16.2, 163.8, 1, False),
        (20.0, 8.0, 2, True),
        (20.0, 8.0, 1, False),
    ],
)
def test_batch_preference_requires_complete_faster_results(
    sequential_ms: float,
    batch_ms: float,
    decoded_values: int,
    expected: bool,
) -> None:
    assert (
        prefer_metric_batch(
            sequential_ms=sequential_ms,
            batch_ms=batch_ms,
            expected_values=2,
            decoded_values=decoded_values,
        )
        is expected
    )


def test_fast3896_magyar_fixture_disables_metric_batching() -> None:
    fixture_path = (
        Path(__file__).parent / "fixtures" / "fast3896_magyar_sw23.83.19.23e.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    benchmark = fixture["benchmark"]

    assert fixture["capabilities"]["wan_status"] == {
        "connected": True,
        "status": "supported",
        "value_type": "str",
    }

    assert not prefer_metric_batch(
        sequential_ms=benchmark["sequential_median_ms"],
        batch_ms=benchmark["batch_median_ms"],
        expected_values=benchmark["confirmed_action_count"],
        decoded_values=benchmark["decoded_value_count"],
    )

    expected_invalid_path = {
        "exception": "UnknownException",
        "code": 16777242,
        "description": "XMO_INVALID_PATH_ERR",
    }
    for channel_type in ("downstream", "upstream"):
        schema = fixture["docsis_channel_schemas"][channel_type]
        assert schema["status"] == "error"
        assert schema["fields"] == {}
        assert schema["error"] == expected_invalid_path


def test_fast3896_magyar_fixture_describes_docsis_collections() -> None:
    fixture_path = (
        Path(__file__).parent / "fixtures" / "fast3896_magyar_sw23.83.19.23e.json"
    )
    collections = json.loads(fixture_path.read_text(encoding="utf-8"))[
        "docsis_collections"
    ]

    assert collections["downstream"]["path"].endswith("/Downstreams")
    assert collections["downstream"]["count"] == 26
    assert collections["downstream"]["locked_count"] == 26
    assert collections["downstream"]["item_fields"]["SNR"] == "float"
    assert collections["downstream"]["item_fields"]["power_level"] == "float"
    assert collections["downstream"]["item_fields"]["uid"] == "int"

    assert collections["upstream"]["path"].endswith("/Upstreams")
    assert collections["upstream"]["count"] == 7
    assert collections["upstream"]["locked_count"] == 7
    assert collections["upstream"]["item_fields"]["power_level"] == "float"
    assert collections["upstream"]["item_fields"]["uid"] == "int"

    profile = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert profile["docsis_units"] == {
        "frequency": {"api_gui_scale": "1:1", "unit": "Hz"},
        "power_level": {
            "api_gui_scale": "1:1",
            "display_precision": 1,
            "unit": "dBmV",
        },
        "SNR": {
            "api_gui_scale": "1:1",
            "display_precision": 1,
            "unit": "dB",
        },
        "symbol_rate": {"api_gui_scale": "1:1", "unit": "ksps"},
        "codewords": {"measurement": "cumulative_count"},
    }
    indexed_schemas = profile["docsis_actual_uid_schemas"]
    for channel_type in ("downstream", "upstream"):
        assert indexed_schemas[channel_type]["status"] == "error"
        assert indexed_schemas[channel_type]["error"] == {
            "exception": "UnknownException",
            "code": 16777242,
            "description": "XMO_INVALID_PATH_ERR",
        }
        assert "<collection uid>" in indexed_schemas[channel_type]["xpath_template"]
