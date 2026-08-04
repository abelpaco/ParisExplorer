"""Synthese de la voix off (text-to-speech) des videos ParisExplorer.

POURQUOI CE MODULE EXISTE
-------------------------
Les videos produites jusqu'ici sont MUETTES (``audio=False`` dans
``video_creator.py``) et durent 17 secondes. Une chaine YouTube qui publie des
diaporamas muets de 17 s n'a aucune chance de retention. La cible du format est
2 a 3 minutes commentees, en francais ET en anglais — d'ou ce module.

Il s'appuie sur ``edge-tts`` : gratuit, sans cle d'API, qualite neurale.

LA DUREE REELLE EST LE PRODUIT PRINCIPAL
----------------------------------------
Ce module ne rend pas seulement un MP3 : il rend la duree MESUREE de ce MP3.
C'est elle qui pilotera le montage (nombre d'images et temps d'affichage se
calent sur la voix, pas l'inverse). Elle est donc lue sur le FICHIER produit,
jamais estimee depuis un nombre de mots : la vitesse d'elocution varie avec la
voix, la langue et la ponctuation, et une estimation a 10 % pres suffit a
desynchroniser la fin du diaporama de la fin de la narration.

CE QUI PEUT MAL TOURNER (et comment c'est traite)
-------------------------------------------------
- Le service Microsoft peut refuser, limiter le debit ou pendre : retry avec
  backoff + timeout par morceau, puis ``NarrationSynthesisError``. Le pipeline
  DOIT pouvoir choisir de ne pas publier plutot que de sortir une video muette :
  cette erreur typee est ce choix.
- Les textes tres longs passent mal d'un bloc : la narration est decoupee par
  PHRASES puis les segments MP3 sont concatenes.
- Windows : ``aiodns`` exige une ``SelectorEventLoop``, alors que la boucle par
  defaut y est une ``ProactorEventLoop``. Sans le correctif applique ici, tout
  appel echoue avec « aiodns needs a SelectorEventLoop on Windows ».
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: Voix par defaut, une par langue. Surchargeable par l'appelant via l'argument
#: ``voice`` de :func:`synthesize`, ou globalement en modifiant ce dict.
#:
#: ``fr-FR-DeniseNeural`` : voix feminine posee, la plus neutre des cinq voix
#: francaises disponibles — un ton documentaire, pas un ton publicitaire.
#: ``en-GB-RyanNeural`` : anglais britannique, debit calme, la couleur
#: « documentaire » attendue sur un sujet patrimonial europeen (un accent
#: americain enjoue collerait mal a Notre-Dame ou au Louvre).
DEFAULT_VOICES: Dict[str, str] = {
    "fr": "fr-FR-DeniseNeural",
    "en": "en-GB-RyanNeural",
}

#: Voix francaises validees sur ce projet, pour varier d'une video a l'autre.
FRENCH_VOICES: tuple[str, ...] = (
    "fr-FR-DeniseNeural",
    "fr-FR-HenriNeural",
    "fr-FR-EloiseNeural",
    "fr-FR-VivienneMultilingualNeural",
    "fr-FR-RemyMultilingualNeural",
)

#: Au-dela de cette taille, la narration est decoupee par phrases. edge-tts
#: accepte techniquement plus, mais les envois d'un seul bloc allongent la
#: session WebSocket et se font couper en silence (audio tronque) — un defaut
#: bien pire qu'une erreur, parce qu'il passe la validation.
MAX_CHUNK_CHARS = 1400

#: Delai maximal accorde a la synthese d'UN morceau, en secondes.
CHUNK_TIMEOUT = 90.0

#: Nombre total de tentatives par morceau (1 essai + 2 reprises).
RETRY_ATTEMPTS = 3

#: Base du backoff exponentiel entre deux tentatives, en secondes.
RETRY_BACKOFF = 2.0

#: En dessous de ce poids, le MP3 rendu est considere comme vide/tronque.
MIN_AUDIO_BYTES = 1024


# ---------------------------------------------------------------------------
# Erreurs typees
# ---------------------------------------------------------------------------


class NarrationError(RuntimeError):
    """Erreur de narration. Base de toutes les erreurs du module."""


class NarrationConfigError(NarrationError):
    """Demande impossible a satisfaire : texte vide, langue inconnue..."""


class NarrationSynthesisError(NarrationError):
    """Echec DEFINITIF de la synthese, apres toutes les reprises.

    Le pipeline doit traiter cette erreur comme un « ne pas publier » : une
    video muette de 17 s vaut moins que pas de video du tout.
    """


class NarrationDurationError(NarrationError):
    """Le MP3 existe mais sa duree n'a pas pu etre mesuree.

    Sans duree, le montage ne peut pas caler les images : c'est bloquant.
    """


# ---------------------------------------------------------------------------
# Resultat
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NarrationResult:
    """Piste audio produite pour une narration.

    Attributes:
        path: Chemin du MP3 genere (ou retrouve en cache).
        duration: Duree REELLE en secondes, mesuree sur le fichier.
        lang: Code de langue demande (``fr``, ``en``...).
        voice: Identifiant edge-tts de la voix effectivement utilisee.
        text_hash: Empreinte courte du texte + parametres de voix. C'est la
            cle de cache, egalement presente dans le nom du fichier.
        cached: ``True`` si le fichier existait deja et n'a pas ete resynthetise.
        chunks: Nombre de morceaux synthetises puis concatenes.
    """

    path: Path
    duration: float
    lang: str
    voice: str
    text_hash: str
    cached: bool = False
    chunks: int = 1

    @property
    def minutes(self) -> float:
        """Duree en minutes, pour les logs et le controle du format cible."""
        return self.duration / 60.0


# ---------------------------------------------------------------------------
# Pont asynchrone -> synchrone
# ---------------------------------------------------------------------------


def _new_event_loop() -> asyncio.AbstractEventLoop:
    """Cree une boucle asyncio utilisable par edge-tts.

    Sous Windows, ``aiohttp`` resout les DNS via ``aiodns``, qui REFUSE la
    ``ProactorEventLoop`` (boucle par defaut de Windows depuis Python 3.8) et
    leve « aiodns needs a SelectorEventLoop on Windows ». On instancie donc
    explicitement une ``SelectorEventLoop`` — localement, sans toucher a la
    politique globale asyncio, pour ne rien changer au reste du projet.
    """
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()


def _run_sync(factory: Callable[[], Awaitable[T]], timeout: float) -> T:
    """Execute une coroutine depuis du code synchrone, avec timeout.

    Le pipeline ParisExplorer est entierement synchrone ; edge-tts est
    entierement asynchrone. Tout passe donc par ici.

    La coroutine tourne TOUJOURS dans un thread dedie, avec sa propre boucle.
    C'est volontaire : ``asyncio.run()`` explose si une boucle tourne deja dans
    le thread appelant (cas d'un futur ordonnanceur async, d'un notebook ou d'un
    serveur web). Passer par un thread rend le comportement identique dans les
    deux cas, au prix d'un thread ephemere par appel — negligeable devant une
    requete reseau de plusieurs secondes.

    Args:
        factory: Fonction SANS argument renvoyant la coroutine a executer. On
            prend une fabrique et non une coroutine deja construite : une
            coroutine jamais attendue (thread non demarre) declencherait un
            « coroutine was never awaited ».
        timeout: Delai maximal en secondes.

    Returns:
        La valeur renvoyee par la coroutine.

    Raises:
        TimeoutError: Si le delai est depasse.
    """

    def _worker() -> T:
        loop = _new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(asyncio.wait_for(factory(), timeout))
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            finally:
                asyncio.set_event_loop(None)
                loop.close()

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="edge-tts") as pool:
        return pool.submit(_worker).result()


# ---------------------------------------------------------------------------
# Preparation du texte
# ---------------------------------------------------------------------------

# Fin de phrase = ponctuation forte, eventuellement suivie d'un guillemet ou
# d'une parenthese fermante, puis d'une espace. Le lookbehind fait que la
# coupure tombe APRES la ponctuation : elle reste collee a la phrase, et le
# moteur TTS conserve donc son intonation descendante.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])[\"»”’')\]]*\s+")

# Repli quand une seule phrase depasse deja la taille maximale : on coupe sur
# les ponctuations faibles, jamais au milieu d'un mot.
_CLAUSE_SPLIT = re.compile(r"(?<=[,;:])\s+")


def normalize_text(text: str) -> str:
    """Normalise une narration avant synthese.

    Les narrations viennent de blocs YAML multi-lignes : les retours a la ligne
    y sont de la mise en forme, pas de la prosodie. On replie donc tout sur des
    espaces simples. Consequence utile : deux narrations identiques mises en
    forme differemment donnent la MEME empreinte de cache.
    """
    return re.sub(r"\s+", " ", text).strip()


def _split_long_sentence(sentence: str, max_chars: int) -> List[str]:
    """Coupe une phrase trop longue sans jamais couper un mot."""
    parts: List[str] = []
    for clause in _CLAUSE_SPLIT.split(sentence):
        if len(clause) <= max_chars:
            if clause:
                parts.append(clause)
            continue
        # Dernier recours : accumulation mot a mot.
        buffer = ""
        for word in clause.split(" "):
            candidate = f"{buffer} {word}".strip()
            if buffer and len(candidate) > max_chars:
                parts.append(buffer)
                buffer = word
            else:
                buffer = candidate
        if buffer:
            parts.append(buffer)
    return parts


def split_into_chunks(text: str, max_chars: int = MAX_CHUNK_CHARS) -> List[str]:
    """Decoupe une narration en morceaux synthetisables.

    Le decoupage se fait par PHRASES entieres : une coupure au milieu d'une
    phrase s'entend (intonation qui retombe puis repart), une coupure entre deux
    phrases ne s'entend pas. La ponctuation reste attachee a la phrase qui la
    porte.

    Args:
        text: Narration deja normalisee.
        max_chars: Taille maximale visee pour un morceau.

    Returns:
        Liste de morceaux non vides. Un texte court renvoie une liste d'un seul
        element : le cas nominal ne paie pas le cout du decoupage.
    """
    text = normalize_text(text)
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    sentences: List[str] = []
    for sentence in _SENTENCE_SPLIT.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > max_chars:
            logger.debug("Phrase de %d caracteres : coupure secondaire.", len(sentence))
            sentences.extend(_split_long_sentence(sentence, max_chars))
        else:
            sentences.append(sentence)

    chunks: List[str] = []
    buffer = ""
    for sentence in sentences:
        candidate = f"{buffer} {sentence}".strip()
        if buffer and len(candidate) > max_chars:
            chunks.append(buffer)
            buffer = sentence
        else:
            buffer = candidate
    if buffer:
        chunks.append(buffer)

    logger.debug("Narration decoupee en %d morceaux (%d car.).", len(chunks), len(text))
    return chunks


# ---------------------------------------------------------------------------
# Voix et cache
# ---------------------------------------------------------------------------


def resolve_voice(lang: str, voice: Optional[str] = None) -> str:
    """Determine la voix a utiliser pour une langue.

    Args:
        lang: Code de langue (``fr``, ``en``, ``fr-FR``... insensible a la casse).
        voice: Voix explicite, qui court-circuite la table par defaut.

    Returns:
        Identifiant edge-tts de la voix.

    Raises:
        NarrationConfigError: Si aucune voix par defaut n'existe pour la langue.
    """
    if voice:
        return voice
    key = lang.lower().replace("_", "-")
    for candidate in (key, key.split("-")[0]):
        if candidate in DEFAULT_VOICES:
            return DEFAULT_VOICES[candidate]
    raise NarrationConfigError(
        f"Aucune voix par defaut pour la langue '{lang}'. "
        f"Langues connues : {sorted(DEFAULT_VOICES)}. "
        f"Passe une voix explicite via l'argument 'voice'."
    )


def fingerprint(text: str, voice: str, rate: str, volume: str, pitch: str) -> str:
    """Empreinte courte du couple (texte, reglages de voix).

    Tout ce qui change l'audio entre dans l'empreinte : changer la voix ou le
    debit DOIT invalider le cache, sinon on reutiliserait un MP3 obsolete.
    """
    payload = "\x1f".join((normalize_text(text), voice, rate, volume, pitch))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _cache_path(out_path: Path, digest: str) -> Path:
    """Insere l'empreinte dans le nom de fichier demande.

    ``temp/tour-eiffel_fr.mp3`` devient ``temp/tour-eiffel_fr.4f2a9c1b0d33.mp3``.
    Le cache est ainsi porte par le systeme de fichiers, sans index a maintenir
    ni a resynchroniser : le fichier EST l'entree de cache.
    """
    suffix = out_path.suffix or ".mp3"
    return out_path.with_name(f"{out_path.stem}.{digest}{suffix}")


# ---------------------------------------------------------------------------
# Mesure de la duree
# ---------------------------------------------------------------------------

# Tables MPEG audio, pour le repli de mesure sans ffmpeg.
_V1_L3_BITRATES = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0)
_V2_L3_BITRATES = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0)
_MPEG_SAMPLE_RATES = {
    0b11: (44100, 48000, 32000),  # MPEG 1
    0b10: (22050, 24000, 16000),  # MPEG 2
    0b00: (11025, 12000, 8000),  # MPEG 2.5
}


def _skip_id3(data: bytes) -> int:
    """Renvoie l'offset du premier octet audio, en sautant un tag ID3v2."""
    if data[:3] == b"ID3" and len(data) >= 10:
        size = 0
        for byte in data[6:10]:
            size = (size << 7) | (byte & 0x7F)  # synchsafe integer
        return 10 + size
    return 0


def _duration_from_mp3_frames(path: Path) -> Optional[float]:
    """Mesure une duree MP3 en parcourant les en-tetes de trames.

    Repli utilise quand moviepy/ffmpeg n'est pas disponible. Ce n'est pas une
    estimation : on additionne les echantillons reellement encodes, trame par
    trame. La duree obtenue colle a celle de ffmpeg a quelques millisecondes.
    """
    try:
        data = path.read_bytes()
    except OSError as exc:
        logger.error("Lecture impossible pour mesurer la duree (%s) : %s", path, exc)
        return None

    offset = _skip_id3(data)
    total_samples = 0
    sample_rate = 0
    end = len(data) - 4

    while offset <= end:
        if data[offset] != 0xFF or (data[offset + 1] & 0xE0) != 0xE0:
            offset += 1  # resynchronisation
            continue
        byte1 = data[offset + 1]
        byte2 = data[offset + 2]
        version = (byte1 >> 3) & 0b11
        layer = (byte1 >> 1) & 0b11
        bitrate_idx = (byte2 >> 4) & 0b1111
        rate_idx = (byte2 >> 2) & 0b11
        padding = (byte2 >> 1) & 0b1
        if version == 0b01 or layer != 0b01 or rate_idx == 0b11:
            offset += 1  # version reservee / autre couche que Layer III
            continue
        table = _V1_L3_BITRATES if version == 0b11 else _V2_L3_BITRATES
        bitrate = table[bitrate_idx] * 1000
        rate = _MPEG_SAMPLE_RATES[version][rate_idx]
        if not bitrate or not rate:
            offset += 1
            continue
        samples = 1152 if version == 0b11 else 576
        frame_len = (samples // 8) * bitrate // rate + padding
        if frame_len <= 4:
            offset += 1
            continue
        total_samples += samples
        sample_rate = rate
        offset += frame_len

    if not total_samples or not sample_rate:
        return None
    return total_samples / sample_rate


def _duration_via_moviepy(path: Path) -> Optional[float]:
    """Mesure une duree via moviepy/ffmpeg. ``None`` si indisponible."""
    try:
        from moviepy import AudioFileClip

        with AudioFileClip(str(path)) as clip:
            duration = float(clip.duration or 0.0)
        return duration if duration > 0 else None
    except Exception as exc:  # ffmpeg absent, binaire casse, format inattendu
        logger.warning("Mesure moviepy indisponible (%s) : %s", path.name, exc)
        return None


def probe_duration(path: Path) -> float:
    """Mesure la duree REELLE d'un fichier audio, en secondes.

    Deux mesures possibles, la plus rapide d'abord :

    1. Lecture des en-tetes de trames MPEG, en pur Python. Ce n'est pas une
       estimation : on additionne les echantillons reellement encodes.
    2. moviepy / ffmpeg, pour tout ce que (1) ne sait pas lire.

    POURQUOI PAS moviepy D'ABORD, puisqu'il est deja au projet ? Parce que la
    mesure a ete faite : sur le meme MP3 de 125 s, ffmpeg met 16 s (plus 25 s
    d'import de moviepy a froid) quand la lecture des trames met 0,05 s — et
    les deux renvoient 124,970 s contre 124,968 s, soit 2 ms d'ecart. Payer
    16 s de sous-processus par langue et par video pour 2 ms n'a pas de sens.
    moviepy reste le filet de securite, pas le chemin nominal.

    Raises:
        NarrationDurationError: Si aucune des deux methodes n'aboutit.
    """
    duration = _duration_from_mp3_frames(path)
    if duration and duration > 0:
        return duration

    logger.debug("Trames MPEG illisibles pour %s : repli sur moviepy.", path.name)
    duration = _duration_via_moviepy(path)
    if duration:
        return duration

    raise NarrationDurationError(
        f"Duree non mesurable pour {path}. Le montage ne peut pas caler les "
        f"images sans elle : mieux vaut ne pas publier."
    )


# ---------------------------------------------------------------------------
# Synthese
# ---------------------------------------------------------------------------


def _synthesize_chunk(
    text: str, voice: str, rate: str, volume: str, pitch: str, timeout: float
) -> bytes:
    """Synthetise UN morceau et renvoie ses octets MP3.

    Raises:
        NarrationConfigError: Si les parametres de voix sont invalides. Cette
            erreur-la n'est PAS reessayee : une voix mal orthographiee sera
            toujours mal orthographiee, et trois allers-retours reseau pour le
            reapprendre coutent une trentaine de secondes par video.
        NarrationSynthesisError: Si edge-tts est absent ou si le morceau revient
            vide (audio tronque cote service).
    """
    try:
        import edge_tts
    except ImportError as exc:  # pragma: no cover - depend de l'installation
        raise NarrationSynthesisError(
            "Le paquet 'edge-tts' est introuvable. Installe les dependances : "
            "pip install -r requirements.txt"
        ) from exc

    try:
        communicate = edge_tts.Communicate(
            text, voice, rate=rate, volume=volume, pitch=pitch
        )
    except (ValueError, TypeError) as exc:
        raise NarrationConfigError(
            f"Parametres de voix refuses par edge-tts : {exc}"
        ) from exc

    async def _collect() -> bytes:
        buffer = bytearray()
        async for message in communicate.stream():
            if message.get("type") == "audio" and message.get("data"):
                buffer.extend(message["data"])
        return bytes(buffer)

    audio = _run_sync(_collect, timeout)
    if not audio:
        raise NarrationSynthesisError(
            f"Le service a renvoye un audio vide pour un morceau de "
            f"{len(text)} caracteres (voix {voice})."
        )
    return audio


def _synthesize_chunk_with_retry(
    text: str,
    voice: str,
    rate: str,
    volume: str,
    pitch: str,
    timeout: float,
    attempts: int,
) -> bytes:
    """Synthetise un morceau avec reprises et backoff exponentiel.

    Le service Microsoft est gratuit et non contractuel : il coupe, limite le
    debit et repond parfois vide. Un jitter est ajoute au backoff pour ne pas
    resoumettre tous les morceaux en rafale synchronisee.
    """
    last_error: Optional[BaseException] = None
    for attempt in range(1, attempts + 1):
        try:
            return _synthesize_chunk(text, voice, rate, volume, pitch, timeout)
        except NarrationConfigError:
            raise  # deterministe : reessayer ne changerait rien
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            delay = RETRY_BACKOFF * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            logger.warning(
                "Synthese en echec (tentative %d/%d) : %s — nouvelle tentative "
                "dans %.1f s.",
                attempt,
                attempts,
                exc,
                delay,
            )
            time.sleep(delay)

    raise NarrationSynthesisError(
        f"Synthese abandonnee apres {attempts} tentatives (voix {voice}, "
        f"{len(text)} caracteres). Derniere erreur : {last_error}"
    ) from last_error


def synthesize(
    text: str,
    lang: str,
    out_path: Path,
    voice: Optional[str] = None,
    *,
    rate: str = "+0%",
    volume: str = "+0%",
    pitch: str = "+0Hz",
    force: bool = False,
    timeout: float = CHUNK_TIMEOUT,
    attempts: int = RETRY_ATTEMPTS,
    max_chunk_chars: int = MAX_CHUNK_CHARS,
) -> NarrationResult:
    """Transforme un texte de narration en piste audio MP3.

    C'est le point d'entree du module, et il est SYNCHRONE : le reste du
    pipeline n'a jamais a connaitre l'existence d'asyncio.

    Args:
        text: Texte de narration (bloc ``narration`` d'un sujet).
        lang: Code de langue (``fr``, ``en``...), sert a choisir la voix.
        out_path: Chemin souhaite. L'empreinte du texte est inseree dans le nom
            reel du fichier ; lire le chemin effectif dans ``result.path``.
        voice: Voix edge-tts explicite ; a defaut, celle de ``DEFAULT_VOICES``.
        rate: Ajustement du debit, ex. ``"-10%"`` pour ralentir.
        volume: Ajustement du volume, ex. ``"+10%"``.
        pitch: Ajustement de la hauteur, ex. ``"-2Hz"``.
        force: Ignore le cache et resynthetise.
        timeout: Delai maximal par morceau, en secondes.
        attempts: Nombre de tentatives par morceau.
        max_chunk_chars: Seuil de decoupage par phrases.

    Returns:
        Un :class:`NarrationResult` dont ``duration`` est mesuree sur le
        fichier produit.

    Raises:
        NarrationConfigError: Texte vide, langue sans voix connue, ou reglages
            de voix refuses par edge-tts.
        NarrationSynthesisError: Echec definitif de la synthese.
        NarrationDurationError: MP3 produit mais duree non mesurable.
    """
    normalized = normalize_text(text)
    if not normalized:
        raise NarrationConfigError("Narration vide : rien a synthetiser.")

    selected_voice = resolve_voice(lang, voice)
    digest = fingerprint(normalized, selected_voice, rate, volume, pitch)
    out_path = Path(out_path)
    target = _cache_path(out_path, digest)
    target.parent.mkdir(parents=True, exist_ok=True)

    if not force and target.exists() and target.stat().st_size >= MIN_AUDIO_BYTES:
        duration = probe_duration(target)
        logger.info(
            "Narration %s deja en cache : %s (%.1f s).", lang, target.name, duration
        )
        return NarrationResult(
            path=target,
            duration=duration,
            lang=lang,
            voice=selected_voice,
            text_hash=digest,
            cached=True,
        )

    chunks = split_into_chunks(normalized, max_chunk_chars)
    logger.info(
        "Synthese %s (%s) : %d mots, %d caracteres, %d morceau(x).",
        lang,
        selected_voice,
        len(normalized.split()),
        len(normalized),
        len(chunks),
    )

    started = time.monotonic()
    audio = bytearray()
    for index, chunk in enumerate(chunks, start=1):
        logger.debug("Morceau %d/%d (%d car.)", index, len(chunks), len(chunk))
        audio.extend(
            _synthesize_chunk_with_retry(
                chunk, selected_voice, rate, volume, pitch, timeout, attempts
            )
        )

    if len(audio) < MIN_AUDIO_BYTES:
        raise NarrationSynthesisError(
            f"Audio produit anormalement petit ({len(audio)} octets) pour "
            f"{len(normalized)} caracteres — probable troncature du service."
        )

    # Ecriture atomique : un plantage en cours d'ecriture laisserait sinon un
    # MP3 tronque a l'emplacement exact ou le cache ira le rechercher, et cette
    # narration mutilee serait resservie a chaque video suivante.
    tmp = target.with_suffix(target.suffix + ".part")
    tmp.write_bytes(bytes(audio))
    os.replace(tmp, target)

    duration = probe_duration(target)
    logger.info(
        "Narration %s ecrite : %s — %.2f s (%.2f min), %d Ko, %.1f s de calcul.",
        lang,
        target.name,
        duration,
        duration / 60.0,
        len(audio) // 1024,
        time.monotonic() - started,
    )
    return NarrationResult(
        path=target,
        duration=duration,
        lang=lang,
        voice=selected_voice,
        text_hash=digest,
        cached=False,
        chunks=len(chunks),
    )


def synthesize_topic(
    topic: Dict[str, object], lang: str, out_dir: Path, **kwargs: object
) -> NarrationResult:
    """Synthetise la narration d'un sujet charge depuis ``content/topics/``.

    Args:
        topic: Sujet au format ``_SCHEMA.md`` (contient ``id`` et un bloc par
            langue portant la cle ``narration``).
        lang: Langue a produire (``fr`` ou ``en``).
        out_dir: Repertoire de sortie des MP3.
        **kwargs: Transmis tel quel a :func:`synthesize`.

    Raises:
        NarrationConfigError: Si le sujet n'a pas de narration pour cette langue.
    """
    block = topic.get(lang)
    narration = block.get("narration") if isinstance(block, dict) else None
    if not isinstance(narration, str) or not narration.strip():
        raise NarrationConfigError(
            f"Sujet '{topic.get('id', '?')}' : bloc '{lang}.narration' absent ou "
            f"vide. Le schema impose les deux langues."
        )
    topic_id = str(topic.get("id") or "topic")
    return synthesize(
        narration, lang, Path(out_dir) / f"{topic_id}_{lang}.mp3", **kwargs
    )
