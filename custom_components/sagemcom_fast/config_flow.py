"""Config flow for Sagemcom integration."""

from collections.abc import Mapping
from typing import Any

from aiohttp import ClientError
from homeassistant import config_entries
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from sagemcom_api.client import SagemcomClient
from sagemcom_api.exceptions import (
    AccessRestrictionException,
    AuthenticationException,
    LoginConnectionException,
    LoginRetryErrorException,
    LoginTimeoutException,
    MaximumSessionCountException,
    UnsupportedHostException,
)
import voluptuous as vol

from .api import create_client
from .const import CONF_ENCRYPTION_METHOD, DOMAIN, LOGGER
from .options_flow import OptionsFlow


async def async_validate_input(
    hass: HomeAssistant, user_input: dict[str, Any]
) -> dict[str, Any]:
    """Validate the credentials and return the config entry data."""
    data = user_input.copy()
    data[CONF_USERNAME] = username = data.get(CONF_USERNAME) or ""
    data[CONF_PASSWORD] = password = data.get(CONF_PASSWORD) or ""
    host = data[CONF_HOST]
    ssl = data[CONF_SSL]

    session = async_get_clientsession(hass, data[CONF_VERIFY_SSL])

    client = SagemcomClient(
        host=host,
        username=username,
        password=password,
        session=session,
        ssl=ssl,
    )

    encryption_method = await client.get_encryption_method()
    if encryption_method is None:
        raise AuthenticationException("No login method accepted the credentials")
    data[CONF_ENCRYPTION_METHOD] = encryption_method
    LOGGER.debug("Detected encryption method: %s", encryption_method)

    # Validate with the same client setup the config entry will use.
    client, owned_session = create_client(
        hass,
        host=host,
        username=username,
        password=password,
        encryption_method=encryption_method,
        ssl=ssl,
        verify_ssl=data[CONF_VERIFY_SSL],
    )
    try:
        await client.login()
        await client.logout()
    finally:
        if owned_session is not None:
            owned_session.detach()

    return data


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sagemcom."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    _host: str | None = None
    _username: str | None = None

    async def _async_try_validate_input(
        self, user_input: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, dict[str, str]]:
        """Return the validated entry data, or the form errors to show."""
        try:
            return await async_validate_input(self.hass, user_input), {}
        except AccessRestrictionException:
            error = "access_restricted"
        except AuthenticationException:
            error = "invalid_auth"
        except (TimeoutError, ClientError, ConnectionError, LoginConnectionException):
            error = "cannot_connect"
        except LoginTimeoutException:
            error = "login_timeout"
        except MaximumSessionCountException:
            error = "maximum_session_count"
        except LoginRetryErrorException:
            error = "login_retry_error"
        except UnsupportedHostException:
            error = "unsupported_host"
        except Exception as exception:  # pylint: disable=broad-except
            error = "unknown"
            LOGGER.exception(exception)
        return None, {"base": error}

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input:
            self._host = user_input[CONF_HOST]
            self._username = user_input.get(CONF_USERNAME) or ""
            # TODO change to gateway mac address or something more unique
            await self.async_set_unique_id(self._host)
            self._abort_if_unique_id_configured()

            data, errors = await self._async_try_validate_input(user_input)
            if data is not None:
                return self.async_create_entry(title=self._host, data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=self._host): str,
                    vol.Optional(CONF_USERNAME, default=self._username): str,
                    vol.Optional(CONF_PASSWORD): str,
                    vol.Required(CONF_SSL, default=False): bool,
                    vol.Required(CONF_VERIFY_SSL, default=False): bool,
                }
            ),
            description_placeholders={
                "supported_devices_url": "https://github.com/iMicknl/ha-sagemcom-fast#supported-devices"
            },
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Start reauthentication after the router rejected the credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Validate replacement credentials for the linked config entry."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            data, errors = await self._async_try_validate_input(
                {**reauth_entry.data, **user_input}
            )
            if data is not None:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={
                        CONF_USERNAME: data[CONF_USERNAME],
                        CONF_PASSWORD: data[CONF_PASSWORD],
                        CONF_ENCRYPTION_METHOD: data[CONF_ENCRYPTION_METHOD],
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_USERNAME, default=reauth_entry.data.get(CONF_USERNAME, "")
                    ): str,
                    vol.Optional(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get options flow for this handler."""
        return OptionsFlow(config_entry)
