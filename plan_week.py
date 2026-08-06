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
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_DIR = Path(__file__).resolve().parent
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(PROJECT_DIR))

logger = logging.getLogger("plan")

VIDEOS_ROOT = Path("content/videos")
CARDS_ROOT = Path("content/cards")
PLAN_FILE = Path("content/metadata/publication_plan.json")

# Creneaux par defaut : deux le matin, deux l'apres-midi, un le soir.
DEFAULT_SLOTS = ["08:00", "10:30", "13:00", "16:30", "19:30"]

# Fuseau des creneaux. Il est EXPLICITE, et c'est essentiel : le VPS tourne en
# UTC alors que la chaine s'adresse a un public parisien. Une heure naive
# ecrite ici et relue la-bas decalerait toutes les publications de deux heures
# en ete, d'une en hiver — sans jamais lever la moindre erreur.
DEFAULT_TIMEZONE = "Europe/Paris"

# Un quota d'API standard (10 000 unites par jour) et un envoi a ~1600 unites
# donnent six envois quotidiens au maximum. On refuse d'en planifier plus :
# depasser ne produit pas une erreur claire, ca produit des echecs en fin de
# journee, quand personne ne regarde.
MAX_UPLOADS_PER_DAY = 6

# Nombre maximal de publications tirees d'une meme unite sujet+langue. Les
# Shorts sont decoupes dans la narration de la video longue : au-dela de deux,
# on sert le meme contenu.
MAX_PER_UNIT = 2

# Videos longues visees par jour, le reste en Shorts. Sans cette cible, le
# planificateur ecoule d'abord TOUS les longs puis tous les Shorts : la premiere
# moitie de semaine devient lourde, la seconde n'offre plus que du format court
# a qui decouvre la chaine ce jour-la. Chaque journee doit se tenir seule.
LONGS_PER_DAY = 2


@dataclass
class Item:
    """Une publication candidate : un fichier, et de quoi la situer."""

    topic_id: str
    lang: str
    kind: str  # "long", "short" ou "card"
    short_index: Optional[int]
    video: Path
    meta: Path
    category: str
    title: str
    card_index: Optional[int] = None

    @property
    def key(self) -> str:
        base = f"{self.topic_id}:{self.lang}"
        if self.short_index:
            return f"{base}:short-{self.short_index}"
        if self.card_index:
            return f"{base}:card-{self.card_index}"
        return base

    @property
    def unit(self) -> str:
        # Les cartes animees ont leur propre budget : six secondes de teaser ne
        # doivent pas consommer les deux creneaux du sujet et empecher la video
        # longue ou un Short de sortir.
        base = f"{self.topic_id}:{self.lang}"
        return f"{base}:cards" if self.kind == "card" else base


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
            "card": self.item.card_index,
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

    # Cartes animees : les metadonnees par carte sont ecrites par card_pack.py,
    # a cote du mp4. Une carte sans mp4 (rendu image seule) n'est pas un
    # candidat : l'onglet Communaute la prendra, pas le fil des Shorts.
    for meta_file in sorted(CARDS_ROOT.glob("*/*.json")):
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Metadonnees de carte illisibles (%s) : %s", meta_file, exc)
            continue
        if "card_index" not in data:
            continue
        motion = Path(data["video"]) if data.get("video") else None
        if not motion or not motion.exists():
            continue
        topic_id, lang = data["topic_id"], data["lang"]
        items.append(Item(topic_id, lang, "card", None, motion, meta_file,
                          topics.get(topic_id, "decouverte"), data["title"],
                          card_index=data["card_index"]))
    return items


def _score(
    item: Item, previous: Optional[Item], day_topics: set, day_longs: int,
    anchored_today: bool = False,
) -> tuple:
    """Cle de tri : plus c'est petit, plus le candidat convient a ce creneau.

    L'ordre des composantes EST la priorite des regles. Un sujet dont c'est le
    jour anniversaire passe devant tout : c'est sa seule fenetre de l'annee.
    Ensuite, le sujet deja vu dans la journee pese plus lourd que la langue,
    qui pese plus lourd que la categorie, qui pese plus lourd que le format.
    """
    same_topic_today = item.topic_id in day_topics
    same_lang = previous is not None and item.lang == previous.lang
    same_category = previous is not None and item.category == previous.category
    # Le format voulu depend de ce que la journee contient DEJA : on prend des
    # longs tant que la cible du jour n'est pas atteinte, des Shorts ensuite.
    wants_long = day_longs < LONGS_PER_DAY
    wrong_format = (item.kind == "long") != wants_long
    # A creneau non-long, une carte animee passe avant un Short. Sans ce
    # composant, le depart se faisait a la CLE alphabetique et les cartes ne
    # sortaient jamais — un accident de nommage, pas un choix editorial. Le
    # stock de cartes est petit et deja plafonne par MAX_PER_UNIT : le coup de
    # pouce ne peut pas transformer le fil en diaporama.
    not_card = item.kind != "card"
    return (not anchored_today, same_topic_today, same_lang, same_category,
            wrong_format, not_card, item.key)


def build_plan(
    items: List[Item],
    published: set,
    start: date,
    days: int,
    slots: List[str],
    zone: ZoneInfo,
    anchors: Optional[Dict[str, str]] = None,
) -> List[Slot]:
    """Repartit les publications sur ``days`` jours.

    ``anchors`` associe un sujet a sa date anniversaire (MM-JJ). Un sujet ancre
    n'est candidat QUE le jour anniversaire — « ce jour-la a Paris » publie un
    autre jour perdrait tout son sens — et ce jour-la, il passe en tete.
    """
    anchors = anchors or {}
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
        day_key = day.strftime("%m-%d")
        day_topics: set = set()
        day_longs = 0
        for slot_text in slots:
            hour, minute = (int(p) for p in slot_text.split(":"))
            candidates = [
                i for i in available
                if per_unit.get(i.unit, 0) < MAX_PER_UNIT
                and anchors.get(i.topic_id) in (None, day_key)
            ]
            if not candidates:
                logger.warning(
                    "Plus de contenu disponible au %s %s : le plan s'arrete la.",
                    day, slot_text,
                )
                return plan

            chosen = min(
                candidates,
                key=lambda i: _score(
                    i, previous, day_topics, day_longs,
                    anchored_today=anchors.get(i.topic_id) == day_key,
                ),
            )
            available.remove(chosen)
            per_unit[chosen.unit] = per_unit.get(chosen.unit, 0) + 1
            day_topics.add(chosen.topic_id)
            day_longs += 1 if chosen.kind == "long" else 0
            previous = chosen
            plan.append(
                Slot(datetime.combine(day, time(hour, minute), tzinfo=zone), chosen)
            )

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
    schedule_cfg = config.get("schedule", {})
    slots = args.slots or schedule_cfg.get("post_times") or DEFAULT_SLOTS
    zone_name = schedule_cfg.get("timezone") or DEFAULT_TIMEZONE
    try:
        zone = ZoneInfo(zone_name)
    except Exception as exc:
        logger.error("Fuseau horaire inconnu (%s) : %s", zone_name, exc)
        return 1
    start = date.fromisoformat(args.start) if args.start else date.today() + timedelta(days=1)

    all_topics = topic_loader.load_topics(only_ready=False)
    topics = {t.id: t.category for t in all_topics}
    anchors = {t.id: t.anchor_date for t in all_topics if t.anchor_date}
    items = discover(topics)
    registry = TopicRegistry()
    published = {name.lower() for name in registry.published_names()}

    logger.info(
        "%d publication(s) disponible(s) sur le disque, %d deja publiee(s). "
        "Creneaux en %s.",
        len(items), len(published), zone_name,
    )

    try:
        plan = build_plan(items, published, start, args.days, list(slots), zone,
                          anchors=anchors)
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
        if slot.item.kind == "long":
            kind = "video "
        elif slot.item.kind == "card":
            kind = f"carte{slot.item.card_index}"
        else:
            kind = f"short{slot.item.short_index}"
        print(f"  {slot.when:%H:%M}  {slot.item.lang}  {kind}  {slot.item.title[:56]}")

    wanted = args.days * len(slots)
    print(f"\n{len(plan)}/{wanted} creneaux remplis — plan ecrit dans {PLAN_FILE}")
    if len(plan) < wanted:
        print("Il manque du contenu : produis d'autres sujets pour completer la semaine.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
