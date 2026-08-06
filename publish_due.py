"""Publie le creneau echu, s'il y en a un. Concu pour tourner en tache planifiee.

POURQUOI CE SCRIPT EXISTE
-------------------------
Le calendrier dit quoi publier et quand. Il faut encore quelque chose qui se
reveille regulierement, regarde l'heure, et agisse. C'est ce script, appele par
cron toutes les quinze minutes.

TROIS PROTECTIONS, ET AUCUNE N'EST DECORATIVE
---------------------------------------------
1. **Un seul envoi par execution.** Si la machine a ete arretee une journee,
   cinq creneaux sont echus d'un coup. Les publier tous ferait un lot de cinq
   videos a la meme minute — exactement ce qu'on cherchait a eviter en etalant.
   On rattrape donc un creneau a la fois, au rythme du cron.

2. **Rien au-dela du retard tolere.** Un creneau vieux de trois jours n'a plus
   de sens : le publier maintenant desorganise le calendrier suivant. Il est
   abandonne, et signale.

3. **Le registre fait foi, pas le plan.** Le plan dit ce qui etait prevu ; seul
   le registre sait ce qui est parti. Un plan regenere ne doit jamais faire
   republier.

Usage :
    python publish_due.py            publie le creneau echu, s'il y en a un
    python publish_due.py --dry-run  dit ce qu'il ferait, sans rien envoyer
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(PROJECT_DIR))

logger = logging.getLogger("due")

PLAN_FILE = Path("content/metadata/publication_plan.json")

# Au-dela, un creneau rate est abandonne plutot que rattrape. Publier un contenu
# prevu il y a trois jours decale tout le reste sans rien apporter.
MAX_LATENESS = timedelta(hours=6)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Publie le creneau echu, s'il y en a un.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--plan", type=Path, default=PLAN_FILE)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    if not args.plan.exists():
        logger.error("Aucun plan (%s). Lance `python plan_week.py`.", args.plan)
        return 1

    try:
        slots = json.loads(args.plan.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.error("Plan illisible : %s", exc)
        return 1

    from topic_registry import TopicRegistry

    registry = TopicRegistry()
    now = datetime.now(timezone.utc)

    due = []
    for slot in slots:
        when = datetime.fromisoformat(slot["when"])
        if when.tzinfo is None:
            # Un plan sans fuseau viendrait d'une version anterieure : le lire
            # comme de l'UTC decalerait les publications de deux heures en ete.
            # Mieux vaut refuser que deviner.
            logger.error(
                "Creneau sans fuseau horaire (%s) : regenere le plan avec "
                "`python plan_week.py`.", slot["when"],
            )
            return 1
        if when > now:
            continue
        if registry.is_published(slot["key"]):
            continue
        due.append((when, slot))

    if not due:
        logger.info("Rien a publier pour l'instant.")
        return 0

    due.sort(key=lambda pair: pair[0])
    when, slot = due[0]
    lateness = now - when

    if len(due) > 1:
        logger.warning(
            "%d creneaux en retard. On n'en publie qu'UN par execution : le "
            "rattrapage se fera au rythme de la tache planifiee.", len(due),
        )

    if lateness > MAX_LATENESS:
        logger.error(
            "Creneau « %s » en retard de %s, au-dela du seuil de %s : abandonne. "
            "Regenere le plan pour le replacer.",
            slot["key"], lateness, MAX_LATENESS,
        )
        return 1

    logger.info(
        "Creneau echu : %s (%s, prevu %s, retard %s)",
        slot["key"], slot["title"][:50], when.isoformat(timespec="minutes"), lateness,
    )

    if args.dry_run:
        logger.info("--dry-run : rien n'a ete envoye.")
        return 0

    from publish import publish

    return publish(
        Path(slot["video"]), Path(slot["meta"]),
        short=slot.get("short"), card=slot.get("card"),
    )


if __name__ == "__main__":
    raise SystemExit(main())
