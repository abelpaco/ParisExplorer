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

# Quota etendu le 28/08/2026 (audit API approuve) : 26 000 unites/jour pendant
# six mois, soit seize envois theoriques a ~1600 unites piece. On en autorise
# quinze — la marge paie les videos.list du suivi et un rattrapage manuel.
# Depasser ne produit pas une erreur claire, ca produit des echecs en fin de
# journee, quand personne ne regarde. A l'echeance du grant (~fevrier 2027),
# si le quota retombe a 10 000, ramener cette constante a 6.
MAX_UPLOADS_PER_DAY = 15

# Nombre maximal de publications tirees d'une meme unite sujet+langue. Les
# Shorts sont decoupes dans la narration de la video longue : au-dela de deux,
# on sert le meme contenu.
MAX_PER_UNIT = 2

# Jours de la semaine qui portent une video longue — lundi, mercredi,
# vendredi (decision Paco du 06/09/2026 : TROIS longues par semaine, pas une
# par jour). La mesure qui a motive l'espacement : le stock ne comptait plus
# que onze videos longues non publiees contre cent cinquante-six Shorts, et
# une longue par jour l'epuisait en onze jours. Trois par semaine tiennent
# pres d'un mois, le temps que le vivier en fabrique d'autres.
#
# Les autres jours alternent Short et carte. Un jour charge (anniversaire,
# ferie) ne porte qu'UNE longue lui aussi : neuf longues d'affilee videraient
# la reserve en une journee.
JOURS_LONGUE = (0, 2, 4)


def composition(jour: date, creneaux: int) -> tuple:
    """La sequence de formats attendue ce jour-la, creneau par creneau.

    C'est une CIBLE, pas un filtre : si le stock ne contient rien du format
    attendu, le planificateur sert autre chose plutot que de laisser un trou.

    Deux versions ont precede celle-ci, et leurs defauts expliquent sa forme.
    Une cible chiffree de longs par jour ecoulait d'abord tous les longs, puis
    tous les Shorts : la premiere moitie de semaine devenait lourde et la
    seconde n'offrait plus que du format court. Une preference fixe aux cartes
    a ensuite fait monopoliser les soirees des que leur stock a grossi,
    faisant disparaitre les Shorts. Une sequence explicite ne peut deriver ni
    dans un sens ni dans l'autre.
    """
    avec_longue = jour.weekday() in JOURS_LONGUE
    formats = ["long"] if avec_longue else []
    decalage = 1 if avec_longue else 0
    while len(formats) < creneaux:
        # Apres l'eventuelle longue, Short et carte alternent, le Short en
        # premier : c'est le format qui porte le plus (mesure du 28/08,
        # mediane de 73 vues/jour contre 41 pour les cartes).
        rang = len(formats) - decalage
        formats.append("short" if rang % 2 == 0 else "card")
    return tuple(formats[:creneaux])

# Les jours ou l'audience est la et ou le quota le permet, on publie plus
# (directive Paco du 28/08/2026) : jour anniversaire d'un sujet ancre, ou
# jour ferie francais. Creneaux de ces jours charges — surchargeables par
# `schedule.post_times_charge` dans config.yaml.
SLOTS_CHARGE = ["08:00", "09:30", "11:00", "12:30", "14:00",
                "15:30", "17:00", "18:30", "20:00"]

# Feries francais a date fixe. Les fetes mobiles (Paques, Ascension,
# Pentecote) demanderaient un comput — hors de proportion ici : les ajouter
# l'annee venue via `schedule.jours_charges` dans config.yaml si on y tient.
FERIES_FRANCE = {"01-01", "05-01", "05-08", "07-14", "08-15",
                 "11-01", "11-11", "12-25"}


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
    item: Item, previous: Optional[Item], day_topics: set,
    kind_voulu: Optional[str] = None, anchored_today: bool = False,
) -> tuple:
    """Cle de tri : plus c'est petit, plus le candidat convient a ce creneau.

    L'ordre des composantes EST la priorite des regles. Un sujet dont c'est le
    jour anniversaire passe devant tout : c'est sa seule fenetre de l'annee.
    Vient ensuite le FORMAT attendu a ce creneau — la composition d'une
    journee est une promesse faite au spectateur qui decouvre la chaine ce
    jour-la, elle prime sur la variete de langue ou de categorie. Le reste
    departage : sujet deja vu aujourd'hui, puis langue, puis categorie.
    """
    wrong_kind = kind_voulu is not None and item.kind != kind_voulu
    same_topic_today = item.topic_id in day_topics
    same_lang = previous is not None and item.lang == previous.lang
    same_category = previous is not None and item.category == previous.category
    return (not anchored_today, wrong_kind, same_topic_today, same_lang,
            same_category, item.key)


def build_plan(
    items: List[Item],
    published: set,
    start: date,
    days: int,
    slots: List[str],
    zone: ZoneInfo,
    anchors: Optional[Dict[str, str]] = None,
    slots_charge: Optional[List[str]] = None,
    jours_charges_extra: Optional[set] = None,
) -> List[Slot]:
    """Repartit les publications sur ``days`` jours.

    ``anchors`` associe un sujet a sa date anniversaire (MM-JJ). Un sujet ancre
    n'est candidat QUE le jour anniversaire — « ce jour-la a Paris » publie un
    autre jour perdrait tout son sens — et ce jour-la, il passe en tete.

    ``slots_charge`` remplace ``slots`` les jours charges : anniversaire d'un
    sujet ancre encore en stock, ferie francais, ou date de
    ``jours_charges_extra`` (MM-JJ). Le quota etendu ne sert a rien s'il dort.
    """
    anchors = anchors or {}
    jours_charges_extra = jours_charges_extra or set()
    for liste in (slots, slots_charge or []):
        if len(liste) > MAX_UPLOADS_PER_DAY:
            raise ValueError(
                f"{len(liste)} creneaux par jour, mais le quota d'API n'en "
                f"autorise que {MAX_UPLOADS_PER_DAY}. Reduis la cadence ou "
                f"demande une extension de quota."
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
        # Jour charge : un sujet ancre tombe ce jour-la ET a encore du stock
        # (un anniversaire sans contenu ne merite pas neuf creneaux), ou ferie.
        jour_charge = bool(slots_charge) and (
            day_key in FERIES_FRANCE
            or day_key in jours_charges_extra
            or any(anchors.get(i.topic_id) == day_key for i in available)
        )
        day_slots = slots_charge if jour_charge else slots
        if jour_charge:
            logger.info(
                "Jour charge %s : %d creneaux au lieu de %d.",
                day, len(day_slots), len(slots),
            )
        formats_du_jour = composition(day, len(day_slots))
        for rang, slot_text in enumerate(day_slots):
            hour, minute = (int(p) for p in slot_text.split(":"))
            kind_voulu = formats_du_jour[rang]
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
                    i, previous, day_topics, kind_voulu,
                    anchored_today=anchors.get(i.topic_id) == day_key,
                ),
            )
            if chosen.kind != kind_voulu:
                # Deux raisons possibles, et il ne faut pas les confondre :
                # le stock est vide de ce format (a signaler), ou un sujet
                # ancre est passe devant, ce qui est le comportement voulu.
                if not any(i.kind == kind_voulu for i in candidates):
                    logger.info(
                        "%s %s : plus de %s en stock, %s servi a la place.",
                        day, slot_text, kind_voulu, chosen.kind,
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
    slots_charge = schedule_cfg.get("post_times_charge") or SLOTS_CHARGE
    jours_charges_extra = set(schedule_cfg.get("jours_charges") or [])
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

    # Les sujets BD (content/bd) publient leurs Shorts par les memes
    # metadonnees que les videos, mais leurs categories et leurs dates
    # anniversaire vivent dans leur propre schema. Sans cette fusion, une
    # naissance ancree au 15 janvier sortirait n'importe quand.
    import bd_topics
    for subject in bd_topics.load_subjects(only_ready=False):
        topics.setdefault(subject.id, subject.category)
        if subject.anchor_date:
            anchors.setdefault(subject.id, subject.anchor_date)
    items = discover(topics)
    # Droit de retrait de Paco (bot_ecoute.py) : un sujet retire ne doit
    # jamais etre replanifie, meme si ses fichiers existent sur le disque.
    retires_file = Path("content/metadata/sujets_retires.json")
    if retires_file.exists():
        retires = set(json.loads(retires_file.read_text(encoding="utf-8"))["retires"])
        avant = len(items)
        items = [i for i in items if i.topic_id not in retires]
        if len(items) != avant:
            logger.info("%d publication(s) ecartees (sujets retires).", avant - len(items))
    registry = TopicRegistry()
    published = {name.lower() for name in registry.published_names()}

    logger.info(
        "%d publication(s) disponible(s) sur le disque, %d deja publiee(s). "
        "Creneaux en %s.",
        len(items), len(published), zone_name,
    )

    try:
        plan = build_plan(items, published, start, args.days, list(slots), zone,
                          anchors=anchors, slots_charge=list(slots_charge),
                          jours_charges_extra=jours_charges_extra)
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
