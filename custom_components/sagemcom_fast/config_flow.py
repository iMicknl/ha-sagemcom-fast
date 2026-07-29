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
from homeassistant.helpers.device_registry import format_mac
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

from .const import (
    CONF_ENCRYPTION_METHOD,
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    GATEWAY_UNIQUE_ID_MAC_PREFIX,
    GATEWAY_UNIQUE_ID_SERIAL_PREFIX,
    LOGGER,
)
from .options_flow import OptionsFlow


@dataclass(frozen=True, slots=True)
class SagemcomConfigFlowValidationResult:
    """Result of validating config flow input against a gateway."""

    title: str
    data: dict[str, Any]
    serial_number: str | None
    mac_address: str


def gateway_unique_id(
    *, serial_number: str | None, mac_address: str | None
) -> str | None:
    """Return a namespaced stable gateway identity, preferring its MAC."""
    if mac_address and (normalized_mac := format_mac(mac_address.strip())):
        return f"{GATEWAY_UNIQUE_ID_MAC_PREFIX}:{normalized_mac}"

    if serial_number and (normalized_serial := serial_number.strip()):
        return f"{GATEWAY_UNIQUE_ID_SERIAL_PREFIX}:{normalized_serial}"

    return None


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

    VERSION = CONFIG_ENTRY_VERSION
    MINOR_VERSION = CONFIG_ENTRY_MINOR_VERSION
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    _host: str | None = None
    _username: str | None = None

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input:
            self._host = user_input[CONF_HOST]
            self._username = user_input.get(CONF_USERNAME) or ""

            try:
                validation_result = await async_validate_input(self.hass, user_input)
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
            else:
                unique_id = gateway_unique_id(
                    serial_number=validation_result.serial_number,
                    mac_address=validation_result.mac_address,
                )
                if unique_id is None:
                    errors["base"] = "unknown"
                else:
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=validation_result.title,
                        data=validation_result.data,
                    )

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

    async def async_step_reauth(self, user_input=None):
        """Start reauthentication for the linked config entry."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Validate replacement credentials for the linked config entry."""
        errors = {}
        reauth_entry = self._get_reauth_entry()

        if user_input:
            validation_input = {**reauth_entry.data, **user_input}

            try:
                validation_result = await async_validate_input(
                    self.hass,
                    validation_input,
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
            else:
                unique_id = gateway_unique_id(
                    serial_number=validation_result.serial_number,
                    mac_address=validation_result.mac_address,
                )
                if unique_id is None:
                    errors["base"] = "unknown"
                else:
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_mismatch(reason="wrong_device")
                    return self.async_update_reload_and_abort(
                        reauth_entry,
                        data_updates={
                            CONF_USERNAME: validation_result.data[CONF_USERNAME],
                            CONF_PASSWORD: validation_result.data[CONF_PASSWORD],
                            CONF_ENCRYPTION_METHOD: validation_result.data[
                                CONF_ENCRYPTION_METHOD
                            ],
                        },
                    )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=reauth_entry.data.get(CONF_USERNAME, ""),
                    ): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get options flow for this handler."""
        return OptionsFlow(config_entry)
