"""Traduction des messages composés à l'exécution.

Home Assistant traduit déclarativement les noms et états d'entités, mais
**pas** le texte libre des notifications. Le seul mécanisme officiel est
le cache de traductions, interrogeable à l'exécution dans la langue de
l'utilisateur.

Deux contraintes ont dicté la conception :

- les gabarits de messages vivent sous la clé `common` de strings.json.
  C'est la seule catégorie de premier niveau qui soit à la fois validée
  par hassfest, plate, et autorisée à contenir des paramètres `{...}` ;
- l'alerting s'exécute dans un `@callback` synchrone. On ne peut donc pas
  y attendre le chargement des traductions : elles sont préchargées au
  démarrage, puis lues depuis le cache.

Home Assistant superpose toujours l'anglais sous la langue demandée : une
clé absente d'une traduction retombe sur l'anglais au lieu de disparaître.
"""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.translation import (
    async_get_cached_translations,
    async_load_integrations,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_preload(hass: HomeAssistant) -> None:
    """Charge les traductions du domaine avant la première notification."""
    try:
        await async_load_integrations(hass, {DOMAIN})
    except Exception as err:  # noqa: BLE001 - une notification non traduite
        # vaut mieux qu'une intégration qui refuse de démarrer.
        _LOGGER.debug("Préchargement des traductions impossible : %s", err)


class Translator:
    """Accès aux libellés traduits, dans la langue courante."""

    def __init__(self, hass: HomeAssistant, language: str | None = None) -> None:
        # Une requête Assist porte sa propre langue, qui n'est pas
        # nécessairement celle de l'interface : on répond dans la langue
        # de la question quand elle est connue.
        language = language or hass.config.language
        self._common = async_get_cached_translations(hass, language, "common", DOMAIN)
        self._entity = async_get_cached_translations(hass, language, "entity", DOMAIN)

    # ------------------------------------------------------------------
    # Gabarits de messages
    # ------------------------------------------------------------------

    def text(self, key: str, **placeholders: object) -> str:
        """Rend un gabarit de la section `common`.

        Renvoie la clé elle-même si la traduction manque : un message
        laid reste préférable à une exception dans une notification.
        """
        template = self._common.get(f"component.{DOMAIN}.common.{key}")
        if template is None:
            return key
        if not placeholders:
            return template
        try:
            return template.format(**placeholders)
        except (KeyError, IndexError, ValueError):
            _LOGGER.debug("Paramètres manquants pour la traduction « %s »", key)
            return template

    # ------------------------------------------------------------------
    # Libellés d'entités, réutilisés tels quels dans les messages
    # ------------------------------------------------------------------

    def state(self, platform: str, key: str, state: str | None) -> str | None:
        """Libellé traduit d'un état (niveau de risque, stade…)."""
        if state is None:
            return None
        return self._entity.get(
            f"component.{DOMAIN}.entity.{platform}.{key}.state.{state}", state
        )

    def name(self, platform: str, key: str) -> str:
        """Nom traduit d'une entité, réutilisé comme intitulé de risque."""
        return self._entity.get(f"component.{DOMAIN}.entity.{platform}.{key}.name", key)

    def risk_level(self, level: str | None) -> str | None:
        """« Alerte » / « Warning » selon la langue."""
        return self.state("sensor", "frost_risk", level)

    def stage(self, stage: str | None) -> str | None:
        """« Pleine floraison » / « Full bloom » selon la langue."""
        return self.state("select", "phenology_stage", stage)


    def risk_name(self, model: str) -> str:
        """« Risque de gel » / « Frost risk » — l'intitulé du modèle."""
        return self.name("sensor", f"{model}_risk")

    def pest_stage(self, stage: str | None) -> str:
        """« Éclosion généralisée » / « Peak egg hatch ».

        Les jalons du cycle d'un insecte ne sont l'état d'aucune entité :
        ils vivent en attribut. Home Assistant ne les traduit donc pas
        tout seul, et ils sont rangés à plat dans la section `common`.
        """
        if stage is None:
            return ""
        return self.text(f"pest_stage_{stage}")


@callback
def async_translator(hass: HomeAssistant, language: str | None = None) -> Translator:
    return Translator(hass, language)
