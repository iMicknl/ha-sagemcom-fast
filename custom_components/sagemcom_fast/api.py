"""Helpers for serialized access to the Sagemcom API."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from sagemcom_api.client import SagemcomClient

from .const import LOGGER

_T = TypeVar("_T")


class SagemcomApi:
    """Serialize API calls and manage the router login lifecycle."""

    def __init__(
        self,
        client: SagemcomClient,
        *,
        client_factory: Callable[[SagemcomClient], SagemcomClient] | None = None,
    ) -> None:
        """Initialize the API helper."""
        self.client = client
        self._client_factory = client_factory or self._fresh_client
        self._lock = asyncio.Lock()

    @staticmethod
    def _fresh_client(client: SagemcomClient) -> SagemcomClient:
        """Create an unauthenticated client while retaining the shared HTTP session."""
        return SagemcomClient(
            host=client.host,
            username=client.username,
            password=client.password,
            authentication_method=client.authentication_method,
            session=client.session,
            ssl=client.protocol == "https",
        )

    async def async_call(self, action: Callable[[SagemcomClient], Awaitable[_T]]) -> _T:
        """Run one API action in an authenticated, serialized session."""
        async with self._lock:
            logged_in = False
            action_succeeded = False
            try:
                await self.client.login()
                logged_in = True
                result = await action(self.client)
                action_succeeded = True
                return result
            finally:
                if logged_in:
                    try:
                        await self.client.logout()
                    except Exception:  # pylint: disable=broad-except
                        if action_succeeded:
                            raise
                        LOGGER.warning(
                            "Failed to log out after an API action failed",
                            exc_info=True,
                        )

    async def async_terminal_call(
        self, action: Callable[[SagemcomClient], Awaitable[_T]]
    ) -> _T:
        """Run an action that invalidates the router session, such as reboot."""
        async with self._lock:
            await self.client.login()
            try:
                return await action(self.client)
            finally:
                # A logout can race a router that is already restarting. Replace
                # the stateful client so the next call authenticates from scratch.
                self.client = self._client_factory(self.client)
