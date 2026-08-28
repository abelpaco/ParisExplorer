"""Annonce chaque publication YouTube sur le canal Telegram de la chaine.

POURQUOI CE SCRIPT
------------------
Le moteur publie sur YouTube ; ce script est le premier « robinet » de
diffusion externe (decision Paco du 28/08/2026). Il lit le registre des
publications — la seule verite — et annonce sur le canal ce qui n'a pas
encore ete annonce : la video en natif quand elle tient dans la limite
des bots (50 Mo), sinon le lien. Telegram est le reseau le plus permissif
en matiere d'automatisation : un bot declare qui poste dans son propre
canal est l'usage nominal de la plateforme.

CE QUE CE SCRIPT REFUSE DE FAIRE
--------------------------------
- Inonder : au premier lancement, ``--init`` enregistre tout l'existant
  comme deja annonce SANS rien envoyer ; ensuite, 3 annonces max par
  passage. Un canal qui recoit 80 videos d'un coup perd ses abonnes le
  jour de sa naissance.
- Vivre sans jeton : si ``telegram_annonce.secret`` n'existe pas, il se
  met en veille (code 0) — le cron peut etre arme avant que le canal
  n'existe.
- Perdre le fil : l'etat est ecrit apres CHAQUE envoi reussi, jamais en
  fin de lot — un plantage au milieu ne fait pas de double annonce.

    python telegram_annonce.py --init   enregistre l'existant, n'envoie rien
    python telegram_annonce.py          annonce le nouveau (cron horaire)

``telegram_annonce.secret`` (chmod 600, gitignore) :
    {"token": "123456:ABC...", "chat_id": "@le_canal"}
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import requests

logger = logging.getLogger("telegram")

SECRET_FILE = Path("telegram_annonce.secret")
REGISTRY_FILE = Path("content/metadata/published_topics.json")
STATE_FILE = Path("content/metadata/telegram_annonces.json")

# Limite d'envoi de fichier pour un bot : 50 Mo. On garde une marge.
TAILLE_MAX = 48 * 1024 * 1024
MAX_PAR_PASSAGE = 3
TIMEOUT_ENVOI = 180


def _charger_secret():
    if not SECRET_FILE.exists():
        return None
    secret = json.loads(SECRET_FILE.read_text(encoding="utf-8"))
    if not secret.get("token") or not secret.get("chat_id"):
        raise SystemExit("telegram_annonce.secret : champs token/chat_id requis")
    return secret


def _charger_etat() -> set:
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text(encoding="utf-8"))["annonces"])
    return set()


def _sauver_etat(annonces: set) -> None:
    STATE_FILE.write_text(
        json.dumps({"annonces": sorted(annonces)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _publications() -> list:
    return json.load(open(REGISTRY_FILE, encoding="utf-8"))["published"]


def _fichier_local(name: str) -> Path | None:
    """Retrouve le mp4 d'une cle de registre — meme logique que le plan."""
    parts = name.split(":")
    sujet, lang = parts[0], parts[1]
    if len(parts) == 2:
        p = Path(f"content/videos/{sujet}/{sujet}-{lang}.mp4")
        return p if p.exists() else None
    suffix = parts[2]
    if suffix.startswith("card-"):
        n = int(suffix.split("-")[1])
        p = Path(f"content/cards/{sujet}/{sujet}-{lang}-story-{n:02d}.mp4")
        return p if p.exists() else None
    if suffix.startswith("short-"):
        meta = Path(f"content/videos/{sujet}/{sujet}-{lang}.json")
        if meta.exists():
            m = json.load(open(meta, encoding="utf-8"))
            n = int(suffix.split("-")[1])
            shorts = m.get("shorts", [])
            if 0 < n <= len(shorts) and Path(shorts[n - 1]).exists():
                return Path(shorts[n - 1])
    return None


def _annoncer(secret: dict, entree: dict) -> None:
    base = f"https://api.telegram.org/bot{secret['token']}"
    caption = f"{entree['title']}\n\n▶️ https://youtu.be/{entree['video_id']}"
    fichier = _fichier_local(entree["name"])
    if fichier and fichier.stat().st_size <= TAILLE_MAX:
        with open(fichier, "rb") as flux:
            reponse = requests.post(
                f"{base}/sendVideo",
                data={"chat_id": secret["chat_id"], "caption": caption,
                      "supports_streaming": True},
                files={"video": (fichier.name, flux, "video/mp4")},
                timeout=TIMEOUT_ENVOI,
            )
    else:
        # Longue trop lourde ou fichier local disparu : le lien suffit,
        # Telegram deroule l'apercu YouTube.
        reponse = requests.post(
            f"{base}/sendMessage",
            data={"chat_id": secret["chat_id"], "text": caption},
            timeout=30,
        )
    corps = reponse.json()
    if not corps.get("ok"):
        raise RuntimeError(f"Telegram a refuse ({entree['name']}) : {corps}")


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Annonce les publications sur Telegram.")
    parser.add_argument("--init", action="store_true",
                        help="enregistre tout l'existant comme annonce, sans rien envoyer")
    args = parser.parse_args(argv)

    publications = _publications()
    etat = _charger_etat()

    if args.init:
        noms = {p["name"] for p in publications}
        _sauver_etat(etat | noms)
        logger.info("Baseline : %d publication(s) marquees annoncees, 0 envoi.", len(noms))
        return 0

    secret = _charger_secret()
    if secret is None:
        logger.info("Pas de telegram_annonce.secret : veille (rien a faire).")
        return 0

    nouvelles = [p for p in publications if p["name"] not in etat]
    if not nouvelles:
        logger.info("Rien a annoncer.")
        return 0

    for entree in nouvelles[:MAX_PAR_PASSAGE]:
        _annoncer(secret, entree)
        etat.add(entree["name"])
        _sauver_etat(etat)  # apres CHAQUE envoi : un plantage ne double rien
        logger.info("Annonce : %s (%s)", entree["name"], entree["video_id"])
    restant = len(nouvelles) - min(len(nouvelles), MAX_PAR_PASSAGE)
    if restant:
        logger.info("%d annonce(s) en attente pour les prochains passages.", restant)
    return 0


if __name__ == "__main__":
    sys.exit(main())
