"""Pack reseaux : les legendes pretes a coller pour X, TikTok, Instagram, WhatsApp.

POURQUOI CE SCRIPT
------------------
Decision Paco du 28/08/2026 : diffuser sur les autres reseaux, d'abord a la
main (les API de TikTok/Instagram exigent des audits, les chaines WhatsApp
n'en ont pas, X attend un compte de marque muri). Ce script fabrique donc,
pour chaque publication YouTube, un bloc de legendes adaptees par reseau,
ecrit dans ``content/posts/<sujet>/`` — le dossier que la synchronisation
livre deja sur le poste de Paco toutes les deux heures.

La VIDEO, elle, n'est pas copiee : elle est deja sur le telephone, en pleine
qualite, dans le canal Telegram (annonce automatique) — l'enregistrer depuis
Telegram puis la coller dans TikTok/Instagram/WhatsApp est le chemin le plus
court. Le pack ne transporte que du texte.

Meme discipline que l'annonceur Telegram : baseline --init, etat sauve au
fil de l'eau, aucun envoi nulle part — ce script ECRIT DES FICHIERS, c'est
la main de Paco qui poste.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import texte_social

logger = logging.getLogger("reseaux")

REGISTRY_FILE = Path("content/metadata/published_topics.json")
STATE_FILE = Path("content/metadata/reseaux_annonces.json")
POSTS_ROOT = Path("content/posts")

HASHTAGS = {
    "fr": {
        "x": "#Paris #Histoire",
        "tiktok": "#paris #histoire #parissecret #culture #apprendresurtiktok",
        "instagram": "#paris #histoire #parissecret #culturegenerale #reels",
    },
    "en": {
        "x": "#Paris #History",
        "tiktok": "#paris #history #hiddenparis #learnontiktok #france",
        "instagram": "#paris #history #hiddenparis #travel #reels",
    },
}


def _lang_de(name: str) -> str:
    parts = name.split(":")
    return parts[1] if len(parts) > 1 else "fr"


def _bloc(entree: dict) -> str:
    lang = _lang_de(entree["name"])
    tags = HASHTAGS.get(lang, HASHTAGS["fr"])
    # L'accroche, jamais le titre : plusieurs Shorts d'une meme video portent
    # le MEME titre, et les reseaux sanctionnent le contenu duplique.
    titre = texte_social.texte_attribue(entree["name"], entree["title"])
    lien = f"https://youtu.be/{entree['video_id']}"
    quand = entree.get("published_at", "")[:10]
    return (
        f"## {entree['name']} — publie le {quand}\n\n"
        f"Video : a enregistrer depuis le canal Telegram t.me/ParisExplorer "
        f"(post du meme jour), pleine qualite.\n\n"
        f"**X**\n\n{titre}\n{lien}\n{tags['x']}\n\n"
        f"**TikTok**\n\n{titre}\n{tags['tiktok']}\n\n"
        f"**Instagram (Reels)**\n\n{titre}\n{tags['instagram']}\n\n"
        f"**WhatsApp (chaine / statut)**\n\n{titre}\n▶️ {lien}\n\n"
        f"---\n\n"
    )


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Ecrit les legendes reseaux des publications.")
    parser.add_argument("--init", action="store_true",
                        help="marque tout l'existant comme traite, sans rien ecrire")
    args = parser.parse_args(argv)

    publications = json.load(open(REGISTRY_FILE, encoding="utf-8"))["published"]
    etat = set(json.loads(STATE_FILE.read_text(encoding="utf-8"))["traites"]) if STATE_FILE.exists() else set()

    if args.init:
        etat |= {p["name"] for p in publications}
        STATE_FILE.write_text(json.dumps({"traites": sorted(etat)}, indent=2), encoding="utf-8")
        logger.info("Baseline : %d publication(s) marquees traitees.", len(etat))
        return 0

    nouvelles = [p for p in publications if p["name"] not in etat]
    for entree in nouvelles:
        topic_id = entree["name"].split(":")[0]
        dossier = POSTS_ROOT / topic_id
        dossier.mkdir(parents=True, exist_ok=True)
        fichier = dossier / f"{topic_id}-reseaux.md"
        if not fichier.exists():
            fichier.write_text(
                f"# Pack reseaux — {topic_id}\n\n"
                "Legendes pretes a coller. La video se recupere depuis le canal\n"
                "Telegram (pleine qualite), jamais re-telechargee de YouTube\n"
                "(filigrane et recompression).\n\n---\n\n",
                encoding="utf-8",
            )
        with open(fichier, "a", encoding="utf-8") as flux:
            flux.write(_bloc(entree))
        etat.add(entree["name"])
        STATE_FILE.write_text(json.dumps({"traites": sorted(etat)}, indent=2), encoding="utf-8")
        logger.info("Pack reseaux : %s -> %s", entree["name"], fichier)
    if not nouvelles:
        logger.info("Rien de nouveau.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
