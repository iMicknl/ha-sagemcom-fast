"""Config flow for Sagemcom integration."""
import logging

from aiohttp import ClientError
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from sagemcom_api.client import SagemcomClient
from sagemcom_api.enums import EncryptionMethod
from sagemcom_api.exceptions import (
    AccessRestrictionException,
    AuthenticationException,
    LoginTimeoutException,
)
import voluptuous as vol

from .const import CONF_ENCRYPTION_METHOD, DOMAIN, OptionsFlow

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
        host = user_input.get(CONF_HOST)
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

        if user_input:
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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlow(config_entries)
