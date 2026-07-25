"""Config flow pour Sentinelle Ecowitt."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    AVAILABLE_MODELS,
    CONF_CROP,
    CONF_ENABLED_MODELS,
    CONF_FALLBACK_HUMIDITY_ENTITY,
    CONF_FALLBACK_RAIN_ENTITY,
    CONF_FALLBACK_TEMP_ENTITY,
    CONF_FALLBACK_WIND_ENTITY,
    CONF_HUMIDITY_ENTITY,
    CONF_LEAF_WETNESS_ENTITY,
    CONF_RAIN_ENTITY,
    CONF_RAIN_PENALTY,
    CONF_STAGE,
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
from .models.crops import GENERIC_CROP, crop_options, stage_options

MODEL_LABELS = {
    MODEL_FROST: "Risque de gel (seuils phénologiques)",
    MODEL_LATE_BLIGHT: "Mildiou (Hutton + Smith)",
    MODEL_POWDERY_MILDEW: "Oïdium (indice Gubler-Thomas)",
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


def _crop_schema(defaults: dict | None = None) -> dict:
    """Culture surveillée : détermine les seuils de gel appliqués."""
    defaults = defaults or {}
    crop = defaults.get(CONF_CROP, GENERIC_CROP)

    schema: dict = {
        vol.Required(CONF_CROP, default=crop): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value=key, label=label)
                    for key, label in crop_options()
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )
    }

    stages = stage_options(crop)
    if stages:
        default_stage = defaults.get(CONF_STAGE) or stages[0][0]
        schema[
            vol.Optional(CONF_STAGE, default=default_stage)
        ] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value=key, label=label)
                    for key, label in stages
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )

    schema[
        vol.Required(CONF_RAIN_PENALTY, default=defaults.get(CONF_RAIN_PENALTY, True))
    ] = selector.BooleanSelector()

    return schema


def _fallback_schema(defaults: dict | None = None) -> dict:
    """Capteurs temps réel d'une station officielle (ex. MeteoSwiss)."""
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
    """Flux en trois étapes : capteurs, culture, sources de secours."""

    VERSION = 3

    def __init__(self) -> None:
        self._data: dict = {}

    async def async_step_user(self, user_input: dict | None = None):
        if user_input is not None:
            name = user_input.pop("name", DEFAULT_NAME)
            await self.async_set_unique_id(f"{DOMAIN}_{name}")
            self._abort_if_unique_id_configured()
            self._data = {"name": name, **user_input}
            return await self.async_step_crop()

        schema = vol.Schema(
            {vol.Required("name", default=DEFAULT_NAME): str, **_ecowitt_schema()}
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_crop(self, user_input: dict | None = None):
        """Culture et stade phénologique de départ."""
        if user_input is not None:
            self._data.update(user_input)
            # Le choix de la culture change la liste des stades : si
            # l'utilisateur en a sélectionné une sans que le formulaire
            # ait pu proposer les stades correspondants, on redemande.
            crop = user_input.get(CONF_CROP, GENERIC_CROP)
            if stage_options(crop) and CONF_STAGE not in user_input:
                return self.async_show_form(
                    step_id="crop", data_schema=vol.Schema(_crop_schema(self._data))
                )
            return await self.async_step_fallback()

        return self.async_show_form(
            step_id="crop", data_schema=vol.Schema(_crop_schema())
        )

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
    """Permet de tout revoir après coup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        schema = vol.Schema(
            {
                **_ecowitt_schema(current),
                **_crop_schema(current),
                **_fallback_schema(current),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
