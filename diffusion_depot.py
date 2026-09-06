"""Depot de diffusion manuelle : le mp4 source + les legendes, ranges par jour.

POURQUOI CE SCRIPT (flow de Paco, 28/08/2026)
---------------------------------------------
YouTube et Telegram recoivent chaque publication le jour J, automatiquement.
Les reseaux a publication manuelle (chaine WhatsApp, X, TikTok, Instagram)
doivent suivre sous 24 h — « coherence affichee sur tout support ». Ce script
depose donc, pour chaque publication, le FICHIER SOURCE (pleine qualite,
sans filigrane — ce que TikTok et Instagram preferent) et un .txt de
legendes dans ``content/diffusion-manuelle/<date>/``. La synchronisation a
manifeste existante rapatrie ce dossier sur le poste de Paco (D:) ; il ouvre
le dossier du jour, tout y est.

Le serveur purge ses copies apres PURGE_JOURS : le disque du VPS n'est pas
une armoire (93 % au moment ou ce script nait), et D: garde sa propre vie —
le manifeste fait que rien ne ressuscite.

Les deux-points des cles de registre deviennent des underscores dans les
noms de fichiers : Windows n'accepte pas « : » dans un nom.
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger("depot")

REGISTRY_FILE = Path("content/metadata/published_topics.json")
STATE_FILE = Path("content/metadata/diffusion_depot.json")
DEPOT_ROOT = Path("content/diffusion-manuelle")
PURGE_JOURS = 7

import texte_social
from telegram_annonce import _fichier_local  # meme logique de resolution
from pack_reseaux import HASHTAGS, _lang_de


def _legendes(entree: dict) -> str:
    lang = _lang_de(entree["name"])
    tags = HASHTAGS.get(lang, HASHTAGS["fr"])
    # Meme accroche que le pack reseaux : l'attribution est journalisee, donc
    # un Short porte le meme texte partout — et ce texte n'appartient qu'a lui.
    titre = texte_social.texte_attribue(entree["name"], entree["title"])
    lien = f"https://youtu.be/{entree['video_id']}"
    return (
        f"{entree['name']} — publie le {entree.get('published_at', '')[:16]}\n"
        f"{'=' * 60}\n\n"
        f"X :\n{titre}\n{lien}\n{tags['x']}\n\n"
        f"TikTok :\n{titre}\n{tags['tiktok']}\n\n"
        f"Instagram :\n{titre}\n{tags['instagram']}\n\n"
        f"WhatsApp :\n{titre}\n▶️ {lien}\n"
    )


def _purger() -> None:
    if not DEPOT_ROOT.exists():
        return
    limite = (datetime.now(timezone.utc) - timedelta(days=PURGE_JOURS)).date()
    for dossier in DEPOT_ROOT.iterdir():
        if not dossier.is_dir():
            continue
        try:
            jour = datetime.strptime(dossier.name, "%Y-%m-%d").date()
        except ValueError:
            continue
        if jour < limite:
            shutil.rmtree(dossier)
            logger.info("Purge serveur : %s (> %d jours).", dossier.name, PURGE_JOURS)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Depose mp4 + legendes pour la diffusion manuelle.")
    parser.add_argument("--init", action="store_true",
                        help="marque tout l'existant comme depose, sans rien copier")
    args = parser.parse_args(argv)

    publications = json.load(open(REGISTRY_FILE, encoding="utf-8"))["published"]
    etat = set(json.loads(STATE_FILE.read_text(encoding="utf-8"))["deposes"]) if STATE_FILE.exists() else set()

    if args.init:
        etat |= {p["name"] for p in publications}
        STATE_FILE.write_text(json.dumps({"deposes": sorted(etat)}, indent=2), encoding="utf-8")
        logger.info("Baseline : %d publication(s) marquees deposees.", len(etat))
        return 0

    DEPOT_ROOT.mkdir(parents=True, exist_ok=True)
    for entree in [p for p in publications if p["name"] not in etat]:
        jour = entree.get("published_at", "")[:10] or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dossier = DEPOT_ROOT / jour
        dossier.mkdir(parents=True, exist_ok=True)
        base = entree["name"].replace(":", "_")
        fichier = _fichier_local(entree["name"])
        if fichier:
            shutil.copy2(fichier, dossier / f"{base}.mp4")
        (dossier / f"{base}.txt").write_text(_legendes(entree), encoding="utf-8")
        etat.add(entree["name"])
        STATE_FILE.write_text(json.dumps({"deposes": sorted(etat)}, indent=2), encoding="utf-8")
        logger.info("Depose : %s -> %s (%s)", entree["name"], dossier,
                    "mp4+txt" if fichier else "txt seul, mp4 introuvable")

    _purger()
    return 0


if __name__ == "__main__":
    sys.exit(main())
