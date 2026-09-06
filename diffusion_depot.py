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
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("depot")

# WhatsApp n'affiche AUCUN apercu quand Paco colle une legende a la main : le
# post arrive nu, la ou les autres reseaux vont chercher une vignette. Chaque
# publication part donc avec son image de couverture, prete a joindre.
#
# Les cartes ont deja la leur — un PNG compose et signe. Les videos et les
# Shorts n'ont rien : on extrait une image du montage. Pas la premiere, qui
# ouvre presque toujours sur un fondu au noir : une image prise au cinquieme
# du film, choisie par le filtre `thumbnail` de ffmpeg parmi un lot.
MINIATURE_INSTANT = 0.20
MINIATURE_LARGEUR = 1080
POLICE_GRASSE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

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
        f"   (joindre la miniature du dossier : WhatsApp n'en genere aucune)\n"
    )


def _duree(video: Path) -> Optional[float]:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(video)],
            capture_output=True, text=True, timeout=60,
        )
        return float(r.stdout.strip())
    except (ValueError, OSError, subprocess.SubprocessError):
        return None


def _signer(image: Path) -> None:
    """Pose la pastille de marque en bas de la miniature.

    Une image extraite d'un montage ne dit pas d'ou elle vient. Collee dans
    une conversation WhatsApp, entre deux photos de famille, elle doit se
    reconnaitre en une seconde.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return
    try:
        with Image.open(image) as art:
            art = art.convert("RGB")
            largeur, hauteur = art.size
            dessin = ImageDraw.Draw(art)
            corps = max(16, int(largeur * 0.028))
            police = ImageFont.truetype(POLICE_GRASSE, corps)
            libelle = "PARIS EXPLORER"
            boite = dessin.textbbox((0, 0), libelle, font=police)
            lt, ht = boite[2] - boite[0], boite[3] - boite[1]
            marge = int(largeur * 0.03)
            x2, y2 = largeur - marge, hauteur - marge
            x1, y1 = x2 - lt - corps * 1.6, y2 - ht - corps * 1.1
            dessin.rounded_rectangle([x1, y1, x2, y2], radius=(y2 - y1) / 2,
                                     fill=(16, 20, 32))
            dessin.text((x1 + corps * 0.8, y1 + (y2 - y1 - ht) / 2 - boite[1]),
                        libelle, font=police, fill=(245, 243, 238))
            art.save(image, "JPEG", quality=88, optimize=True)
    except Exception as exc:
        logger.warning("Pastille non posee sur %s : %s", image.name, exc)


def _miniature(video: Optional[Path], dossier: Path, base: str) -> Optional[Path]:
    """L'image de couverture a joindre au post manuel."""
    if video is None:
        return None
    # Une carte a deja son visuel, compose et signe : on ne le refait pas.
    png = video.with_suffix(".png")
    if png.exists():
        cible = dossier / f"{base}.png"
        shutil.copy2(png, cible)
        return cible

    cible = dossier / f"{base}.jpg"
    depart = (_duree(video) or 0) * MINIATURE_INSTANT
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-ss", f"{depart:.2f}", "-i", str(video),
         "-vf", f"thumbnail,scale={MINIATURE_LARGEUR}:-2",
         "-frames:v", "1", "-q:v", "3", str(cible)],
        capture_output=True, text=True,
    )
    if r.returncode != 0 or not cible.exists():
        logger.warning("Miniature impossible pour %s : %s", base, r.stderr[-200:])
        return None
    _signer(cible)
    return cible


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
    parser.add_argument("--relegender", action="store_true",
                        help="reecrit les legendes deja deposees, sans retoucher aux mp4")
    parser.add_argument("--reminiaturer", action="store_true",
                        help="fabrique les miniatures manquantes des depots existants")
    args = parser.parse_args(argv)

    publications = json.load(open(REGISTRY_FILE, encoding="utf-8"))["published"]
    etat = set(json.loads(STATE_FILE.read_text(encoding="utf-8"))["deposes"]) if STATE_FILE.exists() else set()

    if args.relegender:
        # Les legendes deposees avant `texte_social` portent les titres, donc
        # les doublons. Seuls les .txt sont reecrits : recopier les mp4 ferait
        # retransferer des centaines de megaoctets pour rien.
        par_nom = {e["name"]: e for e in publications}
        refaits = 0
        for txt in sorted(DEPOT_ROOT.glob("*/*.txt")):
            entree = par_nom.get(txt.stem.replace("_", ":"))
            if entree:
                txt.write_text(_legendes(entree), encoding="utf-8")
                refaits += 1
        logger.info("%d legende(s) reecrite(s) avec les textes actuels.", refaits)
        return 0

    if args.reminiaturer:
        # Les depots d'avant cette version n'ont que le mp4 et la legende.
        faites = 0
        for mp4 in sorted(DEPOT_ROOT.glob("*/*.mp4")):
            base = mp4.stem
            if (mp4.parent / f"{base}.jpg").exists() or (mp4.parent / f"{base}.png").exists():
                continue
            source = _fichier_local(base.replace("_", ":"))
            if _miniature(source or mp4, mp4.parent, base):
                faites += 1
        logger.info("%d miniature(s) fabriquee(s) dans les depots existants.", faites)
        return 0

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
        _miniature(fichier, dossier, base)
        (dossier / f"{base}.txt").write_text(_legendes(entree), encoding="utf-8")
        etat.add(entree["name"])
        STATE_FILE.write_text(json.dumps({"deposes": sorted(etat)}, indent=2), encoding="utf-8")
        logger.info("Depose : %s -> %s (%s)", entree["name"], dossier,
                    "mp4+txt" if fichier else "txt seul, mp4 introuvable")

    _purger()
    return 0


if __name__ == "__main__":
    sys.exit(main())
