"""Compose un calendrier de publication a partir de ce qui est REELLEMENT produit.

POURQUOI CE MODULE EXISTE
-------------------------
Tenir cinq publications par jour ne demande pas seulement d'avoir assez de
fichiers : il faut decider lequel sort quand. Pris au hasard, le calendrier
enchaine deux fois le meme sujet, ou trois videos francaises d'affilee, ou deux
Shorts tires de la meme narration. Chacun de ces cas donne au spectateur
l'impression d'un fil qui se repete.

Le planificateur repartit donc en respectant trois regles, dans cet ordre :

1. **Jamais deux publications du meme sujet le meme jour.** Un spectateur qui
   ouvre la chaine dans la journee ne doit pas tomber deux fois sur la meme
   histoire.
2. **Alternance des langues.** Deux publications consecutives ne sont pas dans
   la meme langue tant qu'un choix reste possible.
3. **Alternance des categories.** On evite trois monuments a la suite.

Ce qui est deja publie est exclu par le registre, pas par une liste tenue a la
main : c'est la meme memoire longue qui empeche les republications.

CE QUE CE MODULE NE FAIT PAS
----------------------------
Il ne publie rien. Il ecrit un plan, qu'on lit et qu'on corrige avant que quoi
que ce soit ne parte. La publication reste une commande separee et explicite.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_DIR = Path(__file__).resolve().parent
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(PROJECT_DIR))

logger = logging.getLogger("plan")

VIDEOS_ROOT = Path("content/videos")
PLAN_FILE = Path("content/metadata/publication_plan.json")

# Creneaux par defaut : deux le matin, deux l'apres-midi, un le soir.
DEFAULT_SLOTS = ["08:00", "10:30", "13:00", "16:30", "19:30"]

# Un quota d'API standard (10 000 unites par jour) et un envoi a ~1600 unites
# donnent six envois quotidiens au maximum. On refuse d'en planifier plus :
# depasser ne produit pas une erreur claire, ca produit des echecs en fin de
# journee, quand personne ne regarde.
MAX_UPLOADS_PER_DAY = 6

# Nombre maximal de publications tirees d'une meme unite sujet+langue. Les
# Shorts sont decoupes dans la narration de la video longue : au-dela de deux,
# on sert le meme contenu.
MAX_PER_UNIT = 2


@dataclass
class Item:
    """Une publication candidate : un fichier, et de quoi la situer."""

    topic_id: str
    lang: str
    kind: str  # "long" ou "short"
    short_index: Optional[int]
    video: Path
    meta: Path
    category: str
    title: str

    @property
    def key(self) -> str:
        base = f"{self.topic_id}:{self.lang}"
        return f"{base}:short-{self.short_index}" if self.short_index else base

    @property
    def unit(self) -> str:
        return f"{self.topic_id}:{self.lang}"


@dataclass
class Slot:
    """Un creneau du calendrier."""

    when: datetime
    item: Item

    def as_dict(self) -> dict:
        return {
            "when": self.when.isoformat(timespec="minutes"),
            "key": self.item.key,
            "kind": self.item.kind,
            "lang": self.item.lang,
            "category": self.item.category,
            "title": self.item.title,
            "video": str(self.item.video),
            "meta": str(self.item.meta),
            "short": self.item.short_index,
        }


def discover(topics: Dict[str, str]) -> List[Item]:
    """Recense les videos produites sur le disque, longues et Shorts.

    On lit le DISQUE, pas une liste de ce qu'on croit avoir fabrique : un rendu
    interrompu laisse un sujet a moitie produit, et le plan doit refleter ce qui
    existe vraiment.
    """
    items: List[Item] = []
    for meta_file in sorted(VIDEOS_ROOT.glob("*/*.json")):
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Metadonnees illisibles (%s) : %s", meta_file, exc)
            continue

        topic_id, lang = data["topic_id"], data["lang"]
        category = topics.get(topic_id, "decouverte")

        long_video = Path(data["video"]) if data.get("video") else None
        if long_video and long_video.exists():
            items.append(Item(topic_id, lang, "long", None, long_video, meta_file,
                              category, data["title"]))

        for index, short in enumerate(data.get("shorts", []), start=1):
            path = Path(short)
            if path.exists():
                items.append(Item(topic_id, lang, "short", index, path, meta_file,
                                  category, data["title"]))
    return items


def _score(item: Item, previous: Optional[Item], day_topics: set) -> tuple:
    """Cle de tri : plus c'est petit, plus le candidat convient a ce creneau.

    L'ordre des composantes EST la priorite des regles. Le sujet deja vu dans la
    journee pese plus lourd que la langue, qui pese plus lourd que la categorie.
    """
    same_topic_today = item.topic_id in day_topics
    same_lang = previous is not None and item.lang == previous.lang
    same_category = previous is not None and item.category == previous.category
    # Les videos longues passent avant les Shorts a egalite : ce sont elles qui
    # font le catalogue, les Shorts amenent le trafic vers elles.
    is_short = item.kind == "short"
    return (same_topic_today, same_lang, same_category, is_short, item.key)


def build_plan(
    items: List[Item],
    published: set,
    start: date,
    days: int,
    slots: List[str],
) -> List[Slot]:
    """Repartit les publications sur ``days`` jours."""
    if len(slots) > MAX_UPLOADS_PER_DAY:
        raise ValueError(
            f"{len(slots)} creneaux par jour, mais le quota d'API n'en autorise "
            f"que {MAX_UPLOADS_PER_DAY}. Reduis la cadence ou demande une "
            f"extension de quota."
        )

    available = [i for i in items if i.key not in published]
    per_unit: Dict[str, int] = {}
    plan: List[Slot] = []
    previous: Optional[Item] = None

    for offset in range(days):
        day = start + timedelta(days=offset)
        day_topics: set = set()
        for slot_text in slots:
            hour, minute = (int(p) for p in slot_text.split(":"))
            candidates = [
                i for i in available if per_unit.get(i.unit, 0) < MAX_PER_UNIT
            ]
            if not candidates:
                logger.warning(
                    "Plus de contenu disponible au %s %s : le plan s'arrete la.",
                    day, slot_text,
                )
                return plan

            chosen = min(candidates, key=lambda i: _score(i, previous, day_topics))
            available.remove(chosen)
            per_unit[chosen.unit] = per_unit.get(chosen.unit, 0) + 1
            day_topics.add(chosen.topic_id)
            previous = chosen
            plan.append(Slot(datetime.combine(day, time(hour, minute)), chosen))

    return plan


def main(argv=None) -> int:
    import yaml

    import topic_loader
    from topic_registry import TopicRegistry

    parser = argparse.ArgumentParser(description="Compose le calendrier de publication.")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--start", help="date de debut, AAAA-MM-JJ (defaut : demain)")
    parser.add_argument("--slots", nargs="*", default=None, help="heures des creneaux")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stdout
    )

    config = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8")) or {}
    slots = args.slots or config.get("schedule", {}).get("post_times") or DEFAULT_SLOTS
    start = date.fromisoformat(args.start) if args.start else date.today() + timedelta(days=1)

    topics = {t.id: t.category for t in topic_loader.load_topics(only_ready=False)}
    items = discover(topics)
    registry = TopicRegistry()
    published = {name.lower() for name in registry.published_names()}

    logger.info(
        "%d publication(s) disponible(s) sur le disque, %d deja publiee(s).",
        len(items), len(published),
    )

    try:
        plan = build_plan(items, published, start, args.days, list(slots))
    except ValueError as exc:
        logger.error("%s", exc)
        return 1

    PLAN_FILE.parent.mkdir(parents=True, exist_ok=True)
    PLAN_FILE.write_text(
        json.dumps([s.as_dict() for s in plan], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    current_day = None
    for slot in plan:
        if slot.when.date() != current_day:
            current_day = slot.when.date()
            print(f"\n{current_day:%A %d %B}".upper())
        kind = "video " if slot.item.kind == "long" else f"short{slot.item.short_index}"
        print(f"  {slot.when:%H:%M}  {slot.item.lang}  {kind}  {slot.item.title[:56]}")

    wanted = args.days * len(slots)
    print(f"\n{len(plan)}/{wanted} creneaux remplis — plan ecrit dans {PLAN_FILE}")
    if len(plan) < wanted:
        print("Il manque du contenu : produis d'autres sujets pour completer la semaine.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
