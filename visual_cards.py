"""Cartes visuelles : une image de fond, un texte dessus, aux formats sociaux.

POURQUOI CE MODULE EXISTE
-------------------------
Une video montee coute quelques minutes de calcul et surtout du temps
d'ecriture. Pour tenir trois publications par jour, la chaine a besoin d'un
format leger : une image forte, une phrase, la marque. Ca se produit en une
seconde, ca se lit en trois, et ca ramene vers les videos.

Les cartes reutilisent tout l'amont : memes sujets YAML, memes photos creditees
de Wikimedia, meme registre. Seul le rendu final change.

LE VRAI PROBLEME, C'EST LA LISIBILITE
-------------------------------------
Poser du texte blanc sur une photo quelconque marche une fois sur deux : un ciel
clair, une facade en pierre blonde, et la phrase disparait. Le module ne parie
donc pas — il MESURE la luminosite de la zone de texte et fonce le voile jusqu'a
obtenir un contraste suffisant. Une carte illisible est pire qu'une carte
absente : elle brule une image et une idee.
"""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

logger = logging.getLogger(__name__)

# Formats sociaux. Le carre passe partout ; le portrait occupe plus d'ecran dans
# un fil ; l'histoire sert aussi de couverture de Short.
CARD_FORMATS = {
    "square": (1080, 1080),
    "portrait": (1080, 1350),
    "story": (1080, 1920),
}
DEFAULT_FORMAT = "portrait"

# Identite. Le bleu de zinc des toits parisiens, l'or des dômes.
INK = (16, 20, 32)
PAPER = (245, 243, 238)
ACCENT = (214, 168, 78)
BRAND = "PARIS EXPLORER"

# Marges internes, en fraction de la largeur.
MARGIN_RATIO = 0.085

# Luminosite maximale toleree sous du texte blanc (0-255). Au-dessus, le voile
# est renforce. 118 correspond a un contraste confortable en lecture mobile.
MAX_TEXT_AREA_LUMINANCE = 118
SCRIM_STEP = 0.12
SCRIM_MAX_PASSES = 6

# Polices candidates, par ordre de preference. DejaVu passe en premier parce que
# c'est celle du VPS, donc celle de la PRODUCTION : preferer une police locale
# ferait des cartes differentes selon la machine qui les fabrique.
FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/seguisb.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)

# Bornes de longueur d'une phrase retenue comme carte. Trop court, ca ne dit
# rien ; trop long, ca ne se lit pas sur un telephone.
CARD_TEXT_MIN = 45
CARD_TEXT_MAX = 165

# Libelles des categories. Les identifiants des sujets sont volontairement sans
# accent — ce sont des cles, pas du texte. Les afficher tels quels mettrait
# « DECOUVERTE » sur une carte publique.
CATEGORY_LABELS = {
    "monument": {"fr": "Monument", "en": "Landmark"},
    "histoire": {"fr": "Histoire", "en": "History"},
    "decouverte": {"fr": "Découverte", "en": "Discover"},
    "economie": {"fr": "Économie", "en": "Economy"},
    "sport": {"fr": "Sport", "en": "Sport"},
    "actualite": {"fr": "Actualité", "en": "News"},
}


def category_label(category: str, lang: str) -> str:
    """Libelle affichable d'une categorie, dans la langue de la carte.

    Une categorie inconnue est renvoyee telle quelle plutot qu'ecartee : mieux
    vaut une etiquette imparfaite qu'une carte sans reperage.
    """
    entry = CATEGORY_LABELS.get((category or "").strip().lower())
    if not entry:
        return category or ""
    return entry.get(lang) or entry.get("fr", category)


class CardError(RuntimeError):
    """La carte n'a pas pu etre fabriquee."""


@dataclass
class Card:
    """Une carte produite."""

    path: Path
    text: str
    index: int
    total: int
    background: Optional[Path] = None
    credit: str = ""


@dataclass
class CardSeries:
    """Une serie de cartes pour un sujet et une langue."""

    topic_id: str
    lang: str
    fmt: str
    style: str
    cards: List[Card] = field(default_factory=list)
    credits: str = ""


# ---------------------------------------------------------------------------
# Polices
# ---------------------------------------------------------------------------

_font_path: Optional[str] = None


def font_file() -> str:
    """Chemin de la police utilisee, resolu une fois pour toutes.

    Raises:
        CardError: aucune police vectorielle trouvee. On leve PLUTOT que de
            retomber sur ``ImageFont.load_default()`` : cette police de secours
            est une bitmap minuscule, non redimensionnable. Elle produirait des
            cartes techniquement valides et visuellement inutilisables — une
            panne qui ne se voit qu'a l'oeil, trop tard.
    """
    global _font_path
    if _font_path:
        return _font_path
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            _font_path = candidate
            logger.info("Police des cartes : %s", candidate)
            return _font_path
    raise CardError(
        "Aucune police vectorielle trouvee. Installe DejaVu "
        "(apt-get install fonts-dejavu-core) ou complete FONT_CANDIDATES."
    )


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_file(), size)


# ---------------------------------------------------------------------------
# Mise en page du texte
# ---------------------------------------------------------------------------


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> List[str]:
    """Coupe le texte en lignes qui tiennent dans ``max_width``."""
    words = text.split()
    lines: List[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _fit_text(
    draw: ImageDraw.ImageDraw, text: str, box: Tuple[int, int], start: int, floor: int
) -> Tuple[ImageFont.FreeTypeFont, List[str], int]:
    """Plus grande taille de police qui fait tenir le texte dans la boite.

    On part du grand et on descend : une phrase courte doit remplir la carte,
    une phrase longue doit rester lisible. La taille n'est jamais figee.
    """
    max_w, max_h = box
    size = start
    while size >= floor:
        font = _font(size)
        lines = _wrap(draw, text, font, max_w)
        line_height = int(size * 1.28)
        if len(lines) * line_height <= max_h:
            return font, lines, line_height
        size -= 2
    font = _font(floor)
    return font, _wrap(draw, text, font, max_w), int(floor * 1.28)


# ---------------------------------------------------------------------------
# Fond
# ---------------------------------------------------------------------------


def _cover(image: Image.Image, size: Tuple[int, int]) -> Image.Image:
    """Recadre l'image pour remplir le format, sans deformation."""
    box_w, box_h = size
    scale = max(box_w / image.width, box_h / image.height)
    new = image.resize(
        (max(box_w, int(image.width * scale)), max(box_h, int(image.height * scale))),
        Image.LANCZOS,
    )
    left = (new.width - box_w) // 2
    # Cadrage vertical biaise vers le haut : sur une photo de monument, le sujet
    # est en haut et le bas n'est souvent que du sol.
    top = (new.height - box_h) // 3
    return new.crop((left, top, left + box_w, top + box_h))


def _poster(image: Image.Image) -> Image.Image:
    """Traitement graphique facon affiche : duotone contraste et grain.

    Ce n'est PAS de l'art genere : c'est un traitement de la photo. Fort
    contraste, deux teintes, un grain leger — le vocabulaire de l'affiche
    serigraphiee. Assumons-le comme tel plutot que de le vendre pour autre chose.
    """
    grey = ImageOps.grayscale(image)
    grey = ImageOps.autocontrast(grey, cutoff=2)
    grey = ImageEnhance.Contrast(grey).enhance(1.35)
    duotone = ImageOps.colorize(grey, black=INK, white=PAPER, mid=ACCENT)

    grain = Image.effect_noise(image.size, 14).convert("L")
    grain = grain.filter(ImageFilter.GaussianBlur(0.4)).convert("RGB")
    return Image.blend(duotone, grain, 0.07)


def _scrim(size: Tuple[int, int], strength: float) -> Image.Image:
    """Voile sombre en degrade, opaque en bas, transparent vers le haut.

    Le texte vit en bas de carte : c'est la que le voile doit etre franc. Plus
    haut, la photo doit rester visible — c'est elle qui donne envie de cliquer.
    """
    width, height = size
    veil = Image.new("L", (1, height))
    for y in range(height):
        position = y / max(1, height - 1)
        # Courbe douce puis franche : le voile monte lentement, puis s'affirme
        # sur le dernier tiers.
        value = strength * (position ** 2.2)
        veil.putpixel((0, y), int(max(0, min(1.0, value)) * 255))
    return veil.resize((width, height))


def _area_luminance(image: Image.Image, box: Tuple[int, int, int, int]) -> float:
    """Luminosite moyenne d'une zone (0 = noir, 255 = blanc)."""
    crop = image.crop(box).convert("L")
    histogram = crop.histogram()
    total = sum(histogram)
    if not total:
        return 0.0
    return sum(i * n for i, n in enumerate(histogram)) / total


def _luminance(color: Tuple[int, int, int]) -> float:
    """Luminosite percue d'une couleur (ponderation ITU-R BT.601)."""
    red, green, blue = color
    return 0.299 * red + 0.587 * green + 0.114 * blue


def _readable_on(
    image: Image.Image, box: Tuple[int, int, int, int], preferred: Tuple[int, int, int]
) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
    """Couleur et liseré lisibles sur cette zone, en partant de la couleur voulue.

    Deux pieges, tous deux rencontres en production :

    - en style affiche, le duotone se sert de la couleur d'accent comme teinte
      mediane : une etiquette doree tombe alors sur un fond dore et disparait ;
    - un fond mi-sombre mi-clair fait une moyenne trompeuse. Une mesure sur une
      zone large peut donner « sombre » alors que la moitie du mot est posee sur
      du blanc. C'est pourquoi l'appelant DOIT passer l'emprise exacte du texte,
      et pourquoi on rend aussi un liseré : il rattrape ce que la moyenne rate.

    Returns:
        ``(couleur, liseré)``, le liseré etant toujours l'oppose lumineux.
    """
    background = _area_luminance(image, box)
    chosen = preferred if abs(_luminance(preferred) - background) >= 60 else (
        PAPER if background < 128 else INK
    )
    outline = INK if _luminance(chosen) >= 128 else PAPER
    return chosen, outline


def _text_bounds(
    draw: ImageDraw.ImageDraw,
    position: Tuple[int, int],
    text: str,
    font,
    size: Tuple[int, int],
) -> Tuple[int, int, int, int]:
    """Emprise reelle d'un texte, bornee au cadre de la carte."""
    left, top, right, bottom = draw.textbbox(position, text, font=font)
    width, height = size
    return (
        max(0, int(left)), max(0, int(top)),
        max(1, min(width, int(right))), max(1, min(height, int(bottom))),
    )


# ---------------------------------------------------------------------------
# Rendu
# ---------------------------------------------------------------------------


def render_card(
    background: Path,
    text: str,
    out_path: Path,
    *,
    fmt: str = DEFAULT_FORMAT,
    style: str = "photo",
    eyebrow: str = "",
    index: Optional[int] = None,
    total: Optional[int] = None,
) -> Path:
    """Fabrique une carte : photo de fond, voile, texte, marque.

    Args:
        background: photo de fond.
        text: la phrase de la carte.
        out_path: PNG a produire.
        fmt: cle de :data:`CARD_FORMATS`.
        style: ``photo`` (photo voilee) ou ``poster`` (duotone serigraphie).
        eyebrow: petite etiquette au-dessus du texte (categorie du sujet).
        index, total: numero dans la serie, affiche en haut a droite.

    Raises:
        CardError: format inconnu, fond illisible, ou police introuvable.
    """
    if fmt not in CARD_FORMATS:
        raise CardError(f"Format inconnu : {fmt}. Connus : {', '.join(CARD_FORMATS)}")
    size = CARD_FORMATS[fmt]
    width, height = size

    try:
        with Image.open(background) as raw:
            base = _cover(raw.convert("RGB"), size)
    except OSError as exc:
        raise CardError(f"Fond illisible ({background}) : {exc}") from exc

    if style == "poster":
        base = _poster(base)
    elif style != "photo":
        raise CardError(f"Style inconnu : {style}. Connus : photo, poster")

    margin = int(width * MARGIN_RATIO)
    text_box = (width - 2 * margin, int(height * 0.42))

    # Le texte se dimensionne AVANT le voile : c'est sa hauteur reelle qui dit
    # quelle zone doit etre assombrie.
    probe = ImageDraw.Draw(base)
    font, lines, line_height = _fit_text(
        probe, text, text_box, start=int(width * 0.082), floor=int(width * 0.036)
    )
    block_height = len(lines) * line_height
    text_top = height - margin - block_height
    if eyebrow:
        text_top -= int(width * 0.055)

    # Voile progressif : on renforce tant que la zone de texte reste trop claire
    # pour du blanc. C'est mesure sur l'image reelle, pas suppose.
    #
    # La zone mesuree est EXACTEMENT le bloc de texte. Mesurer plus large — par
    # exemple jusqu'au bas de la carte — fait une moyenne trompeuse : un bas
    # d'image sombre compense une facade blanche, le seuil est respecte, et le
    # voile ne se declenche pas alors que le texte tombe en plein sur le blanc.
    zone = (margin, max(0, text_top), width - margin, min(height, text_top + block_height))
    strength = 0.55
    card = base
    for attempt in range(SCRIM_MAX_PASSES):
        card = Image.composite(Image.new("RGB", size, INK), base, _scrim(size, strength))
        luminance = _area_luminance(card, zone)
        if luminance <= MAX_TEXT_AREA_LUMINANCE:
            break
        strength = min(1.0, strength + SCRIM_STEP)
        if attempt == SCRIM_MAX_PASSES - 1:
            logger.warning(
                "Fond tres clair (%s) : luminosite %.0f apres voile maximal. "
                "La carte reste lisible mais le fond est presque efface.",
                Path(background).name, luminance,
            )

    draw = ImageDraw.Draw(card)

    small = _font(int(width * 0.026))
    hairline = max(1, int(width * 0.0016))

    def label(position: Tuple[int, int], content: str, font, preferred) -> None:
        """Ecrit un petit texte avec la couleur qui se lit la ou il tombe."""
        bounds = _text_bounds(draw, position, content, font, size)
        fill, outline = _readable_on(card, bounds, preferred)
        draw.text(
            position, content, font=font, fill=fill,
            stroke_width=hairline, stroke_fill=outline,
        )

    # Marque, en haut a gauche.
    label((margin, margin), BRAND, small, PAPER)
    rule_y = margin + int(width * 0.045)
    rule_end = margin + int(width * 0.09)
    rule_color, _ = _readable_on(card, (margin, rule_y - 2, rule_end, rule_y + 3), ACCENT)
    draw.line([(margin, rule_y), (rule_end, rule_y)], fill=rule_color, width=max(2, int(width * 0.005)))

    # Numero dans la serie, en haut a droite.
    if index and total and total > 1:
        counter = f"{index}/{total}"
        label((width - margin - int(draw.textlength(counter, font=small)), margin), counter, small, ACCENT)

    # Etiquette de categorie, juste au-dessus du texte.
    y = text_top
    if eyebrow:
        label((margin, y - int(width * 0.055)), eyebrow.upper(), _font(int(width * 0.028)), ACCENT)

    # Le texte, avec un liseré sombre : meme voile mesure, un detail clair de la
    # photo peut affleurer juste derriere une lettre.
    for line in lines:
        draw.text(
            (margin, y), line, font=font, fill=PAPER,
            stroke_width=max(1, int(width * 0.0022)), stroke_fill=(0, 0, 0),
        )
        y += line_height

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    card.save(out_path, "PNG", optimize=True)
    return out_path


# ---------------------------------------------------------------------------
# Choix des textes
# ---------------------------------------------------------------------------

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def card_texts(topic, lang: str, count: int) -> List[str]:
    """Phrases a mettre en carte, dans l'ordre de lecture.

    Utilise le bloc ``cards`` du sujet s'il existe. Sinon, retombe sur la
    narration : on garde les phrases d'une longueur lisible sur telephone, puis
    on les repartit sur toute la narration plutot que de prendre les premieres —
    une serie doit raconter l'arc du sujet, pas son introduction.
    """
    explicit = getattr(topic.text(lang), "cards", None)
    if explicit:
        return list(explicit)[:count]

    narration = " ".join(topic.text(lang).narration.split())
    sentences = [s.strip() for s in _SENTENCE.split(narration) if s.strip()]
    usable = [s for s in sentences if CARD_TEXT_MIN <= len(s) <= CARD_TEXT_MAX]

    if not usable:
        logger.warning(
            "%s[%s] : aucune phrase de longueur exploitable (%d-%d caracteres). "
            "Ajoute un bloc 'cards' au sujet.",
            topic.id, lang, CARD_TEXT_MIN, CARD_TEXT_MAX,
        )
        return []
    if len(usable) <= count:
        return usable

    step = len(usable) / count
    return [usable[min(len(usable) - 1, int(i * step))] for i in range(count)]


# ---------------------------------------------------------------------------
# Serie
# ---------------------------------------------------------------------------


def build_series(
    topic,
    lang: str,
    backgrounds: Sequence[Path],
    out_dir: Path,
    *,
    count: int = 5,
    fmt: str = DEFAULT_FORMAT,
    style: str = "photo",
    credits: str = "",
) -> CardSeries:
    """Produit la serie de cartes d'un sujet.

    Chaque carte prend un fond different tant qu'il y en a ; au-dela, les fonds
    sont recycles en boucle plutot que de repeter le premier.

    Returns:
        La serie produite. Peut etre vide si aucune phrase n'est exploitable :
        l'appelant DOIT gerer ce cas plutot que de supposer ``count`` cartes.
    """
    texts = card_texts(topic, lang, count)
    if not texts:
        return CardSeries(topic.id, lang, fmt, style, [], credits)
    if not backgrounds:
        raise CardError(f"Aucun fond disponible pour « {topic.id} ».")

    out_dir = Path(out_dir)
    series = CardSeries(topic.id, lang, fmt, style, [], credits)
    total = len(texts)

    for position, text in enumerate(texts, start=1):
        background = Path(backgrounds[(position - 1) % len(backgrounds)])
        target = out_dir / f"{topic.id}-{lang}-{fmt}-{position:02d}.png"
        render_card(
            background, text, target,
            fmt=fmt, style=style,
            eyebrow=category_label(topic.category, lang),
            index=position, total=total,
        )
        series.cards.append(
            Card(path=target, text=text, index=position, total=total, background=background)
        )

    logger.info(
        "%d carte(s) %s/%s pour « %s » [%s] dans %s",
        len(series.cards), fmt, style, topic.id, lang, out_dir,
    )
    return series


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    import image_sourcing
    import topic_loader

    parser = argparse.ArgumentParser(description="Produit une serie de cartes visuelles.")
    parser.add_argument("topic_id")
    parser.add_argument("--lang", default="fr", choices=list(topic_loader.SUPPORTED_LANGS))
    parser.add_argument("--format", default=DEFAULT_FORMAT, choices=list(CARD_FORMATS))
    parser.add_argument("--style", default="photo", choices=["photo", "poster"])
    parser.add_argument("--count", type=int, default=5)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stdout
    )

    topics = {t.id: t for t in topic_loader.load_topics(only_ready=False)}
    topic = topics.get(args.topic_id)
    if topic is None:
        logger.error(
            "Sujet inconnu : %s. Disponibles : %s",
            args.topic_id, ", ".join(sorted(topics)) or "(aucun)",
        )
        return 1

    images = image_sourcing.fetch_for_topic(
        topic.image_queries, max(args.count, 4), Path("content/images") / topic.id
    )
    if not images:
        logger.error("Aucune image exploitable pour « %s ».", topic.id)
        return 1

    series = build_series(
        topic, args.lang,
        [Path(i.local_path) for i in images if i.local_path],
        Path("content/cards") / topic.id,
        count=args.count, fmt=args.format, style=args.style,
        credits=image_sourcing.format_credits(images),
    )
    if not series.cards:
        logger.error("Aucune carte produite.")
        return 1

    print()
    for card in series.cards:
        print(f"{card.index}/{card.total}  {card.path}")
        print(f"        {card.text[:88]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
