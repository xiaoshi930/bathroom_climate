"""Config flow for bathroom_climate integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
)

from .const import (
    CONF_FAN_SWITCH,
    CONF_HEAT_SWITCH,
    CONF_TEMP_SENSOR,
    CONF_VENT_SWITCH,
    DEFAULT_NAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class BathroomClimateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for bathroom_climate."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            return self.async_create_entry(
                title=user_input.get("name", DEFAULT_NAME),
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default="浴霸"): str,
                    vol.Required(CONF_HEAT_SWITCH): EntitySelector(
                        EntitySelectorConfig(domain="switch")
                    ),
                    vol.Required(CONF_FAN_SWITCH): EntitySelector(
                        EntitySelectorConfig(domain="switch")
                    ),
                    vol.Required(CONF_VENT_SWITCH): EntitySelector(
                        EntitySelectorConfig(domain="switch")
                    ),
                    vol.Required(CONF_TEMP_SENSOR): EntitySelector(
                        EntitySelectorConfig(domain="sensor")
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> BathroomClimateOptionsFlow:
        """Get the options flow for this handler."""
        return BathroomClimateOptionsFlow(config_entry)


class BathroomClimateOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for bathroom_climate."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HEAT_SWITCH,
                        default=self._config_entry.data.get(CONF_HEAT_SWITCH),
                    ): EntitySelector(EntitySelectorConfig(domain="switch")),
                    vol.Required(
                        CONF_FAN_SWITCH,
                        default=self._config_entry.data.get(CONF_FAN_SWITCH),
                    ): EntitySelector(EntitySelectorConfig(domain="switch")),
                    vol.Required(
                        CONF_VENT_SWITCH,
                        default=self._config_entry.data.get(CONF_VENT_SWITCH),
                    ): EntitySelector(EntitySelectorConfig(domain="switch")),
                    vol.Required(
                        CONF_TEMP_SENSOR,
                        default=self._config_entry.data.get(CONF_TEMP_SENSOR),
                    ): EntitySelector(EntitySelectorConfig(domain="sensor")),
                }
            ),
        )
