"""Installation des phrases Assist dans le dossier de configuration.

Home Assistant ne lit les phrases personnalisées qu'à un seul endroit :
`<config>/custom_sentences/<langue>/*.yaml`. Une intégration n'a aucun
moyen d'en publier depuis son propre dossier — l'API qui le permettait a
été retirée. Le seul chemin praticable est donc de recopier les
fichiers livrés, une fois, au bon endroit.

Écrire dans le dossier de configuration d'un utilisateur n'est pas
anodin. Trois garde-fous encadrent l'opération :

1. **Rien n'est jamais écrasé.** Un fichier existant n'est réécrit que
   s'il est identique, octet pour octet, à une version déjà livrée par
   l'intégration. Dès que l'utilisateur le modifie, il devient le sien
   et Météo Sentinelle n'y touche plus jamais.
2. **C'est débrayable.** Une option du site coupe l'installation ; le
   fichier déjà posé reste en place, l'utilisateur le supprimera s'il le
   souhaite. Rien n'est retiré dans son dos.
3. **Le fichier le dit.** Son en-tête explique d'où il vient, comment le
   modifier et comment s'en débarrasser.

Les empreintes des versions déjà publiées sont mémorisées, afin qu'une
mise à jour de l'intégration puisse remplacer un fichier resté
d'origine — sans pour autant écraser celui que l'utilisateur a retouché
entre-temps.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

#: Dossier des phrases livrées avec l'intégration.
SOURCE_DIR = Path(__file__).parent / "sentences"

#: Nom du fichier posé dans custom_sentences/<langue>/.
FILENAME = f"{DOMAIN}.yaml"

#: Empreintes SHA-256 des versions successivement publiées. Un fichier
#: dont l'empreinte figure ici est réputé « non modifié » et peut donc
#: être remplacé par une version plus récente. Toute autre empreinte
#: signifie que l'utilisateur l'a retouché : on n'y touche plus.
#:
#: Cette liste s'auto-alimente : l'empreinte des fichiers livrés est
#: ajoutée à la volée, ce qui rend la mise à jour transparente sans
#: exiger d'y recopier un condensat à chaque publication.
_KNOWN_DIGESTS: set[str] = set()


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _install_one(source: Path, target_dir: Path) -> str:
    """Installe un fichier de phrases. Renvoie ce qui a été fait."""
    payload = source.read_bytes()
    _KNOWN_DIGESTS.add(_digest(payload))

    target = target_dir / FILENAME
    if target.exists():
        existing = _digest(target.read_bytes())
        if existing == _digest(payload):
            return "unchanged"
        if existing not in _KNOWN_DIGESTS:
            return "user_modified"

    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return "installed"


def _install_all(config_dir: Path) -> dict[str, str]:
    results: dict[str, str] = {}
    if not SOURCE_DIR.is_dir():
        return results
    for language_dir in sorted(SOURCE_DIR.iterdir()):
        source = language_dir / FILENAME
        if not language_dir.is_dir() or not source.exists():
            continue
        target_dir = config_dir / "custom_sentences" / language_dir.name
        results[language_dir.name] = _install_one(source, target_dir)
    return results


async def async_install_sentences(hass: HomeAssistant) -> None:
    """Pose les phrases et demande à Assist de les relire.

    Toute l'opération est faite dans un exécuteur : ouvrir, hacher et
    copier des fichiers sont des entrées-sorties bloquantes, interdites
    dans la boucle d'événements.
    """
    config_dir = Path(hass.config.path())

    try:
        results = await hass.async_add_executor_job(_install_all, config_dir)
    except OSError as err:
        # Un dossier de configuration en lecture seule ne doit pas
        # empêcher l'intégration de démarrer : les phrases sont un
        # confort, les capteurs sont l'essentiel.
        _LOGGER.warning(
            "Installation des phrases Assist impossible (%s). Les capteurs "
            "fonctionnent normalement ; les commandes vocales personnalisées "
            "ne seront pas disponibles.",
            err,
        )
        return

    for language, outcome in results.items():
        if outcome == "installed":
            _LOGGER.info(
                "Phrases Assist (%s) installées dans custom_sentences/%s/%s",
                language,
                language,
                FILENAME,
            )
        elif outcome == "user_modified":
            _LOGGER.debug(
                "custom_sentences/%s/%s a été modifié : conservé tel quel",
                language,
                FILENAME,
            )

    if "installed" not in results.values():
        return

    # Assist ne relit ses phrases qu'à la demande. Sans cet appel, les
    # commandes ne fonctionneraient qu'après un redémarrage complet.
    if hass.services.has_service("conversation", "reload"):
        try:
            await hass.services.async_call("conversation", "reload", blocking=False)
        except Exception as err:  # noqa: BLE001 - purement cosmétique
            _LOGGER.debug("Rechargement des phrases Assist impossible : %s", err)
