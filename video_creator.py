"""Production des videos de la chaine, pilotee par les sujets YAML.

CE QUI A CHANGE, ET POURQUOI
----------------------------
Ce module fabriquait des diaporamas de TEXTE : quatre cartons dessines avec
Pillow, sans image ni voix, a partir d'une liste ``PARIS_TOPICS`` de huit sujets
codee en dur. Deux impasses : le format ne ressemblait pas a ce qu'on regarde
sur YouTube, et ajouter un sujet demandait de modifier du code — la chaine
plafonnait a huit videos avant de republier.

Desormais un sujet est un fichier YAML (``content/topics/*.yaml``) et la video
est fabriquee par la vraie chaine de production : photos creditees de Wikimedia,
voix off de synthese, montage anime cale sur la narration. Le detail de cette
chaine vit dans ``produce_topic``, ce module n'en est que le pilote pour
l'automatisation.

LA CLE DU REGISTRE PORTE LA LANGUE
----------------------------------
Un sujet donne fait DEUX videos, une par langue. Le registre anti-republication
est donc indexe sur ``sujet:langue`` et non sur le seul sujet : sans cela,
publier la version francaise marquerait le sujet comme fait et la version
anglaise ne sortirait jamais.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import produce_topic
import topic_loader
from content_manager import ContentItem
from topic_registry import TopicRegistry

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGES = ("fr", "en")


def registry_key(topic_id: str, lang: str) -> str:
    """Cle d'un couple sujet/langue dans le registre des publications."""
    return f"{topic_id}:{lang}"


class ParisVideoCreator:
    """Produit les videos de la chaine a partir des sujets YAML."""

    def __init__(
        self, config: Dict[str, Any], registry: Optional[TopicRegistry] = None
    ):
        """
        Args:
            config: configuration de l'application (config.yaml).
            registry: memoire des sujets deja publies. Injectable pour les
                tests ; par defaut, le registre persistant du projet.
        """
        self.config = config
        vc_cfg = config.get("video_creator", {})
        self.output_dir = Path(vc_cfg.get("output_dir", "./content/videos"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.languages: List[str] = list(vc_cfg.get("languages", DEFAULT_LANGUAGES))
        self.with_shorts: bool = bool(vc_cfg.get("shorts", True))
        self.registry = registry or TopicRegistry()

    # ------------------------------------------------------------------
    # Sujets disponibles
    # ------------------------------------------------------------------

    def get_available_topics(self) -> List[Dict[str, Any]]:
        """Tous les couples sujet/langue publiables, sujets en ``ready`` seuls.

        Une entree par langue et par sujet : c'est cette granularite que voient
        le registre et la file d'attente.
        """
        candidates: List[Dict[str, Any]] = []
        for topic in topic_loader.load_topics():
            for lang in self.languages:
                if lang not in topic.langs:
                    logger.info(
                        "Sujet « %s » : pas de narration '%s', langue ignoree.",
                        topic.id, lang,
                    )
                    continue
                candidates.append(
                    {
                        "name": registry_key(topic.id, lang),
                        "topic_id": topic.id,
                        "lang": lang,
                        "title": topic.text(lang).title,
                        "category": topic.category,
                    }
                )
        return candidates

    # ------------------------------------------------------------------
    # Production
    # ------------------------------------------------------------------

    def create_video_for_topic(self, topic: Dict[str, Any]) -> Optional[ContentItem]:
        """Produit la video d'un couple sujet/langue.

        Args:
            topic: entree renvoyee par :meth:`get_available_topics`.

        Returns:
            Le ``ContentItem`` pret pour la file d'attente, ou ``None`` si la
            production a echoue. Un echec ne doit JAMAIS produire un item
            degrade : mieux vaut ne rien publier qu'une video muette ou sans
            images.
        """
        topic_id = topic["topic_id"]
        lang = topic["lang"]

        loaded = {t.id: t for t in topic_loader.load_topics(only_ready=False)}
        source = loaded.get(topic_id)
        if source is None:
            logger.error("Sujet introuvable dans content/topics : %s", topic_id)
            return None

        logger.info("Production de « %s » en %s.", topic_id, lang)
        try:
            production = produce_topic.produce(
                source, lang,
                with_shorts=self.with_shorts,
                output_root=self.output_dir,
            )
        except Exception as exc:
            logger.error("Production echouee pour « %s » [%s] : %s", topic_id, lang, exc)
            return None

        youtube_cfg = self.config.get("youtube", {})
        default_tags: List[str] = youtube_cfg.get("default_tags", [])
        all_tags = list(dict.fromkeys(production.tags + default_tags))

        item = ContentItem(
            content_type="video",
            title=production.title,
            description=production.description,
            file_path=str(production.video),
            tags=all_tags,
            metadata={
                # `topic` est la cle du registre : elle DOIT porter la langue.
                "topic": registry_key(topic_id, lang),
                "topic_id": topic_id,
                "lang": lang,
                "category": source.category,
                "duration_seconds": round(production.duration, 2),
                "shorts": [str(s) for s in production.shorts],
                "generated_by": "ParisVideoCreator",
            },
        )
        logger.info(
            "Video prete : %s (%.0f s, %d Short(s)).",
            production.video, production.duration, len(production.shorts),
        )
        return item

    def create_video_by_name(self, topic_name: str) -> Optional[ContentItem]:
        """Produit la video d'un sujet designe par son identifiant ou son titre.

        Accepte ``tour-eiffel``, ``tour-eiffel:en``, ou un fragment de titre.
        Sans langue precisee, prend la premiere langue configuree.
        """
        wanted = topic_name.strip().lower()
        candidates = self.get_available_topics()

        for candidate in candidates:
            if wanted == candidate["name"].lower():
                return self.create_video_for_topic(candidate)

        for candidate in candidates:
            if wanted == candidate["topic_id"].lower() or wanted in candidate["title"].lower():
                return self.create_video_for_topic(candidate)

        logger.warning(
            "Aucun sujet ne correspond a « %s ». Disponibles : %s",
            topic_name,
            ", ".join(sorted({c["topic_id"] for c in candidates})) or "(aucun)",
        )
        return None

    def create_next_video(
        self, exclude_names: Optional[List[str]] = None
    ) -> Optional[ContentItem]:
        """Produit la prochaine video ni en file d'attente, ni deja publiee.

        Deux filtres, et pas un seul : ``exclude_names`` ne couvre que la file
        COURANTE, donc un sujet publie puis retire de la file redeviendrait
        eligible. Le registre persistant apporte la memoire longue.

        Returns:
            Le ``ContentItem`` produit, ou ``None`` quand il n'y a plus rien a
            publier.
        """
        skip = {n.lower() for n in (exclude_names or []) if n}
        candidates = self.get_available_topics()

        if not candidates:
            logger.error(
                "Aucun sujet publiable dans content/topics : verifie que les "
                "fichiers YAML existent et sont en « status: ready »."
            )
            return None

        for candidate in self.registry.remaining(candidates):
            if candidate["name"].lower() not in skip:
                return self.create_video_for_topic(candidate)

        # Volontairement AUCUN repli sur le premier sujet : republier ferait
        # courir un risque de sanction a une chaine reelle. On prefere ne rien
        # produire et le dire fort — c'est le signal qu'il faut ecrire de
        # nouveaux sujets.
        logger.error(
            "Plus rien a publier : %d couple(s) sujet/langue deja publie(s), "
            "%d en file, %d au catalogue. Ajoute des sujets dans "
            "content/topics — AUCUNE video ne sera generee (republier "
            "exposerait la chaine).",
            len(self.registry), len(skip), len(candidates),
        )
        return None
