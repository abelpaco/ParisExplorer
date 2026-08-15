"""Cartes de lieux : du sujet YAML au PNG 1080x1920 + pack de posts.

POURQUOI CE MODULE EXISTE
-------------------------
``lieu_topics`` valide le sujet, ``lieu_style`` compose le SVG — il restait a
livrer : rasteriser aux dimensions des posts Communaute, ranger les PNG la ou
la synchro vers le poste de Paco les attend deja (``content/cards/<id>/``),
et ecrire le pack de legendes pretes a coller (``content/posts/<id>/``), au
meme format que ``card_pack`` et ``bd_cards``. Aucune nouvelle arborescence :
les chemins sont ceux de l'existant.

LE RASTERISEUR EST CELUI DE bd_cards
------------------------------------
``bd_cards.rasterize`` sait deja trouver rsvg-convert (VPS), Inkscape, puis
un navigateur headless en secours — avec ses pieges connus (tubes de Chrome
sous Windows). On le REUTILISE au lieu de le recrire. Deux precautions de
plus ici, apprises sur ce poste : le PNG cible est SUPPRIME avant le rendu
(Chrome echoue parfois en silence et laisserait l'ancien fichier passer pour
le nouveau), et on attend que la taille du fichier soit STABLE (l'ecriture
du screenshot peut finir apres la sortie du processus).

LE PACK NE CLOBBERE PAS EN SILENCE
----------------------------------
Un meme identifiant peut exister en sujet video (cartes photo) ET en lieu —
« montmartre » est dans ce cas. Leur pack de posts porte le meme nom de
fichier. Si un pack existant ne vient pas d'ici, il est d'abord copie en
``.bak-avant-lieux.md`` avec un avertissement : il se regenere par
``card_pack.py``, mais on ne fait pas disparaitre le travail d'un autre
module sans laisser de trace.

Usage :
    python lieu_cards.py <id> [--lang fr,en]
    python lieu_cards.py --list
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

PROJECT_DIR = Path(__file__).resolve().parent
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(PROJECT_DIR))

import bd_cards
import lieu_style
import lieu_topics

logger = logging.getLogger("lieu")

CARDS_ROOT = Path("content/cards")
POSTS_ROOT = Path("content/posts")

# Libelle du credit d'illustration par style — l'equivalent du « style ligne
# claire » des packs BD.
_CREDIT_STYLE = {
    "impressionniste": "style impressionniste",
    "bd-encrage": "style BD encrage",
    "aquarelle": "style aquarelle",
}


class LieuCardError(RuntimeError):
    """La production d'une carte de lieu n'a pas pu aboutir."""


def _attendre_ecriture(png_path: Path, timeout: float = 20.0) -> None:
    """Attend que le PNG existe et que sa taille soit stable.

    Le rendu navigateur ecrit le screenshot de maniere asynchrone : le
    processus peut se terminer avant la fin de l'ecriture. On considere le
    fichier livre quand deux lectures a 0,3 s d'ecart donnent la meme taille
    non nulle — au-dela du delai, echec bruyant.
    """
    fin = time.monotonic() + timeout
    derniere = -1
    while time.monotonic() < fin:
        if png_path.exists():
            taille = png_path.stat().st_size
            if taille > 0 and taille == derniere:
                return
            derniere = taille
        time.sleep(0.3)
    raise LieuCardError(
        f"{png_path} n'est pas apparu (ou ne s'est pas stabilise) en "
        f"{timeout:.0f} s — rendu rasteriseur suspect."
    )


@dataclass
class LieuCardResult:
    """Ce que la production a ecrit sur le disque, pour une langue."""

    svg: Path
    png: Path
    pack: Path


def render_card(lieu: lieu_topics.Lieu, lang: str) -> tuple[Path, Path]:
    """Compose et rasterise la carte d'un lieu dans une langue.

    Returns:
        (chemin du SVG, chemin du PNG)
    """
    textes = lieu.textes(lang)
    svg = lieu_style.composer(lieu.scene, textes.anecdote, textes.sous_titre,
                              lang)

    out_dir = CARDS_ROOT / lieu.id
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{lieu.id}-{lang}-lieu-01"
    svg_path = out_dir / f"{stem}.svg"
    png_path = out_dir / f"{stem}.png"
    svg_path.write_text(svg, encoding="utf-8")

    # Jamais d'ancien PNG qui pourrait passer pour le rendu du jour.
    png_path.unlink(missing_ok=True)
    bd_cards.rasterize(svg_path, png_path, lieu_style.WIDTH, lieu_style.HEIGHT)
    _attendre_ecriture(png_path)
    logger.info("Carte rendue : %s", png_path)
    return svg_path, png_path


def _proteger_pack_etranger(pack_path: Path, credit: str) -> None:
    """Sauvegarde un pack existant qui ne vient pas des cartes de lieux."""
    if not pack_path.exists():
        return
    contenu = pack_path.read_text(encoding="utf-8")
    if credit in contenu:
        return  # deja un pack de lieu : la re-ecriture est une mise a jour
    bak = pack_path.with_suffix(".md.bak-avant-lieux")
    if not bak.exists():
        shutil.copy(pack_path, bak)
    logger.warning(
        "%s existait (pack d'un autre module) : copie gardee dans %s — il se "
        "regenere par card_pack.py ou bd_cards.py si besoin.",
        pack_path.name, bak.name,
    )


def write_pack(lieu: lieu_topics.Lieu, lang: str, png_path: Path) -> Path:
    """Pack de posts Communaute : la legende prete a coller pour la carte."""
    textes = lieu.textes(lang)
    credit = f"Dessin original Paris Explorer — {_CREDIT_STYLE[lieu.style]}."

    pack_dir = POSTS_ROOT / lieu.id
    pack_dir.mkdir(parents=True, exist_ok=True)
    pack_path = pack_dir / f"{lieu.id}-{lang}-posts.md"
    _proteger_pack_etranger(pack_path, credit)

    contenu = (
        f"# Posts Communaute — {textes.titre} [{lang}]\n\n"
        "Mode d'emploi : YouTube Studio > Communaute > Creer un post, joindre "
        "le PNG indique, coller la legende. Dessins originaux : aucun credit "
        "photo a reporter.\n\n"
        f"## Carte 1 — {png_path.name}\n\n"
        f"Image a joindre : {png_path}\n\n"
        f"Legende a coller :\n\n"
        f"{textes.legende}\n\n"
        f"— Paris Explorer\n{credit}\n"
    )
    pack_path.write_text(contenu, encoding="utf-8")
    logger.info("Pack de posts : %s", pack_path)
    return pack_path


def produce(lieu: lieu_topics.Lieu, langs: List[str]) -> List[LieuCardResult]:
    """Produit les cartes et packs d'un lieu pour chaque langue demandee."""
    resultats: List[LieuCardResult] = []
    for lang in langs:
        svg_path, png_path = render_card(lieu, lang)
        pack_path = write_pack(lieu, lang, png_path)
        resultats.append(LieuCardResult(svg=svg_path, png=png_path,
                                        pack=pack_path))
    return resultats


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Produit la carte de lieu d'un sujet de content/lieux/."
    )
    parser.add_argument("lieu_id", nargs="?", help="identifiant du lieu")
    parser.add_argument("--lang", default="fr,en",
                        help="langues a rendre, separees par des virgules "
                             "(defaut : fr,en)")
    parser.add_argument("--list", action="store_true", dest="list_lieux",
                        help="lister les lieux disponibles")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    if args.list_lieux or not args.lieu_id:
        for lieu in lieu_topics.load_lieux():
            langs = ",".join(sorted(lieu.langs))
            print(f"  {lieu.id:24s} {lieu.type:10s} scene {lieu.scene:14s} "
                  f"[{langs}]")
        return 0

    langs = [l.strip() for l in args.lang.split(",") if l.strip()]
    if not langs:
        logger.error("--lang est vide : rien a rendre")
        return 1

    try:
        lieu = lieu_topics.load_lieu(args.lieu_id)
        resultats = produce(lieu, langs)
    except (lieu_topics.LieuError, lieu_style.LieuStyleError,
            LieuCardError, bd_cards.BdCardError) as exc:
        logger.error("%s", exc)
        return 1

    print()
    for res in resultats:
        print(f"  carte : {res.png}")
        print(f"  pack  : {res.pack}")
    print("\nProchaine etape : le pack de posts se colle a la main dans "
          "YouTube Studio (l'API ne sait pas creer de post Communaute).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
