"""Approvisionnement en photos reelles depuis Wikimedia Commons.

POURQUOI CE MODULE EXISTE
-------------------------
Le pipeline ne produisait qu'un diaporama de texte sur fond degrade : aucune
image de Paris n'apparaissait dans une chaine dont c'est pourtant le sujet.
Ce module fournit la matiere visuelle manquante — des photos libres de droits,
telechargees localement, ACCOMPAGNEES de leur credit.

LE CREDIT N'EST PAS UNE OPTION
------------------------------
La majorite des fichiers de Commons sont sous CC BY ou CC BY-SA : l'attribution
(auteur + licence) est une **obligation legale**, pas une politesse. Le module
applique donc une regle stricte et volontairement conservatrice :

    une image dont on ne sait pas reconstituer le credit n'est pas publiee.

Concretement, une licence non identifiee ecarte l'image, et un auteur illisible
ecarte l'image des que la licence exige l'attribution (toutes les CC BY*). Seuls
le domaine public et CC0 — qui n'imposent pas d'attribution — sont tolerees sans
auteur, et encore : elles sont alors creditees « auteur non precise » plutot que
silencieusement passees sous silence. Mieux vaut trois photos creditees que six
photos qui exposent la chaine a une reclamation.

CE QUE WIKIMEDIA EXIGE DE NOUS EN RETOUR
----------------------------------------
L'API est ouverte et sans cle, mais elle impose un User-Agent descriptif : les
requetes anonymes ou generiques (``python-requests/2.x``) sont bloquees par la
politique de l'infrastructure Wikimedia. D'ou ``USER_AGENT`` ci-dessous — le
modifier pour un libelle vague, c'est casser le module en production.

TOUTES les erreurs reseau sont absorbees : un pipeline de publication ne doit
jamais tomber parce que Commons a renvoye un 503. Une recherche qui echoue rend
une liste vide, et l'appelant reste libre de retomber sur le diaporama de texte.
"""

from __future__ import annotations

import html
import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

__all__ = [
    "ImageResult",
    "search_images",
    "fetch_for_topic",
    "format_credits",
]


# ---------------------------------------------------------------------------
# Constantes reseau
# ---------------------------------------------------------------------------

COMMONS_API_ENDPOINT = "https://commons.wikimedia.org/w/api.php"

# Wikimedia EXIGE un User-Agent identifiant le projet et permettant de nous
# joindre (https://foundation.wikimedia.org/wiki/Policy:User-Agent_policy). Un
# UA generique se fait blacklister ; ce n'est pas une convention de politesse.
_CONTACT = os.getenv("WIKIMEDIA_CONTACT", "https://github.com/ParisExplorer")
USER_AGENT = f"ParisExplorer/1.0 (YouTube automation about Paris; {_CONTACT})"

# (connexion, lecture) : une connexion qui ne s'etablit pas doit echouer vite,
# un telechargement d'image a le droit d'etre plus lent.
REQUEST_TIMEOUT = (10, 30)

# Largeur de la version redimensionnee demandee a Commons. Les originaux montent
# a 8000 px et pesent 30 Mo : inutile pour une video 1920x1080, et couteux.
THUMBNAIL_WIDTH = 1920

# Une image plus etroite que ca serait upscalee dans une video 1080p : floue.
MIN_IMAGE_WIDTH = 1280

# Garde-fou de telechargement : au-dela, c'est un panorama geant ou un scan, pas
# une photo exploitable en diaporama.
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024

# Un rapport largeur/hauteur extreme (panorama file, bandeau) donne, une fois
# insere dans un cadre 16/9, soit deux enormes bandes noires soit un recadrage
# qui ne montre plus rien.
MAX_ASPECT_RATIO = 3.0


# ---------------------------------------------------------------------------
# Constantes de filtrage
# ---------------------------------------------------------------------------

# Extensions gardees : uniquement des formats photo matriciels. Le SVG est
# exclu par nature (c'est du dessin vectoriel : logos, blasons, schemas), le
# GIF/TIF/PDF/DjVu ne sont pas des photos exploitables telles quelles.
_ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})

# Motifs de licence ACCEPTES (domaine public + CC libres).
_LICENSE_ALLOW = (
    re.compile(r"\bcc0\b"),
    re.compile(r"\bcc[\s\-_]?by(?![\s\-_]?n[cd])"),  # CC BY / CC BY-SA
    re.compile(r"public\s*domain"),
    re.compile(r"^pd(?:[\s\-_]|$)"),
    re.compile(r"\bpd[\s\-_]?(old|us|art|self|mark)\b"),
    re.compile(r"domaine\s*public"),
)

# Motifs REJETES, evalues en premier : ils gagnent toujours sur l'allow-list.
# « nc » (non commercial) et « nd » (no derivatives) sont incompatibles avec une
# chaine YouTube monetisable qui remonte les images.
_LICENSE_DENY = (
    re.compile(r"non[\s\-_]?free"),
    re.compile(r"fair[\s\-_]?use"),
    re.compile(r"\bnoncommercial\b|\bnon[\s\-_]commercial\b|\bcc[\s\-_]?by[\s\-_]?nc"),
    re.compile(r"\bnoderiv|\bcc[\s\-_]?by[\s\-_]?nd\b"),
    re.compile(r"\bcopyrighted\b"),
    re.compile(r"all\s+rights\s+reserved"),
    re.compile(r"\bunknown\b|\bunclear\b"),
)

# Licences n'imposant PAS d'attribution : seules celles-la peuvent survivre a un
# auteur introuvable (voir la doctrine en tete de module).
_NO_ATTRIBUTION_REQUIRED = (
    re.compile(r"\bcc0\b"),
    re.compile(r"public\s*domain"),
    re.compile(r"^pd(?:[\s\-_]|$)"),
    re.compile(r"\bpd[\s\-_]?(old|us|art|self|mark)\b"),
    re.compile(r"domaine\s*public"),
)

# Titres de fichiers qui ne sont pas des photos de terrain. Filtre par MOT
# entier : « map » ne doit pas eliminer « Champ de Mars ».
_NON_PHOTO_TITLE_WORDS = re.compile(
    r"\b("
    r"logo|logos|icon|icone|pictogram|pictogramme|"
    r"map|maps|carte|cartes|plan|plans|cadastre|"
    r"diagram|diagramme|schema|schematic|chart|graph|graphique|"
    # Separateur tolerant : les noms de fichiers Commons ecrivent aussi bien
    # "Coat of arms" que "Coat-of-Arms".
    r"coat[\s\-_]+of[\s\-_]+arms|blason|armoiries|flag|drapeau|seal|sceau|"
    r"banner|banniere|stub|template|modele|"
    r"signature|timbre|stamp|blueprint"
    r")\b",
    re.IGNORECASE,
)

_UNKNOWN_AUTHOR_MARKERS = re.compile(
    r"^(unknown|unknown\s+author|inconnu|auteur\s+inconnu|anonymous|anonyme|n/?a|-+)$",
    re.IGNORECASE,
)

_PLACEHOLDER_AUTHOR = "Auteur non precise"


# ---------------------------------------------------------------------------
# Modele
# ---------------------------------------------------------------------------


@dataclass
class ImageResult:
    """Une image de Commons, avec tout ce qu'il faut pour la crediter.

    ``local_path`` vaut ``None`` tant que l'image n'a pas ete telechargee :
    :func:`search_images` ne fait que decrire des candidates, c'est
    :func:`fetch_for_topic` qui les materialise sur le disque.
    """

    title: str
    author: str
    license_name: str
    license_url: str
    commons_url: str
    source_url: str
    width: int  # dimensions du fichier RECUPERE (le rendu 1920 px), pas de
    height: int  # l'original Commons qui peut faire 8000 px
    page_id: int
    # Nom de fichier brut sur Commons ("Cour_Napoleon.jpg"), conserve parce que
    # `title` est, lui, nettoye pour l'affichage et perd son extension.
    file_name: str = ""
    query: str = ""
    local_path: Optional[Path] = None

    @property
    def is_downloaded(self) -> bool:
        """L'image est-elle presente sur le disque et non vide ?"""
        return (
            self.local_path is not None
            and self.local_path.exists()
            and self.local_path.stat().st_size > 0
        )

    def attribution_line(self) -> str:
        """Ligne de credit d'une seule image, prete a etre affichee."""
        line = f"{self.title} — {self.author} ({self.license_name})"
        if self.license_url:
            line = f"{line} — {self.license_url}"
        return line


# ---------------------------------------------------------------------------
# Nettoyage des metadonnees
# ---------------------------------------------------------------------------


def _clean_html(raw: Any) -> str:
    """Reduit un champ ``extmetadata`` a du texte simple.

    Wikimedia ne renvoie PAS du texte brut : le champ ``Artist`` contient
    typiquement ``<a href="/wiki/User:X" title="User:X">Jean Dupont</a>``, et
    parfois plusieurs ``<span>`` de traduction empiles. Colle tel quel dans une
    description YouTube, ca donne du HTML visible — et un credit illisible.
    """
    if not isinstance(raw, str):
        return ""
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", raw)
    # Les elements `display:none` sont des doublons de microformat hCard que
    # Commons cache a l'affichage. Les garder produit "Unknown artistUnknown
    # artist" (cas reel : File:Men_river_Louvre_MAO690.jpg) : on les supprime
    # AVEC leur contenu, contrairement aux autres balises.
    text = re.sub(r"(?is)<(span|div)\b[^>]*display\s*:\s*none[^>]*>.*?</\1>", " ", text)
    # Toute fermeture de balise devient un separateur. Sans ca, les <span> de
    # traduction que Commons empile ressortent colles : le champ Artist de
    # File:Men_river_Louvre_MAO690.jpg donne litteralement
    # "Unknown artistUnknown artist".
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|td|span|bdi|a|b|i)>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", "", text)
    text = html.unescape(text)
    text = text.replace(" ", " ")
    text = re.sub(r"\s+", " ", text).strip()
    # Recolle la ponctuation : "Benh LIEU SONG (<a>Flickr</a>)" laisserait
    # sinon "(Flickr )", le separateur ajoute pour la balise fermante.
    text = re.sub(r"\s+([)\]},.;:!?])", r"\1", text)
    text = re.sub(r"([(\[{])\s+", r"\1", text)
    text = re.sub(r"\(\s*\)|\[\s*\]", "", text).strip()
    # Restes frequents de gabarits Commons.
    text = re.sub(r"^(?:by|par)\s+", "", text, flags=re.IGNORECASE).strip()
    return _collapse_repetition(text.strip(" ,;·|-"))


def _collapse_repetition(text: str) -> str:
    """Reduit « Unknown artist Unknown artist » a « Unknown artist ».

    Commons duplique souvent le meme credit dans plusieurs langues, chacune dans
    son propre ``<span>``. Une fois les balises retirees, la repetition devient
    visible — et un credit qui begaie discredite toute la description.
    """
    words = text.split(" ")
    if len(words) >= 2 and len(words) % 2 == 0:
        half = len(words) // 2
        if words[:half] == words[half:]:
            return " ".join(words[:half])
    return text


def _pretty_title(file_name: str) -> str:
    """Titre lisible a partir d'un nom de fichier Commons.

    « Cour_Napoleon_at_night_-_Louvre.jpg » n'a rien a faire tel quel dans une
    description YouTube : on retire l'extension et les tirets bas.
    """
    stem = Path(file_name).stem.replace("_", " ")
    return re.sub(r"\s+", " ", stem).strip() or file_name


def _extract(meta: Dict[str, Any], key: str) -> str:
    """Lit une entree ``extmetadata`` et la nettoie."""
    entry = meta.get(key)
    if isinstance(entry, dict):
        return _clean_html(entry.get("value"))
    return _clean_html(entry)


def _shorten(text: str, limit: int = 120) -> str:
    """Tronque proprement un credit trop bavard (certains font 400 signes)."""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _slugify(text: str, limit: int = 60) -> str:
    """Nom de fichier sur : sans accents, sans espace, sans caractere Windows."""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-").lower()
    return slug[:limit] or "image"


# ---------------------------------------------------------------------------
# Regles d'eligibilite
# ---------------------------------------------------------------------------


def _license_is_usable(*candidates: str) -> bool:
    """La licence est-elle exploitable (domaine public ou CC libre) ?

    Les motifs de rejet priment : un champ qui dit a la fois « CC BY » et
    « non-free » est rejete. En cas de doute, on ecarte.
    """
    blob = " ".join(c.lower() for c in candidates if c).strip()
    if not blob:
        return False
    if any(pattern.search(blob) for pattern in _LICENSE_DENY):
        return False
    return any(pattern.search(blob) for pattern in _LICENSE_ALLOW)


def _attribution_required(*candidates: str) -> bool:
    """L'attribution est-elle juridiquement exigee par cette licence ?"""
    blob = " ".join(c.lower() for c in candidates if c).strip()
    return not any(pattern.search(blob) for pattern in _NO_ATTRIBUTION_REQUIRED)


def _is_photo_title(title: str) -> bool:
    """Ecarte les fichiers qui ne sont manifestement pas des photos."""
    suffix = Path(title).suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        logger.debug("Ecarte (format %s non photo) : %s", suffix or "?", title)
        return False
    if _NON_PHOTO_TITLE_WORDS.search(title):
        logger.debug("Ecarte (logo/carte/schema d'apres le titre) : %s", title)
        return False
    return True


def _dimensions_are_usable(title: str, width: int, height: int) -> bool:
    """Ecarte les images trop petites ou de proportions inutilisables."""
    if width < MIN_IMAGE_WIDTH:
        logger.debug("Ecarte (%d px de large < %d) : %s", width, MIN_IMAGE_WIDTH, title)
        return False
    if height <= 0:
        return False
    ratio = max(width / height, height / width)
    if ratio > MAX_ASPECT_RATIO:
        logger.debug("Ecarte (proportions %.1f:1 inexploitables) : %s", ratio, title)
        return False
    return True


# ---------------------------------------------------------------------------
# Session HTTP
# ---------------------------------------------------------------------------

_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    """Session partagee : garde les connexions TLS ouvertes et porte le UA."""
    global _session
    if _session is None:
        session = requests.Session()
        session.headers.update(
            {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}
        )
        _session = session
    return _session


# ---------------------------------------------------------------------------
# Recherche
# ---------------------------------------------------------------------------


def _build_result(page: Dict[str, Any], query: str) -> Optional[ImageResult]:
    """Transforme une page d'API en :class:`ImageResult`, ou ``None`` si elle
    ne passe pas les filtres (format, taille, licence, credit)."""
    file_name = str(page.get("title", "")).removeprefix("File:").strip()
    if not file_name or not _is_photo_title(file_name):
        return None
    title = _pretty_title(file_name)

    infos = page.get("imageinfo") or []
    if not infos:
        logger.debug("Ecarte (aucun imageinfo) : %s", title)
        return None
    info = infos[0]

    # L'ELIGIBILITE se juge sur l'ORIGINAL : c'est lui qui dit si la photo est
    # nativement nette. Le rendu 1920 px, lui, fait toujours 1920 de large — le
    # tester reviendrait a n'ecarter personne. (Ces champs n'existent que si
    # `size` figure dans `iiprop` : l'oublier fait silencieusement tout passer
    # a 0 et vide le pipeline.)
    origin_width = int(info.get("width") or 0)
    origin_height = int(info.get("height") or 0)
    if not _dimensions_are_usable(title, origin_width, origin_height):
        return None

    # Ce qui est RENVOYE, en revanche, decrit le fichier reellement telecharge :
    # c'est cette taille-la que le montage video doit cadrer.
    width = int(info.get("thumbwidth") or origin_width)
    height = int(info.get("thumbheight") or origin_height)

    meta = info.get("extmetadata") or {}
    license_name = _extract(meta, "LicenseShortName")
    license_code = _extract(meta, "License")
    usage_terms = _extract(meta, "UsageTerms")
    license_url = _extract(meta, "LicenseUrl")

    if not _license_is_usable(license_name, license_code, usage_terms):
        logger.info(
            "Image ecartee, licence non exploitable (%s) : %s",
            license_name or license_code or usage_terms or "licence absente",
            title,
        )
        return None

    author = _extract(meta, "Artist") or _extract(meta, "Credit")
    if _UNKNOWN_AUTHOR_MARKERS.match(author or ""):
        author = ""
    if not author:
        if _attribution_required(license_name, license_code, usage_terms):
            # Le cas critique : licence CC BY sans auteur exploitable. On ne
            # publie pas — un credit incomplet vaut absence de credit.
            logger.info(
                "Image ecartee, auteur introuvable sous licence a attribution "
                "(%s) : %s",
                license_name or license_code,
                title,
            )
            return None
        author = _PLACEHOLDER_AUTHOR

    # Le thumb 1920 px suffit pour une video 1080p ; on ne rapatrie l'original
    # que si Commons n'a pas su le redimensionner.
    source_url = info.get("thumburl") or info.get("url") or ""
    if not source_url:
        logger.debug("Ecarte (aucune URL de fichier) : %s", title)
        return None

    return ImageResult(
        title=title,
        author=_shorten(author),
        license_name=_shorten(license_name or license_code, 60),
        license_url=license_url,
        commons_url=info.get("descriptionurl")
        or f"https://commons.wikimedia.org/wiki/File:{file_name.replace(' ', '_')}",
        source_url=source_url,
        width=width,
        height=height,
        page_id=int(page.get("pageid") or 0),
        file_name=file_name,
        query=query,
    )


def search_images(query: str, limit: int = 10) -> List[ImageResult]:
    """Cherche des photos exploitables sur Commons pour ``query``.

    Args:
        query: termes de recherche (l'anglais rend plus de resultats).
        limit: nombre de fichiers demandes a l'API. Le resultat en contient
            generalement MOINS : les filtres licence/credit/taille passent
            derriere.

    Returns:
        Les candidates retenues, non telechargees (``local_path`` a ``None``).
        Liste vide si la recherche echoue — jamais d'exception vers le pipeline.
    """
    query = (query or "").strip()
    if not query:
        return []
    limit = max(1, min(int(limit), 50))  # gsrlimit plafonne a 50 sans droits bot

    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": f"{query} filetype:bitmap",
        "gsrnamespace": 6,  # espace de noms « File: »
        "gsrlimit": limit,
        "prop": "imageinfo",
        # `size` est INDISPENSABLE : sans lui l'API ne renvoie ni `width` ni
        # `height`, le filtre de qualite lit 0 partout et ecarte absolument
        # toutes les images — panne silencieuse, aucune erreur HTTP.
        "iiprop": "url|size|extmetadata",
        "iiurlwidth": THUMBNAIL_WIDTH,
    }

    try:
        response = _get_session().get(
            COMMONS_API_ENDPOINT, params=params, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        logger.error("Recherche Commons en echec pour %r : %s", query, exc)
        return []
    except ValueError as exc:  # JSON illisible
        logger.error("Reponse Commons illisible pour %r : %s", query, exc)
        return []

    if "error" in payload:
        logger.error(
            "Commons a renvoye une erreur pour %r : %s", query, payload["error"]
        )
        return []

    pages = (payload.get("query") or {}).get("pages") or {}
    results: List[ImageResult] = []
    for page in pages.values():
        if not isinstance(page, dict):
            continue
        try:
            result = _build_result(page, query)
        except (TypeError, ValueError) as exc:
            logger.warning("Page Commons ignoree (metadonnees inattendues) : %s", exc)
            continue
        if result is not None:
            results.append(result)

    # L'API renvoie les pages dans un dict non ordonne : on retablit l'ordre de
    # pertinence de la recherche via l'index fourni par le generateur.
    results.sort(key=lambda r: _search_rank(pages, r.page_id))
    logger.info(
        "Commons %r : %d fichiers retournes, %d exploitables.",
        query,
        len(pages),
        len(results),
    )
    return results


def _search_rank(pages: Dict[str, Any], page_id: int) -> int:
    """Rang de pertinence d'une page dans la reponse du generateur."""
    for page in pages.values():
        if isinstance(page, dict) and int(page.get("pageid") or 0) == page_id:
            return int(page.get("index") or 999)
    return 999


# ---------------------------------------------------------------------------
# Telechargement + cache
# ---------------------------------------------------------------------------


class _TooLarge(Exception):
    """Le fichier depasse ``MAX_DOWNLOAD_BYTES`` — on abandonne en cours."""


def _local_name(image: ImageResult) -> str:
    """Nom de fichier local DETERMINISTE — c'est ce qui fait le cache.

    Le ``page_id`` prefixe le nom : c'est l'identifiant unique du fichier sur
    Commons, donc deux sujets qui reutilisent la meme photo tombent sur le meme
    fichier local, et un titre a accents ne casse pas le nommage.
    """
    suffix = Path(urlparse(image.source_url).path).suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        suffix = Path(image.file_name).suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        suffix = ".jpg"
    return f"{image.page_id}-{_slugify(image.title)}{suffix}"


def _download(image: ImageResult, dest_dir: Path) -> bool:
    """Telecharge l'image dans ``dest_dir``. Renvoie ``True`` si utilisable.

    Ne re-telecharge jamais un fichier deja present (cache local). En cas
    d'echec, l'ecriture partielle est supprimee : un fichier tronque en cache
    serait pire qu'une absence, il se ferait servir indefiniment.
    """
    target = dest_dir / _local_name(image)
    if target.exists() and target.stat().st_size > 0:
        image.local_path = target
        logger.debug("Cache : %s deja present.", target.name)
        return True

    tmp = target.with_suffix(target.suffix + ".part")
    try:
        with _get_session().get(
            image.source_url, timeout=REQUEST_TIMEOUT, stream=True
        ) as response:
            response.raise_for_status()

            content_type = response.headers.get("content-type", "").lower()
            if not content_type.startswith("image/"):
                logger.warning(
                    "Telechargement refuse, type %r au lieu d'une image : %s",
                    content_type,
                    image.title,
                )
                return False

            written = 0
            with open(tmp, "wb") as handle:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    written += len(chunk)
                    if written > MAX_DOWNLOAD_BYTES:
                        logger.warning(
                            "Telechargement interrompu, fichier > %d Mo : %s",
                            MAX_DOWNLOAD_BYTES // (1024 * 1024),
                            image.title,
                        )
                        raise _TooLarge(image.title)
                    handle.write(chunk)

        if written == 0:
            logger.warning("Fichier vide renvoye par Commons : %s", image.title)
            return False

        tmp.replace(target)
        image.local_path = target
        logger.info("Image telechargee (%d ko) : %s", written // 1024, target.name)
        return True

    except (requests.RequestException, OSError, _TooLarge) as exc:
        logger.error("Telechargement en echec pour %s : %s", image.title, exc)
        return False
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                logger.debug("Fichier temporaire non supprime : %s", tmp)


# ---------------------------------------------------------------------------
# Point d'entree du pipeline
# ---------------------------------------------------------------------------


def _interleave(groups: Sequence[List[ImageResult]]) -> Iterable[ImageResult]:
    """Alterne les resultats des differentes requetes (round-robin).

    Prendre les N premieres images de la premiere requete donnerait dix fois la
    meme facade sous le meme angle. En alternant, chaque requete du sujet
    contribue — c'est ce qui rend le diaporama varie.
    """
    depth = max((len(g) for g in groups), default=0)
    for rank in range(depth):
        for group in groups:
            if rank < len(group):
                yield group[rank]


def fetch_for_topic(
    image_queries: List[str],
    count: int,
    dest_dir: Path,
    *,
    attribution_free_only: bool = False,
) -> List[ImageResult]:
    """Rassemble ``count`` images pretes a l'emploi pour un sujet.

    Parcourt toutes les requetes du sujet, DEDOUBLONNE (une meme photo trouvee
    par deux requetes n'apparait qu'une fois : c'est le ``page_id`` de Commons
    qui fait foi, pas le titre), telecharge, et s'arrete des que le quota est
    atteint.

    Args:
        image_queries: requetes du sujet (champ ``image_queries`` du YAML).
        count: nombre d'images souhaitees.
        dest_dir: dossier de destination, cree au besoin. Sert aussi de cache.
        attribution_free_only: ne garder que le domaine public et le CC0.
            Necessaire des que l'image sera posee la ou AUCUN credit ne peut
            figurer — un avatar de chaine, une miniature, une icone. Une
            photo CC BY parfaitement licenciee y devient contrefaisante,
            faute d'endroit ou nommer son auteur.

    Returns:
        Les images effectivement disponibles sur le disque, creditables. Peut
        etre plus court que ``count`` (filtres + pannes reseau) voire vide :
        l'appelant DOIT gerer ce cas plutot que de supposer le quota atteint.
    """
    count = max(0, int(count))
    if not image_queries or count == 0:
        return []

    dest_dir = Path(dest_dir)
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("Dossier d'images inutilisable (%s) : %s", dest_dir, exc)
        return []

    # On cherche large : les filtres licence/taille eliminent une bonne part des
    # resultats, et un quota atteint de justesse ne laisse aucune marge.
    per_query = max(5, min(count * 2, 25))
    groups = [search_images(query, per_query) for query in image_queries if query]
    if attribution_free_only:
        groups = [
            [i for i in group if not _attribution_required(i.license_name)]
            for group in groups
        ]

    collected: List[ImageResult] = []
    seen_pages: set[int] = set()
    seen_files: set[str] = set()

    for candidate in _interleave(groups):
        if len(collected) >= count:
            break
        # Deux cles de dedoublonnage : l'identifiant Commons (le cas nominal) et
        # le nom de fichier local (filet de secours si page_id manque).
        local_name = _local_name(candidate)
        if candidate.page_id in seen_pages or local_name in seen_files:
            logger.debug("Doublon ignore : %s", candidate.title)
            continue
        seen_pages.add(candidate.page_id)
        seen_files.add(local_name)

        if _download(candidate, dest_dir):
            collected.append(candidate)

    if len(collected) < count:
        logger.warning(
            "Seulement %d image(s) exploitable(s) sur %d demandees "
            "(%d requete(s) explorees).",
            len(collected),
            count,
            len(groups),
        )
    else:
        logger.info("%d image(s) prete(s) dans %s", len(collected), dest_dir)
    return collected


# ---------------------------------------------------------------------------
# Credits
# ---------------------------------------------------------------------------


def format_credits(images: Sequence[ImageResult]) -> str:
    """Bloc de credits a coller en fin de description YouTube.

    Dedoublonne les lignes identiques (une meme photo reutilisee ne se credite
    qu'une fois) et conserve l'ordre d'apparition dans la video.

    Returns:
        Le bloc pret a concatener, ou une chaine VIDE s'il n'y a rien a
        crediter — pour qu'une description sans image ne se termine pas par un
        titre de section orphelin.
    """
    if not images:
        return ""

    lines: List[str] = []
    seen: set[str] = set()
    for image in images:
        line = f"• {image.attribution_line()}"
        if line in seen:
            continue
        seen.add(line)
        lines.append(line)
        if image.commons_url:
            lines.append(f"  {image.commons_url}")

    if not lines:
        return ""

    header = (
        "Credits photos — Wikimedia Commons\n"
        "Les images ci-dessous sont reutilisees dans le respect de leur "
        "licence."
    )
    return f"{header}\n" + "\n".join(lines)
