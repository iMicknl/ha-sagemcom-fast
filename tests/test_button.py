"""Tests for the gateway reboot button."""

from __future__ import annotations

import asyncio

from sagemcom_api.models import DeviceInfo

from custom_components.sagemcom_fast.api import SagemcomApi
from custom_components.sagemcom_fast.button import SagemcomFastRebootButton
from custom_components.sagemcom_fast.const import DOMAIN


class FakeClient:
    """Record the reboot API lifecycle."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def login(self) -> None:
        self.calls.append("login")

    async def reboot(self) -> None:
        self.calls.append("reboot")


def test_reboot_button_uses_translated_name_and_terminal_api_call() -> None:
    """The reboot command should not race router shutdown with logout."""
    client = FakeClient()
    replacement = FakeClient()
    button = SagemcomFastRebootButton(
        DeviceInfo(
            mac_address="AA:BB:CC:DD:EE:FF",
            serial_number="router-serial",
        ),
        SagemcomApi(client, client_factory=lambda _client: replacement),
    )

    asyncio.run(button.async_press())

    assert client.calls == ["login", "reboot"]
    assert button.translation_key == "reboot"
    assert button.unique_id == "router-serial_reboot"
    assert button.device_info["identifiers"] == {(DOMAIN, "router-serial")}
