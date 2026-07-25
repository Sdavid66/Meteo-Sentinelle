"""Config flow pour Sentinelle Ecowitt."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    AVAILABLE_MODELS,
    CONF_ENABLED_MODELS,
    CONF_FALLBACK_HUMIDITY_ENTITY,
    CONF_FALLBACK_RAIN_ENTITY,
    CONF_FALLBACK_TEMP_ENTITY,
    CONF_FALLBACK_WIND_ENTITY,
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


def _optional_entity(key: str, defaults: dict, **selector_kwargs):
    """Sélecteur d'entité facultatif, sans valeur par défaut fantôme."""
    if defaults.get(key):
        marker = vol.Optional(key, default=defaults[key])
    else:
        marker = vol.Optional(key)
    return marker, selector.EntitySelector(
        selector.EntitySelectorConfig(**selector_kwargs)
    )


def _ecowitt_schema(defaults: dict | None = None) -> dict:
    """Capteurs de la station personnelle (Ecowitt) + prévisions."""
    defaults = defaults or {}
    schema: dict = {
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
    }

    for key, kwargs in (
        (CONF_WIND_ENTITY, {"device_class": "wind_speed"}),
        (CONF_RAIN_ENTITY, {"domain": "sensor"}),
        (CONF_LEAF_WETNESS_ENTITY, {"domain": "sensor"}),
    ):
        marker, sel = _optional_entity(key, defaults, **kwargs)
        schema[marker] = sel

    schema[
        vol.Required(CONF_WEATHER_ENTITY, default=defaults.get(CONF_WEATHER_ENTITY))
    ] = selector.EntitySelector(selector.EntitySelectorConfig(domain="weather"))

    schema[
        vol.Required(
            CONF_ENABLED_MODELS,
            default=defaults.get(CONF_ENABLED_MODELS, DEFAULT_ENABLED_MODELS),
        )
    ] = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value=key, label=MODEL_LABELS[key])
                for key in AVAILABLE_MODELS
            ],
            multiple=True,
        )
    )
    return schema


def _fallback_schema(defaults: dict | None = None) -> dict:
    """Capteurs temps réel d'une station officielle (ex. MeteoSwiss).

    Tous facultatifs : ils servent uniquement de secours quand la mesure
    Ecowitt correspondante est absente ou indisponible.
    """
    defaults = defaults or {}
    schema: dict = {}
    for key, kwargs in (
        (CONF_FALLBACK_TEMP_ENTITY, {"device_class": "temperature"}),
        (CONF_FALLBACK_HUMIDITY_ENTITY, {"device_class": "humidity"}),
        (CONF_FALLBACK_WIND_ENTITY, {"device_class": "wind_speed"}),
        (CONF_FALLBACK_RAIN_ENTITY, {"domain": "sensor"}),
    ):
        marker, sel = _optional_entity(key, defaults, **kwargs)
        schema[marker] = sel
    return schema


class SentinelleEcowittConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Flux de configuration en deux étapes : station perso, puis secours."""

    VERSION = 2

    def __init__(self) -> None:
        self._data: dict = {}

    async def async_step_user(self, user_input: dict | None = None):
        if user_input is not None:
            name = user_input.pop("name", DEFAULT_NAME)
            await self.async_set_unique_id(f"{DOMAIN}_{name}")
            self._abort_if_unique_id_configured()
            self._data = {"name": name, **user_input}
            return await self.async_step_fallback()

        schema = vol.Schema(
            {vol.Required("name", default=DEFAULT_NAME): str, **_ecowitt_schema()}
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_fallback(self, user_input: dict | None = None):
        """Étape facultative : sources de secours (MeteoSwiss ou autre)."""
        if user_input is not None:
            name = self._data.pop("name", DEFAULT_NAME)
            return self.async_create_entry(
                title=name, data={**self._data, **user_input}
            )

        return self.async_show_form(
            step_id="fallback", data_schema=vol.Schema(_fallback_schema())
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SentinelleEcowittOptionsFlow(config_entry)


class SentinelleEcowittOptionsFlow(config_entries.OptionsFlow):
    """Permet de changer les entités / modèles activés après coup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        schema = vol.Schema(
            {**_ecowitt_schema(current), **_fallback_schema(current)}
        )
        return self.async_show_form(step_id="init", data_schema=schema)
