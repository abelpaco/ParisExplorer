"""Chargement des sujets depuis ``content/topics/*.yaml``.

POURQUOI CE MODULE EXISTE
-------------------------
Les sujets vivaient dans une liste Python codee en dur (``PARIS_TOPICS``, 8
entrees). Deux consequences : ajouter un sujet demandait de modifier du code, et
la chaine plafonnait a 8 videos avant de republier.

Ici, un sujet = un fichier YAML. On en ajoute autant qu'on veut sans toucher au
Python, et un non-developpeur peut ecrire du contenu.

PARTI PRIS SUR LA VALIDATION
----------------------------
Un sujet mal forme n'est PAS ignore en silence : il est ecarte AVEC un log
d'erreur explicite. Un sujet qui disparait sans bruit, c'est une video qui ne
sort pas et personne qui comprend pourquoi.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

DEFAULT_TOPICS_DIR = Path("content/topics")
SUPPORTED_LANGS = ("fr", "en")

# En dessous de ~300 mots la voix off ne tient pas 2 minutes : le format cible
# n'est pas atteint. On previent au chargement plutot qu'a la publication.
MIN_NARRATION_WORDS = 300

# Date anniversaire : MM-JJ, sans annee — l'evenement revient chaque annee.
# La validation est stricte : un « 8-12 » silencieusement tolere ne matcherait
# jamais le « 08-12 » produit par strftime, et le sujet ne sortirait jamais.
ANCHOR_DATE_RE = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


class TopicError(ValueError):
    """Sujet invalide : champs manquants ou structure incorrecte."""


@dataclass
class TopicText:
    """Textes d'un sujet dans UNE langue."""

    title: str
    subtitle: str
    narration: str
    tags: List[str] = field(default_factory=list)
    # Accroches des cartes visuelles. Optionnel : sans ce bloc, les cartes sont
    # decoupees dans la narration. L'ecrire donne des phrases pensees POUR
    # l'image plutot que pour la voix off — ce n'est pas le meme exercice.
    cards: List[str] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return len(self.narration.split())


@dataclass
class Topic:
    """Un sujet de la chaine, dans toutes ses langues."""

    id: str
    category: str
    status: str
    image_queries: List[str]
    langs: Dict[str, TopicText]
    source_path: Optional[Path] = None
    # Date anniversaire (MM-JJ). Un sujet ancre n'est planifie QUE ce jour-la,
    # chaque annee : « ce jour-la a Paris ». Sans ancre, le sujet est planifiable
    # n'importe quand, comme avant.
    anchor_date: Optional[str] = None

    @property
    def is_ready(self) -> bool:
        return self.status == "ready"

    def text(self, lang: str) -> TopicText:
        """Textes dans la langue demandee, repli sur le francais."""
        return self.langs.get(lang) or self.langs["fr"]


def _parse_lang_block(topic_id: str, lang: str, raw: Any) -> TopicText:
    if not isinstance(raw, dict):
        raise TopicError(f"{topic_id}: le bloc '{lang}' doit etre un dictionnaire")
    missing = [k for k in ("title", "narration") if not raw.get(k)]
    if missing:
        raise TopicError(f"{topic_id}[{lang}]: champ(s) manquant(s) : {', '.join(missing)}")
    tags = raw.get("tags") or []
    if not isinstance(tags, list):
        raise TopicError(f"{topic_id}[{lang}]: 'tags' doit etre une liste")
    cards = raw.get("cards") or []
    if not isinstance(cards, list):
        raise TopicError(f"{topic_id}[{lang}]: 'cards' doit etre une liste")
    return TopicText(
        title=str(raw["title"]).strip(),
        subtitle=str(raw.get("subtitle", "")).strip(),
        narration=str(raw["narration"]).strip(),
        tags=[str(t) for t in tags],
        cards=[" ".join(str(c).split()) for c in cards if str(c).strip()],
    )


def parse_topic(raw: Any, source_path: Optional[Path] = None) -> Topic:
    """Construit un Topic depuis un dict YAML, ou leve TopicError."""
    if not isinstance(raw, dict):
        raise TopicError(f"{source_path}: le fichier doit contenir un dictionnaire")

    topic_id = str(raw.get("id") or "").strip()
    if not topic_id:
        raise TopicError(f"{source_path}: champ 'id' manquant")

    queries = raw.get("image_queries") or []
    if not isinstance(queries, list) or not queries:
        raise TopicError(f"{topic_id}: 'image_queries' doit etre une liste non vide")

    anchor_date = raw.get("anchor_date")
    if anchor_date is not None:
        anchor_date = str(anchor_date).strip()
        if not ANCHOR_DATE_RE.match(anchor_date):
            raise TopicError(
                f"{topic_id}: 'anchor_date' doit etre au format MM-JJ "
                f"(ex. 08-25), recu : {anchor_date!r}"
            )

    langs: Dict[str, TopicText] = {}
    for lang in SUPPORTED_LANGS:
        if lang in raw:
            langs[lang] = _parse_lang_block(topic_id, lang, raw[lang])
    if "fr" not in langs:
        raise TopicError(f"{topic_id}: le bloc 'fr' est obligatoire")
    for lang in SUPPORTED_LANGS:
        if lang not in langs:
            # Non bloquant : on publiera dans les langues disponibles.
            logger.warning("%s: pas de narration '%s' — cette langue sera ignoree", topic_id, lang)

    for lang, text in langs.items():
        if text.word_count < MIN_NARRATION_WORDS:
            logger.warning(
                "%s[%s]: narration de %d mots (< %d) — la video sera plus courte "
                "que le format vise de 2-3 min",
                topic_id,
                lang,
                text.word_count,
                MIN_NARRATION_WORDS,
            )

    return Topic(
        id=topic_id,
        category=str(raw.get("category", "decouverte")),
        status=str(raw.get("status", "draft")),
        image_queries=[str(q) for q in queries],
        langs=langs,
        source_path=source_path,
        anchor_date=anchor_date,
    )


def load_topics(
    topics_dir: Optional[Path | str] = None, only_ready: bool = True
) -> List[Topic]:
    """Charge tous les sujets du dossier, tries par identifiant.

    Args:
        topics_dir: dossier des YAML (defaut ``content/topics``).
        only_ready: ne retenir que les sujets en ``status: ready``.
    """
    directory = Path(topics_dir) if topics_dir else DEFAULT_TOPICS_DIR
    if not directory.exists():
        logger.error("Dossier des sujets introuvable : %s", directory)
        return []

    topics: List[Topic] = []
    for path in sorted(directory.glob("*.yaml")):
        if path.name.startswith("_"):
            continue  # fichiers de documentation (_SCHEMA.md et consorts)
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            topics.append(parse_topic(raw, source_path=path))
        except (TopicError, yaml.YAMLError, OSError) as exc:
            logger.error("Sujet ignore (%s) : %s", path.name, exc)

    if only_ready:
        drafts = [t.id for t in topics if not t.is_ready]
        if drafts:
            logger.info("Sujets en brouillon, non publiables : %s", ", ".join(drafts))
        topics = [t for t in topics if t.is_ready]

    logger.info("%d sujet(s) disponible(s) dans %s", len(topics), directory)
    return topics
