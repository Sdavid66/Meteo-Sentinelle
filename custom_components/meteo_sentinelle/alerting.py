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
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    EVENT_RISK_CHANGED,
    EVENT_STAGE_ADVANCED,
    EVENT_TREATMENT_DUE,
    MODEL_FROST,
    MODEL_LATE_BLIGHT,
    MODEL_POWDERY_MILDEW,
    PEST_MODELS,
    RISK_LEVELS,
    RISK_NONE,
    RISK_SEVERE,
    RISK_WARNING,
)
from .localize import Translator
from .models.spray import next_daytime_slot
from .models.treatments import REASON_EXPIRING, REASON_WASHED_OFF

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
                        "notify_stage_change_bloom"
                        if advance.get("since_bloom")
                        else "notify_stage_change",
                        previous=previous_label,
                        stage=stage_label,
                        gdd=advance["gdd"],
                    ),
                    tr.text(
                        "notify_rest_advice"
                        if advance.get("rest")
                        else "notify_stage_advice"
                    ),
                )
            ),
            title=tr.text(
                "notify_rest_title" if advance.get("rest") else "notify_stage_title",
                tree=advance["tree"],
            ),
            notification_id=f"{DOMAIN}_{advance['subentry_id']}_stage",
        )
    coordinator.pending_advances = []


# ----------------------------------------------------------------------
# Rappels de traitement
# ----------------------------------------------------------------------


def _treatment_notification_id(subentry_id: str, model: str) -> str:
    # Un identifiant par couple (arbre, cible) : le préavis de la veille est
    # remplacé par l'annonce de fin, au lieu de s'y ajouter.
    return f"{DOMAIN}_{subentry_id}_{model}_treatment"


def _local(value: str | None, pattern: str) -> str:
    """Date ISO rendue dans le fuseau de l'installation."""
    moment = dt_util.parse_datetime(value) if value else None
    return dt_util.as_local(moment).strftime(pattern) if moment else "?"


def build_reminder_payload(coordinator, reminder: dict, tr: Translator) -> dict:
    """Contenu de l'événement de rappel, titre et message déjà rédigés.

    `title` et `message` sont traduits ici pour qu'une automatisation puisse
    les relayer tels quels, sans réécrire le texte dans chaque blueprint.
    """
    reason = reminder["reason"]
    model_label = tr.treatment_target(reminder["model"])
    applied = _local(reminder.get("applied_at"), "%d/%m")

    if reason == REASON_EXPIRING:
        title_key = "notify_treatment_soon_title"
        lines = [
            tr.text(
                "notify_treatment_soon",
                applied=applied,
                until=_local(reminder.get("protected_until"), "%d/%m %H:%M"),
            )
        ]
    elif reason == REASON_WASHED_OFF:
        title_key = "notify_treatment_washed_title"
        lines = [
            tr.text(
                "notify_treatment_washed",
                applied=applied,
                rain=f"{reminder.get('rain_since_mm') or 0:.0f}",
            )
        ]
    else:
        title_key = "notify_treatment_expired_title"
        lines = [tr.text("notify_treatment_expired", applied=applied)]

    if reminder.get("product"):
        lines.append(tr.text("notify_treatment_product", product=reminder["product"]))

    level = reminder.get("level")
    at_risk = bool(level) and level != RISK_NONE
    lines.append(
        tr.text("notify_treatment_risk", level=tr.risk_level(level))
        if at_risk
        else tr.text("notify_treatment_no_risk")
    )

    # Seulement un créneau de jour : personne ne sort traiter à 1 h du matin.
    now = dt_util.utcnow()
    slot = next_daytime_slot(coordinator.spray.windows, now, dt_util.as_local)
    window_open = slot is not None and slot[0] <= now
    if window_open:
        lines.append(tr.text("notify_treatment_window_open"))
    elif slot is not None:
        lines.append(
            tr.text(
                "notify_treatment_window",
                when=dt_util.as_local(slot[0]).strftime("%d/%m %H:%M"),
            )
        )
    lines.append(tr.text("notify_treatment_how"))

    return {
        **reminder,
        "model_label": model_label,
        "level_label": tr.risk_level(level) if level else None,
        "next_window": slot[0].isoformat() if slot else None,
        "window_open": window_open,
        "title": tr.text(title_key, tree=reminder["tree"], model=model_label),
        "message": "\n".join(lines),
    }


def process_treatment_reminders(
    hass: HomeAssistant, coordinator, notifications_enabled: bool
) -> None:
    """Émet événement et notification pour chaque rappel de traitement dû."""
    if not coordinator.pending_reminders:
        return
    tr = Translator(hass)
    for reminder in coordinator.pending_reminders:
        payload = build_reminder_payload(coordinator, reminder, tr)
        hass.bus.async_fire(EVENT_TREATMENT_DUE, payload)
        if notifications_enabled:
            persistent_notification.async_create(
                hass,
                payload["message"],
                title=payload["title"],
                notification_id=_treatment_notification_id(
                    reminder["subentry_id"], reminder["model"]
                ),
            )
    coordinator.pending_reminders = []


def dismiss_treatment_reminder(hass: HomeAssistant, subentry_id: str, model: str) -> None:
    """Retire le rappel affiché : le traitement vient d'être refait ou effacé."""
    persistent_notification.async_dismiss(
        hass, _treatment_notification_id(subentry_id, model)
    )
