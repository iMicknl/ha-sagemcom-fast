"""Config flow for Sagemcom integration."""
import logging

from aiohttp import ClientError
import voluptuous as vol
from homeassistant import config_entries, core, exceptions
from homeassistant.const import (
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_HOST,
    HTTP_BAD_REQUEST,
)
from homeassistant.core import callback
from .const import (
    CONF_ENCRYPTION_METHOD,
    CONF_TRACK_WIRELESS_CLIENTS,
    CONF_TRACK_WIRED_CLIENTS,
)

from .const import DOMAIN  # pylint: disable=unused-import

from sagemcom_api.enums import EncryptionMethod
from sagemcom_api.exceptions import (
    AccessRestrictionException,
    AuthenticationException,
    LoginTimeoutException,
    UnauthorizedException,
)
from sagemcom_api.client import SagemcomClient

_LOGGER = logging.getLogger(__name__)

ENCRYPTION_METHODS = [item.value for item in EncryptionMethod]

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_USERNAME): str,
        vol.Optional(CONF_PASSWORD): str,
        vol.Required(CONF_ENCRYPTION_METHOD): vol.In(ENCRYPTION_METHODS),
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sagemcom."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_validate_input(self, user_input):
        """Validate user credentials."""
        username = user_input.get(CONF_USERNAME) or ""
        password = user_input.get(CONF_PASSWORD) or ""
        host = user_input.get(
            CONF_HOST
        )  # TODO Validate if host is valid ip address + port
        encryption_method = user_input.get(CONF_ENCRYPTION_METHOD)

        async with SagemcomClient(
            host, username, password, EncryptionMethod(encryption_method)
        ) as client:
            await client.login()
            return self.async_create_entry(
                title=host,
                data=user_input,
            )

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input.get(CONF_HOST))
            self._abort_if_unique_id_configured()

            try:
                return await self.async_validate_input(user_input)
            except AccessRestrictionException:
                errors["base"] = "access_restricted"
            except AuthenticationException:
                errors["base"] = "invalid_auth"
            except (TimeoutError, ClientError):
                errors["base"] = "cannot_connect"
            except LoginTimeoutException:
                errors["base"] = "login_timeout"
            except Exception as exception:  # pylint: disable=broad-except
                errors["base"] = "unknown"
                _LOGGER.exception(exception)

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )