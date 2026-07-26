#!/usr/bin/env python3
"""Contrôle une intégration Home Assistant avant commit.

Cible les erreurs qui ne produisent aucun message au moment de l'écriture
et ne se révèlent qu'en production : version d'entrée sans migration,
clé de traduction manquante, service non déclaré, icône absente.

    python3 check_integration.py <chemin-du-depot>
    python3 check_integration.py <chemin-du-depot> --publish

Le mode --publish ajoute les critères d'acceptation du magasin HACS par
défaut qui sont vérifiables hors ligne, et rappelle ceux qui dépendent de
GitHub et doivent être contrôlés à la main.

Sortie 0 si tout passe, 1 s'il reste une erreur. Les avertissements
n'échouent pas la commande.

Aucune dépendance obligatoire ; PyYAML et Pillow enrichissent les
contrôles s'ils sont présents.
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


ERRORS: list[str] = []
WARNINGS: list[str] = []
PASSED: list[str] = []

MANIFEST_REQUIRED = [
    "domain",
    "name",
    "version",
    "documentation",
    "issue_tracker",
    "codeowners",
]

# Clés documentées de hacs.json. Les autres sont ignorées par HACS, mais
# leur présence trahit souvent un exemple obsolète recopié tel quel.
HACS_JSON_KEYS = {
    "name",
    "homeassistant",
    "hacs",
    "country",
    "persistent_directory",
    "content_in_root",
    "zip_release",
    "filename",
    "hide_default_branch",
}


def error(message: str) -> None:
    ERRORS.append(message)


def warn(message: str) -> None:
    WARNINGS.append(message)


def ok(message: str) -> None:
    PASSED.append(message)


# ----------------------------------------------------------------------
# Localisation de l'intégration
# ----------------------------------------------------------------------


def find_integration(root: Path) -> Path | None:
    """Trouve le dossier de l'intégration, en validant l'unicité HACS."""
    components = root / "custom_components"
    if not components.is_dir():
        error("custom_components/ est absent : HACS refusera ce dépôt.")
        return None

    candidates = [
        d for d in sorted(components.iterdir()) if d.is_dir() and not d.name.startswith(".")
    ]
    if not candidates:
        error("Aucune intégration dans custom_components/.")
        return None
    if len(candidates) > 1:
        error(
            "HACS n'accepte qu'une intégration par dépôt ; "
            f"{len(candidates)} trouvées : {', '.join(d.name for d in candidates)}."
        )
    else:
        ok(f"Une seule intégration : {candidates[0].name}")
    return candidates[0]


# ----------------------------------------------------------------------
# Fichiers de configuration
# ----------------------------------------------------------------------


def load_json(path: Path) -> dict | None:
    if not path.exists():
        error(f"{path.name} est absent ({path}).")
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as err:
        error(f"{path} : JSON invalide — {err}")
        return None


def check_manifest(integration: Path) -> dict:
    manifest = load_json(integration / "manifest.json") or {}
    if not manifest:
        return {}

    missing = [key for key in MANIFEST_REQUIRED if key not in manifest]
    if missing:
        error(f"manifest.json : clés obligatoires manquantes — {', '.join(missing)}")
    else:
        ok("manifest.json : toutes les clés obligatoires sont présentes")

    if manifest.get("domain") and manifest["domain"] != integration.name:
        error(
            f"manifest.json : domain « {manifest['domain']} » diffère du dossier "
            f"« {integration.name} » ; les deux doivent être identiques."
        )
    elif manifest.get("domain"):
        ok("manifest.json : domain cohérent avec le nom du dossier")

    for placeholder in ("YOUR_", "example.com", "<user>", "changeme"):
        for key, value in manifest.items():
            if isinstance(value, str) and placeholder in value:
                warn(f"manifest.json : « {key} » contient encore « {placeholder} ».")
            if isinstance(value, list) and any(
                isinstance(v, str) and placeholder in v for v in value
            ):
                warn(f"manifest.json : « {key} » contient encore « {placeholder} ».")

    return manifest


def check_hacs_json(root: Path, integration: Path) -> None:
    hacs = load_json(root / "hacs.json")
    if hacs is None:
        return

    # « name » est la seule clé obligatoire, et un contrôle automatique de
    # la soumission la vérifie explicitement.
    if "name" not in hacs:
        error("hacs.json : « name » est la seule clé obligatoire et elle manque.")
    else:
        ok("hacs.json : « name » présent")

    unknown = set(hacs) - HACS_JSON_KEYS
    if unknown:
        warn(
            "hacs.json : clé(s) non documentée(s), probablement issue(s) d'un "
            f"exemple obsolète — {', '.join(sorted(unknown))}"
        )

    country = hacs.get("country")
    if country is not None:
        values = country if isinstance(country, list) else [country]
        bad = [c for c in values if not (isinstance(c, str) and len(c) == 2)]
        if bad:
            error(
                "hacs.json : « country » attend des codes ISO 3166-1 alpha-2 "
                f"à deux lettres — {bad}"
            )
        else:
            ok("hacs.json : « country » au bon format")

    minimum = hacs.get("homeassistant")
    brand = integration / "brand"
    if brand.is_dir() and any(brand.glob("*.png")):
        if not minimum:
            error(
                "Des icônes sont livrées dans brand/, ce qui exige Home Assistant "
                "2026.3.0 : renseigner « homeassistant » dans hacs.json."
            )
        else:
            try:
                major, minor = (int(p) for p in str(minimum).split(".")[:2])
                if (major, minor) < (2026, 3):
                    error(
                        f"hacs.json exige Home Assistant {minimum}, mais les icônes "
                        "locales brand/ nécessitent au minimum 2026.3.0."
                    )
                else:
                    ok(f"hacs.json : version minimale {minimum}, compatible brand/")
            except ValueError:
                warn(f"hacs.json : version « {minimum} » illisible.")


# ----------------------------------------------------------------------
# Dépendances (reproduit la logique de hassfest/dependencies.py)
# ----------------------------------------------------------------------

#: Toujours autorisés sans déclaration : intégrations core (chargées
#: inconditionnellement) et noms de plateformes (sensor.py qui importe
#: homeassistant.components.sensor n'est pas une dépendance externe).
_DEPENDENCY_ALLOWED = {
    "homeassistant",
    "persistent_notification",
    "sensor",
    "switch",
    "select",
    "binary_sensor",
    "number",
    "button",
    "climate",
    "cover",
    "fan",
    "light",
    "lock",
    "siren",
    "text",
    "update",
    "vacuum",
    "valve",
    "water_heater",
    "camera",
    "alarm_control_panel",
    "device_tracker",
    "event",
    "humidifier",
    "image",
    "notify",
    "remote",
    "scene",
    "todo",
    "weather",
}


def _referenced_components(integration: Path) -> set[str]:
    """Domaines importés via homeassistant.components.<domaine>."""
    referenced: set[str] = set()
    for path in integration.glob("**/*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("homeassistant.components."):
                    referenced.add(node.module.split(".")[2])
                elif node.module == "homeassistant.components":
                    referenced.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("homeassistant.components."):
                        referenced.add(alias.name.split(".")[2])
    return referenced


def check_dependencies(integration: Path, manifest: dict) -> None:
    """Un import de homeassistant.components.X non déclaré casse hassfest.

    C'est le contrôle « dependencies » de hassfest : importer un module
    d'une autre intégration (ex. recorder pour lire l'historique) exige de
    la lister dans manifest.json, sous « dependencies » (toujours chargée
    avec l'intégration) ou « after_dependencies » (chargée si présente,
    l'intégration doit tolérer son absence). Sans cela, hassfest échoue
    avec : « Using component X but it's not in 'dependencies' or
    'after_dependencies' ».
    """
    if not manifest:
        return

    declared = set(manifest.get("dependencies", [])) | set(
        manifest.get("after_dependencies", [])
    )
    referenced = _referenced_components(integration)
    missing = sorted(referenced - declared - {integration.name} - _DEPENDENCY_ALLOWED)

    if missing:
        error(
            "manifest.json : composant(s) importé(s) mais non déclaré(s) — "
            f"{', '.join(missing)}. Ajouter à « dependencies » (chargement "
            "obligatoire) ou « after_dependencies » (optionnel, à condition "
            "que le code tolère son absence)."
        )
    else:
        ok("manifest.json : tous les composants importés sont déclarés")


# ----------------------------------------------------------------------
# Migrations
# ----------------------------------------------------------------------


def check_migration(integration: Path) -> None:
    """Le contrôle le plus rentable : VERSION sans handler casse tout."""
    flow = integration / "config_flow.py"
    init = integration / "__init__.py"
    if not flow.exists():
        return

    source = flow.read_text(encoding="utf-8")
    match = re.search(r"^\s*VERSION\s*=\s*(\d+)", source, re.M)
    if not match:
        ok("config_flow.py : VERSION implicite (1), aucune migration requise")
        return

    version = int(match.group(1))
    if version == 1:
        ok("config_flow.py : VERSION = 1, aucune migration requise")
        return

    init_source = init.read_text(encoding="utf-8") if init.exists() else ""
    has_handler = "async_migrate_entry" in init_source

    if not has_handler:
        error(
            f"config_flow.py déclare VERSION = {version} mais __init__.py ne définit "
            "pas async_migrate_entry : Home Assistant refusera de charger les entrées "
            "existantes (« Migration handler not found »). Ajouter le handler, ou "
            "utiliser MINOR_VERSION si le changement est rétrocompatible."
        )
        return

    ok(f"config_flow.py : VERSION = {version} avec async_migrate_entry présent")

    targets = {int(v) for v in re.findall(r"version\s*=\s*(\d+)", init_source)}
    if targets and version not in targets:
        error(
            f"async_migrate_entry n'écrit pas la version {version} du config flow "
            f"(versions écrites : {sorted(targets) or 'aucune'})."
        )
    elif targets:
        ok("La migration écrit bien la version courante du config flow")

    if init_source and not re.search(r"entry\.version\s*>", init_source):
        warn(
            "async_migrate_entry ne semble pas refuser les entrées écrites par une "
            "version plus récente (test « entry.version > N » absent)."
        )


def check_module_functions(integration: Path) -> None:
    init = integration / "__init__.py"
    if not init.exists():
        error("__init__.py est absent.")
        return
    try:
        tree = ast.parse(init.read_text(encoding="utf-8"))
    except SyntaxError as err:
        error(f"__init__.py : erreur de syntaxe — {err}")
        return

    names = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for required in ("async_setup_entry", "async_unload_entry"):
        if required not in names:
            warn(f"__init__.py : {required} est absent au niveau du module.")
    if {"async_setup_entry", "async_unload_entry"} <= names:
        ok("__init__.py : async_setup_entry et async_unload_entry présents")


def check_deprecated_patterns(integration: Path) -> None:
    flow = integration / "config_flow.py"
    if not flow.exists():
        return
    source = flow.read_text(encoding="utf-8")
    if re.search(r"self\.config_entry\s*=\s*config_entry", source):
        warn(
            "config_flow.py : « self.config_entry = config_entry » dans un OptionsFlow "
            "est déprécié — la classe de base fournit déjà self.config_entry."
        )
    else:
        ok("config_flow.py : pas d'affectation dépréciée de config_entry")


# ----------------------------------------------------------------------
# Traductions
# ----------------------------------------------------------------------


def flatten(data: dict, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for key, value in data.items():
        if isinstance(value, dict):
            keys |= flatten(value, f"{prefix}{key}.")
        else:
            keys.add(f"{prefix}{key}")
    return keys


def check_translations(integration: Path) -> None:
    strings_path = integration / "strings.json"
    translations = integration / "translations"

    if not strings_path.exists():
        warn("strings.json est absent : les libellés s'afficheront en clés brutes.")
        return
    strings = load_json(strings_path)
    if strings is None:
        return

    if not translations.is_dir():
        error("translations/ est absent ; en.json est obligatoire.")
        return
    if not (translations / "en.json").exists():
        error("translations/en.json est obligatoire.")

    reference = flatten(strings)
    for path in sorted(translations.glob("*.json")):
        data = load_json(path)
        if data is None:
            continue
        keys = flatten(data)
        missing = reference - keys
        extra = keys - reference
        if missing:
            error(
                f"translations/{path.name} : {len(missing)} clé(s) manquante(s) — "
                f"{', '.join(sorted(missing)[:5])}"
                + (" …" if len(missing) > 5 else "")
            )
        if extra:
            warn(
                f"translations/{path.name} : {len(extra)} clé(s) en trop — "
                f"{', '.join(sorted(extra)[:5])}" + (" …" if len(extra) > 5 else "")
            )
        if not missing and not extra:
            ok(f"translations/{path.name} : {len(keys)} clés alignées sur strings.json")


# ----------------------------------------------------------------------
# Services
# ----------------------------------------------------------------------


def check_services(integration: Path) -> None:
    services_path = integration / "services.yaml"
    const_path = integration / "const.py"

    declared: set[str] = set()
    if const_path.exists():
        declared = set(
            re.findall(
                r'^SERVICE_\w+\s*=\s*[\'"](\w+)[\'"]',
                const_path.read_text(encoding="utf-8"),
                re.M,
            )
        )

    if not services_path.exists():
        if declared:
            error(
                f"{len(declared)} service(s) déclaré(s) dans const.py mais "
                "services.yaml est absent : ils n'apparaîtront pas dans l'interface."
            )
        return

    if yaml is None:
        warn("PyYAML absent : services.yaml non vérifié.")
        return

    try:
        described = set(yaml.safe_load(services_path.read_text(encoding="utf-8")) or {})
    except yaml.YAMLError as err:
        error(f"services.yaml : YAML invalide — {err}")
        return

    if declared:
        if declared - described:
            error(
                "Services déclarés dans const.py mais absents de services.yaml : "
                f"{', '.join(sorted(declared - described))}"
            )
        if described - declared:
            warn(
                "Services décrits dans services.yaml sans constante correspondante : "
                f"{', '.join(sorted(described - declared))}"
            )
        if declared == described:
            ok(f"{len(declared)} service(s) cohérent(s) entre const.py et services.yaml")

    strings = load_json(integration / "strings.json") or {}
    translated = set(strings.get("services", {}))
    if described - translated:
        warn(
            "Services sans traduction dans strings.json : "
            f"{', '.join(sorted(described - translated))}"
        )
    elif described:
        ok("Tous les services sont traduits")


# ----------------------------------------------------------------------
# Icônes
# ----------------------------------------------------------------------


def check_brand(integration: Path) -> None:
    brand = integration / "brand"
    if not brand.is_dir():
        error(
            "brand/ est absent : HACS exige des images de marque, et depuis Home "
            "Assistant 2026.3 elles se livrent dans custom_components/<domain>/brand/."
        )
        return

    icon = brand / "icon.png"
    if not icon.exists():
        error("brand/icon.png est obligatoire.")
        return

    expected = {"icon.png": 256, "icon@2x.png": 512}
    for name, size in expected.items():
        path = brand / name
        if not path.exists():
            if name == "icon@2x.png":
                warn("brand/icon@2x.png (512×512) est recommandé pour les écrans hDPI.")
            continue
        if Image is None:
            ok(f"brand/{name} présent (dimensions non vérifiées, Pillow absent)")
            continue
        with Image.open(path) as image:
            if image.size != (size, size):
                error(
                    f"brand/{name} : {image.size[0]}×{image.size[1]} au lieu de "
                    f"{size}×{size}."
                )
            elif image.mode != "RGBA":
                warn(f"brand/{name} : mode {image.mode}, la transparence est préférée.")
            else:
                ok(f"brand/{name} : {size}×{size} RGBA")


# ----------------------------------------------------------------------
# Syntaxe
# ----------------------------------------------------------------------


def check_syntax(integration: Path) -> None:
    failures = 0
    count = 0
    for path in sorted(integration.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        count += 1
        try:
            ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as err:
            error(f"{path.relative_to(integration)} : erreur de syntaxe ligne {err.lineno}")
            failures += 1
    if not failures and count:
        ok(f"{count} fichier(s) Python sans erreur de syntaxe")


# ----------------------------------------------------------------------
# Mode --publish : critères du magasin HACS par défaut
# ----------------------------------------------------------------------


def check_documentation_files(root: Path) -> None:
    readme = next((p for p in root.glob("README*") if p.is_file()), None)
    if readme is None:
        error("README absent : HACS l'exige pour toute soumission.")
    elif len(readme.read_text(encoding="utf-8", errors="replace").strip()) < 200:
        warn("Le README semble très court pour documenter l'usage.")
    else:
        ok(f"{readme.name} présent")

    if not any(root.glob("LICENSE*")):
        warn("LICENSE absent : fortement recommandé pour un dépôt public.")
    else:
        ok("LICENSE présent")


def check_workflows(root: Path) -> None:
    """Les deux actions doivent exister et passer sans exclusion."""
    workflows = root / ".github" / "workflows"
    if not workflows.is_dir():
        error(
            ".github/workflows/ absent : les actions hassfest et HACS sont "
            "exigées pour la soumission au magasin par défaut."
        )
        return

    content = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in workflows.glob("*.y*ml")
    )

    if "hacs/action" not in content:
        error("Workflow manquant : l'action HACS (hacs/action) est exigée.")
    else:
        ok("Workflow HACS présent")

    if "hassfest" not in content:
        error("Workflow manquant : l'action hassfest est exigée pour les intégrations.")
    else:
        ok("Workflow hassfest présent")

    if re.search(r"^\s*ignore:", content, re.M):
        error(
            "L'action HACS utilise « ignore » : la soumission exige qu'elle passe "
            "sans aucune exclusion. Retirer ce paramètre et corriger la cause."
        )
    elif "hacs/action" in content:
        ok("L'action HACS ne masque aucun contrôle")

    # Créer la release à la main expose à deux oublis : croire qu'un tag
    # suffit, et taguer sans avoir incrémenté le manifest.
    if re.search(r"tags:\s*\n\s*-", content) or "gh release create" in content:
        ok("Workflow de publication automatique des releases présent")
    else:
        warn(
            "Aucun workflow ne crée la release au push d'un tag : la publication "
            "reste manuelle, et rien ne vérifie que le tag correspond à la version "
            "du manifest."
        )


def check_release_version(root: Path, manifest: dict) -> None:
    """Compare la version du manifest au dernier tag Git, si disponible."""
    version = manifest.get("version")
    if not version:
        return
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "tag", "--sort=-creatordate"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return
    if result.returncode != 0:
        return

    tags = [t.strip() for t in result.stdout.splitlines() if t.strip()]
    if not tags:
        warn(
            "Aucun tag Git : HACS exige au moins une release publiée "
            "(un tag seul ne suffit pas, il faut une release GitHub)."
        )
        return

    latest = tags[0].lstrip("vV")
    if latest != str(version):
        warn(
            f"Le dernier tag ({tags[0]}) ne correspond pas à la version du manifest "
            f"({version}) : penser à publier une release pour cette version."
        )
    else:
        ok(f"Version du manifest alignée sur le dernier tag ({tags[0]})")


MANUAL_CHECKLIST = [
    "le dépôt est public et non archivé",
    "le dépôt a une description",
    "le dépôt a des topics",
    "les issues sont activées",
    "une release GitHub complète existe, créée APRÈS le passage des workflows",
    "la soumission se fait par pull request sur hacs/default (pas par une issue)",
    "la ligne est insérée par ordre alphabétique dans le fichier ./integration",
    "la PR part d'une branche dédiée d'un fork personnel, pas d'une organisation",
]


def publish_checklist() -> None:
    print("\nÀ vérifier à la main (dépend de GitHub, non contrôlable hors ligne) :")
    for item in MANUAL_CHECKLIST:
        print(f"  [ ] {item}")


# ----------------------------------------------------------------------


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}

    if not args:
        print(__doc__)
        return 2

    publish = "--publish" in flags

    root = Path(args[0]).resolve()
    if not root.is_dir():
        print(f"Chemin introuvable : {root}")
        return 2

    mode = " (mode publication)" if publish else ""
    print(f"Contrôle de {root}{mode}\n")

    integration = find_integration(root)
    if integration is not None:
        manifest = check_manifest(integration)
        check_hacs_json(root, integration)
        check_dependencies(integration, manifest)
        check_module_functions(integration)
        check_migration(integration)
        check_deprecated_patterns(integration)
        check_translations(integration)
        check_services(integration)
        check_brand(integration)
        check_syntax(integration)

        if publish:
            check_documentation_files(root)
            check_workflows(root)
            check_release_version(root, manifest)

    for message in PASSED:
        print(f"  ok       {message}")
    for message in WARNINGS:
        print(f"  attention {message}")
    for message in ERRORS:
        print(f"  ERREUR   {message}")

    print(
        f"\n{len(PASSED)} contrôle(s) passé(s), "
        f"{len(WARNINGS)} avertissement(s), {len(ERRORS)} erreur(s)."
    )

    if publish:
        publish_checklist()

    return 1 if ERRORS else 0


if __name__ == "__main__":
    sys.exit(main())
