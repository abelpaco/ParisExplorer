"""Rattrapage : ajoute le lien de la vidéo longue aux cartes déjà publiées.

POURQUOI CE SCRIPT EXISTE
-------------------------
Depuis le 15/08, ``publish`` ajoute lui-même le lien de la longue en tête de
description des cartes animées. Les cartes parties AVANT ce correctif n'ont
pas le lien ; l'API sait mettre à jour une description, ce script le fait une
fois. Idempotent : une carte déjà liée est laissée telle quelle.

⚠️ BLOQUÉ PAR LES SCOPES (15/08) : ``videos.update`` exige le scope sensible
``youtube.force-ssl``, que le jeton n'a pas (upload + readonly seulement) —
et on N'ÉLARGIT PAS les scopes tant que l'audit YouTube API est en cours.
En attendant : rattrapage à la main dans Studio. Ce script resservira si les
scopes sont élargis après l'audit.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(PROJECT_DIR))

from authorize import check_only
from topic_registry import TopicRegistry
from youtube_uploader import YouTubeUploader

CARD_RE = re.compile(r"^(?P<topic>.+):(?P<lang>fr|en):card-\d+$")


def main() -> int:
    if check_only() != 0:
        print("Autorisation invalide — rien n'a été modifié.")
        return 1

    registry = TopicRegistry()
    uploader = YouTubeUploader()
    uploader._authenticate()
    yt = uploader.youtube

    fait, sans_longue, deja, absentes = 0, 0, 0, 0
    for name in registry.published_names():
        m = CARD_RE.match(name)
        if not m:
            continue
        card_id = registry.video_id_of(name)
        long_id = registry.video_id_of(f"{m['topic']}:{m['lang']}")
        if not card_id:
            continue
        if not long_id:
            print(f"[skip] {name} : longue pas encore publiée")
            sans_longue += 1
            continue

        reponse = yt.videos().list(part="snippet", id=card_id).execute()
        items = reponse.get("items", [])
        if not items:
            print(f"[skip] {name} : vidéo {card_id} introuvable (supprimée ?)")
            absentes += 1
            continue
        snippet = items[0]["snippet"]
        if f"youtu.be/{long_id}" in snippet.get("description", ""):
            print(f"[ok]   {name} : lien déjà présent")
            deja += 1
            continue

        libelle = ("▶ La vidéo complète : " if m["lang"] == "fr"
                   else "▶ Watch the full video: ")
        snippet["description"] = (
            f"{libelle}https://youtu.be/{long_id}\n\n" + snippet.get("description", "")
        )
        yt.videos().update(part="snippet", body={"id": card_id, "snippet": snippet}).execute()
        print(f"[maj]  {name} ({card_id}) -> longue {long_id}")
        fait += 1

    print(f"\nBilan : {fait} mise(s) à jour, {deja} déjà liée(s), "
          f"{sans_longue} sans longue, {absentes} introuvable(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
