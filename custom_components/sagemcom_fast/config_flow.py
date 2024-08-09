"""Config flow for Sagemcom integration."""

from aiohttp import ClientError
from homeassistant import config_entries
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from sagemcom_api.client import SagemcomClient
from sagemcom_api.exceptions import (
    AccessRestrictionException,
    AuthenticationException,
    LoginRetryErrorException,
    LoginTimeoutException,
    MaximumSessionCountException,
    UnsupportedHostException,
)
import voluptuous as vol

from .const import CONF_ENCRYPTION_METHOD, DOMAIN, LOGGER
from .options_flow import OptionsFlow


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sagemcom."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    _host: str | None = None
    _username: str | None = None

    async def async_validate_input(self, user_input):
        """Validate user credentials."""
        self._username = user_input.get(CONF_USERNAME) or ""
        password = user_input.get(CONF_PASSWORD) or ""
        self._host = user_input[CONF_HOST]
        ssl = user_input[CONF_SSL]

        session = async_get_clientsession(self.hass, user_input[CONF_VERIFY_SSL])

        client = SagemcomClient(
            host=self._host,
            username=self._username,
            password=password,
            session=session,
            ssl=ssl,
        )

        user_input[CONF_ENCRYPTION_METHOD] = await client.get_encryption_method()
        LOGGER.debug(
            "Detected encryption method: %s", user_input[CONF_ENCRYPTION_METHOD]
        )

        await client.login()
        await client.logout()

        return self.async_create_entry(
            title=self._host,
            data=user_input,
        )

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input:
            # TODO change to gateway mac address or something more unique
            await self.async_set_unique_id(user_input.get(CONF_HOST))
            self._abort_if_unique_id_configured()

            try:
                return await self.async_validate_input(user_input)
            except AccessRestrictionException:
                errors["base"] = "access_restricted"
            except AuthenticationException:
                errors["base"] = "invalid_auth"
            except (TimeoutError, ClientError, ConnectionError):
                errors["base"] = "cannot_connect"
            except LoginTimeoutException:
                errors["base"] = "login_timeout"
            except MaximumSessionCountException:
                errors["base"] = "maximum_session_count"
            except LoginRetryErrorException:
                errors["base"] = "login_retry_error"
            except UnsupportedHostException:
                errors["base"] = "unsupported_host"
            except Exception as exception:  # pylint: disable=broad-except
                errors["base"] = "unknown"
                LOGGER.exception(exception)

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
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get options flow for this handler."""
        return OptionsFlow(config_entry)
