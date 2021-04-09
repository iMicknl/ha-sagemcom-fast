"""Options flow for Sagemcom integration."""

from homeassistant import config_entries
from homeassistant.const import CONF_SCAN_INTERVAL
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from .const import DEFAULT_SCAN_INTERVAL, MIN_SCAN_INTERVAL


class OptionsFlow(config_entries.OptionsFlow):
    """Handle a options flow for Sagemcom."""

    def __init__(self, config_entry):
        """Initialize Sagemcom options flow."""
        self._options = dict(config_entry.options)

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(cv.positive_int, vol.Clamp(min=MIN_SCAN_INTERVAL))
                }
            ),
        )
