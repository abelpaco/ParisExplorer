"""Publie une video produite, et l'inscrit au registre.

POURQUOI CE SCRIPT EXISTE
-------------------------
``produce_topic`` fabrique les fichiers et leurs metadonnees, mais ne publie
rien — c'est volontaire, on doit pouvoir juger une video avant qu'elle existe
publiquement. Ce script est l'etape d'apres, et elle reste separee : publier est
la seule action de la chaine qu'on ne peut pas defaire discretement.

LA CLE DU REGISTRE DISTINGUE LA VIDEO DE SES SHORTS
---------------------------------------------------
Un sujet donne produit une video longue ET des Shorts, tires de la meme
narration. Si tous partageaient la cle ``sujet:langue``, publier un Short
marquerait le sujet comme fait et la video longue ne sortirait jamais. Les
Shorts portent donc leur propre suffixe.

CE QUE CE SCRIPT NE FAIT PAS
----------------------------
Il ne rend rien public de force. Le niveau de confidentialite vient de
``config.yaml``, et tant que le projet Google n'a pas passe l'audit de l'API
YouTube, tout envoi par l'API reste de toute facon verrouille en prive.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

PROJECT_DIR = Path(__file__).resolve().parent
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(PROJECT_DIR))

logger = logging.getLogger("publish")


def registry_key(
    topic_id: str, lang: str, short: Optional[int] = None, card: Optional[int] = None
) -> str:
    """Cle d'une publication. Un Short ne doit jamais consommer la cle du long.

    Les cartes animees ont leur propre suffixe, pour la meme raison que les
    Shorts : publier la carte 1 ne doit marquer ni la video longue ni le
    Short 1 comme faits.
    """
    base = f"{topic_id}:{lang}"
    if short:
        return f"{base}:short-{short}"
    if card:
        return f"{base}:card-{card}"
    return base


def publish(
    video: Path,
    meta: Path,
    *,
    short: Optional[int] = None,
    card: Optional[int] = None,
    privacy: Optional[str] = None,
) -> int:
    import yaml

    from authorize import check_only
    from topic_registry import TopicRegistry
    from youtube_uploader import YouTubeUploader

    # Verification prealable de l'autorisation. Sans elle, un jeton perime fait
    # ouvrir une fenetre de consentement par le constructeur de l'uploader : sur
    # un poste c'est seulement surprenant, sur le VPS c'est un envoi qui attend
    # pour toujours un navigateur qui n'existe pas.
    if check_only() != 0:
        logger.error("Autorisation invalide — rien n'a ete envoye.")
        return 1

    if not video.exists():
        logger.error("Video introuvable : %s", video)
        return 1
    if not meta.exists():
        logger.error("Metadonnees introuvables : %s", meta)
        return 1

    data = json.loads(meta.read_text(encoding="utf-8"))
    config = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8")) or {}
    youtube_cfg = config.get("youtube", {})

    topic_id = data["topic_id"]
    lang = data["lang"]
    key = registry_key(topic_id, lang, short, card)

    registry = TopicRegistry()
    if registry.is_published(key):
        logger.error(
            "Deja publie : %s. Republier exposerait la chaine — rien n'a ete envoye.", key
        )
        return 1

    title = data["title"]
    if short or card:
        # Le suffixe #Shorts n'est pas cosmetique : c'est ce qui range la video
        # dans le fil vertical de YouTube plutot que dans le catalogue normal.
        # Les cartes animees sont verticales et courtes : meme fil, meme regle.
        title = f"{title} #Shorts"
    title = title[:100]

    tags = list(dict.fromkeys(data.get("tags", []) + youtube_cfg.get("default_tags", [])))
    privacy = privacy or youtube_cfg.get("default_privacy", "private")

    logger.info("Envoi de « %s » (%s, %.1f Mo, %s)",
                title, key, video.stat().st_size / 1024 / 1024, privacy)

    uploader = YouTubeUploader()
    video_id = uploader.upload_video(
        video_file=str(video),
        title=title,
        description=data["description"],
        tags=tags,
        category=str(youtube_cfg.get("default_category", "19")),
        privacy_status=privacy,
    )
    if not video_id:
        logger.error("Envoi echoue : rien n'a ete inscrit au registre.")
        return 1

    registry.mark_published(key, video_id=video_id, title=title)
    print(f"\n[ok] Publie : {title}")
    print(f"     https://www.youtube.com/watch?v={video_id}")
    print(f"     confidentialite : {privacy}")
    print(f"     registre        : {key}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Publie une video produite sur YouTube.")
    parser.add_argument("video", type=Path)
    parser.add_argument("meta", type=Path, help="le .json ecrit a cote de la video")
    parser.add_argument("--short", type=int, help="numero du Short, s'il s'agit d'un Short")
    parser.add_argument("--card", type=int, help="numero de la carte, s'il s'agit d'une carte animee")
    parser.add_argument("--privacy", choices=["private", "unlisted", "public"])
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stdout
    )
    return publish(args.video, args.meta, short=args.short, card=args.card, privacy=args.privacy)


if __name__ == "__main__":
    raise SystemExit(main())
