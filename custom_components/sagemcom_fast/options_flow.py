"""Options flow for Sagemcom integration."""

from homeassistant import config_entries
from homeassistant.const import CONF_SCAN_INTERVAL
import voluptuous as vol

SCAN_INTERVAL = 10


class OptionsFlow(config_entries.OptionsFlow):
    """Handle a options flow for Sagemcom."""

    def __init__(self, config_entry):
        """Initialize Sagecom options flow."""
        self._config_entry = config_entry
        self.options = dict(config_entry.options)

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            self.options[CONF_SCAN_INTERVAL] = user_input[CONF_SCAN_INTERVAL]
            return self.async_create_entry(title="", data=self.options)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self._config_entry.options.get(
                            CONF_SCAN_INTERVAL, SCAN_INTERVAL
                        ),
                    ): int
                }
            ),
        )
