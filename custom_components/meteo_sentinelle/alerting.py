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
    RISK_LEVELS,
    RISK_SEVERE,
    RISK_WARNING,
)
from .models.crops import STAGE_LABELS

_LOGGER = logging.getLogger(__name__)

MODEL_LABELS = {
    MODEL_FROST: "gel",
    MODEL_LATE_BLIGHT: "mildiou",
    MODEL_POWDERY_MILDEW: "oïdium",
}

LEVEL_LABELS = {
    "none": "aucun risque",
    "watch": "à surveiller",
    "warning": "alerte",
    "severe": "risque sévère",
}

#: Niveaux justifiant une notification (les autres restent en événement).
NOTIFY_LEVELS = {RISK_WARNING, RISK_SEVERE}


def _rank(level: str) -> int:
    try:
        return RISK_LEVELS.index(level)
    except ValueError:
        return 0


def _frost_detail(result) -> str:
    """Phrase explicative pour une alerte gel, avec le contexte utile."""
    parts: list[str] = []
    reference = getattr(result, "reference_min", None)
    if reference is not None:
        where = (
            "au niveau du sol"
            if getattr(result, "reference", "air") == "surface"
            else "sous abri"
        )
        parts.append(f"minimum attendu {reference:.1f} °C {where}")
    t10 = getattr(result, "t10", None)
    if t10 is not None:
        parts.append(f"seuil de dégâts {t10:.1f} °C")
    when = getattr(result, "next_frost_time", None)
    if when is not None:
        parts.append(f"vers {when.strftime('%d/%m %Hh')}")
    return ", ".join(parts)


def _disease_detail(model: str, result) -> str:
    if model == MODEL_LATE_BLIGHT:
        bits = []
        if getattr(result, "hutton_met", False):
            bits.append("critères de Hutton remplis")
        elif getattr(result, "hutton_consecutive_days", 0):
            bits.append("une journée favorable")
        hours = getattr(result, "last_day_wet_hours", None)
        if hours:
            bits.append(f"{hours} h d'humidité continue hier")
        return ", ".join(bits)
    if model == MODEL_POWDERY_MILDEW:
        index = getattr(result, "index", None)
        interval = getattr(result, "spray_interval_days", None)
        bits = []
        if index is not None:
            bits.append(f"indice {index}/100")
        if interval:
            bits.append(f"intervalle conseillé {interval} jours")
        return ", ".join(bits)
    return ""


def build_risk_payload(tree, model: str, previous: str | None, result) -> dict:
    """Contenu de l'événement émis à chaque changement de niveau."""
    level = getattr(result, "level", None)
    payload = {
        "tree": tree.display_name,
        "subentry_id": tree.subentry_id,
        "crop": tree.crop,
        "crop_label": tree.crop_label,
        "stage": tree.stage,
        "stage_label": tree.stage_label,
        "model": model,
        "model_label": MODEL_LABELS.get(model, model),
        "level": level,
        "level_label": LEVEL_LABELS.get(level, level),
        "previous_level": previous,
        "escalated": _rank(level or "none") > _rank(previous or "none"),
    }
    if model == MODEL_FROST:
        payload["detail"] = _frost_detail(result)
        payload["t10"] = getattr(result, "t10", None)
        payload["t90"] = getattr(result, "t90", None)
        payload["reference_min"] = getattr(result, "reference_min", None)
    else:
        payload["detail"] = _disease_detail(model, result)
    return payload


def process_risk_changes(
    hass: HomeAssistant, coordinator, notifications_enabled: bool
) -> None:
    """Compare les niveaux au cycle précédent et alerte si nécessaire."""
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
            payload = build_risk_payload(tree, model, previous, result)
            hass.bus.async_fire(EVENT_RISK_CHANGED, payload)

            # On ne notifie qu'à l'aggravation, et seulement à partir de
            # « alerte » : une amélioration n'a pas à réveiller personne.
            if (
                notifications_enabled
                and level in NOTIFY_LEVELS
                and payload["escalated"]
            ):
                _notify_risk(hass, coordinator, payload)


def _notify_risk(hass: HomeAssistant, coordinator, payload: dict) -> None:
    title = f"{payload['tree']} — {payload['model_label']} : {payload['level_label']}"
    lines = []
    if payload.get("stage_label"):
        lines.append(f"Stade : {payload['stage_label']}")
    if payload.get("detail"):
        lines.append(payload["detail"])
    lines.append(
        "Ces modèles sont indicatifs et supposent le pathogène présent ; "
        "ils ne remplacent pas une observation sur place."
        if payload["model"] != MODEL_FROST
        else "Vérifiez la prévision avant d'engager une protection."
    )
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
    for advance in coordinator.pending_advances:
        hass.bus.async_fire(EVENT_STAGE_ADVANCED, advance)

        if not notifications_enabled:
            continue

        stage_label = STAGE_LABELS.get(advance["stage"], advance["stage"])
        previous_label = (
            STAGE_LABELS.get(advance["previous_stage"], advance["previous_stage"])
            if advance.get("previous_stage")
            else "non renseigné"
        )
        persistent_notification.async_create(
            hass,
            (
                f"Le stade est passé de « {previous_label} » à "
                f"« {stage_label} » d'après le cumul de degrés-jours "
                f"({advance['gdd']} °C·j).\n\n"
                "Ce changement a été appliqué automatiquement et modifie les "
                "seuils de gel utilisés pour cet arbre. Si l'observation sur "
                "place ne correspond pas, corrigez le stade depuis l'entité "
                "« Stade phénologique » : votre correction fait autorité. "
                "Vous pouvez aussi désactiver l'avancement automatique pour "
                "cet arbre."
            ),
            title=f"{advance['tree']} — stade avancé automatiquement",
            notification_id=f"{DOMAIN}_{advance['subentry_id']}_stage",
        )
    coordinator.pending_advances = []
