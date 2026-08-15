"""Chargement des sujets « cartes de lieux » depuis ``content/lieux/*.yaml``.

POURQUOI CE MODULE EXISTE
-------------------------
Les cartes de lieux des posts Communaute (quartier, place, lieu urbain) ne
sont ni des sujets video (``content/topics``) ni des sujets BD
(``content/bd``) : une carte de lieu n'a pas de narration de 350 mots ni de
storyboard — elle a UNE scene dessinee, UNE anecdote en deux lignes, et une
legende de post. Plutot que de tordre un schema existant, les lieux ont le
leur — meme esprit, memes regles que ``bd_topics`` : un fichier YAML par
sujet, vocabulaire ferme, echec bruyant.

LE TYPE IMPOSE LE STYLE
-----------------------
C'est la charte validee par Paco le 14/08/2026
(``content/cartes-lieux-echantillons/LISEZMOI.md``) : un QUARTIER se peint en
impressionniste Belle Epoque, une PLACE s'encre en BD, un LIEU URBAIN se lave
a l'aquarelle. Le YAML ne choisit donc PAS son style : il declare son type,
et le style en decoule. Ca garantit qu'aucun sujet ne « sortira de la
charte » par une simple faute de frappe dans un champ style.

L'ANECDOTE EST EN DEUX LIGNES, ET C'EST VOULU
---------------------------------------------
La cesure de l'anecdote est un choix EDITORIAL, pas un repliement
automatique : sur les references validees, la coupe tombe la ou la phrase
respire. Le YAML porte donc deux lignes exactes, et le pipeline les pose
telles quelles — pas de ``wrap_text`` ici.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

import lieu_style
from topic_loader import SUPPORTED_LANGS

logger = logging.getLogger(__name__)

DEFAULT_LIEUX_DIR = Path("content/lieux")

# Le vocabulaire ferme des types, et le style que chacun IMPOSE.
TYPES_STYLE = {
    "quartier": "impressionniste",
    "place": "bd-encrage",
    "urbain": "aquarelle",
}

# Les seules cles admises, au niveau du fichier et dans un bloc de langue.
_CLES_RACINE = {"id", "type", "scene"} | set(SUPPORTED_LANGS)
_CLES_LANGUE = {"anecdote", "sous_titre", "titre", "legende"}


class LieuError(ValueError):
    """Sujet de lieu invalide : champ manquant ou vocabulaire inconnu."""


@dataclass
class LieuTextes:
    """Textes d'un lieu dans UNE langue."""

    anecdote: List[str]     # exactement 2 lignes, cesure editoriale
    sous_titre: str         # ex. « MONTMARTRE » — pied du cartel impressionniste
    titre: str              # titre du pack de posts
    legende: str            # legende prete a coller du post Communaute


@dataclass
class Lieu:
    """Un lieu, dans toutes ses langues."""

    id: str
    type: str
    scene: str
    langs: Dict[str, LieuTextes]
    source_path: Optional[Path] = None

    @property
    def style(self) -> str:
        return TYPES_STYLE[self.type]

    def textes(self, lang: str) -> LieuTextes:
        """Textes dans la langue demandee — PAS de repli silencieux.

        Une carte rendue « en » avec des textes « fr » serait publiee telle
        quelle : mieux vaut echouer que livrer une carte bilingue malgre elle.
        """
        try:
            return self.langs[lang]
        except KeyError:
            raise LieuError(
                f"« {self.id} » n'a pas de textes '{lang}'. "
                f"Langues disponibles : {', '.join(sorted(self.langs))}"
            ) from None


def _parse_lang_block(lieu_id: str, lang: str, raw: Any) -> LieuTextes:
    if not isinstance(raw, dict):
        raise LieuError(f"{lieu_id}: le bloc '{lang}' doit etre un dictionnaire")
    inconnues = set(raw) - _CLES_LANGUE
    if inconnues:
        raise LieuError(
            f"{lieu_id}[{lang}]: cle(s) inconnue(s) : {', '.join(sorted(inconnues))}. "
            f"Admises : {', '.join(sorted(_CLES_LANGUE))}"
        )
    manquantes = [k for k in _CLES_LANGUE if not raw.get(k)]
    if manquantes:
        raise LieuError(
            f"{lieu_id}[{lang}]: champ(s) manquant(s) : {', '.join(sorted(manquantes))}"
        )
    anecdote = raw["anecdote"]
    if (not isinstance(anecdote, list) or len(anecdote) != 2
            or not all(isinstance(l, str) and l.strip() for l in anecdote)):
        raise LieuError(
            f"{lieu_id}[{lang}]: 'anecdote' doit etre une liste de 2 lignes non "
            f"vides — la cesure est un choix editorial, pas un repliement"
        )
    return LieuTextes(
        anecdote=[l.strip() for l in anecdote],
        sous_titre=str(raw["sous_titre"]).strip(),
        titre=str(raw["titre"]).strip(),
        legende=" ".join(str(raw["legende"]).split()),
    )


def parse_lieu(raw: Any, source_path: Optional[Path] = None) -> Lieu:
    """Construit un Lieu depuis un dict YAML, ou leve LieuError."""
    if not isinstance(raw, dict):
        raise LieuError(f"{source_path}: le fichier doit contenir un dictionnaire")

    inconnues = set(raw) - _CLES_RACINE
    if inconnues:
        raise LieuError(
            f"{source_path}: cle(s) inconnue(s) : {', '.join(sorted(inconnues))}. "
            f"Admises : {', '.join(sorted(_CLES_RACINE))}"
        )

    lieu_id = str(raw.get("id") or "").strip()
    if not lieu_id:
        raise LieuError(f"{source_path}: champ 'id' manquant")

    type_ = str(raw.get("type") or "").strip()
    if type_ not in TYPES_STYLE:
        raise LieuError(
            f"{lieu_id}: 'type' doit valoir {' | '.join(sorted(TYPES_STYLE))}, "
            f"recu {type_!r}"
        )

    scene = str(raw.get("scene") or "").strip()
    if scene not in lieu_style.SCENES:
        raise LieuError(
            f"{lieu_id}: scene inconnue {scene!r}. "
            f"Enregistrees : {', '.join(sorted(lieu_style.SCENES))}"
        )
    style_scene = lieu_style.SCENES[scene].style
    style_type = TYPES_STYLE[type_]
    if style_scene != style_type:
        raise LieuError(
            f"{lieu_id}: le type '{type_}' impose le style '{style_type}' mais la "
            f"scene '{scene}' est dessinee en '{style_scene}' — change le type ou "
            f"la scene, la charte ne se contourne pas dans le YAML"
        )

    langs: Dict[str, LieuTextes] = {}
    for lang in SUPPORTED_LANGS:
        if lang in raw:
            langs[lang] = _parse_lang_block(lieu_id, lang, raw[lang])
    if "fr" not in langs:
        raise LieuError(f"{lieu_id}: le bloc 'fr' est obligatoire")
    for lang in SUPPORTED_LANGS:
        if lang not in langs:
            logger.warning(
                "%s: pas de textes '%s' — cette langue sera ignoree", lieu_id, lang
            )

    return Lieu(id=lieu_id, type=type_, scene=scene, langs=langs,
                source_path=source_path)


def load_lieu(lieu_id: str, lieux_dir: Optional[Path | str] = None) -> Lieu:
    """Charge UN lieu par identifiant, ou leve LieuError — jamais en silence."""
    directory = Path(lieux_dir) if lieux_dir else DEFAULT_LIEUX_DIR
    path = directory / f"{lieu_id}.yaml"
    if not path.exists():
        disponibles = sorted(p.stem for p in directory.glob("*.yaml")) \
            if directory.exists() else []
        raise LieuError(
            f"Lieu inconnu : {lieu_id} ({path} n'existe pas). "
            f"Disponibles : {', '.join(disponibles) or '(aucun)'}"
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError) as exc:
        raise LieuError(f"{path}: YAML illisible : {exc}") from exc
    return parse_lieu(raw, source_path=path)


def load_lieux(lieux_dir: Optional[Path | str] = None) -> List[Lieu]:
    """Charge tous les lieux du dossier, tries par identifiant.

    Meme regle que ``bd_topics.load_subjects`` : un fichier invalide est
    ecarte AVEC un log d'erreur, un dossier absent n'est pas une erreur.
    """
    directory = Path(lieux_dir) if lieux_dir else DEFAULT_LIEUX_DIR
    if not directory.exists():
        return []
    lieux: List[Lieu] = []
    for path in sorted(directory.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            lieux.append(parse_lieu(raw, source_path=path))
        except (LieuError, yaml.YAMLError, OSError) as exc:
            logger.error("Lieu ignore (%s) : %s", path.name, exc)
    logger.info("%d lieu(x) dans %s", len(lieux), directory)
    return lieux
