"""Tests for the Sagemcom data update coordinator."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest
from sagemcom_api.exceptions import (
    AccessRestrictionException,
    AuthenticationException,
    LoginRetryErrorException,
    LoginTimeoutException,
    MaximumSessionCountException,
)
from sagemcom_api.models import Device, DeviceInfo

from custom_components.sagemcom_fast.api import SagemcomApi
from custom_components.sagemcom_fast.capabilities import (
    CAPABILITY_XPATHS,
    DOCSIS_COLLECTION_XPATHS,
)
from custom_components.sagemcom_fast.coordinator import SagemcomDataUpdateCoordinator
from custom_components.sagemcom_fast.snapshot import (
    GatewayCapabilities,
    GatewayCapability,
    GatewaySnapshot,
)


class FakeClient:
    """Record API calls and optionally return a host list."""

    def __init__(self, hosts: list[Device] | None = None) -> None:
        self.hosts = hosts or []
        self.metric_values: dict[GatewayCapability, object] = {}
        self.metric_error: Exception | None = None
        self.docsis_values: dict[GatewayCapability, object] = {}
        self.docsis_error: Exception | None = None
        self.calls: list[str] = []

    async def login(self) -> None:
        self.calls.append("login")

    async def logout(self) -> None:
        self.calls.append("logout")

    async def get_hosts(self, *, only_active: bool) -> list[Device]:
        assert only_active is True
        self.calls.append("get_hosts")
        return self.hosts

    async def get_values_by_xpaths(self, xpaths: dict) -> dict:
        self.calls.append("get_values_by_xpaths")
        if self.metric_error is not None:
            raise self.metric_error
        assert set(xpaths) == set(self.metric_values)
        return self.metric_values

    async def get_value_by_xpath(self, xpath: str) -> object:
        self.calls.append("get_value_by_xpath")
        for capability, value in self.metric_values.items():
            if CAPABILITY_XPATHS[capability] == xpath:
                if self.metric_error is not None:
                    raise self.metric_error
                return value
        for capability, value in self.docsis_values.items():
            if DOCSIS_COLLECTION_XPATHS[capability] == xpath:
                if self.docsis_error is not None:
                    raise self.docsis_error
                return value
        raise AssertionError(f"Unexpected XPath: {xpath}")


def _coordinator(client: FakeClient) -> SagemcomDataUpdateCoordinator:
    coordinator = object.__new__(SagemcomDataUpdateCoordinator)
    coordinator.api = SagemcomApi(client)
    coordinator.data = GatewaySnapshot(
        gateway=DeviceInfo(mac_address="AA:BB:CC:DD:EE:00", serial_number="router")
    )
    coordinator.logger = Mock()
    return coordinator


def test_poll_fetches_hosts_and_logs_out() -> None:
    host = Device(phys_address="AA:BB:CC:DD:EE:FF", active=True)
    client = FakeClient([host])

    result = asyncio.run(_coordinator(client)._async_update_data())

    assert result.hosts == {host.id: host}
    assert client.calls == ["login", "get_hosts", "logout"]


def test_poll_batches_confirmed_metrics_after_core_hosts() -> None:
    host = Device(phys_address="AA:BB:CC:DD:EE:FF", active=True)
    client = FakeClient([host])
    client.metric_values = {
        GatewayCapability.UPTIME: "123",
        GatewayCapability.WAN_STATUS: " Up ",
    }
    coordinator = _coordinator(client)
    coordinator.data = coordinator.data.with_capabilities(
        GatewayCapabilities(
            supported=frozenset(client.metric_values), batch_metrics=True
        ),
        {},
    )

    result = asyncio.run(coordinator._async_update_data())

    assert result.metrics == {
        GatewayCapability.UPTIME: 123,
        GatewayCapability.WAN_STATUS: "Up",
    }
    assert client.calls == [
        "login",
        "get_hosts",
        "get_values_by_xpaths",
        "logout",
    ]


def test_poll_reads_metrics_sequentially_when_batch_validation_failed() -> None:
    client = FakeClient()
    client.metric_values = {
        GatewayCapability.UPTIME: "123",
        GatewayCapability.WAN_STATUS: "Up",
    }
    coordinator = _coordinator(client)
    coordinator.data = coordinator.data.with_capabilities(
        GatewayCapabilities(supported=frozenset(client.metric_values)), {}
    )

    result = asyncio.run(coordinator._async_update_data())

    assert result.metrics == {
        GatewayCapability.UPTIME: 123,
        GatewayCapability.WAN_STATUS: "Up",
    }
    assert client.calls == [
        "login",
        "get_hosts",
        "get_value_by_xpath",
        "get_value_by_xpath",
        "logout",
    ]


def test_optional_metric_failure_does_not_discard_core_hosts() -> None:
    host = Device(phys_address="AA:BB:CC:DD:EE:FF", active=True)
    client = FakeClient([host])
    client.metric_values = {GatewayCapability.UPTIME: 1}
    client.metric_error = ConnectionError("optional read failed")
    coordinator = _coordinator(client)
    coordinator.data = coordinator.data.with_capabilities(
        GatewayCapabilities(
            supported=frozenset(client.metric_values), batch_metrics=True
        ),
        {GatewayCapability.UPTIME: 99},
    )

    result = asyncio.run(coordinator._async_update_data())

    assert result.hosts == {host.id: host}
    assert result.metrics == {}
    coordinator.logger.warning.assert_called_once()


def test_poll_reads_confirmed_docsis_collections_sequentially() -> None:
    client = FakeClient()
    client.docsis_values = {
        GatewayCapability.DOCSIS_DOWNSTREAM_CHANNELS: [
            {"uid": 1, "channel_id": 10, "lock_status": True, "SNR": 40.0}
        ],
        GatewayCapability.DOCSIS_UPSTREAM_CHANNELS: [
            {
                "uid": 2,
                "channel_id": 3,
                "lock_status": True,
                "power_level": 42.5,
            }
        ],
    }
    coordinator = _coordinator(client)
    coordinator.data = coordinator.data.with_capabilities(
        GatewayCapabilities(supported=frozenset(client.docsis_values)), {}
    )

    result = asyncio.run(coordinator._async_update_data())

    assert result.docsis_downstream_channels[0].snr == 40.0
    assert result.docsis_upstream_channels[0].power_level == 42.5
    assert client.calls == [
        "login",
        "get_hosts",
        "get_value_by_xpath",
        "get_value_by_xpath",
        "logout",
    ]


def test_docsis_failure_does_not_discard_core_hosts() -> None:
    host = Device(phys_address="AA:BB:CC:DD:EE:FF", active=True)
    client = FakeClient([host])
    client.docsis_values = {GatewayCapability.DOCSIS_DOWNSTREAM_CHANNELS: []}
    client.docsis_error = ConnectionError("optional read failed")
    coordinator = _coordinator(client)
    coordinator.data = coordinator.data.with_capabilities(
        GatewayCapabilities(supported=frozenset(client.docsis_values)),
        {},
    )

    result = asyncio.run(coordinator._async_update_data())

    assert result.hosts == {host.id: host}
    assert result.docsis_downstream_channels == ()
    coordinator.logger.warning.assert_called_once()


@pytest.mark.parametrize(
    ("error", "exception_type", "message"),
    [
        (AccessRestrictionException(), ConfigEntryAuthFailed, "Access restricted"),
        (AuthenticationException(), ConfigEntryAuthFailed, "Invalid credentials"),
        (ConnectionError(), UpdateFailed, "Failed to connect"),
        (TimeoutError(), UpdateFailed, "Failed to connect"),
        (LoginTimeoutException(), UpdateFailed, "Failed to connect"),
        (LoginRetryErrorException(), UpdateFailed, "Too many login attempts"),
        (
            MaximumSessionCountException(),
            UpdateFailed,
            "Maximum session count reached",
        ),
    ],
)
def test_poll_maps_expected_errors(
    error: Exception, exception_type: type[Exception], message: str
) -> None:
    client = FakeClient()
    client.login = AsyncMock(side_effect=error)

    with pytest.raises(exception_type, match=message):
        asyncio.run(_coordinator(client)._async_update_data())
