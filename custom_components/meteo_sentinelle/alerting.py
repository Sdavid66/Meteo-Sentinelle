"""Alertes : événements Home Assistant et notifications persistantes.

Deux niveaux, volontairement séparés :

- **Événements** (`meteo_sentinelle_risk_changed`,
  `meteo_sentinelle_stage_advanced`) — le mécanisme de base. Ils ne
  supposent rien du canal choisi et servent de déclencheur à n'importe
  quelle automatisation, dont le blueprint fourni.
- **Notifications persistantes** — activées par défaut pour que le
  plugin soit utile sans configuration, désactivables dans les options
  pour ceux qui préfèrent router vers leur téléphone.

Une alerte n'est émise qu'au **changement** de niveau, et seulement à
partir de « alerte ». Répéter « risque sévère » toutes les 15 minutes
apprendrait vite à l'utilisateur à ignorer le plugin.
"""
from __future__ import annotations

import logging

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    EVENT_RISK_CHANGED,
    EVENT_STAGE_ADVANCED,
    MODEL_FROST,
    MODEL_LATE_BLIGHT,
    MODEL_POWDERY_MILDEW,
    PEST_MODELS,
    RISK_LEVELS,
    RISK_SEVERE,
    RISK_WARNING,
)
from .localize import Translator

_LOGGER = logging.getLogger(__name__)

#: Chaque modèle emprunte son intitulé au capteur correspondant, déjà
#: traduit : « Risque de gel » / « Frost risk ». Une table de libellés en
#: dur ici retomberait dans le travers d'une seule langue.
#:
#: La convention « <modèle>_risk » vaut pour tous les modèles, y compris
#: les ravageurs : la table n'existe plus que pour la documenter.
MODEL_ENTITY_KEYS = {
    MODEL_FROST: "frost_risk",
    MODEL_LATE_BLIGHT: "late_blight_risk",
    MODEL_POWDERY_MILDEW: "powdery_mildew_risk",
}


def _entity_key(model: str) -> str:
    return MODEL_ENTITY_KEYS.get(model, f"{model}_risk")

#: Niveaux justifiant une notification (les autres restent en événement).
NOTIFY_LEVELS = {RISK_WARNING, RISK_SEVERE}


def _rank(level: str) -> int:
    try:
        return RISK_LEVELS.index(level)
    except ValueError:
        return 0


def _frost_detail(result, tr: Translator) -> str:
    """Phrase explicative pour une alerte gel, avec le contexte utile."""
    parts: list[str] = []
    reference = getattr(result, "reference_min", None)
    if reference is not None:
        key = (
            "detail_frost_min_ground"
            if getattr(result, "reference", "air") == "surface"
            else "detail_frost_min_air"
        )
        parts.append(tr.text(key, temperature=f"{reference:.1f}"))
    t10 = getattr(result, "t10", None)
    if t10 is not None:
        parts.append(tr.text("detail_frost_threshold", temperature=f"{t10:.1f}"))
    when = getattr(result, "next_frost_time", None)
    if when is not None:
        parts.append(tr.text("detail_frost_time", time=when.strftime("%d/%m %H:%M")))
    return ", ".join(parts)


def _disease_detail(model: str, result, tr: Translator) -> str:
    if model == MODEL_LATE_BLIGHT:
        bits = []
        if getattr(result, "hutton_met", False):
            bits.append(tr.text("detail_blight_hutton"))
        elif getattr(result, "hutton_consecutive_days", 0):
            bits.append(tr.text("detail_blight_one_day"))
        hours = getattr(result, "last_day_wet_hours", None)
        if hours:
            bits.append(tr.text("detail_blight_wet_hours", hours=hours))
        return ", ".join(bits)
    if model == MODEL_POWDERY_MILDEW:
        index = getattr(result, "index", None)
        interval = getattr(result, "spray_interval_days", None)
        bits = []
        if index is not None:
            bits.append(tr.text("detail_mildew_index", index=index))
        if interval:
            bits.append(tr.text("detail_mildew_interval", days=interval))
        return ", ".join(bits)
    return ""


def _pest_detail(result, tr: Translator) -> str:
    """Phrase explicative pour un ravageur : où en est son cycle.

    Le cumul brut ne parle à personne ; ce qui informe, c'est le jalon
    atteint et ce qui reste avant le suivant. Un biofix estimé ou une
    saison incomplète sont dits, parce qu'ils changent la confiance à
    accorder au chiffre.
    """
    bits: list[str] = []
    stage = getattr(result, "cycle_stage", None)
    if stage:
        bits.append(tr.pest_stage(stage))

    remaining = getattr(result, "dd_to_next_cycle_stage", None)
    following = getattr(result, "next_cycle_stage", None)
    if remaining is not None and following:
        bits.append(
            tr.text(
                "detail_pest_to_next",
                degree_days=f"{remaining:.0f}",
                stage=tr.pest_stage(following),
            )
        )

    if getattr(result, "biofix_estimated", False):
        bits.append(tr.text("detail_pest_estimated_biofix"))
    if getattr(result, "incomplete_season", False):
        bits.append(tr.text("detail_pest_incomplete_season"))
    return ", ".join(bits)


def build_risk_payload(
    tree, model: str, previous: str | None, result, tr: Translator
) -> dict:
    """Contenu de l'événement émis à chaque changement de niveau.

    Les clés `*_label` portent le texte déjà traduit, pour que les
    automatisations et blueprints puissent l'afficher tel quel ; les clés
    sans suffixe portent la valeur technique, stable quelle que soit la
    langue, pour les comparaisons.
    """
    level = getattr(result, "level", None)
    payload = {
        "tree": tree.display_name,
        "subentry_id": tree.subentry_id,
        "crop": tree.crop,
        "crop_label": tree.crop_label,
        "stage": tree.stage,
        "stage_label": tr.stage(tree.stage),
        "model": model,
        "model_label": tr.name("sensor", _entity_key(model)),
        "level": level,
        "level_label": tr.risk_level(level),
        "previous_level": previous,
        "escalated": _rank(level or "none") > _rank(previous or "none"),
    }
    if model == MODEL_FROST:
        payload["detail"] = _frost_detail(result, tr)
        payload["t10"] = getattr(result, "t10", None)
        payload["t90"] = getattr(result, "t90", None)
        payload["reference_min"] = getattr(result, "reference_min", None)
    elif model in PEST_MODELS:
        payload["detail"] = _pest_detail(result, tr)
        payload["cycle_stage"] = getattr(result, "cycle_stage", None)
        payload["degree_days"] = getattr(result, "degree_days", None)
    else:
        payload["detail"] = _disease_detail(model, result, tr)
    return payload


def process_risk_changes(
    hass: HomeAssistant, coordinator, notifications_enabled: bool
) -> None:
    """Compare les niveaux au cycle précédent et alerte si nécessaire."""
    tr = Translator(hass)
    for subentry_id, results in (coordinator.data or {}).items():
        tree = coordinator.tree(subentry_id)
        if tree is None:
            continue

        for model, result in results.items():
            level = getattr(result, "level", None)
            if level is None:
                continue
            previous = tree.last_levels.get(model)
            if previous == level:
                continue

            tree.last_levels[model] = level
            payload = build_risk_payload(tree, model, previous, result, tr)
            hass.bus.async_fire(EVENT_RISK_CHANGED, payload)

            # On ne notifie qu'à l'aggravation, et seulement à partir de
            # « alerte » : une amélioration n'a pas à réveiller personne.
            if (
                notifications_enabled
                and level in NOTIFY_LEVELS
                and payload["escalated"]
            ):
                _notify_risk(hass, payload, tr)


def _notify_risk(hass: HomeAssistant, payload: dict, tr: Translator) -> None:
    title = tr.text(
        "notify_risk_title",
        tree=payload["tree"],
        model=payload["model_label"],
        level=payload["level_label"],
    )
    lines = []
    if payload.get("stage_label"):
        lines.append(tr.text("notify_stage_line", stage=payload["stage_label"]))
    if payload.get("detail"):
        lines.append(payload["detail"])
    if payload["model"] == MODEL_FROST:
        lines.append(tr.text("notify_frost_caveat"))
    elif payload["model"] in PEST_MODELS:
        lines.append(tr.text("notify_pest_caveat"))
    else:
        lines.append(tr.text("notify_disease_caveat"))
    persistent_notification.async_create(
        hass,
        "\n".join(lines),
        title=title,
        notification_id=(
            f"{DOMAIN}_{payload['subentry_id']}_{payload['model']}"
        ),
    )


def process_stage_advances(
    hass: HomeAssistant, coordinator, notifications_enabled: bool
) -> None:
    """Émet événement et notification pour chaque stade avancé automatiquement."""
    tr = Translator(hass)
    for advance in coordinator.pending_advances:
        hass.bus.async_fire(EVENT_STAGE_ADVANCED, advance)

        if not notifications_enabled:
            continue

        stage_label = tr.stage(advance["stage"])
        previous_label = (
            tr.stage(advance["previous_stage"])
            if advance.get("previous_stage")
            else tr.text("stage_not_set")
        )
        persistent_notification.async_create(
            hass,
            "\n\n".join(
                (
                    tr.text(
                        "notify_stage_change",
                        previous=previous_label,
                        stage=stage_label,
                        gdd=advance["gdd"],
                    ),
                    tr.text("notify_stage_advice"),
                )
            ),
            title=tr.text("notify_stage_title", tree=advance["tree"]),
            notification_id=f"{DOMAIN}_{advance['subentry_id']}_stage",
        )
    coordinator.pending_advances = []
