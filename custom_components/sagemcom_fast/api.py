"""Create Sagemcom F@st API clients."""

from __future__ import annotations

from aiohttp import ClientSession, CookieJar
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from sagemcom_api.client import SagemcomClient
from sagemcom_api.enums import ApiMode, EncryptionMethod


def create_client(
    hass: HomeAssistant,
    *,
    host: str,
    username: str,
    password: str,
    encryption_method: EncryptionMethod,
    ssl: bool,
    verify_ssl: bool,
) -> tuple[SagemcomClient, ClientSession | None]:
    """Return a client and the session the caller must detach, if it owns one."""
    if encryption_method is EncryptionMethod.NONE:
        # REST firmware keeps its session in a cookie set by an IP address,
        # which the shared Home Assistant cookie jar rejects. Legacy routers
        # must keep the shared jar: an unsafe jar breaks some of them.
        session = aiohttp_client.async_create_clientsession(
            hass,
            verify_ssl=verify_ssl,
            auto_cleanup=False,
            cookie_jar=CookieJar(unsafe=True),
        )
        owned_session: ClientSession | None = session
        api_mode = ApiMode.REST
    else:
        session = aiohttp_client.async_get_clientsession(hass, verify_ssl=verify_ssl)
        owned_session = None
        # Without a pin, a transient error page makes the client fall back to
        # REST, whose calls then fail with an auth error and trigger reauth.
        api_mode = ApiMode.LEGACY

    client = SagemcomClient(
        host=host,
        username=username,
        password=password,
        authentication_method=encryption_method,
        session=session,
        ssl=ssl,
        api_mode=api_mode,
    )
    return client, owned_session
