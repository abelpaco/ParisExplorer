"""Gabarits SVG « ligne claire » : portraits, pictogrammes et cartes BD.

POURQUOI CE MODULE EXISTE
-------------------------
Les cartes photo racontent des LIEUX. Pour raconter des PERSONNES — naissances
de Parisiens celebres, anniversaires d'evenements — la photo est un piege :
portraits sous droits, gravures aux licences floues, sujets proteges. Le dessin
vectoriel original supprime le probleme a la racine : zero credit, zero licence,
et une identite visuelle que personne d'autre n'a.

Le style retenu est la « ligne claire » de l'ecole franco-belge : aplats de
couleurs franches, contour noir d'epaisseur constante, pas d'ombrage. C'est le
style le PLUS adapte au SVG — et le nommer « ligne claire » plutot que « style
Herge » n'est pas un detail : le style est libre, la marque ne l'est pas, et
l'ayant droit d'Herge est procedurier.

CE QUE CE MODULE FAIT, ET NE FAIT PAS
-------------------------------------
Il compose des chaines SVG deterministes : memes entrees, memes pixels. Il ne
rasterise pas (voir ``bd_cards``) et ne connait pas les sujets YAML (voir
``bd_topics``). Le vocabulaire des styles — coiffures, costumes, pictogrammes —
vit ICI et nulle part ailleurs : les validations de ``bd_topics`` s'y referent.

LE PORTRAIT EVOQUE, IL NE PHOTOGRAPHIE PAS
------------------------------------------
Un portrait parametrable (coiffure, pilosite, costume, accessoires) donne un
personnage RECONNAISSABLE par ses attributs — la perruque de Moliere, la robe
noire de Piaf — pas un sosie. C'est assume : c'est exactement ce que fait la
caricature de presse, et c'est ce qui reste fabricable en vectoriel a la chaine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Canevas et palette
# ---------------------------------------------------------------------------

WIDTH, HEIGHT = 1080, 1920

INK = "#1a1a1a"
CREAM = "#f6ead2"          # fond papier
MEDALLION = "#f9e7bd"      # fond du medaillon
RED = "#c0392b"            # rideau et accent par defaut
RED_DARK = "#8e2820"       # plis du rideau
GOLD = "#e9b949"           # galon, boutons, etoiles
SKIN_DEFAULT = "#f9d1a0"
BROWN_TEXT = "#5d4037"
GREY_TEXT = "#333333"

# Piles de polices : DejaVu d'abord parce que c'est la police du VPS, donc de
# la PRODUCTION — meme logique que FONT_CANDIDATES dans visual_cards. Sur un
# poste Windows sans DejaVu, Georgia et Arial prennent le relais.
SERIF = "'DejaVu Serif', Georgia, 'Times New Roman', serif"
SANS = "'DejaVu Sans', Arial, sans-serif"

# Vocabulaires. Ce sont les CLES admises dans les YAML de content/bd/ ;
# bd_topics les valide contre ces ensembles.
HAIR_STYLES = ("perruque", "mi-longs", "courts", "chignon", "chauve")
PILOSITES = ("moustache-fine", "moustache-epaisse", "barbe", "bouc", "mouche",
             "favoris")
COSTUMES = ("habit-ancien", "redingote", "robe", "moderne", "uniforme")
ACCESSOIRES = ("lunettes", "beret", "noeud", "boucles-oreilles")

# Facteurs de largeur moyenne d'un caractere, en fraction de la taille de
# police. Mesures sur DejaVu (la police de production) et volontairement un
# peu LARGES : mieux vaut une ligne coupee trop tot qu'un mot qui deborde.
_W_SANS = 0.56
_W_SANS_BOLD = 0.60
_W_SERIF_CAPS = 0.80  # nom en capitales serif gras, interlettrage compris


class StyleError(ValueError):
    """Parametre de style inconnu : coiffure, costume ou pictogramme."""


@dataclass
class Portrait:
    """Description d'un portrait ligne claire.

    Chaque champ est un choix dans un vocabulaire ferme (voir les constantes du
    module) : c'est ce qui rend le rendu previsible. Un attribut manquant a un
    defaut neutre — le portrait le plus generique possible.
    """

    cheveux: str = "courts"
    couleur_cheveux: str = "#3a2a1a"
    pilosite: List[str] = field(default_factory=list)
    costume: str = "moderne"
    couleur_costume: str = "#2f4b6b"
    teint: str = SKIN_DEFAULT
    accessoires: List[str] = field(default_factory=list)

    def check(self) -> None:
        if self.cheveux not in HAIR_STYLES:
            raise StyleError(
                f"Coiffure inconnue : {self.cheveux!r}. Connues : {', '.join(HAIR_STYLES)}"
            )
        for p in self.pilosite:
            if p not in PILOSITES:
                raise StyleError(
                    f"Pilosite inconnue : {p!r}. Connues : {', '.join(PILOSITES)}"
                )
        if self.costume not in COSTUMES:
            raise StyleError(
                f"Costume inconnu : {self.costume!r}. Connus : {', '.join(COSTUMES)}"
            )
        for a in self.accessoires:
            if a not in ACCESSOIRES:
                raise StyleError(
                    f"Accessoire inconnu : {a!r}. Connus : {', '.join(ACCESSOIRES)}"
                )


# ---------------------------------------------------------------------------
# Petits utilitaires texte
# ---------------------------------------------------------------------------


def esc(text: str) -> str:
    """Echappe un texte pour l'inserer dans du SVG."""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def wrap_text(text: str, size: int, max_width: float, factor: float = _W_SANS) -> List[str]:
    """Coupe ``text`` en lignes estimees tenir dans ``max_width`` pixels.

    SVG ne sait pas replier le texte : on le fait ici, avec une LARGEUR
    ESTIMEE (pas de moteur de fontes sous la main). Le facteur est calibre
    large — voir sa definition — pour que l'estimation echoue du bon cote.
    """
    per_char = size * factor
    max_chars = max(8, int(max_width / per_char))
    words = str(text).split()
    lines: List[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if len(trial) <= max_chars or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def fit_text(
    text: str, box: Tuple[float, float], start: int, floor: int,
    factor: float = _W_SANS, line_height: float = 1.38,
) -> Tuple[int, List[str]]:
    """Plus grande taille qui fait tenir ``text`` dans ``box`` (largeur, hauteur).

    Meme demarche que ``_fit_text`` de visual_cards : on part du grand et on
    descend, jamais l'inverse.
    """
    max_w, max_h = box
    size = start
    while size > floor:
        lines = wrap_text(text, size, max_w, factor)
        if len(lines) * size * line_height <= max_h:
            return size, lines
        size -= 2
    return floor, wrap_text(text, floor, max_w, factor)


def name_font_size(name: str, max_width: float = 900.0, cap: int = 150) -> int:
    """Taille du grand nom en capitales, bornee par la largeur de la carte."""
    length = max(1, len(name))
    return max(40, min(cap, int(max_width / (length * _W_SERIF_CAPS))))


# ---------------------------------------------------------------------------
# Elements de decor communs
# ---------------------------------------------------------------------------


def _curtain(depth: float = 1.0) -> str:
    """Rideau de theatre en haut de carte. ``depth`` module sa hauteur."""
    d = depth
    return f'''
  <path d="M0,0 L1080,0 L1080,{130*d:.0f} Q900,{255*d:.0f} 720,{140*d:.0f} Q540,{268*d:.0f} 360,{140*d:.0f} Q180,{255*d:.0f} 0,{130*d:.0f} Z"
        fill="{RED}" stroke="{INK}" stroke-width="8" stroke-linejoin="round"/>
  <path d="M180,{20*d:.0f} Q170,{80*d:.0f} 150,{125*d:.0f}" stroke="{RED_DARK}" stroke-width="7" fill="none" stroke-linecap="round"/>
  <path d="M400,{25*d:.0f} Q395,{90*d:.0f} 380,{150*d:.0f}" stroke="{RED_DARK}" stroke-width="7" fill="none" stroke-linecap="round"/>
  <path d="M540,{30*d:.0f} Q540,{110*d:.0f} 540,{190*d:.0f}" stroke="{RED_DARK}" stroke-width="7" fill="none" stroke-linecap="round"/>
  <path d="M680,{25*d:.0f} Q685,{90*d:.0f} 700,{150*d:.0f}" stroke="{RED_DARK}" stroke-width="7" fill="none" stroke-linecap="round"/>
  <path d="M900,{20*d:.0f} Q910,{80*d:.0f} 930,{125*d:.0f}" stroke="{RED_DARK}" stroke-width="7" fill="none" stroke-linecap="round"/>
  <path d="M0,{148*d:.0f} Q180,{272*d:.0f} 360,{158*d:.0f} Q540,{286*d:.0f} 720,{158*d:.0f} Q900,{272*d:.0f} 1080,{148*d:.0f}"
        fill="none" stroke="{GOLD}" stroke-width="18" stroke-linecap="round"/>'''


def _brand(y: int, accent: str) -> str:
    return (f'<text x="540" y="{y}" text-anchor="middle" font-family="{SANS}" '
            f'font-size="30" letter-spacing="10" fill="{accent}" '
            f'font-weight="bold">PARIS EXPLORER</text>')


def _svg(body: str) -> str:
    return (f'<svg viewBox="0 0 {WIDTH} {HEIGHT}" xmlns="http://www.w3.org/2000/svg">\n'
            f'  <rect width="{WIDTH}" height="{HEIGHT}" fill="{CREAM}"/>{body}\n</svg>\n')


# ---------------------------------------------------------------------------
# Portrait : couches successives dans le medaillon
# ---------------------------------------------------------------------------
#
# Le repere est FIXE : medaillon centre en (540, 870), rayon 400, visage centre
# en (540, 802). Toutes les geometries ci-dessous sont ecrites dans ce repere
# et validees a l'oeil sur un rendu — les re-parametrer par variable rendrait
# chaque forme illisible sans rien apporter : on deplace le portrait entier par
# ``transform`` quand une carte le veut ailleurs ou plus petit.

_S = 'stroke-linecap="round" stroke-linejoin="round"'


def _hair_back(p: Portrait) -> str:
    c, k = p.couleur_cheveux, INK
    if p.cheveux == "perruque":
        return f'''
    <path d="M540,538 C455,540 370,585 338,665 Q300,705 314,762 Q276,808 300,868
             Q270,922 302,978 Q286,1038 336,1078 Q355,1112 425,1112 Q475,1118 505,1088
             L505,770 Q540,750 575,770 L575,1088 Q605,1118 655,1112 Q725,1112 744,1078
             Q794,1038 778,978 Q810,922 780,868 Q804,808 766,762 Q780,705 742,665
             C710,585 625,540 540,538 Z" fill="{c}" stroke="{k}" stroke-width="9"/>
    <path d="M352,700 q-26,42 -2,84" stroke="{k}" stroke-width="5" fill="none"/>
    <path d="M330,880 q-22,44 4,86" stroke="{k}" stroke-width="5" fill="none"/>
    <path d="M728,700 q26,42 2,84" stroke="{k}" stroke-width="5" fill="none"/>
    <path d="M750,880 q22,44 -4,86" stroke="{k}" stroke-width="5" fill="none"/>
    <path d="M400,1010 q-18,38 8,70" stroke="{k}" stroke-width="5" fill="none"/>
    <path d="M680,1010 q18,38 -8,70" stroke="{k}" stroke-width="5" fill="none"/>'''
    if p.cheveux == "mi-longs":
        return f'''
    <path d="M540,545 C450,548 366,600 344,690 C325,790 328,930 356,1030
             Q374,1078 440,1078 L470,930 Q462,760 505,705 L575,705
             Q618,760 610,930 L640,1078 Q706,1078 724,1030
             C752,930 755,790 736,690 C714,600 630,548 540,545 Z"
          fill="{c}" stroke="{k}" stroke-width="9"/>
    <path d="M380,760 q-14,90 6,180" stroke="{k}" stroke-width="5" fill="none"/>
    <path d="M700,760 q14,90 -6,180" stroke="{k}" stroke-width="5" fill="none"/>'''
    if p.cheveux == "chignon":
        return f'''
    <circle cx="540" cy="528" r="62" fill="{c}" stroke="{k}" stroke-width="8"/>
    <path d="M505,540 q35,-26 70,0" stroke="{k}" stroke-width="5" fill="none"/>'''
    if p.cheveux == "chauve":
        return f'''
    <ellipse cx="402" cy="810" rx="42" ry="62" fill="{c}" stroke="{k}" stroke-width="8"/>
    <ellipse cx="678" cy="810" rx="42" ry="62" fill="{c}" stroke="{k}" stroke-width="8"/>'''
    return ""  # courts : tout est dans la couche avant


def _hair_front(p: Portrait) -> str:
    c, k = p.couleur_cheveux, INK
    if p.cheveux == "perruque":
        return f'''
    <path d="M398,662 Q540,588 682,662 Q655,702 618,682 Q578,706 540,688 Q502,706 462,682 Q425,702 398,662 Z"
          fill="{c}" stroke="{k}" stroke-width="7"/>'''
    if p.cheveux == "mi-longs":
        return f'''
    <path d="M402,668 Q540,596 678,668 Q620,692 540,684 Q460,692 402,668 Z"
          fill="{c}" stroke="{k}" stroke-width="7"/>'''
    if p.cheveux == "courts":
        return f'''
    <path d="M378,712 C370,592 452,536 540,536 C628,536 710,592 702,712
             Q694,652 652,648 Q596,606 540,612 Q484,606 428,648 Q386,652 378,712 Z"
          fill="{c}" stroke="{k}" stroke-width="8"/>'''
    if p.cheveux == "chignon":
        return f'''
    <path d="M382,700 C376,596 456,540 540,540 C624,540 704,596 698,700
             Q640,640 540,636 Q440,640 382,700 Z"
          fill="{c}" stroke="{k}" stroke-width="8"/>
    <path d="M395,690 Q430,760 415,830" stroke="{k}" stroke-width="6" fill="none"/>
    <path d="M685,690 Q650,760 665,830" stroke="{k}" stroke-width="6" fill="none"/>'''
    return ""


def _ears_visible(p: Portrait) -> bool:
    return p.cheveux in ("courts", "chignon", "chauve")


def _costume(p: Portrait) -> str:
    c, k, skin = p.couleur_costume, INK, p.teint
    coat = (f'<path d="M170,1420 C250,1130 400,1052 540,1052 '
            f'C680,1052 830,1130 910,1420 L170,1420 Z" '
            f'fill="{c}" stroke="{k}" stroke-width="9"/>')
    if p.costume == "habit-ancien":
        return f'''
    {coat}
    <path d="M540,1180 L540,1300" stroke="{k}" stroke-width="6"/>
    <circle cx="540" cy="1225" r="13" fill="{GOLD}" stroke="{k}" stroke-width="5"/>
    <circle cx="540" cy="1290" r="13" fill="{GOLD}" stroke="{k}" stroke-width="5"/>
    <path d="M472,1028 L608,1028 L622,1165 Q540,1195 458,1165 Z"
          fill="#ffffff" stroke="{k}" stroke-width="7"/>
    <path d="M540,1028 L540,1180" stroke="{k}" stroke-width="5"/>'''
    if p.costume == "redingote":
        return f'''
    {coat}
    <path d="M540,1060 L462,1150 L540,1268 L618,1150 Z" fill="#ffffff" stroke="{k}" stroke-width="7"/>
    <path d="M462,1150 L505,1075 L540,1128 L575,1075 L618,1150" fill="none" stroke="{k}" stroke-width="6"/>
    <path d="M512,1120 Q540,1098 568,1120 Q540,1150 512,1120 Z" fill="#ffffff" stroke="{k}" stroke-width="6"/>'''
    if p.costume == "robe":
        return f'''
    <path d="M170,1420 C250,1140 390,1058 540,1058 C690,1058 830,1140 910,1420 L170,1420 Z"
          fill="{c}" stroke="{k}" stroke-width="9"/>
    <path d="M448,1062 Q540,1168 632,1062 L632,1062 Q540,1120 448,1062 Z"
          fill="{skin}" stroke="{k}" stroke-width="7"/>
    <circle cx="484" cy="1104" r="9" fill="{GOLD}" stroke="{k}" stroke-width="4"/>
    <circle cx="512" cy="1122" r="9" fill="{GOLD}" stroke="{k}" stroke-width="4"/>
    <circle cx="540" cy="1128" r="9" fill="{GOLD}" stroke="{k}" stroke-width="4"/>
    <circle cx="568" cy="1122" r="9" fill="{GOLD}" stroke="{k}" stroke-width="4"/>
    <circle cx="596" cy="1104" r="9" fill="{GOLD}" stroke="{k}" stroke-width="4"/>'''
    if p.costume == "moderne":
        return f'''
    {coat}
    <path d="M540,1058 L468,1146 L540,1250 L612,1146 Z" fill="#ffffff" stroke="{k}" stroke-width="7"/>
    <path d="M468,1146 L420,1090 M612,1146 L660,1090" stroke="{k}" stroke-width="6"/>
    <path d="M540,1128 L521,1160 L533,1300 L540,1320 L547,1300 L559,1160 Z"
          fill="{RED}" stroke="{k}" stroke-width="6"/>'''
    if p.costume == "uniforme":
        return f'''
    {coat}
    <path d="M540,1120 L540,1400" stroke="{k}" stroke-width="6"/>
    <circle cx="540" cy="1180" r="12" fill="{GOLD}" stroke="{k}" stroke-width="5"/>
    <circle cx="540" cy="1250" r="12" fill="{GOLD}" stroke="{k}" stroke-width="5"/>
    <circle cx="540" cy="1320" r="12" fill="{GOLD}" stroke="{k}" stroke-width="5"/>
    <rect x="300" y="1090" width="130" height="42" rx="10" fill="{GOLD}" stroke="{k}" stroke-width="6"/>
    <rect x="650" y="1090" width="130" height="42" rx="10" fill="{GOLD}" stroke="{k}" stroke-width="6"/>
    <path d="M310,1132 l0,26 M336,1132 l0,26 M362,1132 l0,26 M388,1132 l0,26 M414,1132 l0,26"
          stroke="{k}" stroke-width="5"/>
    <path d="M666,1132 l0,26 M692,1132 l0,26 M718,1132 l0,26 M744,1132 l0,26 M770,1132 l0,26"
          stroke="{k}" stroke-width="5"/>
    <path d="M430,1210 l12,24 26,4 -19,18 5,26 -24,-13 -24,13 5,-26 -19,-18 26,-4 Z"
          fill="{GOLD}" stroke="{k}" stroke-width="4"/>'''
    return coat


def _facial_hair(p: Portrait) -> str:
    parts: List[str] = []
    c, k, skin = p.couleur_cheveux, INK, p.teint
    kinds = set(p.pilosite)
    if "barbe" in kinds:
        parts.append(f'''
    <path d="M398,820 Q414,1030 540,1052 Q666,1030 682,820
             Q650,884 604,894 Q574,952 540,952 Q506,952 476,894 Q430,884 398,820 Z"
          fill="{c}" stroke="{k}" stroke-width="7"/>
    <ellipse cx="540" cy="932" rx="58" ry="34" fill="{skin}"/>''')
    if "moustache-fine" in kinds:
        parts.append(f'''
    <path d="M533,893 Q508,882 484,890" stroke="{k}" stroke-width="7" fill="none"/>
    <path d="M547,893 Q572,882 596,890" stroke="{k}" stroke-width="7" fill="none"/>''')
    if "moustache-epaisse" in kinds:
        parts.append(f'''
    <path d="M540,886 Q492,872 458,896 Q494,916 538,906 L542,906 Q586,916 622,896 Q588,872 540,886 Z"
          fill="{c}" stroke="{k}" stroke-width="6"/>''')
    if "bouc" in kinds:
        parts.append(f'''
    <path d="M506,972 Q540,1046 574,972 Q540,994 506,972 Z"
          fill="{c}" stroke="{k}" stroke-width="6"/>''')
    if "mouche" in kinds:
        parts.append(f'<path d="M532,974 Q540,990 548,974 Q540,981 532,974 Z" fill="{k}"/>')
    if "favoris" in kinds:
        parts.append(f'''
    <path d="M406,750 L442,762 L436,900 L410,878 Z" fill="{c}" stroke="{k}" stroke-width="6"/>
    <path d="M674,750 L638,762 L644,900 L670,878 Z" fill="{c}" stroke="{k}" stroke-width="6"/>''')
    return "".join(parts)


def _accessories(p: Portrait) -> str:
    parts: List[str] = []
    k = INK
    kinds = set(p.accessoires)
    if "lunettes" in kinds:
        parts.append(f'''
    <circle cx="492" cy="784" r="40" fill="none" stroke="{k}" stroke-width="7"/>
    <circle cx="588" cy="784" r="40" fill="none" stroke="{k}" stroke-width="7"/>
    <path d="M532,784 Q540,776 548,784" stroke="{k}" stroke-width="7" fill="none"/>
    <path d="M452,784 L410,772 M628,784 L670,772" stroke="{k}" stroke-width="7"/>''')
    if "beret" in kinds:
        parts.append(f'''
    <g transform="rotate(-6 540 596)">
      <ellipse cx="540" cy="596" rx="196" ry="58" fill="{p.couleur_costume}" stroke="{k}" stroke-width="8"/>
      <circle cx="540" cy="538" r="10" fill="{k}"/>
    </g>''')
    if "noeud" in kinds:
        parts.append(f'''
    <path d="M540,1072 L470,1040 L470,1104 Z" fill="{RED}" stroke="{k}" stroke-width="6"/>
    <path d="M540,1072 L610,1040 L610,1104 Z" fill="{RED}" stroke="{k}" stroke-width="6"/>
    <circle cx="540" cy="1072" r="16" fill="{RED}" stroke="{k}" stroke-width="6"/>''')
    if "boucles-oreilles" in kinds and _ears_visible(p):
        parts.append(f'''
    <circle cx="396" cy="872" r="11" fill="{GOLD}" stroke="{k}" stroke-width="4"/>
    <circle cx="684" cy="872" r="11" fill="{GOLD}" stroke="{k}" stroke-width="4"/>''')
    return "".join(parts)


def portrait_group(p: Portrait) -> str:
    """Le portrait complet, couche par couche, dans le repere canonique.

    L'ORDRE des couches est la seule subtilite : costume, cou, cheveux
    arriere, oreilles, visage, cheveux avant, traits, pilosite, accessoires.
    Le visage RECOUVRE la masse des cheveux ; la frange recouvre le visage.
    """
    p.check()
    skin, k = p.teint, INK
    ears = ""
    if _ears_visible(p):
        ears = f'''
    <ellipse cx="392" cy="812" rx="24" ry="38" fill="{skin}" stroke="{k}" stroke-width="7"/>
    <ellipse cx="688" cy="812" rx="24" ry="38" fill="{skin}" stroke="{k}" stroke-width="7"/>'''
    return f'''
  <g {_S}>
    {_costume(p)}
    <rect x="505" y="950" width="70" height="110" fill="{skin}" stroke="{k}" stroke-width="7"/>
    {_hair_back(p)}{ears}
    <ellipse cx="540" cy="802" rx="150" ry="192" fill="{skin}" stroke="{k}" stroke-width="9"/>
    {_hair_front(p)}
    <path d="M455,748 Q490,726 525,744" stroke="{k}" stroke-width="8" fill="none"/>
    <path d="M555,744 Q590,726 625,748" stroke="{k}" stroke-width="8" fill="none"/>
    <circle cx="492" cy="782" r="10" fill="{k}"/>
    <circle cx="588" cy="782" r="10" fill="{k}"/>
    <path d="M540,772 C550,802 558,832 560,855 Q560,872 540,872 Q532,868 527,861"
          stroke="{k}" stroke-width="7" fill="none"/>
    <path d="M497,930 Q540,950 583,930" stroke="{k}" stroke-width="7" fill="none"/>
    {_facial_hair(p)}
    {_accessories(p)}
  </g>'''


def portrait_medallion(p: Portrait, *, transform: str = "") -> str:
    """Medaillon complet : fond, portrait clippe au cercle, contour."""
    open_g = f'<g transform="{transform}">' if transform else "<g>"
    return f'''
  {open_g}
  <circle cx="540" cy="870" r="400" fill="{MEDALLION}"/>
  <clipPath id="medaillon"><circle cx="540" cy="870" r="400"/></clipPath>
  <g clip-path="url(#medaillon)">{portrait_group(p)}</g>
  <circle cx="540" cy="870" r="400" fill="none" stroke="{INK}" stroke-width="10"/>
  </g>'''


# ---------------------------------------------------------------------------
# Pictogrammes
# ---------------------------------------------------------------------------
#
# Chaque pictogramme est dessine centre en (0, 0) dans un rayon d'environ 150,
# au trait de 10. Il se place et se met a l'echelle par ``transform``.

ICONS: Dict[str, str] = {
    "plume": f'''
    <path d="M-24,150 C-64,60 -58,-60 44,-152 C92,-108 78,24 -2,112 Z"
          fill="#f5f0e6" stroke="{INK}" stroke-width="10" stroke-linejoin="round"/>
    <path d="M-24,150 C6,60 24,-40 44,-152" stroke="{INK}" stroke-width="8" fill="none"/>
    <path d="M-24,150 L-52,198" stroke="{INK}" stroke-width="10" stroke-linecap="round"/>''',
    "masque": f'''
    <path d="M-110,-118 Q0,-158 110,-118 Q132,20 62,110 Q0,152 -62,110 Q-132,20 -110,-118 Z"
          fill="{GOLD}" stroke="{INK}" stroke-width="10" stroke-linejoin="round"/>
    <path d="M-72,-30 Q-46,-52 -20,-30" stroke="{INK}" stroke-width="9" fill="none" stroke-linecap="round"/>
    <path d="M20,-30 Q46,-52 72,-30" stroke="{INK}" stroke-width="9" fill="none" stroke-linecap="round"/>
    <path d="M-62,28 Q0,96 62,28 Q0,62 -62,28 Z" fill="{INK}"/>''',
    "couronne": f'''
    <path d="M-124,58 L-124,-24 L-62,28 L0,-72 L62,28 L124,-24 L124,58 Z"
          fill="{GOLD}" stroke="{INK}" stroke-width="10" stroke-linejoin="round"/>
    <rect x="-124" y="58" width="248" height="40" rx="10" fill="{GOLD}" stroke="{INK}" stroke-width="10"/>
    <circle cx="-62" cy="78" r="11" fill="{RED}" stroke="{INK}" stroke-width="5"/>
    <circle cx="0" cy="78" r="11" fill="{RED}" stroke="{INK}" stroke-width="5"/>
    <circle cx="62" cy="78" r="11" fill="{RED}" stroke="{INK}" stroke-width="5"/>''',
    "livre": f'''
    <path d="M0,-78 C-40,-110 -108,-110 -140,-88 L-140,78 C-108,58 -40,58 0,88
             C40,58 108,58 140,78 L140,-88 C108,-110 40,-110 0,-78 Z"
          fill="#ffffff" stroke="{INK}" stroke-width="10" stroke-linejoin="round"/>
    <path d="M0,-78 L0,88" stroke="{INK}" stroke-width="8"/>
    <path d="M-112,-52 C-80,-64 -40,-62 -24,-52 M-112,-16 C-80,-28 -40,-26 -24,-16 M-112,20 C-80,8 -40,10 -24,20"
          stroke="{INK}" stroke-width="6" fill="none"/>
    <path d="M112,-52 C80,-64 40,-62 24,-52 M112,-16 C80,-28 40,-26 24,-16 M112,20 C80,8 40,10 24,20"
          stroke="{INK}" stroke-width="6" fill="none"/>''',
    "etoile": f'''
    <path d="M0,-150 L40,-52 L146,-46 L64,22 L92,124 L0,66 L-92,124 L-64,22 L-146,-46 L-40,-52 Z"
          fill="{GOLD}" stroke="{INK}" stroke-width="10" stroke-linejoin="round"/>''',
    "tour-eiffel": f'''
    <path d="M0,-168 L0,-128" stroke="{INK}" stroke-width="10" stroke-linecap="round"/>
    <path d="M-14,-128 L14,-128 C20,-30 34,60 112,152 M-14,-128 C-20,-30 -34,60 -112,152"
          fill="none" stroke="{INK}" stroke-width="10" stroke-linecap="round"/>
    <rect x="-48" y="-24" width="96" height="18" fill="{INK}"/>
    <rect x="-80" y="62" width="160" height="18" fill="{INK}"/>
    <path d="M-58,152 Q0,64 58,152" fill="none" stroke="{INK}" stroke-width="10"/>
    <path d="M-112,152 L112,152" stroke="{INK}" stroke-width="10" stroke-linecap="round"/>''',
    "notre-dame": f'''
    <rect x="-124" y="-140" width="76" height="130" fill="#e8ddc4" stroke="{INK}" stroke-width="10"/>
    <rect x="48" y="-140" width="76" height="130" fill="#e8ddc4" stroke="{INK}" stroke-width="10"/>
    <rect x="-124" y="-14" width="248" height="164" fill="#e8ddc4" stroke="{INK}" stroke-width="10"/>
    <circle cx="0" cy="52" r="42" fill="#ffffff" stroke="{INK}" stroke-width="9"/>
    <circle cx="0" cy="52" r="18" fill="none" stroke="{INK}" stroke-width="6"/>
    <path d="M-86,-42 L-86,-108 M86,-42 L86,-108" stroke="{INK}" stroke-width="7"/>
    <path d="M-100,-70 Q-86,-88 -72,-70 M72,-70 Q86,-88 100,-70" fill="none" stroke="{INK}" stroke-width="6"/>''',
    "coeur": f'''
    <path d="M0,122 C-142,24 -110,-112 0,-42 C110,-112 142,24 0,122 Z"
          fill="{RED}" stroke="{INK}" stroke-width="10" stroke-linejoin="round"/>''',
    "eclair": f'''
    <path d="M22,-152 L-64,12 L-8,12 L-28,152 L72,-22 L14,-22 Z"
          fill="{GOLD}" stroke="{INK}" stroke-width="10" stroke-linejoin="round"/>''',
    "musique": f'''
    <path d="M-38,86 L-38,-96 L84,-120 L84,62" fill="none" stroke="{INK}" stroke-width="12" stroke-linecap="round"/>
    <path d="M-38,-96 L84,-120 L84,-76 L-38,-52 Z" fill="{INK}"/>
    <ellipse cx="-70" cy="86" rx="34" ry="26" fill="{INK}"/>
    <ellipse cx="52" cy="62" rx="34" ry="26" fill="{INK}"/>''',
    "tableau": f'''
    <rect x="-124" y="-150" width="248" height="300" rx="8" fill="{GOLD}" stroke="{INK}" stroke-width="10"/>
    <rect x="-92" y="-118" width="184" height="236" fill="#f5efdf" stroke="{INK}" stroke-width="8"/>
    <ellipse cx="0" cy="-30" rx="46" ry="56" fill="{SKIN_DEFAULT}" stroke="{INK}" stroke-width="7"/>
    <path d="M-46,118 C-40,40 40,40 46,118" fill="#6b4a2f" stroke="{INK}" stroke-width="7"/>
    <circle cx="-16" cy="-38" r="5" fill="{INK}"/>
    <circle cx="16" cy="-38" r="5" fill="{INK}"/>
    <path d="M-14,-6 Q0,4 14,-6" stroke="{INK}" stroke-width="5" fill="none"/>''',
    "drapeau": f'''
    <path d="M-96,-160 L-96,160" stroke="{INK}" stroke-width="12" stroke-linecap="round"/>
    <circle cx="-96" cy="-160" r="12" fill="{GOLD}" stroke="{INK}" stroke-width="6"/>
    <path d="M-96,-140 C-20,-170 30,-110 116,-140 L116,-20 C30,10 -20,-50 -96,-20 Z"
          fill="#ffffff" stroke="{INK}" stroke-width="10" stroke-linejoin="round"/>
    <path d="M-96,-140 C-70,-150 -50,-152 -25,-148 L-25,-28 C-50,-32 -70,-30 -96,-20 Z" fill="#2f4b6b" stroke="{INK}" stroke-width="6"/>
    <path d="M45,-146 C70,-146 90,-143 116,-140 L116,-20 C90,-23 70,-26 45,-26 Z" fill="{RED}" stroke="{INK}" stroke-width="6"/>''',
    "horloge": f'''
    <circle cx="0" cy="0" r="140" fill="#ffffff" stroke="{INK}" stroke-width="12"/>
    <path d="M0,-118 L0,-96 M0,118 L0,96 M-118,0 L-96,0 M118,0 L96,0" stroke="{INK}" stroke-width="9" stroke-linecap="round"/>
    <path d="M0,0 L0,-78 M0,0 L52,26" stroke="{INK}" stroke-width="11" stroke-linecap="round"/>
    <circle cx="0" cy="0" r="12" fill="{INK}"/>''',
}


def icon_group(icon: str, *, x: float, y: float, scale: float = 1.0) -> str:
    if icon not in ICONS:
        raise StyleError(
            f"Pictogramme inconnu : {icon!r}. Connus : {', '.join(sorted(ICONS))}"
        )
    return (f'<g transform="translate({x:.0f},{y:.0f}) scale({scale:.3f})">'
            f'{ICONS[icon]}</g>')


def icon_medallion(icon: str, *, cx: float = 540, cy: float = 870,
                   r: float = 400) -> str:
    """Medaillon a pictogramme : la couverture des sujets sans portrait."""
    return f'''
  <circle cx="{cx:.0f}" cy="{cy:.0f}" r="{r:.0f}" fill="{MEDALLION}"/>
  {icon_group(icon, x=cx, y=cy, scale=r / 240.0)}
  <circle cx="{cx:.0f}" cy="{cy:.0f}" r="{r:.0f}" fill="none" stroke="{INK}" stroke-width="10"/>'''


# ---------------------------------------------------------------------------
# Cartes
# ---------------------------------------------------------------------------


def _balance_two_lines(lines: List[str]) -> List[str]:
    """Reequilibre une coupure en deux lignes.

    Le repliement glouton remplit la premiere ligne a ras bord et laisse
    parfois un seul mot orphelin en seconde ligne — laid sur un bandeau
    centre. On recoupe au mot qui rapproche le plus les deux longueurs.
    """
    if len(lines) != 2:
        return lines
    words = " ".join(lines).split()
    best = lines
    best_gap = abs(len(lines[0]) - len(lines[1]))
    for cut in range(1, len(words)):
        first, second = " ".join(words[:cut]), " ".join(words[cut:])
        gap = abs(len(first) - len(second))
        if gap < best_gap and max(len(first), len(second)) <= max(len(lines[0]), len(lines[1])):
            best, best_gap = [first, second], gap
    return best


def _bottom_band(text: str, accent: str) -> str:
    """Bandeau d'anecdote en pied de carte : trois lignes maximum, JAMAIS coupe.

    Une premiere version plafonnait a deux lignes et TRONQUAIT le reste : une
    accroche de 130 caracteres perdait son dernier mot en production — vu sur
    la couverture de la Joconde, « avant le » sans « lendemain ». La hauteur
    du bandeau permet trois lignes a 26 px : on replie, on ne coupe pas.
    """
    if not text:
        return ""
    size, lines = fit_text(text, (960, 165), start=40, floor=26, line_height=1.4)
    lines = _balance_two_lines(lines[:3])
    line_h = int(size * 1.45)
    top = 1826 - (len(lines) - 1) * line_h // 2
    rows = "".join(
        f'<text x="540" y="{top + i * line_h}" text-anchor="middle" '
        f'font-family="{SANS}" font-size="{size}" fill="#ffffff">{esc(line)}</text>'
        for i, line in enumerate(lines)
    )
    return f'''
  <rect x="0" y="1718" width="1080" height="14" fill="{GOLD}"/>
  <rect x="0" y="1732" width="1080" height="188" fill="{accent}"/>
  {rows}'''


def cover_card(
    *,
    header: str,
    name: str,
    real_name: str = "",
    date_line: str = "",
    place_line: str = "",
    band_text: str = "",
    portrait: Optional[Portrait] = None,
    icon: Optional[str] = None,
    accent: str = RED,
) -> str:
    """Carte de couverture : rideau, medaillon, nom, dates, bandeau.

    ``portrait`` ou ``icon`` : l'un des deux. Un sujet-personne montre son
    portrait ; un sujet-evenement montre son pictogramme.
    """
    if portrait is not None:
        medallion = portrait_medallion(portrait)
    elif icon:
        medallion = icon_medallion(icon)
    else:
        raise StyleError("Couverture sans portrait ni pictogramme.")

    n_size = name_font_size(name)
    parts = [f'''
{_curtain()}
  {_brand(320, accent)}
  <text x="540" y="392" text-anchor="middle" font-family="{SANS}" font-size="36"
        letter-spacing="6" fill="{BROWN_TEXT}" font-weight="bold">{esc(header.upper())}</text>
{medallion}
  <text x="540" y="1435" text-anchor="middle" font-family="{SERIF}" font-size="{n_size}"
        font-weight="bold" fill="{INK}" letter-spacing="4">{esc(name)}</text>
  <rect x="430" y="1462" width="220" height="9" fill="{accent}"/>''']
    if real_name:
        parts.append(
            f'<text x="540" y="1540" text-anchor="middle" font-family="{SERIF}" '
            f'font-size="50" font-style="italic" fill="{BROWN_TEXT}">{esc(real_name)}</text>')
    if date_line:
        parts.append(
            f'<text x="540" y="1614" text-anchor="middle" font-family="{SANS}" '
            f'font-size="44" fill="{GREY_TEXT}">{esc(date_line)}</text>')
    if place_line:
        parts.append(
            f'<text x="540" y="1672" text-anchor="middle" font-family="{SANS}" '
            f'font-size="37" fill="{GREY_TEXT}">{esc(place_line)}</text>')
    parts.append(_bottom_band(band_text, accent))
    return _svg("".join(parts))


def _header_line(header: str, y: int = 346) -> str:
    if not header:
        return ""
    return (f'<text x="540" y="{y}" text-anchor="middle" font-family="{SANS}" '
            f'font-size="36" letter-spacing="6" fill="{BROWN_TEXT}" '
            f'font-weight="bold">{esc(header.upper())}</text>')


def scene_card(
    *,
    text: str,
    icon: str,
    index: int,
    total: int,
    footer: str,
    header: str = "",
    accent: str = RED,
) -> str:
    """Carte de scene : pictogramme en medaillon, recit dans un cartouche.

    Le cartouche rectangulaire est le « recitatif » de la BD : c'est lui qui
    porte la narration. Le pictogramme donne un ancrage visuel a la phrase
    sans exiger une illustration originale par scene — c'est ce qui rend la
    serie fabricable en une commande.
    """
    size, lines = fit_text(text, (830, 560), start=56, floor=38)
    line_h = int(size * 1.42)
    pad = 60
    box_h = len(lines) * line_h + 2 * pad - int(size * 0.35)
    box_top = 1010
    rows = "".join(
        f'<text x="540" y="{box_top + pad + size + i * line_h - int(size * 0.2)}" '
        f'text-anchor="middle" font-family="{SANS}" font-size="{size}" '
        f'fill="{INK}">{esc(line)}</text>'
        for i, line in enumerate(lines)
    )
    return _svg(f'''
{_curtain(0.62)}
  {_brand(266, accent)}
  {_header_line(header)}
  <rect x="906" y="300" width="120" height="66" rx="10" fill="#ffffff" stroke="{INK}" stroke-width="6"/>
  <text x="966" y="346" text-anchor="middle" font-family="{SANS}" font-size="34"
        font-weight="bold" fill="{INK}">{index}/{total}</text>
  <circle cx="540" cy="660" r="230" fill="{MEDALLION}"/>
  {icon_group(icon, x=540, y=660, scale=1.05)}
  <circle cx="540" cy="660" r="230" fill="none" stroke="{INK}" stroke-width="10"/>
  <rect x="90" y="{box_top}" width="900" height="{box_h}" rx="18"
        fill="#fdf6e0" stroke="{INK}" stroke-width="8"/>
  {rows}
  <text x="540" y="1806" text-anchor="middle" font-family="{SERIF}" font-size="46"
        font-weight="bold" letter-spacing="4" fill="{BROWN_TEXT}">{esc(footer)}</text>
  <rect x="465" y="1830" width="150" height="7" fill="{accent}"/>''')


def final_card(
    *,
    fact: str,
    cta: str,
    footer: str,
    header: str = "",
    portrait: Optional[Portrait] = None,
    icon: Optional[str] = None,
    accent: str = RED,
) -> str:
    """Carte finale : le fait a retenir, puis l'appel a s'abonner."""
    if portrait is not None:
        # Portrait reduit et remonte : le repere canonique est centre en
        # (540, 870) ; a l'echelle 0,55 il faut translater de 540*(1-0,55)=243
        # en x et de 600-870*0,55=121,5 en y pour le centrer en (540, 600).
        medallion = portrait_medallion(
            portrait, transform="translate(243,121.5) scale(0.55)"
        )
    elif icon:
        medallion = icon_medallion(icon, cx=540, cy=600, r=220)
    else:
        raise StyleError("Carte finale sans portrait ni pictogramme.")

    size, lines = fit_text(fact, (830, 420), start=54, floor=38)
    line_h = int(size * 1.42)
    pad = 60
    box_top = 950
    box_h = len(lines) * line_h + 2 * pad - int(size * 0.35)
    rows = "".join(
        f'<text x="540" y="{box_top + pad + size + i * line_h - int(size * 0.2)}" '
        f'text-anchor="middle" font-family="{SANS}" font-size="{size}" '
        f'fill="{INK}">{esc(line)}</text>'
        for i, line in enumerate(lines)
    )
    return _svg(f'''
{_curtain(0.62)}
  {_brand(266, accent)}
  {_header_line(header)}
{medallion}
  <text x="540" y="880" text-anchor="middle" font-family="{SERIF}" font-size="52"
        font-weight="bold" letter-spacing="4" fill="{BROWN_TEXT}">{esc(footer)}</text>
  <rect x="465" y="906" width="150" height="7" fill="{accent}"/>
  <rect x="90" y="{box_top}" width="900" height="{box_h}" rx="18"
        fill="#fdf6e0" stroke="{INK}" stroke-width="8"/>
  {rows}
  {_bottom_band(cta, accent)}''')
