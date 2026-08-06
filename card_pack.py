"""Relie les cartes visuelles aux deux canaux qui peuvent les diffuser.

POURQUOI CE SCRIPT EXISTE
-------------------------
Les cartes produites par ``visual_cards`` restaient sur le disque : rien ne les
reliait au calendrier de publication, et rien ne preparait leur usage en post
Communaute. Ce module comble les deux manques, a partir de ce qui existe
REELLEMENT sur le disque :

1. **Un fichier de metadonnees par carte animee**, ecrit a cote du ``.mp4`` et
   au meme format que celui des videos (titre, description creditee, tags).
   C'est ce que ``plan_week`` recense et ce que ``publish`` sait envoyer : la
   carte animee devient un Short publiable, sans rien changer au reste.

2. **Un pack de posts Communaute** : un fichier de legendes pretes a coller,
   une par carte PNG. L'API YouTube ne sait PAS creer de post Communaute —
   il n'existe aucun point d'entree officiel. Cette etape restera donc
   manuelle, et le pack la reduit a un copier-coller depuis YouTube Studio.

LES TEXTES SONT RETROUVES, PAS STOCKES DEUX FOIS
------------------------------------------------
``visual_cards.card_texts`` est deterministe : pour un sujet, une langue et un
nombre de cartes donnes, il redonne les phrases qui ont ete posees sur les
cartes. On s'en sert pour retrouver le texte d'une carte deja rendue.
CONSEQUENCE : si la narration du sujet change APRES le rendu, les textes
retrouves ne correspondent plus aux pixels — il faut alors re-rendre les
cartes avant de relancer ce script.

LES CREDITS VIENNENT DES METADONNEES DE LA VIDEO
------------------------------------------------
Les cartes puisent leurs fonds dans les memes requetes d'images que la video
du sujet, qui en telecharge davantage : le bloc de credits de la video couvre
donc les fonds des cartes (il peut en crediter plus, jamais moins — et
sur-crediter ne viole aucune licence, sous-crediter si).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import List, Optional

PROJECT_DIR = Path(__file__).resolve().parent
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(PROJECT_DIR))

logger = logging.getLogger("card_pack")

CARDS_ROOT = Path("content/cards")
POSTS_ROOT = Path("content/posts")
VIDEOS_ROOT = Path("content/videos")

# Limite YouTube de 100 signes, moins «  #Shorts » ajoute par publish.
TITLE_MAX = 92

# Debut du bloc de credits dans une description ecrite par produce_topic.
CREDITS_MARKER = "Credits photos"


class PackError(RuntimeError):
    """Le pack n'a pas pu etre construit."""


def _fit_title(text: str, limit: int = TITLE_MAX) -> str:
    """Tronque au mot, jamais au milieu d'un mot, et le montre avec « … »."""
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,;:.") + "…"


def _channel_line(lang: str) -> str:
    if lang == "fr":
        return ("Paris Explorer — l'histoire, les monuments et l'actualite de "
                "Paris, en quelques minutes.")
    return ("Paris Explorer — the history, landmarks and news of Paris, "
            "in a few minutes.")


def _topic_credits(topic_id: str, lang: str) -> str:
    """Bloc de credits du sujet, repris des metadonnees de sa video.

    Si la video n'existe pas encore dans cette langue, on se rabat sur l'autre
    langue : les credits d'images sont les memes, seule l'accroche differe et
    on ne reprend pas l'accroche.
    """
    for candidate_lang in (lang, "fr", "en"):
        meta_file = VIDEOS_ROOT / topic_id / f"{topic_id}-{candidate_lang}.json"
        if not meta_file.exists():
            continue
        try:
            description = json.loads(meta_file.read_text(encoding="utf-8"))["description"]
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            logger.warning("Metadonnees video illisibles (%s) : %s", meta_file, exc)
            continue
        position = description.find(CREDITS_MARKER)
        if position >= 0:
            return description[position:].strip()
    logger.warning(
        "Aucun bloc de credits trouve pour « %s » : les descriptions des cartes "
        "partiront sans credits. Produis d'abord la video du sujet.", topic_id,
    )
    return ""


def _discover_files(topic_id: str, lang: str) -> List[dict]:
    """Cartes presentes sur le disque, triees par numero.

    On lit le DISQUE, pas un souvenir de production : un rendu interrompu
    laisse une serie incomplete, et le pack doit refleter ce qui existe.
    """
    directory = CARDS_ROOT / topic_id
    if not directory.exists():
        return []
    pattern = re.compile(
        rf"^{re.escape(topic_id)}-{re.escape(lang)}-(\w+)-(\d{{2}})\.png$"
    )
    found = []
    for png in sorted(directory.glob(f"{topic_id}-{lang}-*.png")):
        match = pattern.match(png.name)
        if not match:
            continue
        motion = png.with_suffix(".mp4")
        found.append({
            "index": int(match.group(2)),
            "fmt": match.group(1),
            "image": png,
            "motion": motion if motion.exists() else None,
        })
    found.sort(key=lambda entry: entry["index"])
    return found


def build(topic, lang: str) -> dict:
    """Ecrit les metadonnees par carte et le pack de posts d'un sujet.

    Returns:
        {"metas": [Path, ...], "pack": Path | None, "cards": int}
    """
    import visual_cards

    files = _discover_files(topic.id, lang)
    if not files:
        raise PackError(
            f"Aucune carte sur le disque pour « {topic.id} » [{lang}]. "
            f"Produis-les d'abord : python visual_cards.py {topic.id} "
            f"--lang {lang} --format story --animate"
        )

    texts = visual_cards.card_texts(topic, lang, len(files))
    if len(texts) < len(files):
        # Moins de phrases que de fichiers : la narration a probablement
        # change depuis le rendu. On s'arrete plutot que d'ecrire des legendes
        # qui ne correspondent pas aux pixels.
        raise PackError(
            f"{len(files)} carte(s) sur le disque mais {len(texts)} texte(s) "
            f"retrouves pour « {topic.id} » [{lang}] : la narration a change "
            f"depuis le rendu. Re-rends les cartes puis relance."
        )

    credits = _topic_credits(topic.id, lang)
    channel = _channel_line(lang)
    tags = list(topic.text(lang).tags)

    metas: List[Path] = []
    captions: List[str] = []
    for entry, text in zip(files, texts):
        description = f"{text}\n\n{channel}"
        if credits:
            description = f"{description}\n\n{credits}"

        if entry["motion"]:
            meta = {
                "topic_id": topic.id,
                "lang": lang,
                "card_index": entry["index"],
                "title": _fit_title(text),
                "description": description,
                "tags": tags,
                "image": str(entry["image"]),
                "video": str(entry["motion"]),
            }
            meta_path = entry["motion"].with_suffix(".json")
            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            metas.append(meta_path)

        caption_credit = (
            "Photos : Wikimedia Commons — credits complets en description des "
            "videos du sujet." if lang == "fr" else
            "Photos: Wikimedia Commons — full credits in the topic's video "
            "descriptions."
        )
        captions.append(
            f"## Carte {entry['index']} — {entry['image'].name}\n\n"
            f"Image a joindre : {entry['image']}\n\n"
            f"Legende a coller :\n\n"
            f"{text}\n\n"
            f"— Paris Explorer\n"
            f"{caption_credit}\n"
        )

    pack_dir = POSTS_ROOT / topic.id
    pack_dir.mkdir(parents=True, exist_ok=True)
    pack_path = pack_dir / f"{topic.id}-{lang}-posts.md"
    header = (
        f"# Posts Communaute — {topic.text(lang).title} [{lang}]\n\n"
        "Mode d'emploi : YouTube Studio > Communaute > Creer un post, joindre "
        "le PNG indique, coller la legende. L'API YouTube ne sait pas creer de "
        "post Communaute : cette etape est manuelle, et c'est voulu — aucun "
        "outil non officiel ne doit toucher la chaine pendant l'audit.\n\n"
    )
    body = "\n".join(captions)
    footer = f"\n---\n\n{credits}\n" if credits else ""
    pack_path.write_text(header + body + footer, encoding="utf-8")

    logger.info(
        "%d carte(s) : %d metadonnee(s) de Short ecrites, pack de posts dans %s",
        len(files), len(metas), pack_path,
    )
    return {"metas": metas, "pack": pack_path, "cards": len(files)}


def main(argv: Optional[List[str]] = None) -> int:
    import topic_loader

    parser = argparse.ArgumentParser(
        description="Ecrit les metadonnees des cartes animees et le pack de posts."
    )
    parser.add_argument("topic_id")
    parser.add_argument("--lang", default="fr", choices=list(topic_loader.SUPPORTED_LANGS))
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stdout
    )

    topics = {t.id: t for t in topic_loader.load_topics(only_ready=False)}
    topic = topics.get(args.topic_id)
    if topic is None:
        logger.error(
            "Sujet inconnu : %s. Disponibles : %s",
            args.topic_id, ", ".join(sorted(topics)) or "(aucun)",
        )
        return 1

    try:
        result = build(topic, args.lang)
    except PackError as exc:
        logger.error("%s", exc)
        return 1

    print()
    for meta in result["metas"]:
        print(f"  short candidat : {meta}")
    print(f"  pack de posts  : {result['pack']}")
    print(
        "\nProchaines etapes : `python plan_week.py` pour planifier les cartes "
        "animees ; le pack de posts se publie a la main dans YouTube Studio."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
