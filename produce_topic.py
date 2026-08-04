"""Produit tout ce qu'il faut pour publier UN sujet, dans UNE langue.

Enchaine les quatre briques du projet — sujet, images, voix, montage — et ecrit
a cote de la video les metadonnees pretes a coller sur YouTube, credits
d'images compris.

Ce script NE PUBLIE RIEN. Il fabrique des fichiers, on les regarde, et la
publication reste une decision separee. C'est volontaire : tant que la chaine
n'a pas repris un rythme sain, chaque video doit pouvoir etre jugee avant
d'exister publiquement.

Usage :
    python produce_topic.py tour-eiffel --lang fr
    python produce_topic.py tour-eiffel --lang en --no-shorts
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import image_sourcing
import narration
import topic_loader
import video_assembly

logger = logging.getLogger("produce")

OUTPUT_ROOT = Path("content/videos")
IMAGE_ROOT = Path("content/images")
AUDIO_ROOT = Path("content/audio")

# Nombre d'images ramenees par sujet. Le montage les recycle pour tenir la
# cadence, mais en dessous de six le diaporama tourne en rond de facon visible.
IMAGES_PER_TOPIC = 8


@dataclass
class Production:
    """Ce qui a ete fabrique pour un sujet et une langue."""

    topic_id: str
    lang: str
    title: str
    description: str
    tags: List[str]
    video: Optional[Path] = None
    shorts: List[Path] = field(default_factory=list)
    duration: float = 0.0
    image_count: int = 0

    def as_dict(self) -> dict:
        return {
            "topic_id": self.topic_id,
            "lang": self.lang,
            "title": self.title,
            "description": self.description,
            "tags": self.tags,
            "video": str(self.video) if self.video else None,
            "shorts": [str(s) for s in self.shorts],
            "duration_seconds": round(self.duration, 2),
            "image_count": self.image_count,
        }


def build_description(topic: topic_loader.Topic, lang: str, images) -> str:
    """Description YouTube : accroche, puis credits obligatoires.

    Les credits ne sont pas une politesse : la plupart des images de Commons
    sont sous CC BY ou CC BY-SA, qui EXIGENT l'attribution. Retirer ce bloc
    rendrait la video contrefaisante.
    """
    text = topic.text(lang)
    intro = text.subtitle or text.title

    if lang == "fr":
        pitch = (
            f"{intro}\n\n"
            "Paris Explorer — l'histoire, les monuments et l'actualite de Paris, "
            "en quelques minutes."
        )
    else:
        pitch = (
            f"{intro}\n\n"
            "Paris Explorer — the history, landmarks and news of Paris, "
            "in a few minutes."
        )

    credits = image_sourcing.format_credits(images)
    return f"{pitch}\n\n{credits}".strip() if credits else pitch


def produce(
    topic: topic_loader.Topic,
    lang: str,
    *,
    with_shorts: bool = True,
    force_audio: bool = False,
    output_root: Optional[Path] = None,
) -> Production:
    """Fabrique la video (et ses Shorts) d'un sujet dans une langue.

    Args:
        topic: sujet charge depuis ``content/topics``.
        lang: langue de la narration et des metadonnees.
        with_shorts: produire aussi la declinaison verticale.
        force_audio: ignorer le cache de voix off.
        output_root: dossier des videos. Vient de ``video_creator.output_dir``
            quand l'appel passe par l'automatisation ; sans lui, ce module
            ecrirait ailleurs que la configuration ne le dit.
    """
    videos_root = Path(output_root) if output_root else OUTPUT_ROOT
    text = topic.text(lang)
    logger.info(
        "Sujet « %s » [%s] — %d mots de narration.", topic.id, lang, text.word_count
    )

    # 1. Images. Elles servent aux deux langues : un seul telechargement.
    image_dir = IMAGE_ROOT / topic.id
    images = image_sourcing.fetch_for_topic(topic.image_queries, IMAGES_PER_TOPIC, image_dir)
    if not images:
        raise RuntimeError(
            f"Aucune image exploitable pour « {topic.id} » : verifie les "
            f"image_queries du sujet (trop precises ?)."
        )
    if len(images) < 4:
        logger.warning(
            "Seulement %d image(s) pour « %s » : le diaporama va se repeter.",
            len(images), topic.id,
        )

    # 2. Voix off. Une synthese ratee doit ARRETER la production : publier une
    # video muette serait pire que ne rien publier.
    audio_dir = AUDIO_ROOT / topic.id
    voice = narration.synthesize(
        text.narration, lang, audio_dir / f"{topic.id}-{lang}.mp3", force=force_audio
    )
    logger.info("Voix off : %.1f s (%.2f min), voix %s.", voice.duration, voice.minutes, voice.voice)

    # 3. Montage principal (paysage).
    out_dir = videos_root / topic.id
    sources = [Path(image.local_path) for image in images if image.local_path]
    result = video_assembly.assemble(
        sources, voice.path, out_dir / f"{topic.id}-{lang}.mp4"
    )

    production = Production(
        topic_id=topic.id,
        lang=lang,
        title=text.title,
        description=build_description(topic, lang, images),
        tags=text.tags,
        video=result.path,
        duration=result.duration,
        image_count=result.image_count,
    )

    # 4. Shorts verticaux, decoupes sur les silences de la narration.
    if with_shorts:
        production.shorts = video_assembly.build_shorts(
            sources, voice.path, out_dir / "shorts", f"{topic.id}-{lang}"
        )

    # 5. Metadonnees, a cote de la video : titre, description creditee, tags.
    meta_path = out_dir / f"{topic.id}-{lang}.json"
    meta_path.write_text(
        json.dumps(production.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Metadonnees ecrites : %s", meta_path)
    return production


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Produit la video d'un sujet.")
    parser.add_argument("topic_id", help="identifiant du sujet (nom du fichier YAML)")
    parser.add_argument("--lang", default="fr", choices=list(topic_loader.SUPPORTED_LANGS))
    parser.add_argument("--no-shorts", action="store_true", help="ne pas produire les Shorts")
    parser.add_argument("--force-audio", action="store_true", help="ignorer le cache de voix")
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

    try:
        production = produce(
            topic, args.lang,
            with_shorts=not args.no_shorts,
            force_audio=args.force_audio,
        )
    except (RuntimeError, narration.NarrationError, video_assembly.AssemblyError) as exc:
        logger.error("Production interrompue : %s", exc)
        return 1

    print()
    print(f"TITRE   : {production.title}")
    print(f"DUREE   : {production.duration:.0f} s ({production.duration/60:.2f} min)")
    print(f"VIDEO   : {production.video}")
    print(f"SHORTS  : {len(production.shorts)}")
    for short in production.shorts:
        print(f"          {short}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
