"""Signale une dégradation silencieuse plutôt que de la subir.

Les modèles maladie (Hutton, Smith, Gubler-Thomas) raisonnent sur des
séries **horaires continues** reconstruites depuis le recorder. Quand
cet historique manque — capteurs exclus du recorder, purge trop courte,
instance fraîchement installée — ces modèles ne trouvent aucune journée
exploitable et renvoient donc « aucun risque ».

C'est le pire mode de défaillance possible : indiscernable d'une vraie
absence de risque. L'utilisateur voit un capteur vert et en conclut que
tout va bien, alors que le modèle ne tourne tout simplement pas.

Ce module transforme ce silence en **réparation** visible dans
Paramètres → Système → Réparations, créée quand la couverture est
insuffisante et refermée d'elle-même dès qu'elle redevient correcte.
"""
from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import (
    DISEASE_MODELS,
    DOMAIN,
    ISSUE_INSUFFICIENT_HISTORY,
    ISSUE_NO_RECORDER,
    MIN_HISTORY_COVERAGE_HOURS,
)

#: Section du README qui explique quoi faire, liée depuis la réparation.
LEARN_MORE_URL = (
    "https://github.com/Sdavid66/Meteo-Sentinelle#pr%C3%A9requis"
)


@callback
def async_check_history(
    hass: HomeAssistant, entry_id: str, coordinator, enabled: list[str]
) -> None:
    """Crée ou referme les réparations liées à l'historique.

    Ne se déclenche que si un modèle maladie est activé : sans eux, seul
    le gel tourne, et le gel n'a besoin que des prévisions.
    """
    needs_history = any(model in enabled for model in DISEASE_MODELS)

    coverage = getattr(coordinator, "history_coverage", None) or {}
    recorder_issue = f"{ISSUE_NO_RECORDER}_{entry_id}"
    history_issue = f"{ISSUE_INSUFFICIENT_HISTORY}_{entry_id}"

    if not needs_history or not coverage:
        ir.async_delete_issue(hass, DOMAIN, recorder_issue)
        ir.async_delete_issue(hass, DOMAIN, history_issue)
        return

    # 1. Le recorder ne répond pas du tout : rien d'autre n'a de sens.
    if not coverage.get("recorder_available", True):
        ir.async_delete_issue(hass, DOMAIN, history_issue)
        ir.async_create_issue(
            hass,
            DOMAIN,
            recorder_issue,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_NO_RECORDER,
            learn_more_url=LEARN_MORE_URL,
        )
        return

    ir.async_delete_issue(hass, DOMAIN, recorder_issue)

    # 2. Le recorder répond, mais pas assez de données exploitables.
    usable = int(coverage.get("usable_hours", 0))
    if usable >= MIN_HISTORY_COVERAGE_HOURS:
        ir.async_delete_issue(hass, DOMAIN, history_issue)
        return

    ir.async_create_issue(
        hass,
        DOMAIN,
        history_issue,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_INSUFFICIENT_HISTORY,
        translation_placeholders={
            "hours": str(usable),
            "required": str(MIN_HISTORY_COVERAGE_HOURS),
            "window": str(coverage.get("window_hours", 96)),
        },
        learn_more_url=LEARN_MORE_URL,
    )


@callback
def async_clear_issues(hass: HomeAssistant, entry_id: str) -> None:
    """Retire les réparations d'une entrée qu'on décharge."""
    ir.async_delete_issue(hass, DOMAIN, f"{ISSUE_NO_RECORDER}_{entry_id}")
    ir.async_delete_issue(hass, DOMAIN, f"{ISSUE_INSUFFICIENT_HISTORY}_{entry_id}")
