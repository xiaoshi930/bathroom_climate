"""Bathroom Climate platform for HA climate integration."""
from __future__ import annotations

import logging

from homeassistant.components.climate import (
    ClimateEntity,
    HVACMode,
    HVACAction,
    ClimateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_FAN_SWITCH,
    CONF_HEAT_SWITCH,
    CONF_TEMP_SENSOR,
    CONF_VENT_SWITCH,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

SUPPORTED_HVAC_MODES = [
    HVACMode.OFF,
    HVACMode.HEAT,
    HVACMode.FAN_ONLY,
    HVACMode.DRY,
]

SUPPORTED_FEATURES = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.TURN_OFF
    | ClimateEntityFeature.TURN_ON
)

HEAT_HYSTERESIS = 5.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up bathroom_climate climate platform."""
    data = entry.data
    async_add_entities(
        [
            BathroomClimateEntity(
                name=entry.title,
                heat_switch=data[CONF_HEAT_SWITCH],
                fan_switch=data[CONF_FAN_SWITCH],
                vent_switch=data[CONF_VENT_SWITCH],
                temp_sensor=data[CONF_TEMP_SENSOR],
                entry_id=entry.entry_id,
            )
        ]
    )


class BathroomClimateEntity(ClimateEntity, RestoreEntity):
    """Bathroom Climate entity that maps bathroom heater switches to a climate entity."""

    _attr_hvac_modes = SUPPORTED_HVAC_MODES
    _attr_supported_features = SUPPORTED_FEATURES
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 20.0
    _attr_max_temp = 50.0
    _attr_target_temperature_step = 1.0

    def __init__(
        self,
        name: str,
        heat_switch: str,
        fan_switch: str,
        vent_switch: str,
        temp_sensor: str,
        entry_id: str,
    ) -> None:
        """Initialize the climate entity."""
        self._attr_name = name
        self._attr_unique_id = entry_id
        self._heat_switch = heat_switch
        self._fan_switch = fan_switch
        self._vent_switch = vent_switch
        self._temp_sensor = temp_sensor

        self._target_temp: float | None = 50.0
        self._current_temp: float | None = None
        self._hvac_mode: HVACMode = HVACMode.OFF

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()

        # Restore previous state
        last_state = await self.async_get_last_state()
        if last_state is not None:
            if last_state.attributes.get(ATTR_TEMPERATURE) is not None:
                self._target_temp = float(last_state.attributes[ATTR_TEMPERATURE])
            if last_state.state in [mode.value for mode in HVACMode]:
                self._hvac_mode = HVACMode(last_state.state)

        # Listen for temperature sensor changes
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [self._temp_sensor],
                self._async_temp_changed,
            )
        )

        # Listen for switch state changes (for syncing)
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [self._heat_switch, self._fan_switch, self._vent_switch],
                self._async_switch_changed,
            )
        )

        # Read initial temperature
        temp_state = self.hass.states.get(self._temp_sensor)
        if temp_state and temp_state.state not in ("unknown", "unavailable"):
            try:
                self._current_temp = float(temp_state.state)
            except (ValueError, TypeError):
                pass

    @callback
    def _async_temp_changed(self, event) -> None:
        """Handle temperature sensor changes."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in ("unknown", "unavailable"):
            return
        try:
            self._current_temp = float(new_state.state)
        except (ValueError, TypeError):
            return

        # Check heat mode hysteresis
        self._check_heat_hysteresis()
        self.async_write_ha_state()

    @callback
    def _async_switch_changed(self, event) -> None:
        """Handle switch state changes - sync hvac_mode from physical switch changes."""
        # Re-evaluate the hvac_action based on switch states
        self.async_write_ha_state()

    def _check_heat_hysteresis(self) -> None:
        """In heat mode, turn off heating when current temp exceeds target by 5 degrees."""
        if (
            self._hvac_mode != HVACMode.HEAT
            or self._current_temp is None
            or self._target_temp is None
        ):
            return

        if self._current_temp >= self._target_temp + HEAT_HYSTERESIS:
            _LOGGER.debug(
                "Bathroom climate: current temp %.1f >= target %.1f + %d, turning off heat",
                self._current_temp,
                self._target_temp,
                int(HEAT_HYSTERESIS),
            )
            # Turn off heating but keep fan on (still in heat mode concept, but heater off)
            self.hass.async_create_task(
                self.hass.services.async_call(
                    "switch",
                    "turn_off",
                    target={"entity_id": self._heat_switch},
                )
            )

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._current_temp

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        return self._target_temp

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        return self._hvac_mode

    @property
    def hvac_action(self) -> HVACAction:
        """Return the current HVAC action."""
        if self._hvac_mode == HVACMode.OFF:
            return HVACAction.OFF

        heat_on = self._is_switch_on(self._heat_switch)
        fan_on = self._is_switch_on(self._fan_switch)
        vent_on = self._is_switch_on(self._vent_switch)

        if self._hvac_mode == HVACMode.HEAT:
            if heat_on and fan_on:
                return HVACAction.HEATING
            if fan_on:
                return HVACAction.FAN
            return HVACAction.IDLE

        if self._hvac_mode == HVACMode.FAN_ONLY:
            return HVACAction.FAN if fan_on else HVACAction.IDLE

        if self._hvac_mode == HVACMode.DRY:
            return HVACAction.DRYING if vent_on else HVACAction.IDLE

        return HVACAction.IDLE

    def _is_switch_on(self, entity_id: str) -> bool:
        """Check if a switch is on."""
        state = self.hass.states.get(entity_id)
        return state is not None and state.state == "on"

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode."""
        if hvac_mode not in SUPPORTED_HVAC_MODES:
            return

        # First turn off all switches
        await self._async_turn_off_all()

        self._hvac_mode = hvac_mode

        # Turn on appropriate switches for the new mode
        if hvac_mode == HVACMode.HEAT:
            await self._async_turn_on(self._heat_switch)
            await self._async_turn_on(self._fan_switch)
        elif hvac_mode == HVACMode.FAN_ONLY:
            await self._async_turn_on(self._fan_switch)
        elif hvac_mode == HVACMode.DRY:
            await self._async_turn_on(self._vent_switch)

        # Check heat hysteresis after mode change
        self._check_heat_hysteresis()
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs) -> None:
        """Set the target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            self._target_temp = float(temperature)
            # Check heat hysteresis with new target
            self._check_heat_hysteresis()
            self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        """Turn on the climate entity (default to heat mode)."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        """Turn off the climate entity."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def _async_turn_off_all(self) -> None:
        """Turn off all switches."""
        for switch_id in (self._heat_switch, self._fan_switch, self._vent_switch):
            await self.hass.services.async_call(
                "switch",
                "turn_off",
                target={"entity_id": switch_id},
            )

    async def _async_turn_on(self, entity_id: str) -> None:
        """Turn on a switch."""
        await self.hass.services.async_call(
            "switch",
            "turn_on",
            target={"entity_id": entity_id},
        )
