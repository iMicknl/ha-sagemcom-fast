"""Tests for serialized Sagemcom API access."""

from __future__ import annotations

import asyncio

import pytest

from custom_components.sagemcom_fast.api import SagemcomApi


class FakeClient:
    """Record API lifecycle calls."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def login(self) -> None:
        self.calls.append("login")

    async def logout(self) -> None:
        self.calls.append("logout")


def test_action_failure_logs_out_and_preserves_error() -> None:
    client = FakeClient()
    api = SagemcomApi(client)

    async def fail(_client) -> None:
        client.calls.append("action")
        raise ValueError("action failed")

    with pytest.raises(ValueError, match="action failed"):
        asyncio.run(api.async_call(fail))

    assert client.calls == ["login", "action", "logout"]


def test_terminal_action_replaces_client_without_logout() -> None:
    client = FakeClient()
    replacement = FakeClient()
    api = SagemcomApi(client, client_factory=lambda _client: replacement)

    async def action(_client) -> None:
        client.calls.append("reboot")

    asyncio.run(api.async_terminal_call(action))

    assert client.calls == ["login", "reboot"]
    assert api.client is replacement
