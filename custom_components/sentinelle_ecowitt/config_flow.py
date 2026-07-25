"""Config flow pour Sentinelle Ecowitt."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    AVAILABLE_MODELS,
    CONF_ENABLED_MODELS,
    CONF_HUMIDITY_ENTITY,
    CONF_LEAF_WETNESS_ENTITY,
    CONF_RAIN_ENTITY,
    CONF_TEMP_ENTITY,
    CONF_WEATHER_ENTITY,
    CONF_WIND_ENTITY,
    DEFAULT_ENABLED_MODELS,
    DEFAULT_NAME,
    DOMAIN,
    MODEL_FROST,
    MODEL_LATE_BLIGHT,
    MODEL_POWDERY_MILDEW,
)

MODEL_LABELS = {
    MODEL_FROST: "Risque de gel",
    MODEL_LATE_BLIGHT: "Mildiou (modèle Smith simplifié)",
    MODEL_POWDERY_MILDEW: "Oïdium",
}


def _entities_schema(defaults: dict | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_TEMP_ENTITY, default=defaults.get(CONF_TEMP_ENTITY)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(device_class="temperature")
            ),
            vol.Required(
                CONF_HUMIDITY_ENTITY, default=defaults.get(CONF_HUMIDITY_ENTITY)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(device_class="humidity")
            ),
            vol.Optional(
                CONF_WIND_ENTITY, default=defaults.get(CONF_WIND_ENTITY)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(device_class="wind_speed")
            ),
            vol.Optional(
                CONF_RAIN_ENTITY, default=defaults.get(CONF_RAIN_ENTITY)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_LEAF_WETNESS_ENTITY,
                default=defaults.get(CONF_LEAF_WETNESS_ENTITY),
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Required(
                CONF_WEATHER_ENTITY, default=defaults.get(CONF_WEATHER_ENTITY)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="weather")),
            vol.Required(
                CONF_ENABLED_MODELS,
                default=defaults.get(CONF_ENABLED_MODELS, DEFAULT_ENABLED_MODELS),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=key, label=MODEL_LABELS[key])
                        for key in AVAILABLE_MODELS
                    ],
                    multiple=True,
                )
            ),
        }
    )


class EcowittPlantGuardConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Gère le flux de configuration initial."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input.pop("name", DEFAULT_NAME)
            await self.async_set_unique_id(f"{DOMAIN}_{name}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=name, data=user_input)

        schema = vol.Schema({vol.Required("name", default=DEFAULT_NAME): str}).extend(
            _entities_schema().schema
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return EcowittPlantGuardOptionsFlow(config_entry)


class EcowittPlantGuardOptionsFlow(config_entries.OptionsFlow):
    """Permet de changer les entités / modèles activés après coup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init", data_schema=_entities_schema(current)
        )
