"""Config flow for Sagemcom integration."""
import logging

import voluptuous as vol
from homeassistant import config_entries, core, exceptions
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_HOST, HTTP_BAD_REQUEST
from homeassistant.core import callback
from homeassistant.components import ssdp
from .const import CONF_ENCRYPTION_METHOD, CONF_TRACK_WIRELESS_CLIENTS, CONF_TRACK_WIRED_CLIENTS, DOMAIN
from sagemcom_api import SagemcomClient, EncryptionMethod

_LOGGER = logging.getLogger(__name__)

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sagemcom."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlow(config_entry)

    def __init__(self):
        """Initialize."""

        encryption_methods = [str(item.value) for item in EncryptionMethod]

        self.data_schema = {
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Required(CONF_ENCRYPTION_METHOD): vol.In(encryption_methods)
        }

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        await self.async_set_unique_id(user_input[CONF_HOST])
        self._abort_if_unique_id_configured()

        if user_input is not None:
            try:
                validation = await validate_input(self.hass, user_input)
                return self.async_create_entry(title=validation["title"], data=user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.error(
                    "Unknown error connecting with Sagemcom F@st at %s",
                    user_input[CONF_HOST],
                )
                errors["base"] = "unknown"
                return self.async_abort(reason="unknown")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(self.data_schema),
            errors=errors or {}
        )

    async def async_step_unignore(self, user_input):
        unique_id = user_input[CONF_HOST]
        await self.async_set_unique_id(unique_id)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(self.data_schema),
            errors={}
        )

    async def async_step_ssdp(self, discovery_info):
        """Handle SSDP initiated config flow."""
        _LOGGER.warning(f'Found discovery {discovery_info[ssdp.ATTR_SSDP_LOCATION]}')
        _LOGGER.warning(discovery_info)

        # if any(
        #     url == flow["context"].get(CONF_URL) for flow in self._async_in_progress()
        # ):
        #     return self.async_abort(reason="already_in_progress")

        # user_input = {CONF_URL: url}
        # if self._already_configured(user_input):
        #     return self.async_abort(reason="already_configured")

        return await self._async_show_user_form()

class OptionsFlow(config_entries.OptionsFlow):
    """Handle Sagemcom F@st options."""

    def __init__(self, config_entry):
        """Initialize Sagemcom F@st options flow."""
        self.config_entry = config_entry
        self.options = dict(config_entry.options)

        # Set default
        if self.options[CONF_TRACK_WIRELESS_CLIENTS] is None: 
            self.options[CONF_TRACK_WIRELESS_CLIENTS] = True

        if self.options[CONF_TRACK_WIRED_CLIENTS] is None: 
            self.options[CONF_TRACK_WIRED_CLIENTS] = True

    async def async_step_init(self, user_input=None):
        """Manage the UniFi options."""
        
        # if self.show_advanced_options:
        #     return await self.async_step_device_tracker()

        return await self.async_step_simple_options()

    async def async_step_simple_options(self, user_input=None):
        """For simple Jack."""
        if user_input is not None:
            self.options.update(user_input)
            return await self._update_options()

        return self.async_show_form(
            step_id="simple_options",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_TRACK_WIRELESS_CLIENTS,
                        default=self.options[CONF_TRACK_WIRELESS_CLIENTS],
                    ): bool,
                    vol.Optional(
                        CONF_TRACK_WIRED_CLIENTS,
                        default=self.options[CONF_TRACK_WIRED_CLIENTS],
                    ): bool
                }
            ),
        )

    async def _update_options(self):
        """Update config entry options."""
        return self.async_create_entry(title="", data=self.options)

async def validate_input(hass: core.HomeAssistant, data):
    """Validate the user input allows us to connect.

    Data has the keys from DATA_SCHEMA with values provided by the user.
    """

    host = data[CONF_HOST]  # TODO Validate if host is valid ip address
    username = data[CONF_USERNAME]
    password = data[CONF_PASSWORD]
    encryption_method = data[CONF_ENCRYPTION_METHOD]

    # Choose EncryptionMethod.MD5, EncryptionMethod.SHA512 or EncryptionMethod.Unknown
    sagemcom = SagemcomClient(host, username, password, EncryptionMethod.MD5)

    logged_in = await sagemcom.login()

    # TODO Throw CannotConnect or raise InvalidAuth based on Sagemcom acceptions
    if not logged_in:
        raise InvalidAuth

    # Return info that you want to store in the config entry.
    return {"title": f"{host}"}


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""
