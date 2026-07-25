"""Config flow pour Météo Sentinelle.

L'entrée principale porte ce qui est **commun au site** : capteurs,
prévisions, sources de secours, alertes. Chaque **arbre surveillé** est
une sous-entrée, ajoutée depuis le bouton « Ajouter un arbre » de la
page de l'intégration. Les capteurs et la météo restent donc partagés
— une seule requête de prévisions pour tout le verger.
"""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    AVAILABLE_MODELS,
    CONF_AUTO_ADVANCE,
    CONF_CROP,
    CONF_ENABLED_MODELS,
    CONF_FALLBACK_HUMIDITY_ENTITY,
    CONF_FALLBACK_RAIN_ENTITY,
    CONF_FALLBACK_TEMP_ENTITY,
    CONF_FALLBACK_WIND_ENTITY,
    CONF_GDD_OFFSET,
    CONF_HUMIDITY_ENTITY,
    CONF_LEAF_WETNESS_ENTITY,
    CONF_NOTIFICATIONS,
    CONF_RAIN_ENTITY,
    CONF_RAIN_PENALTY,
    CONF_STAGE,
    CONF_TEMP_ENTITY,
    CONF_TREE_NAME,
    CONF_WEATHER_ENTITY,
    CONF_WIND_ENTITY,
    DEFAULT_AUTO_ADVANCE,
    DEFAULT_ENABLED_MODELS,
    DEFAULT_GDD_OFFSET,
    DEFAULT_NAME,
    DEFAULT_NOTIFICATIONS,
    DOMAIN,
    MODEL_FROST,
    MODEL_LATE_BLIGHT,
    MODEL_POWDERY_MILDEW,
    SUBENTRY_TYPE_TREE,
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


def _site_schema(defaults: dict | None = None) -> dict:
    """Capteurs du site + prévisions + modèles + alertes."""
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

    schema[
        vol.Required(CONF_RAIN_PENALTY, default=defaults.get(CONF_RAIN_PENALTY, True))
    ] = selector.BooleanSelector()

    schema[
        vol.Required(
            CONF_NOTIFICATIONS,
            default=defaults.get(CONF_NOTIFICATIONS, DEFAULT_NOTIFICATIONS),
        )
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


def _tree_schema(crop: str | None = None, defaults: dict | None = None) -> vol.Schema:
    """Formulaire d'un arbre. Les stades dépendent de l'espèce choisie."""
    defaults = defaults or {}
    crop = crop or defaults.get(CONF_CROP) or GENERIC_CROP

    schema: dict = {
        vol.Required(
            CONF_TREE_NAME, default=defaults.get(CONF_TREE_NAME, "")
        ): selector.TextSelector(),
        vol.Required(CONF_CROP, default=crop): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value=key, label=label)
                    for key, label in crop_options()
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
    }

    stages = stage_options(crop)
    if stages:
        default_stage = defaults.get(CONF_STAGE) or stages[0][0]
        schema[vol.Required(CONF_STAGE, default=default_stage)] = (
            selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=key, label=label)
                        for key, label in stages
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        )
        schema[
            vol.Required(
                CONF_AUTO_ADVANCE,
                default=defaults.get(CONF_AUTO_ADVANCE, DEFAULT_AUTO_ADVANCE),
            )
        ] = selector.BooleanSelector()
        schema[
            vol.Optional(
                CONF_GDD_OFFSET,
                default=defaults.get(CONF_GDD_OFFSET, DEFAULT_GDD_OFFSET),
            )
        ] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=-300, max=300, step=10, mode=selector.NumberSelectorMode.BOX
            )
        )

    return vol.Schema(schema)


class MeteoSentinelleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configuration du site, puis ajout des arbres en sous-entrées."""

    VERSION = 4

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
            {vol.Required("name", default=DEFAULT_NAME): str, **_site_schema()}
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

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: config_entries.ConfigEntry
    ) -> dict[str, type[config_entries.ConfigSubentryFlow]]:
        """Expose le bouton « Ajouter un arbre » sur la page d'intégration."""
        return {SUBENTRY_TYPE_TREE: TreeSubentryFlowHandler}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        # Depuis Home Assistant 2024.11, la classe de base fournit
        # self.config_entry : lui repasser l'entrée est déprécié.
        return MeteoSentinelleOptionsFlow()


class TreeSubentryFlowHandler(config_entries.ConfigSubentryFlow):
    """Ajout / modification d'un arbre surveillé.

    Le formulaire est présenté deux fois lorsque l'espèce change : la
    liste des stades dépend de l'espèce, et Home Assistant ne sait pas
    reconstruire dynamiquement un schéma en cours de saisie.
    """

    def __init__(self) -> None:
        self._crop: str | None = None

    async def async_step_user(self, user_input: dict | None = None):
        return await self.async_step_tree(user_input)

    async def async_step_tree(self, user_input: dict | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            crop = user_input.get(CONF_CROP, GENERIC_CROP)
            stages = stage_options(crop)

            # L'espèce a changé depuis l'affichage : on réaffiche le
            # formulaire avec les stades correspondants.
            if stages and CONF_STAGE not in user_input:
                self._crop = crop
                return self.async_show_form(
                    step_id="tree",
                    data_schema=_tree_schema(crop, user_input),
                    errors=errors,
                )

            name = (user_input.get(CONF_TREE_NAME) or "").strip()
            if not name:
                from .models.crops import CROPS

                entry = CROPS.get(crop)
                name = entry.label if entry else "Culture"
                user_input[CONF_TREE_NAME] = name

            return self.async_create_entry(title=name, data=user_input)

        return self.async_show_form(
            step_id="tree", data_schema=_tree_schema(self._crop), errors=errors
        )

    async def async_step_reconfigure(self, user_input: dict | None = None):
        """Modification d'un arbre existant."""
        subentry = self._get_reconfigure_subentry()

        if user_input is not None:
            crop = user_input.get(CONF_CROP, GENERIC_CROP)
            stages = stage_options(crop)
            if stages and CONF_STAGE not in user_input:
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=_tree_schema(crop, user_input),
                )
            return self.async_update_and_abort(
                self._get_entry(),
                subentry,
                data=user_input,
                title=user_input.get(CONF_TREE_NAME) or subentry.title,
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_tree_schema(subentry.data.get(CONF_CROP), dict(subentry.data)),
        )


class MeteoSentinelleOptionsFlow(config_entries.OptionsFlow):
    """Réglages communs au site (les arbres se gèrent en sous-entrées)."""

    async def async_step_init(self, user_input: dict | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        schema = vol.Schema(
            {**_site_schema(current), **_fallback_schema(current)}
        )
        return self.async_show_form(step_id="init", data_schema=schema)
