"""Config flow for Sagemcom integration."""

from dataclasses import dataclass
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

from .const import CONF_ENCRYPTION_METHOD, DOMAIN, LOGGER
from .options_flow import OptionsFlow


@dataclass(frozen=True, slots=True)
class SagemcomConfigFlowValidationResult:
    """Result of validating config flow input against a gateway."""

    title: str
    data: dict[str, Any]
    serial_number: str | None
    mac_address: str


async def async_validate_input(
    hass: HomeAssistant, user_input: dict[str, Any]
) -> SagemcomConfigFlowValidationResult:
    """Validate user credentials and collect the gateway identity."""
    data = user_input.copy()
    username = data.get(CONF_USERNAME) or ""
    password = data.get(CONF_PASSWORD) or ""
    data[CONF_USERNAME] = username
    data[CONF_PASSWORD] = password
    host = data[CONF_HOST]

    session = async_get_clientsession(hass, data[CONF_VERIFY_SSL])
    client = SagemcomClient(
        host=host,
        username=username,
        password=password,
        session=session,
        ssl=data[CONF_SSL],
    )

    data[CONF_ENCRYPTION_METHOD] = await client.get_encryption_method()
    LOGGER.debug("Detected encryption method: %s", data[CONF_ENCRYPTION_METHOD])

    await client.login()
    try:
        gateway = await client.get_device_info()
    finally:
        await client.logout()

    return SagemcomConfigFlowValidationResult(
        title=host,
        data=data,
        serial_number=gateway.serial_number,
        mac_address=gateway.mac_address,
    )


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sagemcom."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    _host: str | None = None
    _username: str | None = None

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input:
            self._host = user_input[CONF_HOST]
            self._username = user_input.get(CONF_USERNAME) or ""

            # TODO change to gateway mac address or something more unique
            await self.async_set_unique_id(user_input.get(CONF_HOST))
            self._abort_if_unique_id_configured()

            try:
                validation_result = await async_validate_input(self.hass, user_input)
                return self.async_create_entry(
                    title=validation_result.title,
                    data=validation_result.data,
                )
            except AccessRestrictionException:
                errors["base"] = "access_restricted"
            except AuthenticationException:
                errors["base"] = "invalid_auth"
            except (
                TimeoutError,
                ClientError,
                ConnectionError,
                LoginConnectionException,
            ):
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
            description_placeholders={
                "supported_devices_url": "https://github.com/iMicknl/ha-sagemcom-fast#supported-devices"
            },
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get options flow for this handler."""
        return OptionsFlow(config_entry)
