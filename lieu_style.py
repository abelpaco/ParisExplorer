"""Gabarits SVG des cartes de lieux : trois styles, trois scenes de reference.

POURQUOI CE MODULE EXISTE
-------------------------
Les posts Communaute « lieux » sont passes par une phase d'atelier : trois
cartes echantillons dessinees a la main dans le navigateur, validees par Paco
le 14/08/2026 (``content/cartes-lieux-echantillons/``). Ce module transforme
ces references en GABARITS DETERMINISTES : memes entrees, memes pixels, zero
reseau, pas de navigateur dans la boucle de composition. Toute carte produite
ici doit pouvoir etre posee a cote de sa reference sans dissonance.

LA CHARTE, EN TROIS STYLES
--------------------------
- ``impressionniste`` (quartiers) : touches picturales generees par un bruit
  SEME (le meme grain que la reference), personnages Open Peeps recolores en
  silhouettes feutrees, cartel creme a double filet.
- ``bd-encrage`` (places) : contour #2b2b2b ~7 px, aplats francs, personnages
  dessines MAIN — les Open Peeps ont ete essayes puis ECARTES sur ce style
  (preference client), ne pas les reintroduire. Bande blanche + cartouche
  jaune « LE SAVIEZ-VOUS ? » + pastille noire.
- ``aquarelle`` (lieux urbains) : trait fin #3a332c, lavis translucides
  DECALES du trait (c'est le decalage qui fait l'aquarelle), papier creme,
  tampon rouge rond.

POURQUOI LE SVG PRODUIT EST AUTONOME
------------------------------------
Les references sont des .html avec du CSS et, pour l'impressionniste, un
script qui generait les touches au chargement. Le rasteriseur de production
(rsvg-convert sur le VPS, voir ``bd_cards``) ne connait ni le HTML, ni les
classes CSS, ni le JavaScript : tout est donc porte ici en SVG pur —
attributs de presentation inline, touches picturales calculees en Python par
le MEME generateur pseudo-aleatoire seme que la reference (mulberry32,
graine 20260814). C'est ce qui rend la carte reproductible au pixel pres
d'une machine a l'autre.

LES PERSONNAGES VIENNENT DE L'ARTOTHEQUE
----------------------------------------
``content/art-bibliotheque/open-peeps/`` (CC0). Chaque personnage s'assemble
piece par piece (pose, chevelure, visage, pilosite) dans le repere commun du
kit, et se recolore PAR PIECE — jamais un remplacement global des couleurs,
c'est le piege de la « peau verte » : le corps prend la couleur du vetement,
la tete celle de la carnation. En silhouette impressionniste, trait et aplat
prennent deux tons feutres voisins.

Polices : pile DejaVu d'abord (police du VPS de production), Georgia en
repli sur un poste Windows — meme logique que ``bd_style``. Les references
ont ete validees en Georgia ; l'ecart DejaVu/Georgia est accepte.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from bd_style import SANS, SERIF, esc

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 1080, 1920

ART_DIR = Path("content/art-bibliotheque/open-peeps")

STYLES = ("impressionniste", "bd-encrage", "aquarelle")

# Encres de la charte (LISEZMOI des echantillons).
ENCRE_BD = "#2b2b2b"        # contour BD ~7 px
ENCRE_AQUARELLE = "#3a332c" # trait fin aquarelle
ROUGE_TAMPON = "#b5443a"    # tampon aquarelle et folie de la Villette
JAUNE_CARTOUCHE = "#f9c74f" # cartouche « LE SAVIEZ-VOUS ? »

# Le cartouche BD est par langue : c'est le seul texte fixe traduisible.
LIBELLE_SAVIEZ_VOUS = {"fr": "LE SAVIEZ-VOUS ?", "en": "DID YOU KNOW?"}


class LieuStyleError(ValueError):
    """Composition impossible : scene, piece ou parametre inconnu."""


# ---------------------------------------------------------------------------
# Generateur pseudo-aleatoire seme
# ---------------------------------------------------------------------------
#
# mulberry32, porte bit a bit du JavaScript de la reference impressionniste.
# POURQUOI pas ``random.Random`` : la reference validee a ete generee avec
# CETTE suite ; la reutiliser a graine egale redonne exactement les memes
# touches — la carte du pipeline est superposable a celle que Paco a validee.

def _imul32(a: int, b: int) -> int:
    """Math.imul de JavaScript : multiplication 32 bits, bits conserves."""
    return (a * b) & 0xFFFFFFFF


def mulberry32(graine: int) -> Callable[[], float]:
    """Suite deterministe dans [0, 1), identique a la reference navigateur."""
    etat = graine & 0xFFFFFFFF

    def suivant() -> float:
        nonlocal etat
        etat = (etat + 0x6D2B79F5) & 0xFFFFFFFF
        t = etat
        t = _imul32(t ^ (t >> 15), 1 | t)
        t = ((t + _imul32(t ^ (t >> 7), 61 | t)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0

    return suivant


def _pick(rnd: Callable[[], float], choix: Sequence[str]) -> str:
    """Tirage dans une liste — consomme UN tirage, comme le pick() d'origine."""
    return choix[int(rnd() * len(choix))]


# ---------------------------------------------------------------------------
# Touches picturales : les trois gestes du peintre
# ---------------------------------------------------------------------------
#
# ``dab`` (touche), ``blob`` (tache) et ``poly`` (aplat) sont les primitives
# de la reference impressionniste, portees a l'identique : une carte est un
# empilement de milliers de ces gestes. Les arrondis (.1f) suivent le
# toFixed(1) d'origine — ca borne aussi la taille du fichier SVG.


def dab(x: float, y: float, angle: float, longueur: float, largeur: float,
        couleur: str, opacite: float) -> str:
    """Une touche de pinceau : trait court arrondi, incline, translucide."""
    a = angle * math.pi / 180.0
    dx = math.cos(a) * longueur / 2.0
    dy = math.sin(a) * longueur / 2.0
    return (f'<line x1="{x - dx:.1f}" y1="{y - dy:.1f}" x2="{x + dx:.1f}" '
            f'y2="{y + dy:.1f}" stroke="{couleur}" stroke-width="{largeur:.1f}" '
            f'stroke-linecap="round" opacity="{opacite:.2f}"/>')


def blob(x: float, y: float, rx: float, ry: float, couleur: str,
         opacite: float, rotation: float = 0.0) -> str:
    """Une tache elliptique : pave, ombre portee, fumee."""
    transform = (f' transform="rotate({rotation:.1f} {x:.1f} {y:.1f})"'
                 if rotation else "")
    return (f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" '
            f'fill="{couleur}" opacity="{opacite:.2f}"{transform}/>')


def poly(points: Sequence[Tuple[float, float]], couleur: str,
         opacite: Optional[float] = None) -> str:
    """Un aplat ferme : toit, volet, pan de mur."""
    d = "M" + "L".join(f"{px:.1f},{py:.1f}" for px, py in points) + "Z"
    op = f' opacity="{opacite}"' if opacite is not None else ""
    return f'<path d="{d}" fill="{couleur}"{op}/>'


# ---------------------------------------------------------------------------
# Chargeur-assembleur Open Peeps
# ---------------------------------------------------------------------------
#
# Chaque piece de l'artotheque est un SVG autonome dans le repere commun du
# personnage (LISEZMOI de l'artotheque). L'assemblage empile les pieces avec
# les translations du kit d'origine ; la recoloration remplace les couleurs
# par defaut (#000000 trait, #FFFFFF remplissage) PAR PIECE.

# Translations du kit, dans l'ordre d'empilement (le corps sous la tete).
_SLOTS: Tuple[Tuple[str, Optional[str]], ...] = (
    ("pose", None),
    ("cheveux", "translate(225 0)"),
    ("visage", "translate(384 186)"),
    ("pilosite", "translate(348 338)"),
    ("accessoires", "translate(272 241)"),
)


@dataclass(frozen=True)
class Piece:
    """Une piece Open Peeps et ses deux couleurs de recoloration."""

    fichier: str        # chemin relatif sans extension, ex. « cheveux/Long »
    trait: str          # remplace le #000000 du kit
    remplissage: str    # remplace le #FFFFFF du kit


@lru_cache(maxsize=None)
def _piece_brute(fichier: str) -> str:
    """Contenu interne d'une piece (sans la balise <svg>), lu une fois."""
    chemin = ART_DIR / f"{fichier}.svg"
    if not chemin.exists():
        dossier = chemin.parent
        connues = sorted(p.stem for p in dossier.glob("*.svg")) \
            if dossier.exists() else []
        raise LieuStyleError(
            f"Piece Open Peeps inconnue : {fichier!r}. "
            f"Connues dans {dossier.name}/ : {', '.join(connues) or '(dossier absent)'}"
        )
    texte = chemin.read_text(encoding="utf-8")
    debut = texte.find(">", texte.find("<svg")) + 1
    fin = texte.rfind("</svg>")
    if debut <= 0 or fin < 0:
        raise LieuStyleError(f"{chemin} : pas un SVG de piece lisible")
    return texte[debut:fin].strip()


def _recolore(svg: str, trait: str, remplissage: str) -> str:
    return (svg.replace("#000000", trait)
               .replace("#FFFFFF", remplissage)
               .replace("#ffffff", remplissage))


def peep(*, x: float, y: float, echelle: float, pose: Piece,
         cheveux: Optional[Piece] = None, visage: Optional[Piece] = None,
         pilosite: Optional[Piece] = None,
         accessoires: Optional[Piece] = None) -> str:
    """Un personnage assemble, place et mis a l'echelle dans la carte.

    L'ordre d'empilement est celui du kit : pose, chevelure (qui inclut le
    crane), visage, pilosite, accessoires. La tete reste au meme endroit
    quel que soit le corps — c'est la propriete du repere commun.
    """
    pieces = {"pose": pose, "cheveux": cheveux, "visage": visage,
              "pilosite": pilosite, "accessoires": accessoires}
    morceaux: List[str] = []
    for slot, transform in _SLOTS:
        piece = pieces[slot]
        if piece is None:
            if slot == "pose":
                raise LieuStyleError("Un peep sans pose n'est pas un peep.")
            continue
        contenu = _recolore(_piece_brute(piece.fichier), piece.trait,
                            piece.remplissage)
        ouverture = f'<g transform="{transform}">' if transform else "<g>"
        morceaux.append(f"{ouverture}\n{contenu}\n</g>")
    corps = "\n".join(morceaux)
    return (f'<g transform="translate({x} {y}) scale({echelle})">\n'
            f'{corps}\n</g>')


def silhouette(fichier_pose: str, encre: str, clair: str, *,
               cheveux: Optional[str] = None, visage: Optional[str] = None,
               pilosite: Optional[str] = None) -> Dict[str, Optional[Piece]]:
    """Recette de personnage-silhouette : toutes pieces dans deux tons.

    C'est la declinaison impressionniste : pas de carnation ni de couleur de
    vetement, deux tons feutres voisins suffisent a lire la figure de loin.
    """
    def _p(fichier: Optional[str]) -> Optional[Piece]:
        return Piece(fichier, encre, clair) if fichier else None

    return {"pose": Piece(fichier_pose, encre, clair), "cheveux": _p(cheveux),
            "visage": _p(visage), "pilosite": _p(pilosite),
            "accessoires": None}


# ---------------------------------------------------------------------------
# Blocs de legende — un par style
# ---------------------------------------------------------------------------
#
# L'anecdote arrive en DEUX lignes exactes (cesure editoriale, validee par
# ``lieu_topics``). Chaque style a son ecrin, releve des references :
# cartel creme (impressionniste), bande blanche (BD), papier nu (aquarelle).

# Largeur estimee d'un caractere serif italique 44-46 px, en fraction de la
# taille — calibre sur les references. On PREVIENT si une ligne menace de
# deborder, on ne coupe pas : la cesure appartient a l'editeur.
_LARGEUR_ITALIQUE = 0.47


def _verifier_largeur(lignes: Sequence[str], taille: int, nom_style: str) -> None:
    for ligne in lignes:
        estime = len(ligne) * taille * _LARGEUR_ITALIQUE
        if estime > 1000:
            logger.warning(
                "Legende %s : la ligne « %s » est estimee a %d px pour 1000 px "
                "utiles — verifie le rendu, raccourcis si elle deborde.",
                nom_style, ligne, int(estime),
            )


def cartel_impressionniste(anecdote: Sequence[str], sous_titre: str) -> str:
    """Cartel de musee : fond creme, double filet, italique, pied en petites
    capitales espacees « PARIS EXPLORER · LIEU »."""
    _verifier_largeur(anecdote, 46, "impressionniste")
    return f'''
<g>
  <rect x="0" y="1560" width="1080" height="360" fill="#f6efdd"/>
  <line x1="42" y1="1574" x2="1038" y2="1574" stroke="#7a5a3a" stroke-width="3"/>
  <line x1="42" y1="1583" x2="1038" y2="1583" stroke="#7a5a3a" stroke-width="1.2"/>
  <text x="540" y="1690" font-family="{SERIF}" font-size="46" font-style="italic" fill="#4a3a2c" text-anchor="middle">{esc(anecdote[0])}</text>
  <text x="540" y="1756" font-family="{SERIF}" font-size="46" font-style="italic" fill="#4a3a2c" text-anchor="middle">{esc(anecdote[1])}</text>
  <text x="540" y="1852" font-family="{SERIF}" font-size="30" letter-spacing="7" fill="#7a5a3a" text-anchor="middle">PARIS EXPLORER · {esc(sous_titre.upper())}</text>
</g>'''


def bande_bd(anecdote: Sequence[str], lang: str) -> str:
    """Bande blanche BD : filet noir, cartouche jaune incline
    « LE SAVIEZ-VOUS ? », anecdote en italique, pastille noire de marque."""
    _verifier_largeur(anecdote, 44, "bd-encrage")
    libelle = LIBELLE_SAVIEZ_VOUS.get(lang) or LIBELLE_SAVIEZ_VOUS["fr"]
    return f'''
<g>
  <rect x="0" y="1560" width="1080" height="360" fill="#ffffff"/>
  <rect x="0" y="1560" width="1080" height="6" fill="{ENCRE_BD}"/>
  <g transform="rotate(-3 235 1560)">
    <rect x="55" y="1527" width="360" height="66" rx="10" fill="{JAUNE_CARTOUCHE}" stroke="{ENCRE_BD}" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
    <text x="235" y="1572" text-anchor="middle" font-family="{SANS}" font-size="32" font-weight="bold" fill="{ENCRE_BD}">{esc(libelle)}</text>
  </g>
  <text x="540" y="1730" text-anchor="middle" font-family="{SERIF}" font-size="44" font-style="italic" fill="#222222">{esc(anecdote[0])}</text>
  <text x="540" y="1795" text-anchor="middle" font-family="{SERIF}" font-size="44" font-style="italic" fill="#222222">{esc(anecdote[1])}</text>
  <rect x="745" y="1830" width="300" height="58" rx="29" fill="#1d1d1d"/>
  <text x="895" y="1869" text-anchor="middle" font-family="{SANS}" font-size="28" font-weight="bold" letter-spacing="1" fill="#ffffff">PARIS EXPLORER</text>
</g>'''


def tampon_rouge(cx: float = 540, cy: float = 1838) -> str:
    """Tampon rond « PARIS EXPLORER » a l'encre rouge, legerement tourne.

    Les cercles pointilles passent dans le filtre #ink2 de la scene aquarelle
    (present dans ses defs) pour trembler comme un vrai coup de tampon.
    """
    return f'''
<g transform="rotate(-7 {cx:.0f} {cy:.0f})" opacity="0.75">
  <g filter="url(#ink2)" stroke="{ROUGE_TAMPON}" fill="none">
    <circle cx="{cx:.0f}" cy="{cy:.0f}" r="70" stroke-width="3.2" stroke-dasharray="100 4 140 3 90 4"/>
    <circle cx="{cx:.0f}" cy="{cy:.0f}" r="58" stroke-width="1.8" stroke-dasharray="80 3 100 4"/>
  </g>
  <text x="{cx:.0f}" y="{cy - 5:.0f}" text-anchor="middle" font-family="{SERIF}" font-size="23" letter-spacing="3" fill="{ROUGE_TAMPON}">PARIS</text>
  <text x="{cx:.0f}" y="{cy + 23:.0f}" text-anchor="middle" font-family="{SERIF}" font-size="15" letter-spacing="1" fill="{ROUGE_TAMPON}">EXPLORER</text>
  <circle cx="{cx:.0f}" cy="{cy - 32:.0f}" r="2.6" fill="{ROUGE_TAMPON}"/>
  <circle cx="{cx:.0f}" cy="{cy + 34:.0f}" r="2.6" fill="{ROUGE_TAMPON}"/>
</g>'''


def papier_aquarelle(anecdote: Sequence[str]) -> str:
    """Legende aquarelle : trait de sol irregulier, italique sur papier nu,
    tampon rouge — pas de fond rapporte, le papier EST le fond."""
    _verifier_largeur(anecdote, 44, "aquarelle")
    return f'''
<g filter="url(#ink)" stroke="{ENCRE_AQUARELLE}" fill="none" stroke-linecap="round">
  <path d="M70,1570 q240,8 480,2 q260,-6 460,2" stroke-width="2.8" stroke-dasharray="220 4 180 3 260 5"/>
</g>
<text x="540" y="1672" text-anchor="middle" font-family="{SERIF}" font-style="italic" font-size="44" fill="#4a4038">{esc(anecdote[0])}</text>
<text x="540" y="1736" text-anchor="middle" font-family="{SERIF}" font-style="italic" font-size="44" fill="#4a4038">{esc(anecdote[1])}</text>
{tampon_rouge()}'''


# ---------------------------------------------------------------------------
# Registre des scenes
# ---------------------------------------------------------------------------
#
# Une scene = une fonction qui compose le SVG COMPLET 1080x1920 d'un lieu a
# partir de ses textes. Le registre est la verite que ``lieu_topics`` valide :
# un YAML ne peut nommer qu'une scene enregistree, et le style de la scene
# doit etre celui qu'impose le type du lieu.


@dataclass(frozen=True)
class Scene:
    nom: str
    style: str
    composer: Callable[[Sequence[str], str, str], str]


SCENES: Dict[str, Scene] = {}


def _scene(nom: str, style: str):
    if style not in STYLES:
        raise LieuStyleError(f"Style inconnu : {style!r}. Connus : {', '.join(STYLES)}")

    def enregistre(fn: Callable[[Sequence[str], str, str], str]):
        SCENES[nom] = Scene(nom=nom, style=style, composer=fn)
        return fn

    return enregistre


def composer(nom_scene: str, anecdote: Sequence[str], sous_titre: str,
             lang: str) -> str:
    """Compose le SVG d'une scene enregistree, ou leve LieuStyleError."""
    scene = SCENES.get(nom_scene)
    if scene is None:
        raise LieuStyleError(
            f"Scene inconnue : {nom_scene!r}. "
            f"Enregistrees : {', '.join(sorted(SCENES))}"
        )
    if len(anecdote) != 2:
        raise LieuStyleError(
            f"L'anecdote doit faire exactement 2 lignes (cesure editoriale), "
            f"recu {len(anecdote)}"
        )
    return scene.composer(anecdote, sous_titre, lang)


def _svg(corps: str) -> str:
    """Racine SVG avec taille INTRINSEQUE : indispensable au rendu navigateur
    de secours, qui capture une fenetre aux dimensions de la carte."""
    return (f'<svg width="{WIDTH}" height="{HEIGHT}" '
            f'viewBox="0 0 {WIDTH} {HEIGHT}" '
            f'xmlns="http://www.w3.org/2000/svg">\n{corps}\n</svg>\n')


# ---------------------------------------------------------------------------
# Matiere SVG des references validees (14/08/2026)
# ---------------------------------------------------------------------------
#
# Ces blocs sont la matiere premiere extraite des ``.source.html`` de
# ``content/cartes-lieux-echantillons/`` : decors dessines main, classes CSS
# cuites en attributs inline, HTML retire. Ils ne se retouchent pas a la main
# ici — une evolution de la charte passe par une nouvelle reference validee.

_CONCORDE_CORPS = r"""

<!-- ===================== SKY ===================== -->
<rect x="0" y="0" width="1080" height="1060" fill="#a9def2"/>

<!-- clouds -->
<path fill="#ffffff" d="M110,255 a42,42 0 0 1 62,-36 a48,48 0 0 1 86,4 a36,36 0 0 1 46,32 z" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
<path fill="#ffffff" d="M760,330 a38,38 0 0 1 56,-32 a44,44 0 0 1 80,4 a33,33 0 0 1 42,28 z" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
<path fill="#ffffff" d="M880,150 a30,30 0 0 1 45,-26 a35,35 0 0 1 63,3 a26,26 0 0 1 33,23 z" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
<path fill="#ffffff" d="M70,620 a30,30 0 0 1 45,-26 a35,35 0 0 1 63,3 a26,26 0 0 1 33,23 z" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>

<!-- ===================== EIFFEL (distant) ===================== -->
<g>
  <line x1="170" y1="552" x2="170" y2="602" stroke-width="6" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
  <path fill="#7d93a8" d="M162,600 L178,600 L184,690 L156,690 Z" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <rect x="138" y="686" width="64" height="13" fill="#7d93a8" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <path fill="#7d93a8" d="M156,699 L184,699 L208,756 L132,756 Z" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <rect x="122" y="754" width="96" height="14" fill="#7d93a8" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <path fill="#7d93a8" d="M132,768 L208,768 L238,878 L196,878 Q186,822 170,822 Q154,822 144,878 L102,878 Z" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <line x1="140" y1="792" x2="200" y2="836" stroke-width="4" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
  <line x1="200" y1="792" x2="140" y2="836" stroke-width="4" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
</g>

<!-- ===================== ROOFTOPS ===================== -->
<g>
  <!-- block 1 -->
  <path fill="#5d7285" d="M-10,900 L20,868 L200,868 L230,900 Z" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <rect x="-10" y="900" width="240" height="104" fill="#efe0c0" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <rect x="20" y="920" width="16" height="26" fill="#b3a17f"/><rect x="62" y="920" width="16" height="26" fill="#b3a17f"/>
  <rect x="104" y="920" width="16" height="26" fill="#b3a17f"/><rect x="146" y="920" width="16" height="26" fill="#b3a17f"/>
  <rect x="188" y="920" width="16" height="26" fill="#b3a17f"/>
  <!-- block 2 -->
  <path fill="#68809a" d="M230,904 L258,862 L432,862 L460,904 Z" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <rect x="230" y="904" width="230" height="100" fill="#f2e3c6" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <rect x="258" y="922" width="16" height="26" fill="#b3a17f"/><rect x="300" y="922" width="16" height="26" fill="#b3a17f"/>
  <rect x="342" y="922" width="16" height="26" fill="#b3a17f"/><rect x="384" y="922" width="16" height="26" fill="#b3a17f"/>
  <rect x="426" y="922" width="16" height="26" fill="#b3a17f"/>
  <!-- block 3 (behind obelisk) -->
  <path fill="#5d7285" d="M460,898 L488,860 L664,860 L692,898 Z" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <rect x="460" y="898" width="232" height="106" fill="#ead9b8" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <rect x="488" y="920" width="16" height="26" fill="#b3a17f"/><rect x="640" y="920" width="16" height="26" fill="#b3a17f"/>
  <!-- block 4 -->
  <path fill="#68809a" d="M692,902 L720,864 L888,864 L916,902 Z" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <rect x="692" y="902" width="224" height="102" fill="#f2e3c6" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <rect x="720" y="922" width="16" height="26" fill="#b3a17f"/><rect x="762" y="922" width="16" height="26" fill="#b3a17f"/>
  <rect x="804" y="922" width="16" height="26" fill="#b3a17f"/><rect x="846" y="922" width="16" height="26" fill="#b3a17f"/>
  <!-- block 5 -->
  <path fill="#5d7285" d="M916,896 L944,866 L1090,866 L1090,896 Z" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <rect x="916" y="896" width="180" height="108" fill="#efe0c0" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <rect x="944" y="920" width="16" height="26" fill="#b3a17f"/><rect x="986" y="920" width="16" height="26" fill="#b3a17f"/>
  <rect x="1028" y="920" width="16" height="26" fill="#b3a17f"/>
  <!-- chimneys -->
  <rect x="90" y="838" width="22" height="34" fill="#c9705a" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <rect x="330" y="832" width="22" height="34" fill="#c9705a" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <rect x="790" y="834" width="22" height="34" fill="#c9705a" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
</g>

<!-- ===================== BALUSTRADE ===================== -->
<g>
  <rect x="-10" y="1008" width="1100" height="52" fill="#cdbb96"/>
  <rect x="-10" y="996" width="1100" height="18" fill="#e8d9ba" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <g fill="#e0cfa9">
    <rect x="24" y="1016" width="16" height="40" rx="7" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/><rect x="80" y="1016" width="16" height="40" rx="7" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <rect x="136" y="1016" width="16" height="40" rx="7" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/><rect x="192" y="1016" width="16" height="40" rx="7" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <rect x="248" y="1016" width="16" height="40" rx="7" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/><rect x="304" y="1016" width="16" height="40" rx="7" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <rect x="360" y="1016" width="16" height="40" rx="7" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/><rect x="416" y="1016" width="16" height="40" rx="7" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <rect x="648" y="1016" width="16" height="40" rx="7" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/><rect x="704" y="1016" width="16" height="40" rx="7" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <rect x="760" y="1016" width="16" height="40" rx="7" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/><rect x="816" y="1016" width="16" height="40" rx="7" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <rect x="872" y="1016" width="16" height="40" rx="7" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/><rect x="928" y="1016" width="16" height="40" rx="7" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <rect x="984" y="1016" width="16" height="40" rx="7" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/><rect x="1040" y="1016" width="16" height="40" rx="7" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
  </g>
  <rect x="-10" y="1056" width="1100" height="16" fill="#e8d9ba" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
</g>

<!-- ===================== GROUND ===================== -->
<rect x="0" y="1068" width="1080" height="492" fill="#dfcda6"/>
<g stroke-width="4" opacity="0.85" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round">
  <path d="M0,1148 Q540,1128 1080,1148" fill="none"/>
  <path d="M0,1268 Q540,1244 1080,1268" fill="none"/>
  <path d="M0,1420 Q540,1392 1080,1420" fill="none"/>
  <line x1="120" y1="1148" x2="116" y2="1268"/>
  <line x1="420" y1="1140" x2="414" y2="1262"/>
  <line x1="760" y1="1142" x2="766" y2="1264"/>
  <line x1="980" y1="1148" x2="988" y2="1268"/>
  <line x1="260" y1="1268" x2="252" y2="1420"/>
  <line x1="600" y1="1256" x2="596" y2="1400"/>
  <line x1="900" y1="1262" x2="910" y2="1414"/>
  <line x1="60" y1="1420" x2="52" y2="1560"/>
  <line x1="480" y1="1400" x2="474" y2="1560"/>
  <line x1="840" y1="1408" x2="850" y2="1560"/>
</g>

<!-- ===================== LAMPPOSTS ===================== -->
<g>
  <!-- left -->
  <g>
    <path fill="#33544e" d="M78,1080 L112,1080 L106,1040 L84,1040 Z" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
    <rect x="89" y="770" width="12" height="272" fill="#33544e" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
    <rect x="83" y="900" width="24" height="12" rx="5" fill="#f2c14e" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <rect x="81" y="762" width="28" height="14" rx="6" fill="#f2c14e" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="95" cy="732" r="24" fill="#fdf6e3" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
    <path fill="#f2c14e" d="M95,694 L104,710 L86,710 Z" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
  </g>
  <!-- right -->
  <g>
    <path fill="#33544e" d="M983,1080 L1017,1080 L1011,1040 L989,1040 Z" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
    <rect x="994" y="770" width="12" height="272" fill="#33544e" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
    <rect x="988" y="900" width="24" height="12" rx="5" fill="#f2c14e" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <rect x="986" y="762" width="28" height="14" rx="6" fill="#f2c14e" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="1000" cy="732" r="24" fill="#fdf6e3" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
    <path fill="#f2c14e" d="M1000,694 L1009,710 L991,710 Z" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
  </g>
</g>

<!-- ===================== OBELISK ===================== -->
<g>
  <!-- shadow -->
  <ellipse cx="620" cy="1192" rx="150" ry="24" fill="#c8b184"/>
  <!-- pedestal -->
  <rect x="455" y="1148" width="170" height="40" rx="4" fill="#a8977a" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <rect x="470" y="1062" width="140" height="88" fill="#b8a685" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <circle cx="540" cy="1106" r="14" fill="#f2c14e" stroke="#2b2b2b" stroke-width="5"/>
  <rect x="462" y="1040" width="156" height="24" rx="4" fill="#a8977a" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <!-- shaft -->
  <path d="M506,252 L574,252 L602,1042 L478,1042 Z" fill="#e6c17b" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <path d="M506,252 L522,252 L496,1042 L478,1042 Z" fill="#d0a659"/>
  <!-- pyramidion -->
  <path d="M540,166 L578,252 L502,252 Z" fill="#f6c453" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <!-- hieroglyph strip (abstract) -->
  <g fill="#a5793a">
    <circle cx="548" cy="310" r="9"/>
    <rect x="534" y="342" width="30" height="9" rx="3"/>
    <path d="M548,378 L562,404 L534,404 Z"/>
    <rect x="536" y="424" width="11" height="11"/><rect x="553" y="424" width="11" height="11"/>
    <path d="M532,470 q8,-14 16,0 q8,14 16,0" fill="none" stroke="#a5793a" stroke-width="7" stroke-linecap="round"/>
    <ellipse cx="548" cy="512" rx="15" ry="9"/>
    <circle cx="548" cy="556" r="8"/><rect x="543" y="566" width="10" height="24" rx="4"/>
    <rect x="532" y="614" width="32" height="9" rx="3"/>
    <path d="M548,648 L563,676 L533,676 Z"/>
    <circle cx="548" cy="716" r="9"/>
    <rect x="534" y="748" width="30" height="9" rx="3"/>
    <path d="M531,790 q8,-14 17,0 q8,14 17,0" fill="none" stroke="#a5793a" stroke-width="7" stroke-linecap="round"/>
    <ellipse cx="548" cy="834" rx="15" ry="9"/>
    <rect x="536" y="866" width="11" height="11"/><rect x="553" y="866" width="11" height="11"/>
    <circle cx="548" cy="914" r="9"/>
    <rect x="533" y="946" width="32" height="9" rx="3"/>
    <path d="M548,978 L563,1006 L533,1006 Z"/>
  </g>
</g>

<!-- ===================== FOUNTAIN (left, mid-ground) ===================== -->
<g>
  <ellipse cx="270" cy="1244" rx="162" ry="26" fill="#c8b184"/>
  <!-- basin wall -->
  <path d="M120,1192 L120,1226 A150,38 0 0 0 420,1226 L420,1192" fill="#276b4f" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <ellipse cx="270" cy="1192" rx="150" ry="38" fill="#2e7d5b" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <ellipse cx="270" cy="1188" rx="124" ry="27" fill="#bfe6f5" stroke="#2b2b2b" stroke-width="5"/>
  <!-- stem + vasque -->
  <rect x="256" y="1076" width="28" height="112" fill="#2e7d5b" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <rect x="250" y="1124" width="40" height="14" rx="6" fill="#f2c14e" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
  <path d="M196,1058 L344,1058 Q342,1084 312,1092 L228,1092 Q198,1084 196,1058 Z" fill="#2e7d5b" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <ellipse cx="270" cy="1058" rx="74" ry="14" fill="#3a8d68" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <!-- narrow water falls from under the vasque -->
  <path d="M208,1064 Q196,1106 192,1148 L206,1152 Q208,1110 224,1072 Z" fill="#eef9fd" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
  <path d="M332,1064 Q344,1106 348,1148 L334,1152 Q332,1110 316,1072 Z" fill="#eef9fd" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
  <ellipse cx="198" cy="1158" rx="11" ry="5" fill="#eef9fd" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
  <ellipse cx="342" cy="1158" rx="11" ry="5" fill="#eef9fd" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
  <!-- central plume -->
  <path d="M256,1058 Q246,1000 270,964 Q294,1000 284,1058 Z" fill="#eef9fd" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
  <circle cx="270" cy="948" r="6" fill="#eef9fd" stroke="#2b2b2b" stroke-width="4"/>
  <circle cx="252" cy="972" r="4" fill="#eef9fd" stroke="#2b2b2b" stroke-width="3"/>
  <circle cx="289" cy="978" r="4" fill="#eef9fd" stroke="#2b2b2b" stroke-width="3"/>
  <circle cx="270" cy="1058" r="9" fill="#f2c14e" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
</g>

<!-- ===================== ICE-CREAM CART + VENDOR (right, mid-ground) ===================== -->
<g>
  <ellipse cx="945" cy="1348" rx="110" ry="18" fill="#c8b184"/>
  <!-- awning poles -->
  <line x1="888" y1="1232" x2="888" y2="1156" stroke-width="7" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
  <line x1="1002" y1="1232" x2="1002" y2="1156" stroke-width="7" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
  <!-- awning -->
  <g>
    <rect x="866" y="1122" width="158" height="36" fill="#e63946" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
    <rect x="893" y="1125" width="26" height="30" fill="#ffffff"/>
    <rect x="945" y="1125" width="26" height="30" fill="#ffffff"/>
    <rect x="997" y="1125" width="24" height="30" fill="#ffffff"/>
    <path d="M866,1158 a13,13 0 0 0 26,0 z" fill="#e63946" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <path d="M892,1158 a13,13 0 0 0 26,0 z" fill="#ffffff" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <path d="M918,1158 a13,13 0 0 0 26,0 z" fill="#e63946" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <path d="M944,1158 a13,13 0 0 0 26,0 z" fill="#ffffff" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <path d="M970,1158 a13,13 0 0 0 26,0 z" fill="#e63946" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <path d="M996,1158 a13,13 0 0 0 26,0 z" fill="#ffffff" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
  </g>
  <!-- vendor (left of cart) -->
  <g>
    <line x1="836" y1="1256" x2="832" y2="1314" stroke-width="20" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="836" y1="1256" x2="832" y2="1314" stroke="#33415c" stroke-width="10" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="856" y1="1256" x2="862" y2="1314" stroke-width="20" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="856" y1="1256" x2="862" y2="1314" stroke="#33415c" stroke-width="10" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <ellipse cx="830" cy="1319" rx="13" ry="6" fill="#2b2b2b"/>
    <ellipse cx="864" cy="1319" rx="13" ry="6" fill="#2b2b2b"/>
    <rect x="820" y="1198" width="52" height="62" rx="17" fill="#ffffff" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
    <line x1="864" y1="1214" x2="884" y2="1240" stroke-width="18" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="864" y1="1214" x2="884" y2="1240" stroke="#ffffff" stroke-width="9" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="828" y1="1214" x2="810" y2="1238" stroke-width="18" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="828" y1="1214" x2="810" y2="1238" stroke="#ffffff" stroke-width="9" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M801,1244 L817,1244 L809,1270 Z" fill="#d9a066" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="809" cy="1238" r="9" fill="#f4978e" stroke="#2b2b2b" stroke-width="5"/>
    <circle cx="846" cy="1168" r="21" fill="#c68863" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
    <path d="M828,1160 L864,1160 L858,1140 L834,1140 Z" fill="#f5f0e6" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <line x1="837" y1="1166" x2="831" y2="1166" stroke-width="5" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
  </g>
  <!-- cart body -->
  <rect x="878" y="1232" width="134" height="82" rx="10" fill="#ffffff" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <path d="M906,1298 L922,1266 L938,1298 Z" fill="#d9a066" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
  <circle cx="922" cy="1258" r="11" fill="#f4978e" stroke="#2b2b2b" stroke-width="5"/>
  <rect x="956" y="1252" width="40" height="10" rx="4" fill="#e63946" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
  <rect x="956" y="1272" width="40" height="10" rx="4" fill="#f2c14e" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
  <circle cx="904" cy="1324" r="22" fill="#d8e2e8" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <circle cx="904" cy="1324" r="6" fill="#2b2b2b"/>
  <circle cx="986" cy="1324" r="22" fill="#d8e2e8" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <circle cx="986" cy="1324" r="6" fill="#2b2b2b"/>
</g>

<!-- ===================== CYCLIST (center, mid-ground) ===================== -->
<g>
  <ellipse cx="472" cy="1348" rx="100" ry="15" fill="#c8b184"/>
  <!-- wheels -->
  <circle cx="420" cy="1330" r="35" fill="#d8e2e8" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <circle cx="420" cy="1330" r="5" fill="#2b2b2b"/>
  <line x1="420" y1="1300" x2="420" y2="1360" stroke-width="4" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
  <line x1="390" y1="1330" x2="450" y2="1330" stroke-width="4" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="524" cy="1330" r="35" fill="#d8e2e8" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <circle cx="524" cy="1330" r="5" fill="#2b2b2b"/>
  <line x1="524" y1="1300" x2="524" y2="1360" stroke-width="4" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
  <line x1="494" y1="1330" x2="554" y2="1330" stroke-width="4" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
  <!-- frame -->
  <g stroke-width="15" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round">
    <path d="M420,1330 L470,1326 L460,1272 M470,1326 L510,1268 M524,1330 L510,1268" fill="none"/>
  </g>
  <g stroke="#d62828" stroke-width="7" fill="none" stroke-linecap="round" stroke-linejoin="round">
    <path d="M420,1330 L470,1326 L460,1272 M470,1326 L510,1268 M524,1330 L510,1268" fill="none"/>
  </g>
  <circle cx="470" cy="1326" r="7" fill="#2b2b2b"/>
  <!-- rider legs -->
  <path d="M460,1268 L482,1300 L470,1330" stroke-width="22" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M460,1268 L482,1300 L470,1330" stroke="#33415c" stroke-width="11" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  <!-- rider torso -->
  <line x1="458" y1="1266" x2="498" y2="1218" stroke-width="28" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
  <line x1="458" y1="1266" x2="498" y2="1218" stroke="#3a86ff" stroke-width="15" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  <!-- arm -->
  <line x1="496" y1="1224" x2="512" y2="1262" stroke-width="20" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
  <line x1="496" y1="1224" x2="512" y2="1262" stroke="#3a86ff" stroke-width="10" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="513" cy="1264" r="7" fill="#f2c9a0" stroke="#2b2b2b" stroke-width="4"/>
  <!-- head + helmet -->
  <circle cx="510" cy="1196" r="20" fill="#f2c9a0" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <path d="M492,1190 A20,20 0 0 1 528,1188 L530,1196 L490,1198 Z" fill="#f9c74f" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
  <line x1="519" y1="1198" x2="525" y2="1198" stroke-width="5" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
</g>

<!-- ===================== COUPLE + CHILD (foreground left) ===================== -->
<g>
  <ellipse cx="230" cy="1512" rx="120" ry="17" fill="#c8b184"/>
  <ellipse cx="112" cy="1510" rx="52" ry="12" fill="#c8b184"/>
  <!-- child + balloon -->
  <g>
    <circle cx="128" cy="1245" r="30" fill="#e63946" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
    <path d="M126,1276 L130,1276 L134,1286 L122,1286 Z" fill="#2b2b2b"/>
    <path d="M128,1286 Q140,1330 135,1370" stroke-width="4" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="118" y1="1450" x2="112" y2="1500" stroke-width="18" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="118" y1="1450" x2="112" y2="1500" stroke="#5f6caf" stroke-width="9" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="132" y1="1450" x2="140" y2="1500" stroke-width="18" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="132" y1="1450" x2="140" y2="1500" stroke="#5f6caf" stroke-width="9" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <ellipse cx="110" cy="1504" rx="12" ry="6" fill="#2b2b2b"/>
    <ellipse cx="142" cy="1504" rx="12" ry="6" fill="#2b2b2b"/>
    <rect x="104" y="1398" width="44" height="58" rx="15" fill="#f9c74f" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
    <line x1="140" y1="1408" x2="136" y2="1372" stroke-width="16" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="140" y1="1408" x2="136" y2="1372" stroke="#f9c74f" stroke-width="8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="135" cy="1370" r="7" fill="#f2c9a0" stroke="#2b2b2b" stroke-width="4"/>
    <line x1="110" y1="1410" x2="102" y2="1444" stroke-width="16" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="110" y1="1410" x2="102" y2="1444" stroke="#f9c74f" stroke-width="8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="124" cy="1372" r="20" fill="#f2c9a0" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
    <path d="M106,1366 A20,20 0 0 1 142,1364 L142,1356 L106,1358 Z" fill="#6b4b32" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <line x1="132" y1="1372" x2="137" y2="1372" stroke-width="5" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
  </g>
  <!-- man -->
  <g>
    <line x1="205" y1="1400" x2="188" y2="1498" stroke-width="26" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="205" y1="1400" x2="188" y2="1498" stroke="#3d405b" stroke-width="13" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="225" y1="1400" x2="244" y2="1496" stroke-width="26" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="225" y1="1400" x2="244" y2="1496" stroke="#3d405b" stroke-width="13" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <ellipse cx="184" cy="1503" rx="16" ry="8" fill="#2b2b2b"/>
    <ellipse cx="250" cy="1501" rx="16" ry="8" fill="#2b2b2b"/>
    <rect x="186" y="1295" width="62" height="115" rx="22" fill="#e07a5f" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
    <line x1="198" y1="1322" x2="180" y2="1398" stroke-width="22" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="198" y1="1322" x2="180" y2="1398" stroke="#e07a5f" stroke-width="11" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="179" cy="1401" r="8" fill="#f2c9a0" stroke="#2b2b2b" stroke-width="4"/>
    <line x1="240" y1="1322" x2="270" y2="1390" stroke-width="22" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="240" y1="1322" x2="270" y2="1390" stroke="#e07a5f" stroke-width="11" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="220" cy="1255" r="27" fill="#f2c9a0" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
    <path d="M195,1244 A27,27 0 0 1 245,1244 L245,1236 L195,1238 Z" fill="#4a3226" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <line x1="230" y1="1252" x2="237" y2="1252" stroke-width="5" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M226,1268 q7,5 14,0" stroke-width="4" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
  </g>
  <!-- woman -->
  <g>
    <line x1="285" y1="1438" x2="278" y2="1500" stroke-width="22" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="285" y1="1438" x2="278" y2="1500" stroke="#f2c9a0" stroke-width="11" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="315" y1="1438" x2="326" y2="1498" stroke-width="22" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="315" y1="1438" x2="326" y2="1498" stroke="#f2c9a0" stroke-width="11" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <ellipse cx="276" cy="1505" rx="14" ry="7" fill="#2b2b2b"/>
    <ellipse cx="330" cy="1503" rx="14" ry="7" fill="#2b2b2b"/>
    <path d="M276,1300 L326,1300 Q332,1300 334,1310 L346,1432 Q347,1442 336,1442 L266,1442 Q255,1442 256,1432 L268,1310 Q270,1300 276,1300 Z" fill="#81b29a" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
    <line x1="286" y1="1322" x2="272" y2="1388" stroke-width="20" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="286" y1="1322" x2="272" y2="1388" stroke="#81b29a" stroke-width="10" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="318" y1="1322" x2="342" y2="1392" stroke-width="20" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="318" y1="1322" x2="342" y2="1392" stroke="#81b29a" stroke-width="10" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <rect x="332" y="1396" width="26" height="30" rx="6" fill="#f9c74f" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="344" cy="1396" r="6" fill="none" stroke="#2b2b2b" stroke-width="4"/>
    <circle cx="300" cy="1258" r="25" fill="#c68863" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
    <path d="M277,1248 A25,25 0 0 1 323,1246 L323,1238 L277,1242 Z" fill="#3a2a1e" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="322" cy="1234" r="11" fill="#3a2a1e" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <line x1="309" y1="1256" x2="315" y2="1256" stroke-width="5" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M304,1270 q6,4 12,0" stroke-width="4" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="271" cy="1390" r="9" fill="#c68863" stroke="#2b2b2b" stroke-width="4"/>
  </g>
</g>

<!-- ===================== TOURIST (foreground right) ===================== -->
<g>
  <ellipse cx="762" cy="1496" rx="70" ry="14" fill="#c8b184"/>
  <line x1="752" y1="1392" x2="745" y2="1484" stroke-width="26" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
  <line x1="752" y1="1392" x2="745" y2="1484" stroke="#b08968" stroke-width="13" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  <line x1="772" y1="1392" x2="780" y2="1484" stroke-width="26" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
  <line x1="772" y1="1392" x2="780" y2="1484" stroke="#b08968" stroke-width="13" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  <ellipse cx="741" cy="1489" rx="16" ry="8" fill="#2b2b2b"/>
  <ellipse cx="786" cy="1489" rx="16" ry="8" fill="#2b2b2b"/>
  <rect x="792" y="1300" width="26" height="58" rx="11" fill="#2a9d8f" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <rect x="736" y="1290" width="58" height="110" rx="20" fill="#f4a261" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <line x1="748" y1="1312" x2="720" y2="1262" stroke-width="22" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
  <line x1="748" y1="1312" x2="720" y2="1262" stroke="#f4a261" stroke-width="11" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  <line x1="780" y1="1312" x2="724" y2="1280" stroke-width="22" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
  <line x1="780" y1="1312" x2="724" y2="1280" stroke="#f4a261" stroke-width="11" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  <g transform="rotate(-10 710 1264)">
    <rect x="697" y="1240" width="27" height="48" rx="5" fill="#2b2b2b" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <rect x="702" y="1248" width="17" height="28" fill="#9fd8ef"/>
  </g>
  <circle cx="722" cy="1258" r="8" fill="#8d5524" stroke="#2b2b2b" stroke-width="4"/>
  <circle cx="726" cy="1280" r="8" fill="#8d5524" stroke="#2b2b2b" stroke-width="4"/>
  <circle cx="764" cy="1250" r="26" fill="#8d5524" stroke="#2b2b2b" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
  <path d="M740,1240 A26,26 0 0 1 788,1240 L788,1232 L740,1234 Z" fill="#1f1a16" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
  <line x1="752" y1="1248" x2="745" y2="1248" stroke-width="5" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
</g>

<!-- ===================== PIGEONS ===================== -->
<g>
  <!-- pecking pigeon -->
  <ellipse cx="505" cy="1500" rx="52" ry="9" fill="#c8b184"/>
  <g transform="translate(53,-40) translate(452,1516) scale(1.5) translate(-452,-1516)">
    <path d="M470,1500 L482,1492 L474,1506 Z" fill="#8b98a5" stroke="#2b2b2b" stroke-width="4" stroke-linejoin="round"/>
    <ellipse cx="452" cy="1508" rx="21" ry="13" fill="#9aa7b3" transform="rotate(12 452 1508)" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <ellipse cx="456" cy="1506" rx="11" ry="7" fill="#7f8c99" transform="rotate(12 456 1506)"/>
    <circle cx="431" cy="1518" r="9" fill="#9aa7b3" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <path d="M424,1523 L416,1529 L427,1529 Z" fill="#f4a261"/>
    <circle cx="429" cy="1516" r="2.4" fill="#2b2b2b"/>
    <line x1="448" y1="1522" x2="445" y2="1533" stroke-width="4" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="458" y1="1522" x2="458" y2="1533" stroke-width="4" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
  </g>
  <!-- standing pigeon -->
  <ellipse cx="557" cy="1552" rx="52" ry="9" fill="#c8b184"/>
  <g transform="translate(-75,6) translate(630,1512) scale(1.5) translate(-630,-1512)">
    <path d="M610,1508 L598,1500 L607,1514 Z" fill="#75828f" stroke="#2b2b2b" stroke-width="4" stroke-linejoin="round"/>
    <ellipse cx="630" cy="1512" rx="21" ry="13" fill="#8b98a5" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <ellipse cx="626" cy="1510" rx="11" ry="7" fill="#75828f"/>
    <circle cx="652" cy="1500" r="9" fill="#8b98a5" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <path d="M660,1500 L670,1503 L660,1506 Z" fill="#f4a261"/>
    <circle cx="654" cy="1498" r="2.4" fill="#2b2b2b"/>
    <line x1="626" y1="1524" x2="624" y2="1534" stroke-width="4" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="636" y1="1524" x2="636" y2="1534" stroke-width="4" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
  </g>
  <!-- small pigeon near fountain -->
  <g transform="translate(-200,-113)">
    <ellipse cx="352" cy="1300" rx="16" ry="11" fill="#9aa7b3" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <ellipse cx="349" cy="1299" rx="8" ry="5" fill="#7f8c99"/>
    <circle cx="367" cy="1291" r="7" fill="#9aa7b3" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <path d="M373,1291 L381,1293 L373,1296 Z" fill="#f4a261"/>
    <circle cx="369" cy="1289" r="2" fill="#2b2b2b"/>
    <line x1="349" y1="1310" x2="348" y2="1318" stroke-width="3" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="357" y1="1310" x2="357" y2="1318" stroke-width="3" fill="none" stroke="#2b2b2b" stroke-linecap="round" stroke-linejoin="round"/>
  </g>
</g>

"""

# Le ``concorde-bd.source.html`` a encore bouge APRES le rendu du PNG valide :
# ses deux pigeons (celui de la fontaine, celui qui se tient debout) n'y sont
# plus a la place que montre le PNG. Le PNG valide fait foi — on repositionne
# les deux groupes tels que valides, et on garde la trace du correctif ICI
# plutot que de retoucher la reference en silence.
_CONCORDE_CORPS = (_CONCORDE_CORPS
    .replace('<g transform="translate(-200,-113)">',
             '<g transform="translate(44,-113)">')
    .replace('<g transform="translate(-75,6) translate(630,1512) scale(1.5) '
             'translate(-630,-1512)">',
             '<g transform="translate(630,1512) scale(1.5) '
             'translate(-630,-1512)">')
    .replace('<ellipse cx="557" cy="1552" rx="52" ry="9" fill="#c8b184"/>',
             '<ellipse cx="630" cy="1548" rx="52" ry="9" fill="#c8b184"/>'))

_VILLETTE_DEFS = r"""

<defs>
  <filter id="wash" x="-20%" y="-20%" width="140%" height="140%">
    <feTurbulence type="fractalNoise" baseFrequency="0.012" numOctaves="3" seed="7" result="n"/>
    <feDisplacementMap in="SourceGraphic" in2="n" scale="18"/>
  </filter>
  <filter id="wash2" x="-20%" y="-20%" width="140%" height="140%">
    <feTurbulence type="fractalNoise" baseFrequency="0.02" numOctaves="3" seed="23" result="n"/>
    <feDisplacementMap in="SourceGraphic" in2="n" scale="26"/>
  </filter>
  <filter id="wash3" x="-25%" y="-25%" width="150%" height="150%">
    <feTurbulence type="fractalNoise" baseFrequency="0.008" numOctaves="2" seed="41" result="n"/>
    <feDisplacementMap in="SourceGraphic" in2="n" scale="34"/>
  </filter>
  <filter id="ink" x="-10%" y="-10%" width="120%" height="120%">
    <feTurbulence type="fractalNoise" baseFrequency="0.025" numOctaves="2" seed="11" result="n"/>
    <feDisplacementMap in="SourceGraphic" in2="n" scale="4"/>
  </filter>
  <filter id="ink2" x="-10%" y="-10%" width="120%" height="120%">
    <feTurbulence type="fractalNoise" baseFrequency="0.03" numOctaves="2" seed="55" result="n"/>
    <feDisplacementMap in="SourceGraphic" in2="n" scale="5"/>
  </filter>
  <filter id="grain">
    <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="3" result="n"/>
    <feColorMatrix in="n" type="matrix" values="0 0 0 0 0.45  0 0 0 0 0.42  0 0 0 0 0.36  0 0 0 0.06 0"/>
  </filter>
</defs>

"""

_VILLETTE_CORPS = r"""

<!-- ============ PAPER ============ -->
<rect width="1080" height="1920" fill="#f4efe4"/>
<rect width="1080" height="1920" filter="url(#grain)"/>

<!-- ============ SKY : pale blooms + brush strokes ============ -->
<g filter="url(#wash3)">
  <ellipse cx="300" cy="180" rx="250" ry="90" fill="#a9bcc2" opacity="0.13"/>
  <ellipse cx="740" cy="130" rx="210" ry="75" fill="#c9b99b" opacity="0.10"/>
  <path d="M120,330 q220,-50 440,-16 q90,14 150,44 q-160,36 -360,22 q-160,-10 -230,-50 Z" fill="#b3c2c0" opacity="0.11"/>
  <ellipse cx="880" cy="360" rx="170" ry="60" fill="#c8bda4" opacity="0.11"/>
  <path d="M60,470 q140,-36 300,-10 q60,10 90,30 q-130,28 -260,16 q-100,-8 -130,-36 Z" fill="#a9bcc2" opacity="0.12"/>
</g>

<!-- ============ GEODE (au fond, posee sur la berge) ============ -->
<!-- washes, offset from the ink on purpose -->
<g transform="translate(9,-7)" filter="url(#wash)">
  <circle cx="760" cy="646" r="178" fill="#8fa3ae" opacity="0.40"/>
  <path d="M592,700 a178,178 0 0,0 336,20 q-86,40 -176,26 q-102,-12 -160,-46 Z" fill="#71858f" opacity="0.40"/>
  <path d="M660,505 q58,-46 130,-32 q36,8 56,26 q-66,-10 -114,8 q-48,16 -72,-2 Z" fill="#f4efe4" opacity="0.6"/>
</g>
<g filter="url(#wash2)">
  <ellipse cx="700" cy="560" rx="70" ry="36" fill="#c6d2d6" opacity="0.35"/>
  <path d="M690,780 a178,178 0 0,0 160,-40 q-30,44 -80,52 q-50,8 -80,-12 Z" fill="#5d707a" opacity="0.30"/>
</g>
<!-- plaza + shadow anchoring the sphere -->
<g filter="url(#wash2)">
  <ellipse cx="756" cy="836" rx="190" ry="26" fill="#8d968f" opacity="0.30"/>
  <ellipse cx="756" cy="842" rx="120" ry="14" fill="#5d707a" opacity="0.25"/>
</g>
<!-- ink : sphere + geodesic facets (two diagonal families + arcs) -->
<g filter="url(#ink)" stroke="#3a332c" fill="none" stroke-linecap="round">
  <circle cx="754" cy="650" r="176" stroke-width="3.4" stroke-dasharray="230 4 310 3 390 5"/>
  <!-- horizontal arcs -->
  <path d="M582,608 q172,52 344,10" stroke-width="2.2" stroke-dasharray="110 4 90 3"/>
  <path d="M592,712 q162,46 324,4" stroke-width="2.2" stroke-dasharray="90 5 120 3"/>
  <path d="M622,520 q132,40 276,14" stroke-width="2" stroke-dasharray="90 4 70 4"/>
  <!-- diagonal family 1 -->
  <path d="M636,514 q100,140 88,300" stroke-width="2" stroke-dasharray="80 4 60 3"/>
  <path d="M712,482 q90,150 62,330" stroke-width="2" stroke-dasharray="70 4 90 3"/>
  <path d="M806,486 q66,140 22,320" stroke-width="2" stroke-dasharray="90 3 60 4"/>
  <!-- diagonal family 2 -->
  <path d="M876,530 q-110,130 -104,290" stroke-width="2" stroke-dasharray="70 4 80 3"/>
  <path d="M694,488 q-80,120 -96,250" stroke-width="2" stroke-dasharray="80 3 60 4"/>
  <!-- short facet chords, top right -->
  <path d="M846,556 l38,34" stroke-width="1.8"/>
  <path d="M872,610 l30,-20" stroke-width="1.8"/>
  <!-- base -->
  <path d="M636,812 q120,24 240,-8" stroke-width="2.6"/>
</g>

<!-- ============ DISTANT TREES (far bank, in front of geode base) ============ -->
<g filter="url(#wash2)">
  <ellipse cx="90" cy="852" rx="120" ry="52" fill="#93a486" opacity="0.42"/>
  <ellipse cx="480" cy="848" rx="140" ry="46" fill="#9aab8c" opacity="0.36"/>
  <ellipse cx="545" cy="818" rx="85" ry="40" fill="#88997c" opacity="0.36"/>
  <ellipse cx="990" cy="842" rx="125" ry="48" fill="#93a486" opacity="0.40"/>
  <ellipse cx="925" cy="812" rx="65" ry="36" fill="#88997c" opacity="0.30"/>
  <ellipse cx="640" cy="850" rx="70" ry="34" fill="#93a486" opacity="0.32"/>
</g>
<g filter="url(#ink)" stroke="#3a332c" fill="none" stroke-linecap="round">
  <path d="M20,850 q30,-30 64,-18 q22,-20 56,-8 q28,-16 52,4 q14,10 18,22" stroke-width="2.6"/>
  <path d="M408,850 q26,-26 58,-16 q20,-18 54,-6 q26,-14 60,4 q22,-10 42,8" stroke-width="2.6"/>
  <path d="M888,842 q28,-28 60,-14 q22,-18 56,-4 q26,-12 58,10" stroke-width="2.6"/>
  <path d="M584,852 q22,-22 50,-12 q18,-14 46,-2 q20,-8 36,8" stroke-width="2.4"/>
</g>

<!-- ============ FOLIE ROUGE (Tschumi) ============ -->
<!-- washes offset -->
<g transform="translate(10,-8)" filter="url(#wash)">
  <rect x="168" y="612" width="200" height="200" fill="#b5443a" opacity="0.48"/>
  <rect x="168" y="712" width="200" height="100" fill="#a03a32" opacity="0.30"/>
  <polygon points="368,712 452,796 452,868 368,792" fill="#b5443a" opacity="0.40"/>
  <rect x="238" y="556" width="66" height="56" fill="#b5443a" opacity="0.42"/>
</g>
<!-- ink -->
<g filter="url(#ink2)" stroke="#3a332c" fill="none" stroke-linecap="round" stroke-linejoin="round">
  <!-- main cube + 3x3 grid -->
  <rect x="172" y="616" width="196" height="196" stroke-width="3.4" stroke-dasharray="150 4 200 3 170 5"/>
  <path d="M172,681 h196 M172,746 h196" stroke-width="2.4" stroke-dasharray="70 4 90 3"/>
  <path d="M237,616 v196 M302,616 v196" stroke-width="2.4" stroke-dasharray="80 3 70 4"/>
  <!-- small top volume -->
  <rect x="240" y="558" width="62" height="58" stroke-width="2.8"/>
  <path d="M240,588 h62" stroke-width="2"/>
  <!-- external staircase descending to the ground (steps zigzag + railing) -->
  <path d="M368,716 L392,740 L392,756 L414,778 L414,794 L436,816 L436,832 L458,854 L458,868" stroke-width="2.8"/>
  <path d="M368,700 L462,794" stroke-width="2.4"/>
  <path d="M368,700 L368,716 M416,748 v14 M462,794 v18" stroke-width="2.2"/>
  <!-- stilts + ground -->
  <path d="M188,812 v58 M352,812 v56" stroke-width="2.8"/>
  <path d="M156,872 q140,10 320,-4" stroke-width="2.6"/>
</g>

<!-- ============ CANAL : wash bands with paper gaps ============ -->
<g filter="url(#wash3)">
  <path d="M-30,892 h1140 v52 h-1140 Z" fill="#9db2ba" opacity="0.34"/>
  <path d="M-30,956 h1140 v70 h-1140 Z" fill="#8aa0aa" opacity="0.30"/>
  <path d="M-30,1042 h660 v56 h-660 Z" fill="#9db2ba" opacity="0.28"/>
  <path d="M700,1048 h410 v50 h-410 Z" fill="#8aa0aa" opacity="0.26"/>
  <path d="M-30,1112 h1140 v66 h-1140 Z" fill="#7d939e" opacity="0.30"/>
  <path d="M-30,1192 h1140 v58 h-1140 Z" fill="#9db2ba" opacity="0.28"/>
</g>
<!-- reflections : broken vertical patches -->
<g filter="url(#wash2)">
  <path d="M212,896 q16,4 30,0 l-4,52 q-12,4 -24,0 Z" fill="#b5443a" opacity="0.24"/>
  <path d="M218,972 q14,4 26,0 l-6,66 q-10,4 -18,0 Z" fill="#b5443a" opacity="0.20"/>
  <path d="M226,1064 q12,4 22,0 l-6,54 q-8,4 -14,0 Z" fill="#b5443a" opacity="0.16"/>
  <path d="M714,896 q34,6 62,0 l-8,58 q-24,6 -46,0 Z" fill="#71858f" opacity="0.22"/>
  <path d="M726,978 q28,6 50,0 l-10,60 q-18,6 -32,0 Z" fill="#71858f" opacity="0.18"/>
</g>
<!-- water ink ripples -->
<g filter="url(#ink)" stroke="#3a332c" fill="none" stroke-linecap="round">
  <path d="M40,912 q60,8 120,0 q70,-8 130,2" stroke-width="2.2" opacity="0.75"/>
  <path d="M600,924 q70,8 140,-2 q60,-6 120,4" stroke-width="2.2" opacity="0.7"/>
  <path d="M110,992 q80,10 150,0 q60,-8 110,4" stroke-width="2.4" opacity="0.8"/>
  <path d="M60,1128 q90,10 170,0 q70,-8 120,4" stroke-width="2.4" opacity="0.75"/>
  <path d="M700,1160 q80,8 160,-2 q60,-6 120,4" stroke-width="2.4" opacity="0.8"/>
  <path d="M300,1218 q90,10 180,0 q80,-8 150,4" stroke-width="2.6" opacity="0.8"/>
  <path d="M180,1064 q60,8 120,0" stroke-width="2.2" opacity="0.6"/>
  <path d="M850,1056 q60,8 120,0" stroke-width="2.2" opacity="0.6"/>
  <path d="M420,1120 q50,7 100,0" stroke-width="2.2" opacity="0.55"/>
  <!-- far bank edge -->
  <path d="M-10,886 q260,14 540,6 q300,-10 560,2" stroke-width="3" stroke-dasharray="300 4 260 3 340 5"/>
</g>

<!-- ============ PENICHE (dans l'eau) ============ -->
<g transform="translate(8,-6)" filter="url(#wash)">
  <path d="M520,1010 L950,1002 L940,1092 Q740,1108 560,1096 L522,1078 Z" fill="#6b6258" opacity="0.5"/>
  <rect x="800" y="944" width="126" height="62" fill="#8a7f70" opacity="0.45"/>
  <rect x="530" y="1012" width="406" height="16" fill="#b5443a" opacity="0.42"/>
</g>
<g filter="url(#ink2)" stroke="#3a332c" fill="none" stroke-linecap="round" stroke-linejoin="round">
  <path d="M514,1006 L956,998 L944,1088 Q742,1106 562,1094 L516,1072 Z" stroke-width="3.2" stroke-dasharray="260 4 200 3 240 5"/>
  <path d="M522,1030 L948,1022" stroke-width="2.2"/>
  <rect x="804" y="940" width="122" height="60" stroke-width="2.8"/>
  <path d="M812,960 h26 M850,960 h26 M888,960 h26" stroke-width="2.4"/>
  <path d="M862,978 v20" stroke="#b5443a" stroke-width="4" opacity="0.7"/>
  <circle cx="600" cy="1054" r="7" stroke-width="2.2"/>
  <circle cx="660" cy="1054" r="7" stroke-width="2.2"/>
  <circle cx="720" cy="1054" r="7" stroke-width="2.2"/>
  <path d="M948,1010 q26,-16 30,-40" stroke-width="2.4"/>
</g>
<!-- waterline cutting the hull -->
<g filter="url(#wash2)">
  <path d="M490,1076 h500 v34 h-500 Z" fill="#8aa0aa" opacity="0.34"/>
</g>
<g filter="url(#ink)" stroke="#3a332c" fill="none" stroke-linecap="round">
  <path d="M480,1082 q80,10 170,4 q120,-8 210,0 q80,6 150,-4" stroke-width="2.6" opacity="0.85"/>
  <path d="M540,1116 q80,8 160,0 M760,1122 q80,8 160,-2" stroke-width="2.2" opacity="0.7"/>
</g>
<!-- dark reflection under the barge -->
<g filter="url(#wash2)">
  <path d="M560,1120 q180,16 360,-4 l-14,44 q-160,16 -320,0 Z" fill="#4f5a55" opacity="0.18"/>
</g>

<!-- ============ NEAR BANK : patches, not a slab ============ -->
<g filter="url(#wash3)">
  <path d="M-20,1272 Q240,1252 520,1268 Q560,1330 540,1420 Q300,1440 -20,1410 Z" fill="#a5a88c" opacity="0.34"/>
  <path d="M560,1276 Q820,1288 1100,1268 L1100,1400 Q860,1424 600,1404 Q570,1340 560,1276 Z" fill="#9aa080" opacity="0.30"/>
  <path d="M-20,1450 Q280,1428 560,1450 Q820,1470 1100,1444 L1100,1560 L-20,1560 Z" fill="#8f9478" opacity="0.26"/>
  <path d="M200,1300 Q420,1290 560,1304 Q580,1350 566,1396 Q380,1408 220,1394 Q198,1346 200,1300 Z" fill="#c2b691" opacity="0.24"/>
</g>
<g filter="url(#ink)" stroke="#3a332c" fill="none" stroke-linecap="round">
  <path d="M-10,1268 Q300,1246 620,1266 Q890,1282 1090,1260" stroke-width="3" stroke-dasharray="280 4 220 3 300 5"/>
  <path d="M70,1348 q80,-8 150,-2 M780,1356 q90,-8 170,0" stroke-width="2.2" opacity="0.65"/>
  <path d="M240,1306 q160,-10 320,2" stroke-width="2.2" opacity="0.55"/>
  <path d="M620,1470 q40,4 80,0 M150,1490 q30,4 60,0" stroke-width="2.2" opacity="0.6"/>
</g>

<!-- ============ WALKER + DOG ============ -->
<g transform="translate(7,-5)" filter="url(#wash)">
  <path d="M316,1336 q28,-8 44,8 q12,20 12,58 l-4,58 -64,2 -6,-64 q-4,-44 18,-62 Z" fill="#5f7078" opacity="0.48"/>
  <circle cx="338" cy="1312" r="17" fill="#c09a7c" opacity="0.35"/>
  <path d="M462,1466 q28,-18 60,-8 q18,8 16,28 l-8,20 -52,2 -18,-22 Z" fill="#7a6f60" opacity="0.42"/>
</g>
<g filter="url(#ink2)" stroke="#3a332c" fill="none" stroke-linecap="round" stroke-linejoin="round">
  <!-- head + cap -->
  <circle cx="338" cy="1310" r="16" stroke-width="3"/>
  <path d="M322,1304 q14,-10 30,-2" stroke-width="2.4"/>
  <!-- coat : clear silhouette, flaring -->
  <path d="M330,1326 q-22,10 -26,44 l-6,72 q22,10 76,4 l-2,-74 q-2,-36 -22,-46" stroke-width="3.2"/>
  <path d="M338,1340 v96" stroke-width="2" stroke-dasharray="30 4 40 3"/>
  <!-- legs : stride -->
  <path d="M320,1446 l-14,62 M356,1446 l14,60" stroke-width="3.2"/>
  <path d="M304,1508 l20,6 M370,1506 l20,4" stroke-width="2.8"/>
  <!-- arm + leash -->
  <path d="M356,1352 q24,26 42,44" stroke-width="2.8"/>
  <path d="M398,1396 Q444,1444 478,1468" stroke-width="2" stroke-dasharray="22 3 28 2 24 3"/>
  <!-- dog : head, ears, legs, tail -->
  <path d="M470,1470 q4,-10 16,-12 l26,-2 q14,0 22,10 q6,10 2,20 l-8,12 -48,2 -12,-14 Z" stroke-width="2.8"/>
  <circle cx="516" cy="1462" r="11" stroke-width="2.6"/>
  <path d="M508,1454 q-4,8 -2,14 M524,1456 q4,8 2,13" stroke-width="2.4"/>
  <path d="M526,1466 l8,2" stroke-width="2.2"/>
  <path d="M478,1500 l-2,18 M494,1502 l0,18 M510,1500 l2,18" stroke-width="2.6"/>
  <path d="M472,1478 q-14,-4 -16,-20" stroke-width="2.8"/>
</g>

<!-- ============ GULLS ============ -->
<g filter="url(#ink)" stroke="#3a332c" fill="none" stroke-linecap="round">
  <path d="M440,280 q16,-14 30,0 q14,-14 30,0" stroke-width="2.6"/>
  <path d="M540,344 q12,-11 24,0 q12,-11 24,0" stroke-width="2.4"/>
  <path d="M390,386 q10,-9 20,0 q10,-9 20,0" stroke-width="2.2"/>
</g>

<!-- ============ FOREGROUND GRASSES : dense clusters ============ -->
<g filter="url(#wash2)">
  <path d="M20,1430 q70,-44 160,-20 q34,64 12,150 l-180,0 Z" fill="#7f8a68" opacity="0.30"/>
  <path d="M900,1410 q80,-40 168,-10 q22,74 0,160 l-176,0 Z" fill="#7f8a68" opacity="0.28"/>
  <path d="M600,1490 q40,-24 90,-10 q14,36 4,80 l-96,0 Z" fill="#8a9370" opacity="0.22"/>
</g>
<g filter="url(#ink2)" stroke="#3a332c" fill="none" stroke-linecap="round">
  <!-- left cluster -->
  <path d="M56,1560 q-10,-90 8,-152" stroke-width="3"/>
  <path d="M88,1560 q6,-112 -14,-172" stroke-width="2.6"/>
  <path d="M118,1560 q10,-84 32,-142" stroke-width="2.8"/>
  <path d="M148,1560 q-8,-102 8,-162" stroke-width="2.4"/>
  <path d="M34,1560 q-2,-72 -18,-112" stroke-width="2.4"/>
  <path d="M176,1560 q6,-70 24,-108" stroke-width="2.4"/>
  <path d="M204,1560 q-4,-56 6,-92" stroke-width="2.2"/>
  <path d="M154,1398 q8,-14 22,-16 M62,1408 q-8,-14 -22,-14 M148,1418 q10,-8 22,-6" stroke-width="2.2"/>
  <ellipse cx="152" cy="1394" rx="5" ry="11" transform="rotate(18 152 1394)" stroke-width="2" fill="#3a332c" fill-opacity="0.45"/>
  <ellipse cx="76" cy="1392" rx="4.5" ry="10" transform="rotate(-14 76 1392)" stroke-width="2" fill="#3a332c" fill-opacity="0.45"/>
  <!-- right cluster -->
  <path d="M954,1560 q12,-102 -6,-168" stroke-width="3"/>
  <path d="M988,1560 q-6,-92 20,-152" stroke-width="2.8"/>
  <path d="M1020,1560 q10,-112 -8,-178" stroke-width="2.6"/>
  <path d="M928,1560 q-6,-74 14,-124" stroke-width="2.4"/>
  <path d="M1048,1560 q4,-82 -12,-132" stroke-width="2.4"/>
  <path d="M900,1560 q-2,-58 10,-96" stroke-width="2.2"/>
  <path d="M1010,1408 q12,-12 26,-12 M950,1390 q-10,-14 -26,-12" stroke-width="2.2"/>
  <ellipse cx="1014" cy="1384" rx="5" ry="11" transform="rotate(14 1014 1384)" stroke-width="2" fill="#3a332c" fill-opacity="0.45"/>
  <ellipse cx="944" cy="1388" rx="4.5" ry="10" transform="rotate(-16 944 1388)" stroke-width="2" fill="#3a332c" fill-opacity="0.45"/>
  <!-- mid tufts -->
  <path d="M636,1560 q4,-42 -8,-72 M658,1560 q2,-52 14,-78 M616,1560 q-2,-36 -12,-54 M680,1560 q0,-40 10,-60" stroke-width="2.4"/>
  <!-- pebbles -->
  <path d="M770,1520 q8,-6 16,0 q4,6 -4,10 q-10,2 -12,-10 M820,1540 q6,-5 13,0 q3,5 -3,8 q-8,2 -10,-8" stroke-width="2"/>
</g>

"""

_MONTMARTRE_DEFS = r"""

<defs>
  <linearGradient id="skyG" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#8fa0b6"/>
    <stop offset="0.5" stop-color="#c2cbd6"/>
    <stop offset="0.8" stop-color="#dcd8cb"/>
    <stop offset="1" stop-color="#e2ddce"/>
  </linearGradient>
  <linearGradient id="streetG" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#b6b8bc"/>
    <stop offset="0.4" stop-color="#a3a5ab"/>
    <stop offset="1" stop-color="#8a8b92"/>
  </linearGradient>
  <linearGradient id="talusG" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#938e63"/>
    <stop offset="1" stop-color="#6d6a49"/>
  </linearGradient>
  <clipPath id="clipIllus"><rect x="0" y="0" width="1080" height="1560"/></clipPath>
  <clipPath id="clipSky"><rect x="0" y="0" width="1080" height="1050"/></clipPath>
  <clipPath id="clipStreet"><path d="M497,828 L595,828 L878,1560 L212,1560 Z"/></clipPath>
  <clipPath id="clipTalus"><path d="M660,1015 L1080,925 L1080,1560 L872,1560 Z"/></clipPath>
  <clipPath id="clipBldL"><path d="M120,700 L430,660 L430,1000 L120,1010 Z"/></clipPath>
  <clipPath id="clipBldR"><path d="M650,660 L955,705 L955,1020 L650,1015 Z"/></clipPath>
  <clipPath id="clipCab"><rect x="0" y="860" width="300" height="700"/></clipPath></defs>

"""

_MONTMARTRE_SACRE = r"""

<g id="sacre" transform="translate(0,16)">
    <path d="M380,592 L380,540 L440,535 L440,470 L470,465 L470,430 L610,430 L610,465 L640,470 L640,535 L700,540 L700,592 Z" fill="#96a3bd"/>
    <rect x="480" y="420" width="120" height="60" fill="#909db8"/>
    <path d="M478,424 C478,352 540,330 540,330 C540,330 602,352 602,424 Z" fill="#a7b2c9"/>
    <rect x="528" y="300" width="24" height="34" fill="#909db8"/>
    <path d="M526,302 C526,282 540,276 540,276 C540,276 554,282 554,302 Z" fill="#a7b2c9"/>
    <line x1="540" y1="276" x2="540" y2="258" stroke="#909db8" stroke-width="4" stroke-linecap="round"/>
    <path d="M428,470 C428,432 458,424 458,424 C458,424 488,432 488,470 Z" fill="#a7b2c9"/>
    <path d="M592,470 C592,432 622,424 622,424 C622,424 652,432 652,470 Z" fill="#a7b2c9"/>
    <rect x="662" y="360" width="42" height="180" fill="#96a3bd"/>
    <path d="M658,364 C658,326 683,318 683,318 C683,318 708,326 708,364 Z" fill="#a7b2c9"/>
    <path d="M540,332 C575,345 600,375 601,424 L580,424 C578,378 562,350 540,332 Z" fill="#8593b0" opacity="0.75"/>
    <path d="M683,320 C695,326 706,340 707,363 L698,363 C697,341 691,329 683,320 Z" fill="#8593b0" opacity="0.65"/>
    <rect x="500" y="500" width="18" height="50" rx="9" fill="#8593b0" opacity="0.5"/>
    <rect x="531" y="500" width="18" height="50" rx="9" fill="#8593b0" opacity="0.5"/>
    <rect x="562" y="500" width="18" height="50" rx="9" fill="#8593b0" opacity="0.5"/>
    <path d="M480,418 C481,358 522,336 538,331" fill="none" stroke="#e2e7f0" stroke-width="3.5" stroke-linecap="round" opacity="0.6"/>
    <path d="M430,466 C431,440 448,428 457,425" fill="none" stroke="#e2e7f0" stroke-width="2.8" stroke-linecap="round" opacity="0.55"/>
    <path d="M594,466 C595,440 612,428 621,425" fill="none" stroke="#e2e7f0" stroke-width="2.8" stroke-linecap="round" opacity="0.55"/>
    <path d="M660,362 C661,334 675,321 682,319" fill="none" stroke="#e2e7f0" stroke-width="2.8" stroke-linecap="round" opacity="0.55"/>
    <path d="M527,300 C527,286 535,278 539,277" fill="none" stroke="#e2e7f0" stroke-width="2.2" stroke-linecap="round" opacity="0.55"/>
  </g>

"""

_MONTMARTRE_MORRIS = r"""

<g id="morris">
    <ellipse cx="806" cy="1214" rx="52" ry="12" fill="#55523f" opacity="0.4"/>
    <rect x="762" y="1022" width="88" height="192" rx="10" fill="#34413a"/>
    <ellipse cx="806" cy="1026" rx="50" ry="15" fill="#40514a"/>
    <path d="M760,1020 C760,982 852,982 852,1020 Z" fill="#313d35"/>
    <path d="M756,1020 L856,1020 L850,1032 L762,1032 Z" fill="#2c372f"/>
    <ellipse cx="806" cy="986" rx="12" ry="6" fill="#40514a"/>
    <line x1="806" y1="984" x2="806" y2="966" stroke="#313d35" stroke-width="5" stroke-linecap="round"/>
    <rect x="776" y="1052" width="60" height="136" fill="#ddd1b2"/>
    <rect x="776" y="1052" width="60" height="30" fill="#96493e"/>
    <line x1="784" y1="1100" x2="828" y2="1100" stroke="#8a8172" stroke-width="4" stroke-linecap="round"/>
    <line x1="784" y1="1114" x2="828" y2="1114" stroke="#8a8172" stroke-width="4" stroke-linecap="round"/>
    <line x1="784" y1="1128" x2="820" y2="1128" stroke="#8a8172" stroke-width="4" stroke-linecap="round"/>
    <line x1="784" y1="1148" x2="826" y2="1148" stroke="#9c5044" stroke-width="5" stroke-linecap="round" opacity="0.8"/>
    <line x1="784" y1="1164" x2="814" y2="1164" stroke="#8a8172" stroke-width="4" stroke-linecap="round"/>
  </g>

"""

_MONTMARTRE_LAMP = r"""

<g id="lamp">
    <ellipse cx="352" cy="1428" rx="34" ry="9" fill="#565247" opacity="0.5"/>
    <path d="M338,1428 L343,1330 L361,1330 L366,1428 Z" fill="#39463b"/>
    <rect x="347" y="980" width="10" height="360" fill="#39463b"/>
    <path d="M334,980 L370,980 L364,952 L340,952 Z" fill="#39463b"/>
    <path d="M332,954 L340,902 L364,902 L372,954 Z" fill="#f0d9a0"/>
    <path d="M332,954 L340,902 L364,902 L372,954 Z" fill="none" stroke="#2f3a31" stroke-width="3.5"/>
    <line x1="352" y1="902" x2="352" y2="954" stroke="#2f3a31" stroke-width="2.5"/>
    <line x1="336" y1="928" x2="368" y2="928" stroke="#2f3a31" stroke-width="2"/>
    <path d="M326,902 L378,902 L352,878 Z" fill="#39463b"/>
    <line x1="352" y1="882" x2="352" y2="870" stroke="#39463b" stroke-width="5" stroke-linecap="round"/>
    <rect x="330" y="952" width="44" height="8" fill="#2f3a31"/>
    <ellipse cx="352" cy="930" rx="58" ry="44" fill="#f2dca6" opacity="0.14"/>
  </g>

"""


# ---------------------------------------------------------------------------
# Scene « concorde » — place, BD encrage
# ---------------------------------------------------------------------------
#
# Portee telle quelle de la reference validee : ciel, obelisque, fontaine,
# marchand de glaces, cycliste, famille, touriste, pigeons — personnages
# dessines MAIN (les Open Peeps sont ecartes de ce style, voir la charte).
# Les classes CSS de la reference (.o, .o5, .nk, .cl) ont ete cuites en
# attributs inline pour rester compatibles rsvg-convert.


@_scene("concorde", "bd-encrage")
def scene_concorde(anecdote: Sequence[str], sous_titre: str, lang: str) -> str:
    return _svg(_CONCORDE_CORPS + bande_bd(anecdote, lang))


# ---------------------------------------------------------------------------
# Scene « villette » — lieu urbain, BD inde aquarelle
# ---------------------------------------------------------------------------
#
# Portee telle quelle de la reference validee : Geode, folie rouge de
# Tschumi, canal de l'Ourcq, peniche, promeneur au chien, herbes du premier
# plan. Les lavis passent dans des filtres feTurbulence/feDisplacementMap
# (supportes par librsvg) et sont volontairement DECALES du trait d'encre.


@_scene("villette", "aquarelle")
def scene_villette(anecdote: Sequence[str], sous_titre: str, lang: str) -> str:
    return _svg(_VILLETTE_DEFS + "\n" + _VILLETTE_CORPS
                + papier_aquarelle(anecdote))


# ---------------------------------------------------------------------------
# Scene « montmartre » — quartier, impressionniste Belle Epoque
# ---------------------------------------------------------------------------
#
# La reference generait ses milliers de touches picturales dans le navigateur
# avec mulberry32(20260814). Ce portage rejoue la MEME suite dans le MEME
# ordre d'appel : chaque tirage compte, y compris ceux des branches non
# retenues — deplacer un appel decale toute la suite et change la carte.
# C'est pour ca que le code suit pas a pas la structure du script d'origine
# plutot qu'une factorisation plus « jolie ».

# Les six passants Open Peeps de la reference : position, echelle, pieces,
# et les deux tons feutres de la silhouette (trait, aplat).
_PEEPS_MONTMARTRE = (
    (667.70, 1174.23, 0.12459, "poses-debout/PolkaDots", "cheveux/Long",
     "visages/CheersNM", None, "#2f2822", "#453b32"),
    (285.46, 1138.75, 0.09508, "poses-debout/BlazerBW", "cheveux/Short",
     "visages/Serious", "pilosite/Handlebars", "#2a2521", "#3d3630"),
    (514.67, 970.03, 0.06066, "poses-debout/ShirtPantsBW", "cheveux/ShortMessy",
     "visages/Smile", None, "#332d27", "#4a423a"),
    (559.31, 977.87, 0.05738, "poses-debout/PolkaDots", "cheveux/Bun",
     "visages/CheersNM", None, "#362f28", "#4e4438"),
    (877.95, 1085.70, 0.05410, "poses-debout/EasingBW", "cheveux/ShortCurly",
     "visages/Solemn", None, "#3a332b", "#52483c"),
    (944.23, 1059.38, 0.04754, "poses-debout/RestingBW", "cheveux/Bun",
     "visages/Smile", None, "#332d26", "#4a4136"),
)


def _montmartre_peeps() -> str:
    morceaux = []
    for x, y, ech, pose, chv, vis, pil, encre, clair in _PEEPS_MONTMARTRE:
        pieces = silhouette(pose, encre, clair, cheveux=chv, visage=vis,
                            pilosite=pil)
        morceaux.append(peep(x=x, y=y, echelle=ech, **pieces))
    return "\n".join(morceaux)


@_scene("montmartre", "impressionniste")
def scene_montmartre(anecdote: Sequence[str], sous_titre: str, lang: str) -> str:
    rnd = mulberry32(20260814)

    # --- CIEL : 1350 touches, froides en haut, chaudes vers l'horizon -----
    ciel: List[str] = []
    froides = ("#8ea0b8", "#97a8bd", "#a5b2c4", "#b3bccb")
    medianes = ("#bcc4d0", "#c8ccd4", "#d2d4d8", "#c4c3c6")
    chaudes = ("#ddd8cc", "#e4ddcd", "#d8d2c4", "#e9e2d2")
    for _ in range(1350):
        x = rnd() * 1080
        y = (rnd() ** 1.1) * 780
        t = y / 780
        r = rnd()
        if t < 0.4:
            c = _pick(rnd, froides) if r < 0.75 else _pick(rnd, medianes)
        elif t < 0.72:
            c = (_pick(rnd, medianes) if r < 0.6
                 else (_pick(rnd, froides) if r < 0.85 else _pick(rnd, chaudes)))
        else:
            c = _pick(rnd, chaudes) if r < 0.75 else _pick(rnd, medianes)
        ciel.append(dab(x, y, (rnd() - 0.5) * 20, 30 + rnd() * 48,
                        7 + rnd() * 7, c, 0.35 + rnd() * 0.4))
    nuageux = ("#dfe0e2", "#e8e6e0", "#d4d6da", "#eeeae0")
    for cx, cy, rr in ((210, 140, 180), (720, 110, 150), (480, 260, 130),
                       (900, 300, 120), (150, 380, 110), (620, 430, 90)):
        for _ in range(60):
            a = rnd() * 6.283
            d = math.sqrt(rnd()) * rr
            ang = (rnd() - 0.5) * 14
            lg = 32 + rnd() * 48
            w = 9 + rnd() * 6
            c = _pick(rnd, nuageux)
            op = 0.3 + rnd() * 0.35
            ciel.append(dab(cx + math.cos(a) * d * 1.6,
                            cy + math.sin(a) * d * 0.55, ang, lg, w, c, op))
    for bx, by in ((300, 190), (340, 175), (820, 230)):
        ciel.append(
            f'<path d="M{bx - 9},{by} Q{bx - 4},{by - 6} {bx},{by} '
            f'Q{bx + 4},{by - 6} {bx + 9},{by}" fill="none" stroke="#6b7484" '
            f'stroke-width="2.5" stroke-linecap="round" opacity="0.6"/>')

    # --- CRETE de la Butte ------------------------------------------------
    crete: List[str] = ['<path d="M0,830 C150,770 320,650 540,612 C740,650 '
                        '940,770 1080,822 L1080,1560 L0,1560 Z" fill="#adaf99"/>']
    tons_crete = ("#a3a68e", "#b2b49c", "#9aa088", "#bab8a0", "#a8ab90")
    for _ in range(300):
        x = rnd() * 1080
        if x < 540:
            crest_y = 830 - 218 * math.sin((x / 540) * 1.5708)
        else:
            crest_y = 612 + 210 * math.sin(((x - 540) / 540) * 1.5708)
        y = crest_y + rnd() * (1020 - crest_y)
        crete.append(dab(x, y, (rnd() - 0.5) * 30, 14 + rnd() * 24,
                         7 + rnd() * 6, _pick(rnd, tons_crete),
                         0.35 + rnd() * 0.3))

    # --- VERDURE de crete, devant la base de la basilique -----------------
    verdure: List[str] = [poly(((350, 660), (380, 616), (460, 596), (540, 590),
                                (640, 598), (710, 622), (740, 660), (540, 672)),
                               "#9ba18a", 0.95)]
    tons_verts = ("#9aa088", "#a8ab90", "#8d9480", "#b2b298", "#9fa68e", "#87906f")
    for _ in range(150):
        x = 360 + rnd() * 380
        y = 598 + rnd() * 70
        verdure.append(dab(x, y, (rnd() - 0.5) * 40, 14 + rnd() * 22,
                           7 + rnd() * 6, _pick(rnd, tons_verts),
                           0.5 + rnd() * 0.35))

    # --- TOITS lointains sur les pentes -----------------------------------
    toits: List[str] = []
    tons_toit = ("#a7afba", "#b1b7c0", "#9da5b2")
    tons_mur = ("#d7d0c0", "#dcd4c4", "#d0c9b8")

    def _bande_toits(x0: float, x1: float, y_de: Callable[[float], float]) -> None:
        x = x0
        while x < x1:
            w = 42 + rnd() * 52
            hh = 32 + rnd() * 40
            y = y_de(x) + rnd() * 16
            pts_mur = ((x, y + hh), (x, y), (x + w / 2, y - 14 - rnd() * 10),
                       (x + w, y), (x + w, y + hh))
            toits.append(poly(pts_mur, _pick(rnd, tons_mur), 0.95))
            pts_toit = ((x - 3, y + 2), (x + w / 2, y - 16 - rnd() * 8),
                        (x + w + 3, y + 2), (x + w / 2, y - 6))
            toits.append(poly(pts_toit, _pick(rnd, tons_toit), 0.95))
            for k in range(3):
                if rnd() < 0.7:
                    toits.append(poly(((x + 8 + k * 12, y + 8),
                                       (x + 15 + k * 12, y + 8),
                                       (x + 15 + k * 12, y + 22),
                                       (x + 8 + k * 12, y + 22)),
                                      "#8e897c", 0.7))
            x += w * 0.9

    _bande_toits(-20, 360,
                 lambda x: 830 - 218 * math.sin((max(x, 0) / 540) * 1.5708) + 30)
    _bande_toits(720, 1085,
                 lambda x: 612 + 210 * math.sin(((x - 540) / 540) * 1.5708) + 26)

    # --- IMMEUBLES : texture des murs, puis fenetres ----------------------
    tex_g: List[str] = []
    tex_d: List[str] = []
    tons_gauche = ("#cabfa8", "#d8cfbb", "#c2b7a0", "#ddd4c0", "#bdb29a", "#cfc3aa")
    for _ in range(300):
        tex_g.append(dab(120 + rnd() * 310, 660 + rnd() * 350,
                         90 + (rnd() - 0.5) * 18, 16 + rnd() * 28,
                         7 + rnd() * 6, _pick(rnd, tons_gauche),
                         0.25 + rnd() * 0.3))
    tons_droite = ("#cfc5ae", "#ded5c0", "#c8bda6", "#e2dac6", "#c1b69e", "#d4c9b2")
    for _ in range(300):
        tex_d.append(dab(650 + rnd() * 305, 660 + rnd() * 355,
                         90 + (rnd() - 0.5) * 18, 16 + rnd() * 28,
                         7 + rnd() * 6, _pick(rnd, tons_droite),
                         0.25 + rnd() * 0.3))

    def _fenetre(tampon: List[str], x: float, y: float, w: float, h: float,
                 biais: float) -> None:
        """Fenetre a la touche : linteau, embrasure, reflets, volets."""
        tampon.append(dab(x + w / 2, y - 6, biais, w + 14, 7, "#c9c0aa", 0.7))
        tampon.append(poly(((x, y), (x + w, y + biais * 0.06 * w),
                            (x + w, y + h + biais * 0.06 * w), (x, y + h)),
                           "#77705f", 0.85))
        tampon.append(dab(x + w * 0.3, y + h * 0.3, 75, h * 0.45, 5, "#a3a3a8", 0.5))
        tampon.append(dab(x + w * 0.7, y + h * 0.6, 75, h * 0.4, 4, "#8e8b84", 0.45))
        tampon.append(poly(((x - 8, y + 1), (x - 2, y + 1), (x - 2, y + h - 1),
                            (x - 8, y + h - 1)), "#aca084", 0.75))
        tampon.append(poly(((x + w + 2, y + 1), (x + w + 8, y + 1),
                            (x + w + 8, y + h - 1), (x + w + 2, y + h - 1)),
                           "#aca084", 0.75))

    fen_g: List[str] = []
    for r in range(3):
        for c in range(4):
            x = 152 + c * 72
            y = 714 + r * 94 - c * 2.4
            _fenetre(fen_g, x, y, 34, 56, -2)
            if r == 1:
                fen_g.append(dab(x + 17, y + 58, 0, 44, 3.5, "#6a6255", 0.7))
    fen_d: List[str] = []
    for r in range(3):
        for c in range(4):
            x = 684 + c * 70
            y = 718 + r * 92 + c * 2.4
            _fenetre(fen_d, x, y, 34, 56, 2)
            if r == 1:
                fen_d.append(dab(x + 17, y + 60, 0, 44, 3.5, "#6a6255", 0.7))
    # Corniches d'etage et ombrage de forme.
    fen_g.append(dab(275, 796, -4.4, 300, 4, "#b3a88e", 0.6))
    fen_g.append(dab(275, 890, -4.4, 300, 4, "#b3a88e", 0.6))
    fen_g.append(poly(((400, 664), (430, 660), (430, 1000), (400, 1002)),
                      "#b6ab92", 0.45))
    fen_d.append(dab(800, 800, 4.4, 296, 4, "#b8ad94", 0.6))
    fen_d.append(dab(800, 892, 4.4, 296, 4, "#b8ad94", 0.6))
    fen_d.append(poly(((650, 660), (678, 664), (678, 1016), (650, 1015)),
                      "#baaf96", 0.45))
    # Jardinieres fleuries (accent rouge feutre) — dans le tampon gauche,
    # comme la reference (quelques-unes debordent sur l'immeuble droit, et
    # c'est ce que montre le PNG valide).
    tons_fleurs = ("#9c4a3e", "#a85a48", "#7d8a52")
    for fx, fy in ((169, 873), (701, 884), (841, 889)):
        fen_g.append(poly(((fx - 6, fy), (fx + 40, fy), (fx + 40, fy + 8),
                           (fx - 6, fy + 8)), "#7c6a52", 0.9))
        for i in range(7):
            fen_g.append(dab(fx + i * 6.5, fy - 3 + (rnd() - 0.5) * 4,
                             (rnd() - 0.5) * 50, 6 + rnd() * 6,
                             4.5 + rnd() * 2.5, _pick(rnd, tons_fleurs), 0.85))
    # Cheminees et fumee.
    chem: List[str] = []
    for cx, cy in ((200, 648), (330, 634), (720, 646), (880, 668)):
        chem.append(poly(((cx, cy), (cx + 22, cy), (cx + 22, cy - 34),
                          (cx, cy - 34)), "#9b7f6a", 0.95))
        chem.append(poly(((cx - 2, cy - 34), (cx + 24, cy - 34),
                          (cx + 24, cy - 40), (cx - 2, cy - 40)),
                         "#b09680", 0.95))
        for i in range(8):
            chem.append(blob(cx + 11 + (rnd() - 0.5) * 20 + i * 4,
                             cy - 48 - i * 10, 8 + i * 2.4, 5 + i * 1.4,
                             "#d8d8d4", 0.15 + rnd() * 0.09))
    # Texture des toits de zinc.
    zinc_g = ("#8b98a6", "#a0acb8", "#7f8c9a")
    zinc_d = ("#90a0ac", "#a4b0ba", "#84929e")
    for _ in range(60):
        chem.append(dab(120 + rnd() * 310, 636 + rnd() * 40,
                        -7 + (rnd() - 0.5) * 8, 18 + rnd() * 22,
                        6 + rnd() * 4, _pick(rnd, zinc_g), 0.4))
        chem.append(dab(660 + rnd() * 300, 650 + rnd() * 40,
                        7 + (rnd() - 0.5) * 8, 18 + rnd() * 22,
                        6 + rnd() * 4, _pick(rnd, zinc_d), 0.4))

    # --- ESCALIER vers la basilique ---------------------------------------
    escalier: List[str] = []
    for i in range(17):
        t = i / 16
        y = 828 - t * 180
        demi = 54 - 32 * t
        escalier.append(dab(540, y, 0, demi * 2, 6.5 - 2.5 * t + 3,
                            "#c6c2b1" if t < 0.5 else "#cfcbbc", 0.85))
        escalier.append(dab(540, y - 4, 0, demi * 1.9, 2.5, "#a8a494", 0.5))
    escalier.append(poly(((468, 832), (494, 648), (504, 648), (492, 832)),
                         "#b5ad98", 0.95))
    escalier.append(poly(((612, 832), (586, 648), (576, 648), (588, 832)),
                         "#aca58f", 0.95))
    tons_pots = ("#87906f", "#9aa080", "#76815f")
    for px, py in ((482, 700), (598, 700), (476, 770), (604, 770)):
        for _ in range(8):
            escalier.append(dab(px + (rnd() - 0.5) * 16, py + (rnd() - 0.5) * 14,
                                (rnd() - 0.5) * 60, 8 + rnd() * 10,
                                5 + rnd() * 4, _pick(rnd, tons_pots), 0.7))

    # --- PAVES de la rue, en perspective ----------------------------------
    paves: List[str] = []
    tons_paves = ("#94989f", "#9ea2a9", "#a8abb1", "#8d9199", "#a39d92", "#98948b")
    tons_loin = ("#adb0b5", "#b4b6ba")
    y = 836.0
    while y < 1590:
        t = (y - 828) / 732
        gauche = 497 + (212 - 497) * t
        droite = 595 + (878 - 595) * t
        rx = 8 + 20 * t
        ry = 2.6 + 6.5 * t
        x = gauche + rx * rnd()
        while x < droite:
            c = _pick(rnd, tons_loin) if t < 0.25 else _pick(rnd, tons_paves)
            paves.append(blob(x + (rnd() - 0.5) * 3, y + (rnd() - 0.5) * 2,
                              rx * (0.85 + rnd() * 0.35),
                              ry * (0.85 + rnd() * 0.3), c,
                              0.35 + rnd() * 0.3 + 0.15 * t))
            if rnd() < 0.3 and t > 0.3:
                paves.append(dab(x, y - ry * 0.8, (rnd() - 0.5) * 16, rx * 1.15,
                                 2.2 + 2.8 * t, "#c3c5c9", 0.35))
            x += rx * 1.75 + rnd() * rx * 0.35
        y += ry * 1.9 + 2
    # Reflet mouille au centre, ornieres de charrette.
    paves.append('<path d="M540,840 C540,1050 545,1300 555,1560" '
                 'stroke="#c9cbce" stroke-width="40" fill="none" '
                 'opacity="0.12" stroke-linecap="round"/>')
    for d in ("M520,845 C500,1000 420,1300 330,1560",
              "M572,845 C600,1000 690,1300 770,1560"):
        paves.append(f'<path d="{d}" stroke="#7b7f88" stroke-width="14" '
                     f'fill="none" opacity="0.22" stroke-linecap="round"/>')

    # --- TALUS et rangs de vigne ------------------------------------------
    talus: List[str] = []
    tons_terre = ("#837e58", "#8f8a62", "#75714c", "#99936c", "#89845e")
    for _ in range(440):
        x = 660 + rnd() * 420
        y = 930 + rnd() * 630
        talus.append(dab(x, y, -12 + (rnd() - 0.5) * 24, 14 + rnd() * 26,
                         7 + rnd() * 7, _pick(rnd, tons_terre),
                         0.35 + rnd() * 0.35))
    vignes: List[str] = []
    ors = ("#c9a24b", "#d8b45e", "#b8953f", "#e0c070")
    verts = ("#8a8f4f", "#6f7d46", "#a3a05a", "#7c8a50")
    for x1, y1, x2, y2, sc in ((700, 1122, 1080, 1028, 0.6),
                               (716, 1244, 1080, 1148, 0.78),
                               (756, 1388, 1080, 1282, 0.92),
                               (816, 1532, 1080, 1428, 1.05)):
        vignes.append(dab((x1 + x2) / 2, (y1 + y2) / 2 + 12 * sc, -13,
                          (x2 - x1) * 0.98, 9 * sc, "#5f5c40", 0.35))
        n = int((x2 - x1) / 46)
        for i in range(n + 1):
            t = i / n
            x = x1 + (x2 - x1) * t
            y = y1 + (y2 - y1) * t
            vignes.append(dab(x, y - 12 * sc, 88 + (rnd() - 0.5) * 10, 28 * sc,
                              4.5 * sc, "#5c4a34", 0.85))
            nf = 10 + int(rnd() * 6)
            for _ in range(nf):
                fx = x + (rnd() - 0.5) * 44 * sc
                fy = y - 20 * sc - rnd() * 28 * sc
                c = _pick(rnd, ors) if rnd() < 0.62 else _pick(rnd, verts)
                vignes.append(dab(fx, fy, (rnd() - 0.5) * 70,
                                  10 + rnd() * 16 * sc, 7 + rnd() * 6 * sc, c,
                                  0.6 + rnd() * 0.3))
            if rnd() < 0.3:
                vignes.append(blob(x + (rnd() - 0.5) * 16, y - 14 * sc,
                                   4.5 * sc, 6 * sc, "#5b4a63", 0.75))

    # --- TROTTOIR de gauche -----------------------------------------------
    trottoir: List[str] = []
    tons_trottoir = ("#aaa397", "#b3ac9c", "#9c9686", "#c0b8a6", "#948e7e")
    for _ in range(170):
        t = rnd()
        y = 840 + t * 710
        x_c = 482 - (482 - 172) * t
        trottoir.append(dab(x_c + (rnd() - 0.5) * 56 * (0.4 + t), y,
                            (rnd() - 0.5) * 20, 10 + rnd() * 20, 6 + rnd() * 6,
                            _pick(rnd, tons_trottoir), 0.3 + rnd() * 0.3))
    trottoir.append('<path d="M497,830 L212,1560" stroke="#c6c0b0" '
                    'stroke-width="7" opacity="0.6" stroke-linecap="round" '
                    'fill="none"/>')

    # --- CABARET : texture, store, devanture ------------------------------
    cab_tex: List[str] = []
    tons_cabaret = ("#b5a488", "#c9b89c", "#ab9a7e", "#d2c2a4", "#a08f74")
    for _ in range(280):
        cab_tex.append(dab(rnd() * 300, 870 + rnd() * 690,
                           90 + (rnd() - 0.5) * 14, 18 + rnd() * 30,
                           8 + rnd() * 6, _pick(rnd, tons_cabaret),
                           0.28 + rnd() * 0.28))
    for i in range(7):
        cab_tex.append(dab(150, 920 + i * 92, 0, 300, 2.5, "#98876c", 0.4))
    store: List[str] = ['<path d="M6,1042 L298,1042 C308,1078 314,1100 '
                        '318,1118 L-12,1118 C-8,1100 -2,1078 6,1042 Z" '
                        'fill="#9c4a3d"/>']
    for i in range(7):
        xt = 20 + i * 42
        xb = 4 + i * 46
        store.append(poly(((xt, 1042), (xt + 14, 1042), (xb + 15, 1118),
                           (xb, 1118)), "#8b4136", 0.7))
    tons_toile = ("#a75a4a", "#93463b", "#b06552", "#8a3f35")
    for _ in range(90):
        store.append(dab(rnd() * 306, 1048 + rnd() * 66, (rnd() - 0.5) * 7,
                         14 + rnd() * 20, 6 + rnd() * 4,
                         _pick(rnd, tons_toile), 0.3 + rnd() * 0.25))
    store.append(dab(152, 1046, 0, 290, 6, "#c07a64", 0.5))
    store.append(dab(152, 1060, 0, 286, 4, "#b3685a", 0.35))
    for i in range(13):
        x = -12 + i * 27.5 + 13.75
        store.append(f'<path d="M{x - 13.75},1116 Q{x},1132 {x + 13.75},1116 '
                     f'L{x + 13.75},1114 L{x - 13.75},1114 Z" fill="#8b4136"/>')
    store.append(poly(((0, 1118), (318, 1118), (318, 1142), (0, 1142)),
                      "#5f4c38", 0.3))

    devanture: List[str] = []
    tons_chaleur = ("#f0cc88", "#d9a95e", "#c99a52", "#f4d89a", "#e8c07a")

    def _vitrine(x: float) -> None:
        """Vitrine chaude du cafe : lueur, lampe, silhouettes attablees,
        brise-bise a mi-hauteur."""
        devanture.append(poly(((x, 1170), (x + 96, 1170), (x + 96, 1340),
                               (x, 1340)), "#54402e", 0.95))
        devanture.append(poly(((x + 7, 1178), (x + 89, 1178), (x + 89, 1332),
                               (x + 7, 1332)), "#e2ba74", 0.92))
        for _ in range(20):
            devanture.append(dab(x + 12 + rnd() * 72, 1184 + rnd() * 100,
                                 (rnd() - 0.5) * 40, 10 + rnd() * 18,
                                 6 + rnd() * 5, _pick(rnd, tons_chaleur), 0.4))
        devanture.append(blob(x + 48, 1196, 16, 8, "#f7e0a8", 0.8))
        devanture.append(dab(x + 48, 1184, 90, 16, 2.5, "#7a5f42", 0.8))
        sx = x + 24 + rnd() * 14
        sx2 = x + 64 + rnd() * 10
        devanture.append(blob(sx, 1266, 13, 10, "#5d452e", 0.9))
        devanture.append(blob(sx, 1252, 7, 8, "#5d452e", 0.9))
        devanture.append(blob(sx2, 1268, 12, 9, "#66503a", 0.85))
        devanture.append(blob(sx2, 1255, 6.5, 7.5, "#66503a", 0.85))
        devanture.append(poly(((x + 7, 1282), (x + 89, 1282), (x + 89, 1332),
                               (x + 7, 1332)), "#c8a06a", 0.9))
        devanture.append(dab(x + 48, 1282, 0, 84, 3.5, "#54402e", 0.9))
        for i in range(7):
            devanture.append(dab(x + 13 + i * 12, 1306, 90, 44, 7,
                                 "#bd9560", 0.6))

    _vitrine(24)
    _vitrine(150)
    devanture.append(poly(((252, 1560), (252, 1330), (298, 1330), (298, 1560)),
                          "#4c3b2c"))
    devanture.append(poly(((260, 1345), (290, 1345), (290, 1460), (260, 1460)),
                          "#6a5540", 0.9))
    devanture.append(blob(286, 1470, 3.5, 3.5, "#c9a45c", 0.9))
    devanture.append(poly(((0, 1544), (300, 1544), (300, 1560), (0, 1560)),
                          "#6d5a44", 0.3))

    # --- FIGURANTS : ombres des peeps, pigeons ----------------------------
    figures: List[str] = []
    for sx, sy, sw in ((730, 1548, 55), (333, 1424, 42), (545, 1152, 28),
                       (588, 1150, 26), (905, 1248, 25), (968, 1202, 22)):
        figures.append(blob(sx, sy + 3, sw, sw * 0.22, "#4a463e", 0.35))
    for px, py in ((452, 1330), (478, 1344)):
        figures.append(blob(px, py, 7, 5, "#8d8f95", 0.95))
        figures.append(blob(px + 6, py - 4, 3.2, 3, "#7c7e86", 0.95))
        figures.append(dab(px - 5, py + 1, -25, 8, 2.5, "#75777f", 0.9))

    # --- VOILES d'atmosphere ----------------------------------------------
    atmo = "".join((
        blob(540, 470, 330, 210, "#dfe3e8", 0.04),
        blob(540, 640, 480, 90, "#dfe0da", 0.08),
        blob(60, 1500, 320, 260, "#4e483c", 0.05),
        blob(1040, 1520, 300, 240, "#4e483c", 0.05),
        blob(540, 1240, 700, 420, "#e8d0a0", 0.05),
    ))

    def _j(morceaux: List[str]) -> str:
        return "\n".join(morceaux)

    corps = f'''{_MONTMARTRE_DEFS}
<g clip-path="url(#clipIllus)">
  <rect x="0" y="0" width="1080" height="1050" fill="url(#skyG)"/>
  <g clip-path="url(#clipSky)">
{_j(ciel)}
  </g>
  <g>
{_j(crete)}
  </g>
  {_MONTMARTRE_SACRE}
  <g>
{_j(verdure)}
  </g>
  <g>
{_j(toits)}
  </g>
  <g>
    <path d="M120,700 L430,660 L430,1000 L120,1010 Z" fill="#d3c9b4"/>
    <path d="M112,702 L430,660 L430,625 L146,662 Z" fill="#93a0ae"/>
    <g clip-path="url(#clipBldL)">
{_j(tex_g)}
    </g>
    <g>
{_j(fen_g)}
    </g>
    <path d="M650,660 L955,705 L955,1020 L650,1015 Z" fill="#d8cfba"/>
    <path d="M650,660 L963,703 L963,668 L680,626 Z" fill="#9aa6b2"/>
    <g clip-path="url(#clipBldR)">
{_j(tex_d)}
    </g>
    <g>
{_j(fen_d)}
    </g>
    <g>
{_j(chem)}
    </g>
  </g>
  <g>
{_j(escalier)}
  </g>
  <path d="M497,828 L595,828 L878,1560 L212,1560 Z" fill="url(#streetG)"/>
  <g clip-path="url(#clipStreet)">
{_j(paves)}
  </g>
  <path d="M660,1015 L1080,925 L1080,1560 L872,1560 Z" fill="url(#talusG)"/>
  <g clip-path="url(#clipTalus)">
{_j(talus)}
  </g>
  <path d="M655,1010 L1080,919 L1080,941 L661,1031 Z" fill="#b3ab94"/>
  <path d="M655,1024 L1080,933 L1080,941 L661,1031 Z" fill="#8f8872" opacity="0.8"/>
  <g>
{_j(vignes)}
  </g>
  <path d="M497,828 L212,1560 L128,1560 L468,830 Z" fill="#a49e90"/>
  <g>
{_j(trottoir)}
  </g>
  <g>
    <rect x="0" y="860" width="300" height="700" fill="#bfae92"/>
    <g clip-path="url(#clipCab)">
{_j(cab_tex)}
    </g>
    <rect x="0" y="860" width="300" height="24" fill="#a6947a"/>
    <rect x="0" y="884" width="300" height="7" fill="#8f7f68"/>
    <rect x="14" y="936" width="276" height="84" rx="6" fill="#443426"/>
    <rect x="20" y="942" width="264" height="72" rx="4" fill="#503e2d"/>
    <text x="152" y="996" font-family="{SERIF}" font-size="44" letter-spacing="9" fill="#d9b96a" text-anchor="middle">CABARET</text>
    <g>
{_j(store)}
    </g>
    <g>
{_j(devanture)}
    </g>
    <ellipse cx="190" cy="1520" rx="240" ry="60" fill="#e8c47a" opacity="0.10"/>
  </g>
  {_MONTMARTRE_MORRIS}
  {_MONTMARTRE_LAMP}
  <g>
{_j(figures)}
  </g>
  <g>
{_montmartre_peeps()}
  </g>
  <g>{atmo}</g>
</g>
{cartel_impressionniste(anecdote, sous_titre)}'''
    return _svg(corps)
