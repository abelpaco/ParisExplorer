"""Avatar de chaine : une image qui doit tenir dans un cercle de 48 pixels.

POURQUOI CE MODULE EST SEPARE DES CARTES
----------------------------------------
Une carte se regarde en grand, dans un fil. Un avatar se regarde en tout petit,
et decoupe en rond. Les deux contraintes sont differentes au point de demander
un traitement different :

1. **YouTube decoupe l'avatar en CERCLE.** Les quatre coins disparaissent. Toute
   composition qui s'appuie sur un coin est perdue.

2. **Il descend a quarante-huit pixels** dans les commentaires et les listes. A
   cette taille, une photo detaillee devient une bouillie grise. Ce qui survit,
   c'est une SILHOUETTE : deux tons, un contraste franc, une forme reconnaissable.

3. **Un avatar n'a nulle part ou porter un credit.** Les licences CC BY et CC
   BY-SA exigent l'attribution : elles sont donc inutilisables ici, quelle que
   soit la beaute de la photo. Ce module n'accepte que le domaine public et le
   CC0.

La verification finale n'est pas esthetique : on relit l'image reduite a 48
pixels et on mesure son contraste. Une forme qui disparait a cette taille est un
avatar rate, meme s'il est superbe en grand.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

PROJECT_DIR = Path(__file__).resolve().parent
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(PROJECT_DIR))

logger = logging.getLogger("avatar")

# Taille recommandee par YouTube. L'image est affichee bien plus petite, mais on
# fournit la source la plus grande pour que le redimensionnement soit fait par
# la plateforme et non par nous.
AVATAR_SIZE = 800

# Taille reelle d'affichage la plus petite (commentaires, listes). C'est a
# CETTE taille qu'on juge le resultat.
SMALL_PREVIEW = 48

# Le sujet doit tenir dans ce cercle, exprime en fraction du cote. Au-dela, il
# touche la zone que le decoupage circulaire va manger.
SAFE_CIRCLE = 0.92

INK = (16, 20, 32)
PAPER = (245, 243, 238)
ACCENT = (214, 168, 78)


class AvatarError(RuntimeError):
    """L'avatar n'a pas pu etre fabrique."""


def _square(
    image: Image.Image, size: int, focus_top: float = 0.38, zoom: float = 1.0
) -> Image.Image:
    """Recadre en carre, en gardant le sujet haut plutot que centre.

    Sur une photo de monument, le sujet occupe le haut ; un recadrage centre
    coupe la pointe et garde du parvis. ``zoom`` resserre encore : un avatar
    demande un cadrage bien plus serre qu'une photo, sous peine de reduire le
    sujet a un point une fois affiche en petit.
    """
    scale = size * zoom / min(image.width, image.height)
    resized = image.resize(
        (max(size, int(image.width * scale)), max(size, int(image.height * scale))),
        Image.LANCZOS,
    )
    left = (resized.width - size) // 2
    top = int((resized.height - size) * focus_top)
    return resized.crop((left, top, left + size, top + size))


def _duotone(image: Image.Image, contrast: float, posterize: Optional[int]) -> Image.Image:
    """Reduit l'image a deux teintes contrastees.

    ``posterize`` ecrase les nuances en un petit nombre de niveaux : c'est ce
    qui transforme une photo en affiche, et surtout ce qui la rend lisible une
    fois reduite a quarante-huit pixels.
    """
    grey = ImageOps.grayscale(image)
    grey = ImageOps.autocontrast(grey, cutoff=1)
    grey = ImageEnhance.Contrast(grey).enhance(contrast)
    if posterize:
        grey = ImageOps.posterize(grey, posterize)
    return ImageOps.colorize(grey, black=INK, white=PAPER, mid=ACCENT)


def _otsu_threshold(grey: Image.Image) -> int:
    """Seuil qui separe le mieux l'image en deux populations (methode d'Otsu).

    Un seuil fixe echoue des que la photo est prise a contre-jour ou par temps
    couvert. Celui-ci se calcule sur l'histogramme de CETTE image.
    """
    histogram = grey.histogram()[:256]
    total = sum(histogram)
    sum_all = sum(i * n for i, n in enumerate(histogram))

    best_threshold, best_variance = 128, -1.0
    weight_back, sum_back = 0, 0
    for level in range(256):
        weight_back += histogram[level]
        if weight_back == 0:
            continue
        weight_fore = total - weight_back
        if weight_fore == 0:
            break
        sum_back += level * histogram[level]
        mean_back = sum_back / weight_back
        mean_fore = (sum_all - sum_back) / weight_fore
        variance = weight_back * weight_fore * (mean_back - mean_fore) ** 2
        if variance > best_variance:
            best_variance, best_threshold = variance, level
    return best_threshold


def _silhouette(
    image: Image.Image, invert: bool = False, solidify: int = 0
) -> Image.Image:
    """Reduit l'image a DEUX tons purs : la forme, et le fond.

    C'est le seul traitement qui survive a quarante-huit pixels. La posterisation
    garde des demi-teintes qui, une fois reduites, se moyennent en une bouillie
    uniforme — teste, et rate. Ici il ne reste qu'une decoupe.

    ``solidify`` epaissit la forme sombre jusqu'a fermer ses ajours. C'est
    indispensable sur un sujet en TREILLIS : la Tour Eiffel est une dentelle,
    un simple seuillage n'en tire que des traits fins qui disparaissent des
    qu'on reduit. C'est le geste classique du dessin d'icone — on remplit
    plutot que de detailler.
    """
    grey = ImageOps.grayscale(image)
    grey = ImageOps.autocontrast(grey, cutoff=1)
    threshold = _otsu_threshold(grey)
    mask = grey.point(lambda v: 255 if v > threshold else 0, mode="1").convert("L")
    mask = mask.filter(ImageFilter.MedianFilter(3))  # gomme le bruit isole

    if solidify:
        # On epaissit la classe MINORITAIRE, qui est le sujet : dans une
        # silhouette, le fond occupe toujours le plus de place. Choisir le filtre
        # a l'aveugle epaissit une fois sur deux le CIEL, qui devore alors le
        # monument — verifie a mes depens.
        values = list(mask.getdata())
        bright = sum(1 for v in values if v > 127)
        subject_is_bright = bright < len(values) - bright
        mask = mask.filter(
            (ImageFilter.MaxFilter if subject_is_bright else ImageFilter.MinFilter)(solidify)
        )

    if invert:
        mask = ImageOps.invert(mask)
    return ImageOps.colorize(mask, black=INK, white=ACCENT)


def _vignette(image: Image.Image, strength: float = 0.55) -> Image.Image:
    """Assombrit les bords pour ramener l'oeil au centre du cercle."""
    size = image.size[0]
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    inset = int(size * 0.06)
    draw.ellipse((inset, inset, size - inset, size - inset), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(size * 0.12))
    dark = Image.new("RGB", (size, size), INK)
    return Image.composite(image, Image.blend(image, dark, strength), mask)


def _ring(image: Image.Image, color=ACCENT) -> Image.Image:
    """Trace un anneau juste a l'interieur du decoupage circulaire."""
    size = image.size[0]
    draw = ImageDraw.Draw(image)
    inset = int(size * (1 - SAFE_CIRCLE) / 2)
    draw.ellipse(
        (inset, inset, size - inset, size - inset),
        outline=color, width=max(3, int(size * 0.012)),
    )
    return image


def small_contrast(image: Image.Image) -> float:
    """Ecart-type des luminosites une fois l'image reduite a 48 pixels.

    C'est la mesure qui compte : elle dit si la forme survit a la taille reelle
    d'affichage. En dessous d'une trentaine, l'avatar se lit comme une tache.
    """
    tiny = image.resize((SMALL_PREVIEW, SMALL_PREVIEW), Image.LANCZOS).convert("L")
    values = list(tiny.getdata())
    mean = sum(values) / len(values)
    return (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5


def make_avatar(
    source: Path,
    out_path: Path,
    *,
    size: int = AVATAR_SIZE,
    style: str = "silhouette",
    contrast: float = 1.6,
    posterize: Optional[int] = 3,
    vignette: bool = True,
    ring: bool = True,
    focus_top: float = 0.38,
    zoom: float = 1.0,
    invert: bool = False,
    solidify: int = 0,
) -> Tuple[Path, float]:
    """Fabrique un avatar carre a partir d'une photo.

    Returns:
        ``(chemin, contraste a 48 px)``. Le second sert a juger : c'est la
        seule mesure qui dit si l'avatar tiendra a sa taille reelle.
    """
    try:
        with Image.open(source) as raw:
            base = _square(raw.convert("RGB"), size, focus_top, zoom)
    except OSError as exc:
        raise AvatarError(f"Image illisible ({source}) : {exc}") from exc

    if style == "silhouette":
        art = _silhouette(base, invert=invert, solidify=solidify)
        vignette = False  # un aplat n'a pas besoin qu'on ramene l'oeil au centre
    elif style == "duotone":
        art = _duotone(base, contrast, posterize)
    else:
        raise AvatarError(f"Style inconnu : {style}. Connus : silhouette, duotone")

    if vignette:
        art = _vignette(art)
    if ring:
        art = _ring(art)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    art.save(out_path, "PNG", optimize=True)

    score = small_contrast(art)
    if score < 30:
        logger.warning(
            "%s : contraste de %.0f a %d px — la forme risque de se lire comme "
            "une tache. Choisis une image a silhouette plus marquee.",
            out_path.name, score, SMALL_PREVIEW,
        )
    return out_path, score


def contact_sheet(paths, out_path: Path, cell: int = 200) -> Path:
    """Planche de comparaison : chaque avatar en grand, puis en tout petit.

    Juger un avatar en grand ne veut rien dire. La planche montre les deux
    tailles cote a cote pour qu'on choisisse sur la bonne.
    """
    paths = list(paths)
    if not paths:
        # Sans ce garde-fou, Pillow echoue sur une image de largeur nulle avec
        # « tile cannot extend outside image » — un message qui ne dit pas du
        # tout que la vraie cause est une liste vide.
        raise AvatarError("Aucun avatar a comparer : la liste est vide.")

    columns = len(paths)
    sheet = Image.new("RGB", (columns * cell, cell + SMALL_PREVIEW + 24), PAPER)
    for index, path in enumerate(paths):
        with Image.open(path) as art:
            big = art.resize((cell - 16, cell - 16), Image.LANCZOS)
            sheet.paste(big, (index * cell + 8, 8))
            tiny = art.resize((SMALL_PREVIEW, SMALL_PREVIEW), Image.LANCZOS)
            sheet.paste(tiny, (index * cell + (cell - SMALL_PREVIEW) // 2, cell + 8))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, "PNG")
    return out_path


# ---------------------------------------------------------------------------
# Glyphe dessine
# ---------------------------------------------------------------------------

# Profil de la tour : demi-largeur en fraction de la hauteur, du pied au sommet.
# Il est DESSINE et non extrait d'une photo, parce qu'aucune photo de treillis ne
# survit a quarante-huit pixels : seuillee elle donne un trait, epaissie elle
# donne un pate. Une icone se dessine avec des masses, pas avec du detail.
_PROFILE = [
    (0.00, 0.255), (0.08, 0.178), (0.18, 0.128), (0.30, 0.098),
    (0.45, 0.078), (0.60, 0.063), (0.75, 0.051), (0.88, 0.040),
    (1.00, 0.020),
]


def eiffel_glyph(
    size: int = AVATAR_SIZE,
    *,
    background=INK,
    foreground=ACCENT,
    ring: bool = True,
) -> Image.Image:
    """Dessine une Tour Eiffel simplifiee, lisible a n'importe quelle taille."""
    art = Image.new("RGB", (size, size), background)
    draw = ImageDraw.Draw(art)

    # La tour occupe la hauteur utile du cercle, centree.
    top = size * 0.20
    bottom = size * 0.86
    height = bottom - top
    centre = size / 2

    def half_width(t: float) -> float:
        """Demi-largeur interpolee a la hauteur relative ``t`` (0 = pied)."""
        for (t0, w0), (t1, w1) in zip(_PROFILE, _PROFILE[1:]):
            if t0 <= t <= t1:
                ratio = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
                return (w0 + (w1 - w0) * ratio) * height
        return _PROFILE[-1][1] * height

    steps = 60
    left_edge = [(centre - half_width(i / steps), bottom - height * i / steps)
                 for i in range(steps + 1)]
    right_edge = [(centre + half_width(i / steps), bottom - height * i / steps)
                  for i in range(steps + 1)]
    draw.polygon(left_edge + list(reversed(right_edge)), fill=foreground)

    # L'arche : c'est elle qui rend la silhouette reconnaissable. Sans elle, le
    # glyphe devient un pylone electrique.
    arch_top = bottom - height * 0.20
    arch_half = half_width(0.20) * 0.80
    draw.pieslice(
        (centre - arch_half, arch_top - arch_half * 1.15,
         centre + arch_half, arch_top + arch_half * 1.15),
        start=180, end=360, fill=background,
    )
    draw.rectangle(
        (centre - arch_half, arch_top, centre + arch_half, bottom), fill=background
    )

    # Les deux plateformes, et le socle qui referme les pieds.
    bar = max(3, int(size * 0.018))
    for level, overhang in ((0.20, 1.30), (0.55, 1.35)):
        y = bottom - height * level
        w = half_width(level) * overhang
        draw.rectangle((centre - w, y - bar / 2, centre + w, y + bar / 2), fill=foreground)
    draw.rectangle(
        (centre - half_width(0.0), bottom - bar, centre + half_width(0.0), bottom),
        fill=foreground,
    )

    if ring:
        _ring(art, foreground)
    return art
