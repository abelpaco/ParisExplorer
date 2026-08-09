"""Chargement des sujets BD depuis ``content/bd/*.yaml``.

POURQUOI CE MODULE EXISTE
-------------------------
Les sujets video (``content/topics``) decrivent une narration de 350 mots et
des requetes d'images : rien de tout ca ne decrit un portrait ligne claire ni
les scenes d'un Short BD de 45 a 90 secondes. Plutot que de tordre le schema
existant, les sujets BD ont le leur — meme esprit, memes regles : un fichier
YAML par sujet, validation stricte, un sujet mal forme est ecarte AVEC un log.

DEUX SORTES DE SUJETS
---------------------
- ``kind: naissance`` : un(e) Parisien(ne) celebre, avec son portrait.
- ``kind: anniversaire`` : un evenement date, avec un pictogramme.

Dans les deux cas, ``anchor_date`` (MM-JJ) fait du sujet un « ce jour-la » que
le planificateur ne place QUE ce jour-la — la meme regle que les sujets video.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

import bd_style
from topic_loader import ANCHOR_DATE_RE, SUPPORTED_LANGS

logger = logging.getLogger(__name__)

DEFAULT_BD_DIR = Path("content/bd")

KINDS = ("naissance", "anniversaire")

# Bornes du nombre de scenes. En dessous de 3, le Short n'a pas d'arc ; au-dela
# de 8, il depasse les 90 secondes visees des que les phrases respirent.
MIN_SCENES, MAX_SCENES = 3, 8

# Bandeau par defaut : une question, pas une categorie. « Le saviez-vous ? »
# attise la curiosite la ou « Naissance d'un Parisien celebre » ne fait
# qu'etiqueter — directive de Paco du 09/08. Un sujet peut toujours imposer le
# sien via son champ ``header``.
HEADERS = {
    "naissance": {
        "fr": {"m": "Le saviez-vous ?", "f": "Le saviez-vous ?"},
        "en": {"m": "Did you know?", "f": "Did you know?"},
    },
    "anniversaire": {
        "fr": {"m": "Le saviez-vous ?", "f": "Le saviez-vous ?"},
        "en": {"m": "Did you know?", "f": "Did you know?"},
    },
}

CTA_DEFAULT = {
    "fr": "Abonne-toi — une histoire de Paris chaque jour.",
    "en": "Subscribe — one Paris story every day.",
}


class BdTopicError(ValueError):
    """Sujet BD invalide : champs manquants ou vocabulaire inconnu."""


@dataclass
class Scene:
    """Une scene : une phrase racontee, un pictogramme qui l'ancre."""

    text: str
    icon: str


@dataclass
class BdText:
    """Textes d'un sujet BD dans UNE langue."""

    title: str
    name: str
    hook: str
    fact: str
    scenes: List[Scene]
    real_name: str = ""
    date_line: str = ""
    place_line: str = ""
    header: str = ""
    cta: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass
class BdSubject:
    """Un sujet BD, dans toutes ses langues."""

    id: str
    kind: str
    category: str
    status: str
    langs: Dict[str, BdText]
    genre: str = "m"
    anchor_date: Optional[str] = None
    year: Optional[int] = None
    accent: str = bd_style.RED
    icon: str = "etoile"
    portrait: Optional[bd_style.Portrait] = None
    source_path: Optional[Path] = None

    @property
    def is_ready(self) -> bool:
        return self.status == "ready"

    def text(self, lang: str) -> BdText:
        """Textes dans la langue demandee, repli sur le francais."""
        return self.langs.get(lang) or self.langs["fr"]

    def header(self, lang: str) -> str:
        explicit = self.text(lang).header
        if explicit:
            return explicit
        table = HEADERS[self.kind].get(lang) or HEADERS[self.kind]["fr"]
        return table.get(self.genre, table["m"])

    def cta(self, lang: str) -> str:
        return self.text(lang).cta or CTA_DEFAULT.get(lang, CTA_DEFAULT["fr"])

    def footer(self, lang: str) -> str:
        """Signature en pied des cartes de scene : « MOLIÈRE · 1622 »."""
        name = self.text(lang).name
        return f"{name} · {self.year}" if self.year else name


def _parse_scene(topic_id: str, lang: str, position: int, raw: Any,
                 default_icon: str) -> Scene:
    if isinstance(raw, str):
        text, icon = raw, default_icon
    elif isinstance(raw, dict):
        text = str(raw.get("text") or "").strip()
        icon = str(raw.get("icon") or default_icon).strip()
    else:
        raise BdTopicError(
            f"{topic_id}[{lang}]: scene {position} — attendu un texte ou un "
            f"dictionnaire {{text, icon}}"
        )
    text = " ".join(str(text).split())
    if not text:
        raise BdTopicError(f"{topic_id}[{lang}]: scene {position} sans texte")
    if icon not in bd_style.ICONS:
        raise BdTopicError(
            f"{topic_id}[{lang}]: scene {position} — pictogramme inconnu "
            f"{icon!r}. Connus : {', '.join(sorted(bd_style.ICONS))}"
        )
    return Scene(text=text, icon=icon)


def _parse_lang_block(topic_id: str, lang: str, raw: Any, default_icon: str) -> BdText:
    if not isinstance(raw, dict):
        raise BdTopicError(f"{topic_id}: le bloc '{lang}' doit etre un dictionnaire")
    missing = [k for k in ("title", "name", "hook", "fact") if not raw.get(k)]
    if missing:
        raise BdTopicError(
            f"{topic_id}[{lang}]: champ(s) manquant(s) : {', '.join(missing)}"
        )
    scenes_raw = raw.get("scenes") or []
    if not isinstance(scenes_raw, list) or not scenes_raw:
        raise BdTopicError(f"{topic_id}[{lang}]: 'scenes' doit etre une liste non vide")
    scenes = [
        _parse_scene(topic_id, lang, i, s, default_icon)
        for i, s in enumerate(scenes_raw, start=1)
    ]
    if not MIN_SCENES <= len(scenes) <= MAX_SCENES:
        logger.warning(
            "%s[%s]: %d scene(s) — vise %d a %d pour tenir 45-90 s",
            topic_id, lang, len(scenes), MIN_SCENES, MAX_SCENES,
        )
    tags = raw.get("tags") or []
    if not isinstance(tags, list):
        raise BdTopicError(f"{topic_id}[{lang}]: 'tags' doit etre une liste")
    return BdText(
        title=str(raw["title"]).strip(),
        name=str(raw["name"]).strip(),
        hook=" ".join(str(raw["hook"]).split()),
        fact=" ".join(str(raw["fact"]).split()),
        scenes=scenes,
        real_name=str(raw.get("real_name", "")).strip(),
        date_line=str(raw.get("date_line", "")).strip(),
        place_line=str(raw.get("place_line", "")).strip(),
        header=str(raw.get("header", "")).strip(),
        cta=str(raw.get("cta", "")).strip(),
        tags=[str(t) for t in tags],
    )


def _parse_portrait(topic_id: str, raw: Any) -> bd_style.Portrait:
    if not isinstance(raw, dict):
        raise BdTopicError(f"{topic_id}: 'portrait' doit etre un dictionnaire")
    known = {"cheveux", "couleur_cheveux", "pilosite", "costume",
             "couleur_costume", "teint", "accessoires"}
    unknown = set(raw) - known
    if unknown:
        raise BdTopicError(
            f"{topic_id}: champ(s) de portrait inconnu(s) : {', '.join(sorted(unknown))}. "
            f"Connus : {', '.join(sorted(known))}"
        )
    portrait = bd_style.Portrait(
        cheveux=str(raw.get("cheveux", "courts")),
        couleur_cheveux=str(raw.get("couleur_cheveux", "#3a2a1a")),
        pilosite=[str(p) for p in (raw.get("pilosite") or [])],
        costume=str(raw.get("costume", "moderne")),
        couleur_costume=str(raw.get("couleur_costume", "#2f4b6b")),
        teint=str(raw.get("teint", bd_style.SKIN_DEFAULT)),
        accessoires=[str(a) for a in (raw.get("accessoires") or [])],
    )
    try:
        portrait.check()
    except bd_style.StyleError as exc:
        raise BdTopicError(f"{topic_id}: {exc}") from exc
    return portrait


def parse_subject(raw: Any, source_path: Optional[Path] = None) -> BdSubject:
    """Construit un BdSubject depuis un dict YAML, ou leve BdTopicError."""
    if not isinstance(raw, dict):
        raise BdTopicError(f"{source_path}: le fichier doit contenir un dictionnaire")

    topic_id = str(raw.get("id") or "").strip()
    if not topic_id:
        raise BdTopicError(f"{source_path}: champ 'id' manquant")

    kind = str(raw.get("kind") or "").strip()
    if kind not in KINDS:
        raise BdTopicError(
            f"{topic_id}: 'kind' doit valoir {' ou '.join(KINDS)}, recu {kind!r}"
        )

    genre = str(raw.get("genre", "m")).strip().lower()
    if genre not in ("m", "f"):
        raise BdTopicError(f"{topic_id}: 'genre' doit valoir m ou f, recu {genre!r}")

    anchor_date = raw.get("anchor_date")
    if anchor_date is not None:
        anchor_date = str(anchor_date).strip()
        if not ANCHOR_DATE_RE.match(anchor_date):
            raise BdTopicError(
                f"{topic_id}: 'anchor_date' doit etre au format MM-JJ "
                f"(ex. 01-15), recu : {anchor_date!r}"
            )

    icon = str(raw.get("icon", "etoile")).strip()
    if icon not in bd_style.ICONS:
        raise BdTopicError(
            f"{topic_id}: pictogramme inconnu {icon!r}. "
            f"Connus : {', '.join(sorted(bd_style.ICONS))}"
        )

    portrait = None
    if raw.get("portrait") is not None:
        portrait = _parse_portrait(topic_id, raw["portrait"])
    if kind == "naissance" and portrait is None:
        raise BdTopicError(
            f"{topic_id}: un sujet 'naissance' doit decrire son 'portrait'"
        )

    year = raw.get("year")
    if year is not None:
        try:
            year = int(year)
        except (TypeError, ValueError) as exc:
            raise BdTopicError(f"{topic_id}: 'year' doit etre un entier") from exc

    langs: Dict[str, BdText] = {}
    for lang in SUPPORTED_LANGS:
        if lang in raw:
            langs[lang] = _parse_lang_block(topic_id, lang, raw[lang], icon)
    if "fr" not in langs:
        raise BdTopicError(f"{topic_id}: le bloc 'fr' est obligatoire")
    for lang in SUPPORTED_LANGS:
        if lang not in langs:
            logger.warning(
                "%s: pas de textes '%s' — cette langue sera ignoree", topic_id, lang
            )

    return BdSubject(
        id=topic_id,
        kind=kind,
        category=str(raw.get("category", "histoire")),
        status=str(raw.get("status", "draft")),
        langs=langs,
        genre=genre,
        anchor_date=anchor_date,
        year=year,
        accent=str(raw.get("accent", bd_style.RED)),
        icon=icon,
        portrait=portrait,
        source_path=source_path,
    )


def load_subjects(
    bd_dir: Optional[Path | str] = None, only_ready: bool = True
) -> List[BdSubject]:
    """Charge tous les sujets BD du dossier, tries par identifiant.

    Un dossier absent n'est pas une erreur : la plupart des commandes de la
    chaine tournent sans aucun sujet BD, et doivent continuer a le faire.
    """
    directory = Path(bd_dir) if bd_dir else DEFAULT_BD_DIR
    if not directory.exists():
        return []

    subjects: List[BdSubject] = []
    for path in sorted(directory.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            subjects.append(parse_subject(raw, source_path=path))
        except (BdTopicError, yaml.YAMLError, OSError) as exc:
            logger.error("Sujet BD ignore (%s) : %s", path.name, exc)

    if only_ready:
        drafts = [s.id for s in subjects if not s.is_ready]
        if drafts:
            logger.info("Sujets BD en brouillon, non publiables : %s", ", ".join(drafts))
        subjects = [s for s in subjects if s.is_ready]

    logger.info("%d sujet(s) BD dans %s", len(subjects), directory)
    return subjects
