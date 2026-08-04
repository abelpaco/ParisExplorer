"""Mémoire persistante des sujets déjà publiés sur la chaîne.

POURQUOI CE MODULE EXISTE
-------------------------
Avant lui, ``create_next_video()`` n'excluait que les sujets présents dans la
FILE D'ATTENTE courante. Dès qu'une vidéo était publiée, elle quittait la file
et son sujet redevenait éligible ; pire, une fois tous les sujets écartés, le
code repartait sur ``PARIS_TOPICS[0]``. Sur une chaîne publiant 3 fois par jour,
la première republication tombait en moins de trois jours — un motif que YouTube
sanctionne (contenu répétitif, faible valeur ajoutée).

Ce registre est donc la mémoire longue du projet : ce qui a été publié une fois
ne l'est jamais deux fois.

CHOIX DE CONCEPTION
-------------------
Le fichier d'état n'est **pas** gitignoré, à dessein. C'est contre-intuitif pour
de l'état d'exécution, mais le perdre (clone frais, reconstruction du conteneur,
volume Docker non monté) ferait exactement revenir le bug qu'on corrige. Un
fichier de quelques kilo-octets versionné vaut mieux qu'une republication.

Le registre est tolérant aux pannes : un fichier absent ou corrompu est traité
comme « rien de publié », jamais comme une erreur bloquante — mais il le SIGNALE
dans les logs, car un registre illisible expose à la republication.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_REGISTRY_PATH = Path("content/metadata/published_topics.json")


def _normalize(name: str) -> str:
    """Clé de comparaison d'un sujet : insensible à la casse et aux espaces."""
    return " ".join(name.lower().split())


class TopicRegistry:
    """Journal append-only des sujets publiés, persisté en JSON."""

    def __init__(self, path: Optional[Path | str] = None) -> None:
        self.path = Path(path) if path else DEFAULT_REGISTRY_PATH
        self._entries: List[Dict[str, Any]] = []
        self._load()

    # ------------------------------------------------------------------
    # Persistance
    # ------------------------------------------------------------------
    def _load(self) -> None:
        if not self.path.exists():
            logger.info("Registre des sujets absent (%s) — démarrage à vide.", self.path)
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            entries = raw.get("published", []) if isinstance(raw, dict) else []
            self._entries = [e for e in entries if isinstance(e, dict) and e.get("name")]
            logger.info("Registre des sujets chargé : %d publiés.", len(self._entries))
        except (json.JSONDecodeError, OSError) as exc:
            # On NE bloque pas, mais on alerte fort : un registre illisible, c'est
            # le risque de republier ce qui est deja en ligne.
            logger.error(
                "Registre des sujets ILLISIBLE (%s) : %s. "
                "Traité comme vide — risque de republication, vérifie ce fichier.",
                self.path,
                exc,
            )

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"published": self._entries}
        # Écriture atomique : un crash en cours d'écriture ne doit pas laisser un
        # registre tronqué, qui serait relu comme « rien de publié ».
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # ------------------------------------------------------------------
    # Lecture
    # ------------------------------------------------------------------
    def is_published(self, name: str) -> bool:
        """Ce sujet a-t-il déjà été publié ?"""
        key = _normalize(name)
        return any(_normalize(e["name"]) == key for e in self._entries)

    def published_names(self) -> List[str]:
        """Noms des sujets déjà publiés, dans l'ordre de publication."""
        return [e["name"] for e in self._entries]

    def remaining(self, topics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sujets de ``topics`` encore jamais publiés, ordre d'origine conservé."""
        return [t for t in topics if not self.is_published(t.get("name", ""))]

    # ------------------------------------------------------------------
    # Écriture
    # ------------------------------------------------------------------
    def mark_published(
        self, name: str, video_id: Optional[str] = None, title: Optional[str] = None
    ) -> None:
        """Enregistre un sujet comme publié. Idempotent."""
        if not name:
            return
        if self.is_published(name):
            logger.debug("Sujet déjà dans le registre : %s", name)
            return
        self._entries.append(
            {
                "name": name,
                "video_id": video_id,
                "title": title,
                "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )
        self._save()
        logger.info("Sujet enregistré comme publié : %s (%d au total)", name, len(self._entries))

    def __len__(self) -> int:
        return len(self._entries)
