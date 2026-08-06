"""Instantane hebdomadaire des statistiques de la chaine.

POURQUOI CE SCRIPT EXISTE
-------------------------
L'API YouTube donne les compteurs d'AUJOURD'HUI, jamais leur histoire. Sans
serie temporelle, une revue hebdomadaire compare des souvenirs a des chiffres.
Ce script fige donc, chaque semaine, vues/likes/commentaires par video et les
compteurs de la chaine dans un JSON date : la revue du lundi compare deux
fichiers, pas une memoire.

Ce qu'il ne mesure PAS : la retention (pourcentage vu, balayages). Elle exige
l'API Analytics, donc un scope OAuth supplementaire — et restreindre ou
etendre les scopes invalide le jeton existant. On lit la retention dans
YouTube Studio, a la main, et ce script s'en tient au scope deja accorde.

Cout : 2 unites de quota par execution (une requete videos, une requete
chaine). Negligeable devant les ~1600 unites d'un envoi.

Usage :
    python stats_snapshot.py           ecrit logs/stats/stats-AAAA-MM-JJ.json
    (cron hebdomadaire : lundi 07:05 UTC, voir crontab)
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(PROJECT_DIR))

logger = logging.getLogger("stats")

REGISTRY_FILE = Path("content/metadata/published_topics.json")
STATS_DIR = Path("logs/stats")

# L'API accepte 50 identifiants par requete videos.list.
BATCH = 50


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stdout
    )

    from authorize import check_only
    from youtube_uploader import YouTubeUploader

    if check_only() != 0:
        logger.error("Autorisation invalide — pas d'instantane.")
        return 1

    try:
        registry = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))["published"]
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        logger.error("Registre illisible (%s) : %s", REGISTRY_FILE, exc)
        return 1

    by_id = {
        e["video_id"]: e for e in registry
        if isinstance(e, dict) and e.get("video_id")
    }
    if not by_id:
        logger.info("Aucune video au registre : rien a mesurer.")
        return 0

    uploader = YouTubeUploader()
    videos = []
    ids = list(by_id)
    for start in range(0, len(ids), BATCH):
        response = uploader.youtube.videos().list(
            part="statistics,status,snippet", id=",".join(ids[start:start + BATCH])
        ).execute()
        for item in response.get("items", []):
            stats = item.get("statistics", {})
            entry = by_id.get(item["id"], {})
            videos.append({
                "video_id": item["id"],
                "key": entry.get("key") or entry.get("name"),
                "title": item["snippet"]["title"],
                "published_at": item["snippet"]["publishedAt"],
                "privacy": item["status"]["privacyStatus"],
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
            })

    channel_response = uploader.youtube.channels().list(
        part="statistics", mine=True
    ).execute()
    channel_stats = channel_response["items"][0]["statistics"]

    snapshot = {
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "channel": {
            "subscribers": int(channel_stats.get("subscriberCount", 0)),
            "views": int(channel_stats.get("viewCount", 0)),
            "videos": int(channel_stats.get("videoCount", 0)),
        },
        "videos": sorted(videos, key=lambda v: -v["views"]),
    }

    STATS_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = STATS_DIR / f"stats-{day}.json"
    out.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    total = sum(v["views"] for v in videos)
    print(f"[ok] Instantane : {out}")
    print(f"     {len(videos)} videos, {total} vues cumulees, "
          f"{snapshot['channel']['subscribers']} abonnes")
    for video in snapshot["videos"][:5]:
        print(f"     {video['views']:>7} vues  {video['title'][:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
