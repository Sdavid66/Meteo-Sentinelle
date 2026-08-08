"""Intents Assist : interroger le verger à la voix.

Trois questions couvrent l'essentiel de l'usage quotidien :

- « Quels sont les risques au verger ? » — le résumé du plus urgent ;
- « Est-ce que je peux traiter demain ? » — la fenêtre de pulvérisation ;
- « Où en est le pommier ? » — le stade phénologique.

Deux mécanismes distincts sont à l'œuvre, et il vaut la peine de les
séparer clairement.

**Les gestionnaires d'intent** (ce fichier) sont enregistrés auprès de
Home Assistant. Ils bénéficient d'un effet de bord précieux : l'API LLM
d'Assist construit automatiquement un outil par intent enregistré. Un
agent conversationnel adossé à un modèle de langage sait donc s'en
servir sans configuration, à condition que la `description` de chaque
gestionnaire soit explicite — c'est elle que le modèle lit.

**Les phrases** (dossier `sentences/`) servent à l'agent local, celui
qui fonctionne sans modèle de langage. Home Assistant ne les lit que
depuis `custom_sentences/<langue>/` dans le dossier de configuration :
une intégration n'a aucun moyen de les publier depuis son propre
dossier. Elles y sont donc recopiées au démarrage, une seule fois, sans
jamais écraser une version modifiée par l'utilisateur (voir
`sentences.py`).
"""
from __future__ import annotations

import logging
from datetime import timedelta

import voluptuous as vol

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, intent
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    INTENT_RISK,
    INTENT_STAGE,
    INTENT_TREATMENT_WINDOW,
    RISK_LEVELS,
)
from .localize import async_translator
from .tree import match_trees

_LOGGER = logging.getLogger(__name__)

_REGISTERED = f"{DOMAIN}_intents_registered"

#: Ordre de gravité, pour désigner « le plus urgent ».
_SEVERITY = {level: index for index, level in enumerate(RISK_LEVELS)}


def _coordinators(hass: HomeAssistant) -> list:
    return list(hass.data.get(DOMAIN, {}).values())


def _matching_trees(hass: HomeAssistant, name: str | None):
    """(coordinator, subentry_id, tree) pour chaque arbre correspondant."""
    found = []
    for coordinator in _coordinators(hass):
        ids = match_trees(coordinator.trees, name)
        if ids is None:
            ids = list(coordinator.trees)
        for subentry_id in ids:
            tree = coordinator.trees.get(subentry_id)
            if tree is not None:
                found.append((coordinator, subentry_id, tree))
    return found


def _slot(intent_obj: intent.Intent, name: str) -> str | None:
    value = (intent_obj.slots.get(name) or {}).get("value")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class _MeteoSentinelleIntent(intent.IntentHandler):
    """Socle commun : réponse de type « réponse à une question »."""

    @callback
    def _answer(self, intent_obj: intent.Intent, speech: str) -> intent.IntentResponse:
        response = intent_obj.create_response()
        response.response_type = intent.IntentResponseType.QUERY_ANSWER
        response.async_set_speech(speech)
        return response

    def _translator(self, intent_obj: intent.Intent):
        return async_translator(intent_obj.hass, intent_obj.language)


class RiskIntentHandler(_MeteoSentinelleIntent):
    """« Quels sont les risques au verger ? »"""

    intent_type = INTENT_RISK
    description = (
        "Donne le niveau de risque agronomique courant (gel, maladies "
        "fongiques, ravageurs) pour les arbres et cultures surveillés par "
        "Météo Sentinelle. Sans argument, résume le risque le plus élevé "
        "de tout le site."
    )
    slot_schema = {
        vol.Optional("tree"): cv.string,
        vol.Optional("model"): cv.string,
    }

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        hass = intent_obj.hass
        translator = self._translator(intent_obj)
        wanted_tree = _slot(intent_obj, "tree")
        wanted_model = _slot(intent_obj, "model")

        matches = _matching_trees(hass, wanted_tree)
        if not matches:
            return self._answer(intent_obj, translator.text("intent_no_tree"))

        worst: tuple[int, str, str, str] | None = None
        for coordinator, subentry_id, tree in matches:
            results = (coordinator.data or {}).get(subentry_id, {})
            for model, result in results.items():
                if wanted_model and model != wanted_model:
                    continue
                level = getattr(result, "level", None)
                if level is None:
                    continue
                rank = _SEVERITY.get(level, 0)
                if worst is None or rank > worst[0]:
                    worst = (rank, tree.display_name, model, level)

        if worst is None:
            return self._answer(intent_obj, translator.text("intent_no_data"))

        _, tree_name, model, level = worst
        if level == RISK_LEVELS[0]:
            return self._answer(
                intent_obj, translator.text("intent_risk_clear", tree=tree_name)
            )

        return self._answer(
            intent_obj,
            translator.text(
                "intent_risk_worst",
                tree=tree_name,
                model=translator.risk_name(model),
                level=(translator.risk_level(level) or level),
            ),
        )


class TreatmentWindowIntentHandler(_MeteoSentinelleIntent):
    """« Est-ce que je peux traiter demain ? »"""

    intent_type = INTENT_TREATMENT_WINDOW
    description = (
        "Indique s'il est possible de pulvériser un traitement, en "
        "cherchant dans les prévisions horaires un créneau où le vent "
        "reste sous le seuil réglementaire, où il ne pleuvra pas "
        "immédiatement après et où la température est dans la plage "
        "utile. Accepte « aujourd'hui » ou « demain »."
    )
    slot_schema = {vol.Optional("day"): cv.string}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        hass = intent_obj.hass
        translator = self._translator(intent_obj)
        day = (_slot(intent_obj, "day") or "").casefold()

        coordinators = _coordinators(hass)
        if not coordinators:
            return self._answer(intent_obj, translator.text("intent_no_data"))

        advice = getattr(coordinators[0], "spray", None)
        if advice is None or not advice.horizon_hours:
            return self._answer(intent_obj, translator.text("intent_spray_no_forecast"))

        if day == "tomorrow":
            target = dt_util.now().date() + timedelta(days=1)
            windows = [
                w for w in advice.windows if dt_util.as_local(w.start).date() == target
            ]
            if not windows:
                return self._answer(
                    intent_obj, translator.text("intent_spray_none_tomorrow")
                )
            window = windows[0]
            return self._answer(
                intent_obj,
                translator.text(
                    "intent_spray_tomorrow",
                    start=_hour(window.start),
                    end=_hour(window.end),
                ),
            )

        if advice.current is not None:
            return self._answer(
                intent_obj,
                translator.text(
                    "intent_spray_open", end=_hour(advice.current.end)
                ),
            )

        if advice.upcoming is not None:
            return self._answer(
                intent_obj,
                translator.text(
                    "intent_spray_upcoming",
                    start=_moment(advice.upcoming.start),
                    end=_hour(advice.upcoming.end),
                ),
            )

        # Expliquer pourquoi c'est non vaut mieux que dire non : la
        # première raison bloquante suffit à orienter l'utilisateur.
        # `text()` renvoyant la clé quand la traduction manque, on
        # retombe sur un message générique plutôt que de la réciter.
        reason = advice.blocking[0] if advice.blocking else "unknown"
        key = f"intent_spray_blocked_{reason}"
        speech = translator.text(key)
        if speech == key:
            speech = translator.text("intent_spray_blocked_unknown")
        return self._answer(intent_obj, speech)


class StageIntentHandler(_MeteoSentinelleIntent):
    """« Où en est le pommier ? »"""

    intent_type = INTENT_STAGE
    description = (
        "Donne le stade phénologique courant d'un arbre suivi par Météo "
        "Sentinelle, ainsi que le prochain stade attendu et les "
        "degrés-jours qui en séparent."
    )
    slot_schema = {vol.Optional("tree"): cv.string}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        hass = intent_obj.hass
        translator = self._translator(intent_obj)
        matches = _matching_trees(hass, _slot(intent_obj, "tree"))

        if not matches:
            return self._answer(intent_obj, translator.text("intent_no_tree"))

        parts: list[str] = []
        for _coordinator, _subentry_id, tree in matches[:3]:
            stage = translator.stage(tree.stage) or translator.text("stage_not_set")
            parts.append(
                translator.text(
                    "intent_stage", tree=tree.display_name, stage=stage
                )
            )
        return self._answer(intent_obj, " ".join(parts))


def _hour(value) -> str:
    return dt_util.as_local(value).strftime("%H:%M")


def _moment(value) -> str:
    local = dt_util.as_local(value)
    if local.date() == dt_util.now().date():
        return local.strftime("%H:%M")
    return local.strftime("%d/%m %H:%M")


@callback
def async_setup_intents(hass: HomeAssistant) -> None:
    """Enregistre les gestionnaires, une seule fois pour toute l'instance."""
    if hass.data.get(_REGISTERED):
        return
    for handler in (
        RiskIntentHandler(),
        TreatmentWindowIntentHandler(),
        StageIntentHandler(),
    ):
        intent.async_register(hass, handler)
    hass.data[_REGISTERED] = True
    _LOGGER.debug("Intents Météo Sentinelle enregistrés")
