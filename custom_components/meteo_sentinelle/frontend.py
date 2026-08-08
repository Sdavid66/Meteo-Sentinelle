"""Publication de la carte Lovelace par l'intégration elle-même.

L'usage courant dans l'écosystème est de publier une carte dans un
**second dépôt** HACS, de catégorie « plugin ». L'utilisateur doit alors
l'installer séparément, puis déclarer une ressource Lovelace — deux
étapes que la moitié des gens rate, pour un fichier de quelques
kilo-octets déjà présent sur leur machine.

L'intégration sert donc sa propre carte : le fichier est exposé sur une
URL statique, puis déclaré comme script supplémentaire du frontend. La
carte est disponible dès l'installation, sans dépôt ni ressource à
ajouter, et elle se met à jour en même temps que l'intégration —
impossible de se retrouver avec une carte et un composant désaccordés.

Contrepartie assumée : le script est chargé sur toutes les pages du
frontend, y compris quand aucun tableau de bord n'affiche la carte.
C'est le prix de l'absence de ressource déclarée, et il reste modeste
pour un fichier de cette taille.
"""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    FRONTEND_BASE_URL,
    FRONTEND_DIR,
    FRONTEND_SCRIPT,
    FRONTEND_URL,
)

_LOGGER = logging.getLogger(__name__)

_REGISTERED = f"{DOMAIN}_frontend_registered"


async def async_register_card(hass: HomeAssistant) -> None:
    """Expose la carte et la déclare au frontend, une fois par instance."""
    if hass.data.get(_REGISTERED):
        return

    directory = Path(__file__).parent / FRONTEND_DIR
    if not (directory / FRONTEND_SCRIPT).exists():
        _LOGGER.warning(
            "Carte Lovelace introuvable dans %s : l'intégration fonctionne, "
            "mais la carte ne sera pas disponible.",
            directory,
        )
        return

    try:
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    FRONTEND_BASE_URL,
                    str(directory),
                    # Le contenu change à chaque mise à jour, mais l'URL
                    # porte un paramètre de version : on peut donc
                    # laisser le navigateur mettre en cache agressivement.
                    True,
                )
            ]
        )
    except (RuntimeError, ValueError) as err:
        # Une seconde entrée de configuration réenregistrerait le même
        # chemin : ce n'est pas une erreur, c'est déjà fait.
        _LOGGER.debug("Chemin statique déjà enregistré : %s", err)

    version = _integration_version(hass)
    add_extra_js_url(hass, f"{FRONTEND_URL}?v={version}")
    hass.data[_REGISTERED] = True
    _LOGGER.debug("Carte Lovelace publiée sur %s", FRONTEND_URL)


def _integration_version(hass: HomeAssistant) -> str:
    """Version du manifest, utilisée pour invalider le cache navigateur."""
    try:
        from homeassistant.loader import async_get_loaded_integration

        return str(async_get_loaded_integration(hass, DOMAIN).version or "0")
    except Exception:  # noqa: BLE001 - un cache non invalidé n'est pas grave
        return "0"
