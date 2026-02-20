"""
Video Creator Module
Generates realistic slideshow videos about Paris topics for ParisExplorer posts.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont
from moviepy import ImageClip, concatenate_videoclips

from content_manager import ContentItem

logger = logging.getLogger(__name__)

# Paris topics with rich content for video generation
PARIS_TOPICS: List[Dict[str, Any]] = [
    {
        "name": "Tour Eiffel",
        "subtitle": "Le symbole de Paris",
        "description": (
            "La Tour Eiffel, construite par Gustave Eiffel pour l'Exposition "
            "universelle de 1889, est le monument le plus visité du monde."
        ),
        "facts": [
            "Hauteur : 330 mètres avec antenne",
            "Construite en 1887–1889",
            "7 millions de visiteurs par an",
            "Peinte tous les 7 ans en trois teintes",
        ],
        "tags": ["Tour Eiffel", "Eiffel Tower", "Paris", "France", "Architecture"],
        "colors": {
            "bg": (15, 25, 50), "accent": (212, 175, 55), "text": (255, 255, 255),
        },
        "location": "Champ-de-Mars, Paris 7e",
    },
    {
        "name": "Musée du Louvre",
        "subtitle": "Le plus grand musée du monde",
        "description": (
            "Le Louvre abrite plus de 380 000 œuvres d'art dont la Joconde "
            "de Léonard de Vinci. Un voyage dans l'histoire de l'humanité."
        ),
        "facts": [
            "35 000 œuvres exposées",
            "Superficie : 72 735 m²",
            "Construit au XIIe siècle",
            "Pyramide de verre inaugurée en 1989",
        ],
        "tags": ["Louvre", "Musée", "Art", "Paris", "Culture", "Joconde"],
        "colors": {
            "bg": (20, 10, 40), "accent": (192, 160, 98), "text": (255, 255, 255),
        },
        "location": "Rue de Rivoli, Paris 1er",
    },
    {
        "name": "Montmartre",
        "subtitle": "Le village des artistes",
        "description": (
            "Montmartre, avec sa célèbre Basilique du Sacré-Cœur, est le quartier "
            "bohème de Paris, berceau des impressionnistes et de la vie artistique."
        ),
        "facts": [
            "Basilique du Sacré-Cœur inaugurée en 1914",
            "Quartier de Picasso et Modigliani",
            "Place du Tertre : des artistes depuis le XIXe s.",
            "Vue panoramique sur tout Paris",
        ],
        "tags": ["Montmartre", "Sacré-Cœur", "Paris", "Art", "Bohème", "Architecture"],
        "colors": {
            "bg": (35, 15, 45), "accent": (230, 200, 255), "text": (255, 255, 255),
        },
        "location": "Butte Montmartre, Paris 18e",
    },
    {
        "name": "Notre-Dame de Paris",
        "subtitle": "La cathédrale gothique",
        "description": (
            "Joyau de l'architecture gothique, Notre-Dame de Paris trône sur "
            "l'île de la Cité depuis le XIIe siècle. Sa renaissance après l'incendie "
            "de 2019 est un symbole de résilience."
        ),
        "facts": [
            "Construction : 1163–1345",
            "Hauteur des tours : 69 mètres",
            "Incendie majeur en avril 2019",
            "Réouverture en décembre 2024",
        ],
        "tags": [
            "Notre-Dame", "Cathédrale", "Paris", "Histoire", "Gothique", "Architecture",
        ],
        "colors": {
            "bg": (25, 20, 10), "accent": (200, 180, 120), "text": (255, 255, 255),
        },
        "location": "Île de la Cité, Paris 4e",
    },
    {
        "name": "Palais de Versailles",
        "subtitle": "La splendeur royale",
        "description": (
            "Résidence des rois de France de Louis XIV à Louis XVI, "
            "le Château de Versailles et ses jardins à la française "
            "incarnent le faste de la monarchie absolue."
        ),
        "facts": [
            "Superficie : 63 154 m² pour le château",
            "800 hectares de parc et jardins",
            "Galerie des Glaces : 357 miroirs",
            "Classé au Patrimoine mondial de l'UNESCO",
        ],
        "tags": ["Versailles", "Château", "Paris", "Royauté", "Histoire", "UNESCO"],
        "colors": {
            "bg": (10, 25, 15), "accent": (255, 215, 0), "text": (255, 255, 255),
        },
        "location": "Versailles, Île-de-France",
    },
    {
        "name": "Les Champs-Élysées",
        "subtitle": "La plus belle avenue du monde",
        "description": (
            "Longue de 1,9 km et large de 70 mètres, l'avenue des Champs-Élysées "
            "relie la Place de la Concorde à l'Arc de Triomphe, "
            "symbole du prestige parisien."
        ),
        "facts": [
            "Longueur : 1,91 km",
            "Largeur : 70 mètres",
            "Défilé du 14-Juillet depuis 1918",
            "Arc de Triomphe : 50 mètres de haut",
        ],
        "tags": [
            "Champs-Élysées", "Arc de Triomphe",
            "Paris", "Avenue", "France", "Tourisme",
        ],
        "colors": {
            "bg": (10, 15, 35), "accent": (220, 220, 255), "text": (255, 255, 255),
        },
        "location": "Paris 8e",
    },
    {
        "name": "Le Marais",
        "subtitle": "Histoire et tendances",
        "description": (
            "Ancien quartier aristocratique, le Marais mêle hôtels particuliers "
            "du XVIIe siècle, galeries d'art contemporain et vie branchée "
            "autour de la Place des Vosges."
        ),
        "facts": [
            "Place des Vosges : plus ancienne place de Paris (1612)",
            "Centre Pompidou inauguré en 1977",
            "Musée Picasso et Musée Carnavalet",
            "Quartier LGBTQ+ historique de Paris",
        ],
        "tags": ["Marais", "Paris", "Histoire", "Architecture", "Art", "Culture"],
        "colors": {
            "bg": (30, 10, 10), "accent": (255, 180, 120), "text": (255, 255, 255),
        },
        "location": "Paris 3e–4e",
    },
    {
        "name": "Musée d'Orsay",
        "subtitle": "L'impressionnisme en majesté",
        "description": (
            "Installé dans une ancienne gare ferroviaire, le Musée d'Orsay "
            "abrite la plus grande collection d'art impressionniste et "
            "post-impressionniste au monde."
        ),
        "facts": [
            "Ancienne gare d'Orsay inaugurée en 1900",
            "Transformée en musée en 1986",
            "3 000 œuvres exposées",
            "Monet, Renoir, Van Gogh, Cézanne...",
        ],
        "tags": ["Orsay", "Impressionnisme", "Musée", "Paris", "Art", "Culture"],
        "colors": {
            "bg": (15, 30, 40), "accent": (150, 210, 240), "text": (255, 255, 255),
        },
        "location": "Quai Anatole France, Paris 7e",
    },
]

# Video dimensions (16:9 aspect ratio, standard HD)
VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720

# Slide durations in seconds
DURATION_TITLE = 4
DURATION_CONTENT = 5
DURATION_OUTRO = 3


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """Load a TrueType font, falling back to the default if unavailable."""
    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:\\Windows\\Fonts\\arial.ttf",
    ]
    for path in font_candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except IOError:
                continue
    # Pillow built-in fallback (limited sizing)
    return ImageFont.load_default()


def _draw_gradient_background(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    color_top: Tuple[int, int, int],
    color_bottom: Tuple[int, int, int],
) -> None:
    """Draw a vertical gradient background."""
    for y in range(height):
        ratio = y / height
        r = int(color_top[0] + (color_bottom[0] - color_top[0]) * ratio)
        g = int(color_top[1] + (color_bottom[1] - color_top[1]) * ratio)
        b = int(color_top[2] + (color_bottom[2] - color_top[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))


def _draw_decorative_lines(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    accent: Tuple[int, int, int],
) -> None:
    """Draw decorative horizontal accent lines."""
    line_y_top = int(height * 0.12)
    line_y_bottom = int(height * 0.88)
    lw = max(2, int(height * 0.004))
    draw.rectangle([40, line_y_top, width - 40, line_y_top + lw], fill=accent)
    draw.rectangle([40, line_y_bottom, width - 40, line_y_bottom + lw], fill=accent)


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    """Wrap text to fit within max_width pixels."""
    words = text.split()
    lines: List[str] = []
    current = ""
    dummy_img = Image.new("RGB", (1, 1))
    dummy_draw = ImageDraw.Draw(dummy_img)
    for word in words:
        test = f"{current} {word}".strip()
        bbox = dummy_draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _create_title_slide(topic: Dict[str, Any]) -> Image.Image:
    """Create the title/intro slide for a topic."""
    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT))
    draw = ImageDraw.Draw(img)

    bg = topic["colors"]["bg"]
    accent = topic["colors"]["accent"]
    text_color = topic["colors"]["text"]

    # Darker variant for bottom of gradient
    bg_bottom = tuple(max(0, c - 25) for c in bg)
    _draw_gradient_background(draw, VIDEO_WIDTH, VIDEO_HEIGHT, bg, bg_bottom)
    _draw_decorative_lines(draw, VIDEO_WIDTH, VIDEO_HEIGHT, accent)

    # Brand tag (top-left)
    brand_font = _load_font(22)
    draw.text((50, 30), "ParisExplorer", font=brand_font, fill=accent)

    # Main title
    title_font = _load_font(72)
    title_lines = _wrap_text(topic["name"], title_font, VIDEO_WIDTH - 120)
    total_h = len(title_lines) * 82
    start_y = (VIDEO_HEIGHT - total_h) // 2 - 40
    for i, line in enumerate(title_lines):
        bbox = draw.textbbox((0, 0), line, font=title_font)
        x = (VIDEO_WIDTH - (bbox[2] - bbox[0])) // 2
        draw.text((x, start_y + i * 82), line, font=title_font, fill=text_color)

    # Subtitle
    sub_font = _load_font(36)
    sub_bbox = draw.textbbox((0, 0), topic["subtitle"], font=sub_font)
    sx = (VIDEO_WIDTH - (sub_bbox[2] - sub_bbox[0])) // 2
    sy = start_y + total_h + 20
    draw.text((sx, sy), topic["subtitle"], font=sub_font, fill=accent)

    # Location tag (bottom-right)
    loc_font = _load_font(20)
    loc_text = f"📍 {topic['location']}"
    loc_bbox = draw.textbbox((0, 0), loc_text, font=loc_font)
    draw.text(
        (VIDEO_WIDTH - (loc_bbox[2] - loc_bbox[0]) - 50, VIDEO_HEIGHT - 50),
        loc_text,
        font=loc_font,
        fill=accent,
    )

    return img


def _create_description_slide(topic: Dict[str, Any]) -> Image.Image:
    """Create the description slide for a topic."""
    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT))
    draw = ImageDraw.Draw(img)

    bg = topic["colors"]["bg"]
    accent = topic["colors"]["accent"]
    text_color = topic["colors"]["text"]

    bg_bottom = tuple(max(0, c - 20) for c in bg)
    _draw_gradient_background(draw, VIDEO_WIDTH, VIDEO_HEIGHT, bg, bg_bottom)
    _draw_decorative_lines(draw, VIDEO_WIDTH, VIDEO_HEIGHT, accent)

    # Brand tag
    brand_font = _load_font(22)
    draw.text((50, 30), "ParisExplorer", font=brand_font, fill=accent)

    # Section heading
    heading_font = _load_font(40)
    draw.text((50, 100), "À découvrir", font=heading_font, fill=accent)

    # Description text
    desc_font = _load_font(30)
    desc_lines = _wrap_text(topic["description"], desc_font, VIDEO_WIDTH - 120)
    y = 170
    for line in desc_lines:
        draw.text((60, y), line, font=desc_font, fill=text_color)
        y += 44

    return img


def _create_facts_slide(topic: Dict[str, Any]) -> Image.Image:
    """Create a slide listing key facts about the topic."""
    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT))
    draw = ImageDraw.Draw(img)

    bg = topic["colors"]["bg"]
    accent = topic["colors"]["accent"]
    text_color = topic["colors"]["text"]

    bg_bottom = tuple(max(0, c - 20) for c in bg)
    _draw_gradient_background(draw, VIDEO_WIDTH, VIDEO_HEIGHT, bg, bg_bottom)
    _draw_decorative_lines(draw, VIDEO_WIDTH, VIDEO_HEIGHT, accent)

    # Brand tag
    brand_font = _load_font(22)
    draw.text((50, 30), "ParisExplorer", font=brand_font, fill=accent)

    # Section heading
    heading_font = _load_font(40)
    draw.text((50, 100), "Le saviez-vous ?", font=heading_font, fill=accent)

    # Facts list
    fact_font = _load_font(28)
    y = 185
    for fact in topic["facts"]:
        # Bullet point accent rectangle
        draw.rectangle([50, y + 10, 60, y + 26], fill=accent)
        draw.text((75, y), fact, font=fact_font, fill=text_color)
        y += 56

    return img


def _create_outro_slide(topic: Dict[str, Any]) -> Image.Image:
    """Create the outro / call-to-action slide."""
    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT))
    draw = ImageDraw.Draw(img)

    bg = topic["colors"]["bg"]
    accent = topic["colors"]["accent"]
    text_color = topic["colors"]["text"]

    bg_bottom = tuple(max(0, c - 30) for c in bg)
    _draw_gradient_background(draw, VIDEO_WIDTH, VIDEO_HEIGHT, bg, bg_bottom)
    _draw_decorative_lines(draw, VIDEO_WIDTH, VIDEO_HEIGHT, accent)

    # Brand name (large, centred)
    brand_big_font = _load_font(80)
    brand_text = "ParisExplorer"
    bb = draw.textbbox((0, 0), brand_text, font=brand_big_font)
    bx = (VIDEO_WIDTH - (bb[2] - bb[0])) // 2
    by = VIDEO_HEIGHT // 2 - 80
    draw.text((bx, by), brand_text, font=brand_big_font, fill=accent)

    # Tagline
    tag_font = _load_font(30)
    tagline = "Abonnez-vous pour explorer Paris avec nous !"
    tb = draw.textbbox((0, 0), tagline, font=tag_font)
    tx = (VIDEO_WIDTH - (tb[2] - tb[0])) // 2
    draw.text((tx, by + 100), tagline, font=tag_font, fill=text_color)

    # Topic credit at bottom
    credit_font = _load_font(22)
    credit = f"Épisode : {topic['name']}"
    cb = draw.textbbox((0, 0), credit, font=credit_font)
    cx = (VIDEO_WIDTH - (cb[2] - cb[0])) // 2
    draw.text((cx, VIDEO_HEIGHT - 60), credit, font=credit_font, fill=accent)

    return img


def _image_to_clip(img: Image.Image, duration: float) -> ImageClip:
    """Convert a PIL Image to a moviepy ImageClip with the given duration."""
    import numpy as np
    arr = np.array(img)
    return ImageClip(arr, duration=duration)


class ParisVideoCreator:
    """
    Creates slideshow videos about Paris landmarks and topics
    ready to be uploaded via the ParisExplorer automation pipeline.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the video creator.

        Args:
            config: Application configuration dictionary (from config.yaml).
        """
        self.config = config
        vc_cfg = config.get("video_creator", {})
        self.output_dir = Path(vc_cfg.get("output_dir", "./content/videos"))
        self.fps = int(vc_cfg.get("fps", 24))
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_available_topics(self) -> List[Dict[str, Any]]:
        """Return the list of available Paris topics."""
        return PARIS_TOPICS

    def create_video_for_topic(
        self, topic: Dict[str, Any]
    ) -> Optional[ContentItem]:
        """
        Generate a slideshow video for the given topic dict and return a
        ContentItem ready to be added to the content queue.

        Args:
            topic: A topic dictionary (as found in PARIS_TOPICS).

        Returns:
            ContentItem with the generated video, or None on failure.
        """
        topic_slug = topic["name"].lower().replace(" ", "_").replace("'", "")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"paris_{topic_slug}_{timestamp}.mp4"
        output_path = self.output_dir / output_filename

        logger.info("Creating video for topic: %s", topic["name"])

        try:
            video_path = self._build_video(topic, output_path)
        except Exception as exc:
            logger.error("Failed to create video for '%s': %s", topic["name"], exc)
            return None

        # Build rich YouTube description
        description = self._build_description(topic)
        youtube_cfg = self.config.get("youtube", {})
        default_tags: List[str] = youtube_cfg.get("default_tags", [])
        all_tags = list(dict.fromkeys(topic["tags"] + default_tags))

        item = ContentItem(
            content_type="video",
            title=f"{topic['name']} - {topic['subtitle']} | ParisExplorer",
            description=description,
            file_path=str(video_path),
            tags=all_tags,
            metadata={
                "topic": topic["name"],
                "location": topic["location"],
                "generated_by": "ParisVideoCreator",
            },
        )

        logger.info("Video created: %s", video_path)
        return item

    def create_video_by_name(self, topic_name: str) -> Optional[ContentItem]:
        """
        Find a topic by name and create its video.

        Args:
            topic_name: Exact or partial (case-insensitive) name of the topic.

        Returns:
            ContentItem or None.
        """
        name_lower = topic_name.lower()
        for topic in PARIS_TOPICS:
            if name_lower in topic["name"].lower():
                return self.create_video_for_topic(topic)
        logger.warning("No topic found matching: %s", topic_name)
        return None

    def create_next_video(
        self, exclude_names: Optional[List[str]] = None
    ) -> Optional[ContentItem]:
        """
        Create a video for the next topic not already in the exclusion list.

        Args:
            exclude_names: List of topic names to skip.

        Returns:
            ContentItem or None.
        """
        skip = {n.lower() for n in (exclude_names or [])}
        for topic in PARIS_TOPICS:
            if topic["name"].lower() not in skip:
                return self.create_video_for_topic(topic)
        logger.warning("All topics have been excluded; cycling back to first topic.")
        return self.create_video_for_topic(PARIS_TOPICS[0])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_video(self, topic: Dict[str, Any], output_path: Path) -> Path:
        """Assemble slides into an MP4 file and return its path."""
        slides = [
            (DURATION_TITLE, _create_title_slide(topic)),
            (DURATION_CONTENT, _create_description_slide(topic)),
            (DURATION_CONTENT, _create_facts_slide(topic)),
            (DURATION_OUTRO, _create_outro_slide(topic)),
        ]

        clips = [_image_to_clip(img, float(dur)) for dur, img in slides]
        final = concatenate_videoclips(clips)

        final.write_videofile(
            str(output_path),
            fps=self.fps,
            codec="libx264",
            audio=False,
            logger=None,  # suppress moviepy progress bars in logs
        )

        final.close()
        for clip in clips:
            clip.close()

        return output_path

    @staticmethod
    def _build_description(topic: Dict[str, Any]) -> str:
        """Build a rich YouTube description for the topic."""
        facts_block = "\n".join(f"• {f}" for f in topic["facts"])
        tags_block = " ".join(f"#{t.replace(' ', '')}" for t in topic["tags"])
        return (
            f"{topic['description']}\n\n"
            f"📍 {topic['location']}\n\n"
            f"🗺️ Points clés :\n{facts_block}\n\n"
            f"🎬 Découvrez Paris avec ParisExplorer !\n\n"
            f"{tags_block} #ParisExplorer #Paris #France #Travel"
        )
