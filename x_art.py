"""Habillage du compte X @parisexplorer75, aux formats de la plateforme.

POURQUOI CE MODULE
------------------
L'identite de la chaine vit dans ``channel_art`` (tour, couleurs, reglages
valides) : la reproduire a la main pour X donnerait deux marques qui se
ressemblent au lieu d'une seule. Ce module ne redessine RIEN — il rejoue les
memes primitives aux dimensions de X.

CE QUE X IMPOSE, ET QUI N'EST PAS DANS LE FORMAT YOUTUBE
-------------------------------------------------------
1. La banniere est en 3:1 (1500x500) la ou YouTube est en 16:9. Recadrer la
   banniere YouTube couperait la moitie de la composition : on recompose.
2. **L'avatar mange le coin bas-gauche de la banniere.** Sur X il deborde de
   la photo de profil vers le haut : tout ce qui est dessine sous y=300 a
   gauche de x=320 disparait derriere. La composition est donc poussee vers
   la droite — pas centree, decalee.
3. L'avatar est affiche en CERCLE et tres petit (48 px dans un fil) : c'est
   le meme logo que YouTube, et c'est voulu — on le regenere juste en 400,
   la taille que X attend.

    python x_art.py            ecrit dans content/brand/x/
    python x_art.py --guides   trace la zone avatar pour verifier
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from channel_art import (
    BLEU,
    IDENTITY,
    channel_logo,
    eiffel_glyph,
    serif_font,
)

logger = logging.getLogger("x-art")

X_AVATAR = 400
X_BANNER = (1500, 500)

# La photo de profil, ramenee aux coordonnees de la banniere (le cercle est
# affiche par-dessus, a cheval sur le bord bas). Premier jet errone : une
# zone de 320 px de large laissait le pied de la tour passer DERRIERE le
# cercle. Mesure refaite sur l'affichage de bureau — le cercle mord jusque
# vers x=440.
AVATAR_CENTRE = (255, 500)
AVATAR_RAYON = 185
AVATAR_ZONE = (0, AVATAR_CENTRE[1] - AVATAR_RAYON,
               AVATAR_CENTRE[0] + AVATAR_RAYON, 500)


def banniere_x(
    out_path: Path,
    *,
    titre: str = "Paris Explorer",
    tagline: str = "L'histoire, les monuments et les secrets de Paris",
    tour_visible: bool = True,
    guides: bool = False,
) -> Path:
    """Compose la banniere 1500x500, hors de la zone de l'avatar.

    ``tour_visible`` : sur X, l'avatar est colle A COTE de la banniere, et il
    porte deja la tour. La redessiner fait deux tours voisines — d'ou la
    variante sans, ou le texte respire seul.
    """
    largeur, hauteur = X_BANNER
    art = Image.new("RGB", X_BANNER, BLEU)
    draw = ImageDraw.Draw(art)

    tour = int(hauteur * 0.62)
    if tour_visible:
        glyphe = eiffel_glyph(
            tour,
            background=BLEU,
            foreground=IDENTITY["tower"],
            ring=False,
        )
        # A droite de la zone avatar, jamais dessus.
        glyphe_x = AVATAR_ZONE[2] + 30
        glyphe_y = (hauteur - tour) // 2
        art.paste(glyphe, (glyphe_x, glyphe_y))
        texte_x = glyphe_x + tour + int(tour * 0.14)
    else:
        texte_x = AVATAR_ZONE[2] + 90

    marge_droite = 70
    largeur_dispo = largeur - texte_x - marge_droite

    # Le titre descend jusqu'a tenir : un titre coupe est pire qu'un petit.
    taille = 96 if tour_visible else 130
    while taille > 40:
        police = serif_font(taille, italic=True)
        boite = draw.textbbox((0, 0), titre, font=police)
        if boite[2] - boite[0] <= largeur_dispo:
            break
        taille -= 2
    draw.text((texte_x, int(hauteur * (0.27 if tour_visible else 0.22))), titre,
              font=police, fill=IDENTITY["tower"])

    # Le filet se pose SOUS les jambages, pas dessus : a 0,545 il touchait le
    # « p » de Explorer et se lisait comme un soulignement.
    filet_y = int(hauteur * 0.60)
    draw.line(
        [(texte_x, filet_y), (texte_x + int(tour * 1.15), filet_y)],
        fill=IDENTITY["text"], width=5,
    )

    taille_tag = 34 if tour_visible else 42
    while taille_tag > 18:
        police_tag = serif_font(taille_tag, italic=False)
        boite = draw.textbbox((0, 0), tagline, font=police_tag)
        if boite[2] - boite[0] <= largeur_dispo:
            break
        taille_tag -= 1
    draw.text((texte_x, filet_y + int(hauteur * 0.06)), tagline,
              font=police_tag, fill=IDENTITY["text"])

    if guides:
        draw.rectangle(AVATAR_ZONE, outline=(0, 255, 0), width=4)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    art.save(out_path, "PNG", optimize=True)
    logger.info("Banniere X : %s (%dx%d)", out_path, largeur, hauteur)
    return out_path


def previsualiser(banniere: Path, avatar: Path, out_path: Path) -> Path:
    """Colle l'avatar a sa place reelle : la seule vue qui dit vrai.

    Une banniere se juge avec la photo de profil DESSUS, comme un avatar se
    juge en 48 px — sinon on valide une composition que personne ne verra.
    """
    fond = Image.open(banniere).convert("RGB")
    taille = AVATAR_RAYON * 2
    vignette = Image.open(avatar).convert("RGB").resize((taille, taille), Image.LANCZOS)
    masque = Image.new("L", (taille, taille), 0)
    ImageDraw.Draw(masque).ellipse((0, 0, taille - 1, taille - 1), fill=255)
    fond.paste(vignette,
               (AVATAR_CENTRE[0] - AVATAR_RAYON, AVATAR_CENTRE[1] - AVATAR_RAYON),
               masque)
    dessin = ImageDraw.Draw(fond)
    dessin.ellipse(
        (AVATAR_CENTRE[0] - AVATAR_RAYON, AVATAR_CENTRE[1] - AVATAR_RAYON,
         AVATAR_CENTRE[0] + AVATAR_RAYON, AVATAR_CENTRE[1] + AVATAR_RAYON),
        outline=(255, 255, 255), width=8,
    )
    fond.save(out_path, "PNG", optimize=True)
    logger.info("Previsualisation : %s", out_path)
    return out_path


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser(description="Habillage du compte X.")
    parser.add_argument("--out", type=Path, default=Path("content/brand/x"))
    parser.add_argument("--guides", action="store_true",
                        help="trace la zone avatar (verification, jamais publie)")
    args = parser.parse_args(argv)

    avatar = channel_logo(args.out / "x-avatar-400.png", size=X_AVATAR)
    logger.info("Avatar X : %s (%d px)", avatar, X_AVATAR)
    # Deux partis, juges dans les conditions reelles : avec la tour (echo du
    # logo) et sans (le texte respire, une seule tour a l'ecran).
    avec = banniere_x(args.out / "x-banniere-A-avec-tour.png", tour_visible=True)
    previsualiser(avec, avatar, args.out / "x-apercu-A-avec-tour.png")
    sans = banniere_x(args.out / "x-banniere-B-sans-tour.png", tour_visible=False)
    previsualiser(sans, avatar, args.out / "x-apercu-B-sans-tour.png")
    if args.guides:
        banniere_x(args.out / "x-banniere-guides.png", guides=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
