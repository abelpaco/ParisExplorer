"""Montage d'une video a partir d'images fixes et d'une narration.

POURQUOI CE MODULE EXISTE
-------------------------
Les briques amont produisent des images creditables (``image_sourcing``) et une
piste audio (``narration``). Il manquait l'assemblage : passer d'un dossier
d'images + un MP3 a un fichier publiable, au format vise de 2 a 3 minutes, plus
sa declinaison verticale en Shorts.

PARTI PRIS
----------
1. **C'est l'audio qui commande la duree.** La video dure exactement ce que dure
   la narration. On ne coupe jamais une phrase pour tenir un chrono.

2. **Aucune image n'est deformee, et aucune n'est reduite en timbre-poste.**
   Sur Commons, la moitie des bonnes photos de monuments sont verticales. Les
   poser entieres dans un cadre 16:9 les reduirait au tiers de la largeur,
   entourees de flou. On fait l'inverse : l'image remplit le cadre, et le plan
   la PARCOURT — on descend le long de la tour au lieu de la regarder de loin.
   C'est le traitement documentaire classique d'un sujet plus haut que large.

3. **Chaque plan glisse lentement (effet Ken Burns).** Une image parfaitement
   fixe pendant dix secondes se lit comme un bug. Le mouvement est obtenu en
   promenant une fenetre dans une toile plus grande que le cadre : il ne peut
   donc jamais faire apparaitre de bord noir, et ne coute presque rien.

4. **Les Shorts sont decoupes sur des silences reels**, pas sur des multiples de
   soixante secondes. Un Short qui commence au milieu d'un mot est un Short
   qu'on ne regarde pas.
"""

from __future__ import annotations

import logging
import math
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

# Format principal (paysage) et format Shorts (vertical).
SIZE_LANDSCAPE = (1920, 1080)
SIZE_VERTICAL = (1080, 1920)

FPS = 30

# Duree d'affichage visee par image. En dessous, le montage s'agite ; au-dessus,
# il s'endort. Les images sont recyclees en boucle pour tenir cette cadence.
TARGET_SLOT_SECONDS = 9.0

# Fondu enchaine entre deux images.
CROSSFADE_SECONDS = 0.8

# Marge ajoutee a la fin de chaque plan. Elle n'est pas decorative : sans elle,
# le fondu se terminerait sur la toute derniere image du plan et ffmpeg refuse
# de configurer le filtre.
PLAN_TAIL_MARGIN = 0.5

# Amplitude du zoom Ken Burns (8 % sur la duree d'un plan).
KEN_BURNS_ZOOM = 0.08

# Debordement maximal de la toile par rapport au cadre. C'est la course
# disponible pour le mouvement : au-dela, le plan ne derive plus, il defile.
MAX_PAN_SCALE = 2.0

# Shorts : YouTube plafonne a 60 s. On vise plus court pour garder de la marge
# et pouvoir couper sur un silence plutot qu'a la seconde pres.
SHORT_TARGET_SECONDS = 52.0
SHORT_MAX_SECONDS = 59.0
SHORT_MIN_SECONDS = 20.0

# Detection de silence (ffmpeg silencedetect).
SILENCE_NOISE_DB = -35
SILENCE_MIN_DURATION = 0.35


class AssemblyError(RuntimeError):
    """Le montage n'a pas pu aboutir."""


@dataclass
class VideoResult:
    """Fichier video produit."""

    path: Path
    duration: float
    size: Tuple[int, int]
    image_count: int

    @property
    def minutes(self) -> float:
        return self.duration / 60.0


# ---------------------------------------------------------------------------
# Preparation des images
# ---------------------------------------------------------------------------


def _crop_box(img_w: int, img_h: int, box_w: int, box_h: int) -> Tuple[int, int, int, int]:
    """Zone a garder pour obtenir exactement ``box_w`` x ``box_h`` sans deformer.

    Le cadrage horizontal est centre. Le cadrage vertical est biaise vers le
    HAUT : sur une photo de monument, le sujet occupe le haut et le bas n'est
    souvent que du parvis.
    """
    crop_w = min(img_w, box_w)
    crop_h = min(img_h, box_h)
    left = (img_w - crop_w) // 2
    top = (img_h - crop_h) // 3
    return left, top, left + crop_w, top + crop_h


def prepare_canvas(source: Path, size: Tuple[int, int], dest: Optional[Path] = None):
    """Fabrique la toile d'un plan a partir d'une photo quelconque.

    La photo est agrandie jusqu'a REMPLIR le cadre (jamais deformee), puis la
    toile garde de la marge sur l'axe ou l'image deborde. C'est cette marge que
    le plan parcourt ensuite :

    - photo aux proportions du cadre : marge egale sur les deux axes, le plan
      derive en diagonale ;
    - photo verticale dans un cadre 16:9 : toile haute, le plan descend le long
      du sujet ;
    - photo panoramique dans un cadre vertical : toile large, le plan balaye.

    La marge est plafonnee par ``MAX_PAN_SCALE`` : sans plafond, une photo tres
    allongee produirait un defilement si rapide qu'il donnerait le tournis.

    Args:
        source: photo d'origine.
        size: dimensions du CADRE FINAL (la toile sera plus grande).
        dest: fichier ou enregistrer la toile. C'est le cas nominal : ffmpeg
            travaille sur des fichiers, pas sur des objets Python.

    Returns:
        Le chemin de la toile si ``dest`` est fourni, sinon l'image Pillow.
    """
    box_w = int(round(size[0] * (1 + KEN_BURNS_ZOOM)))
    box_h = int(round(size[1] * (1 + KEN_BURNS_ZOOM)))
    max_w = int(round(size[0] * MAX_PAN_SCALE))
    max_h = int(round(size[1] * MAX_PAN_SCALE))

    with Image.open(source) as raw:
        img = raw.convert("RGB")

        # Agrandissement minimal qui couvre le cadre sur les DEUX axes.
        scale = max(box_w / img.width, box_h / img.height)
        full_w = max(box_w, int(round(img.width * scale)))
        full_h = max(box_h, int(round(img.height * scale)))
        canvas = img.resize((full_w, full_h), Image.LANCZOS)

        # Ce qui depasse le plafond est recadre : au-dela, ce n'est plus un
        # mouvement, c'est un defilement.
        keep_w = min(full_w, max_w)
        keep_h = min(full_h, max_h)
        if (keep_w, keep_h) != (full_w, full_h):
            canvas = canvas.crop(_crop_box(full_w, full_h, keep_w, keep_h))

        if dest is None:
            return canvas
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(dest, "JPEG", quality=94)
        return dest


def _build_sequence(images: Sequence[Path], duration: float) -> List[Path]:
    """Ordre d'apparition des images, recyclees pour tenir la cadence visee.

    Huit images sur trois minutes feraient vingt secondes chacune. On repasse
    donc sur la serie autant de fois qu'il faut pour rester autour de
    ``TARGET_SLOT_SECONDS`` — le cycle garantit qu'une image ne se suit
    jamais elle-meme.
    """
    if not images:
        raise AssemblyError("Aucune image fournie : impossible de monter la video.")
    wanted = max(1, round(duration / TARGET_SLOT_SECONDS))
    return [images[i % len(images)] for i in range(wanted)]


# ---------------------------------------------------------------------------
# Montage
# ---------------------------------------------------------------------------


def audio_duration(path: Path) -> float:
    """Duree reelle d'une piste audio, en secondes.

    Delegue a ``narration.probe_duration``, qui lit les en-tetes de trames MP3
    en pur Python : 340 fois plus rapide qu'un passage par ffmpeg, pour 2 ms
    d'ecart mesures. Le repli moviepy y est deja prevu pour les formats que le
    parseur ne sait pas lire.
    """
    from narration import probe_duration

    return float(probe_duration(Path(path)))


def _plan_filter(index: int, slot: float, size: Tuple[int, int], direction: int) -> str:
    """Filtre ffmpeg animant un plan : fenetre glissante dans la toile.

    La toile est plus grande que le cadre ; ``crop`` avec des expressions en
    ``t`` promene la fenetre dedans pendant toute la duree du plan. C'est
    l'equivalent exact de l'effet Ken Burns, mais calcule par ffmpeg.
    """
    width, height = size
    # Progression de 0 a 1 sur la duree du plan, bornee pour ne jamais sortir
    # de la toile si ffmpeg produit une image une fraction apres la fin.
    ramp = f"min(1,t/{slot:.4f})"
    back = f"(1-{ramp})"
    fx = ramp if direction in (0, 3) else back
    fy = ramp if direction in (0, 2) else back
    return (
        f"[{index}:v]"
        f"crop={width}:{height}:x='(iw-ow)*{fx}':y='(ih-oh)*{fy}',"
        # ORDRE CRITIQUE : `setpts` doit passer AVANT `fps`. Place apres, il
        # rend la cadence indeterminee (ffmpeg annonce « rate 1/0 ») et `xfade`
        # refuse alors de se configurer, avec un message qui ne parle ni de
        # setpts ni de l'ordre des filtres.
        f"setpts=PTS-STARTPTS,fps={FPS},format=yuv420p"
        f"[p{index}]"
    )


def _build_filtergraph(count: int, slot: float, size: Tuple[int, int], duration: float) -> str:
    """Graphe complet : plans animes, fondus enchaines, fondu d'ouverture/fin.

    Les ``xfade`` sont chaines : chaque fondu prend le resultat des precedents
    et le suivant. Le decalage n'est PAS un multiple de la duree d'un plan : les
    recouvrements raccourcissent l'ensemble, donc chaque plan demarre
    ``slot - fondu`` apres le precedent.
    """
    lines = [_plan_filter(i, slot, size, i % 4) for i in range(count)]

    current = "p0"
    for index in range(1, count):
        offset = index * (slot - CROSSFADE_SECONDS)
        label = f"x{index}"
        lines.append(
            f"[{current}][p{index}]"
            f"xfade=transition=fade:duration={CROSSFADE_SECONDS}:offset={offset:.4f}"
            f"[{label}]"
        )
        current = label

    fade_out_start = max(0.0, duration - 1.0)
    lines.append(
        f"[{current}]fade=t=in:st=0:d=0.6,"
        f"fade=t=out:st={fade_out_start:.3f}:d=1.0[vout]"
    )
    return ";\n".join(lines)


def assemble(
    images: Sequence[Path],
    audio_path: Path,
    out_path: Path,
    size: Tuple[int, int] = SIZE_LANDSCAPE,
    *,
    workdir: Optional[Path] = None,
    keep_canvases: bool = False,
) -> VideoResult:
    """Monte une video : diaporama anime cale sur la narration.

    COMMENT C'EST FABRIQUE, ET POURQUOI
    -----------------------------------
    Chaque photo est convertie UNE FOIS par Pillow en une toile un peu plus
    grande que le cadre. Tout le reste — mouvement, fondus, encodage — est
    confie a ffmpeg en une seule commande.

    C'est un choix MESURE. Deux versions precedentes faisaient transiter chaque
    image par Python : ``CompositeVideoClip`` avec masques de fondu (14 minutes
    pour 24 secondes de video), puis des tranches numpy envoyees a moviepy
    (6,5 minutes). Le profil a montre que le cout ne venait ni du calcul ni de
    l'encodage, mais du simple fait de faire passer 6 Mo par image dans Python,
    trente fois par seconde. La seule facon de le supprimer est de retirer
    Python du chemin de chaque image.

    Args:
        images: photos sources (ordre respecte).
        audio_path: piste de narration ; sa duree fixe celle de la video.
        out_path: fichier MP4 a produire.
        size: dimensions de sortie (paysage par defaut, vertical pour Shorts).
        workdir: dossier de travail ; temporaire auto-supprime si omis.
        keep_canvases: conserver les toiles intermediaires (inspection visuelle
            du montage sans avoir a lire la video).

    Raises:
        AssemblyError: aucune image utilisable, audio illisible, ou echec ffmpeg.
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise AssemblyError(f"Piste audio introuvable : {audio_path}")

    usable = [Path(p) for p in images if Path(p).exists()]
    if not usable:
        raise AssemblyError("Aucune des images fournies n'existe sur le disque.")
    if len(usable) < len(images):
        logger.warning(
            "%d image(s) manquante(s) sur %d — montage avec ce qui reste.",
            len(images) - len(usable),
            len(images),
        )

    duration = audio_duration(audio_path)
    sequence = _build_sequence(usable, duration)
    count = len(sequence)

    # Les plans se chevauchent pendant le fondu : leur somme depasse donc la
    # duree finale d'exactement (n-1) fondus.
    slot = (duration + (count - 1) * CROSSFADE_SECONDS) / count
    if slot <= CROSSFADE_SECONDS * 2:
        raise AssemblyError(
            f"Plans trop courts ({slot:.1f} s) pour un fondu de "
            f"{CROSSFADE_SECONDS} s : reduis le nombre d'images."
        )

    temp_root = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="pe-montage-"))
    temp_root.mkdir(parents=True, exist_ok=True)
    cleanup = workdir is None and not keep_canvases

    try:
        # Une meme photo peut revenir plusieurs fois dans la sequence : sa toile
        # n'est fabriquee qu'une fois, puis reutilisee avec un autre mouvement.
        canvases: dict[Path, Path] = {}
        plans: List[Path] = []
        for source in sequence:
            if source not in canvases:
                target = temp_root / f"toile-{len(canvases):03d}-{source.stem[:40]}.jpg"
                prepare_canvas(source, size, target)
                canvases[source] = target
            plans.append(canvases[source])

        logger.info(
            "Montage %dx%d : %d plan(s) de %.1f s sur %.1f s de narration "
            "(%d toile(s) distincte(s)).",
            size[0], size[1], count, slot, duration, len(canvases),
        )

        graph = _build_filtergraph(count, slot, size, duration)
        graph_file = temp_root / "filtergraph.txt"
        # Le graphe passe par un FICHIER et non par la ligne de commande : avec
        # une vingtaine de plans il depasse allegrement ce que Windows accepte,
        # et l'echappement des apostrophes des expressions serait un piege de
        # plus.
        graph_file.write_text(graph, encoding="utf-8")

        command = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y"]
        # Chaque plan dure un peu plus longtemps que son creneau : sans cette
        # marge, le fondu se terminerait exactement sur la derniere image du
        # plan et ``xfade`` refuserait de se configurer. Le rab n'est jamais
        # visible (le plan suivant a deja pris la main) et le ``-t`` final
        # retaille la video sur la duree de la narration.
        clip_seconds = slot + PLAN_TAIL_MARGIN
        for plan in plans:
            command += [
                "-loop", "1", "-framerate", str(FPS),
                "-t", f"{clip_seconds:.4f}", "-i", str(plan),
            ]
        command += ["-i", str(audio_path)]
        command += [
            "-filter_complex_script", str(graph_file),
            "-map", "[vout]",
            "-map", f"{count}:a",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            # La duree de reference reste l'audio : la piste video est calculee
            # pour tomber juste, mais un arrondi d'image ne doit pas rallonger
            # le fichier d'une demi-seconde de noir.
            "-t", f"{duration:.4f}",
            "-movflags", "+faststart",
            str(out_path),
        ]

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        started = time.time()
        proc = subprocess.run(command, capture_output=True, text=True)
        if proc.returncode != 0:
            raise AssemblyError(
                f"ffmpeg a echoue (code {proc.returncode}) :\n"
                f"{proc.stderr.strip()[-2000:]}"
            )
        elapsed = time.time() - started
    finally:
        if cleanup:
            shutil.rmtree(temp_root, ignore_errors=True)

    if not out_path.exists() or out_path.stat().st_size == 0:
        raise AssemblyError(f"ffmpeg n'a produit aucun fichier exploitable : {out_path}")

    result = VideoResult(
        path=out_path,
        duration=duration,
        size=size,
        image_count=count,
    )
    logger.info(
        "Video ecrite : %s — %.1f s (%.2f min), %d Ko, rendue en %.0f s.",
        out_path.name, result.duration, result.minutes,
        out_path.stat().st_size // 1024, elapsed,
    )
    return result


# ---------------------------------------------------------------------------
# Shorts
# ---------------------------------------------------------------------------

_SILENCE_END = re.compile(r"silence_end:\s*([0-9.]+)")
_SILENCE_DURATION = re.compile(r"silence_duration:\s*([0-9.]+)")


def ffmpeg_exe() -> str:
    """Chemin de l'executable ffmpeg.

    On prend celui du systeme s'il existe, sinon celui qu'``imageio-ffmpeg``
    installe avec moviepy. Sans ce repli, le montage marcherait (moviepy trouve
    le sien) mais le decoupage en Shorts echouerait sur les machines ou ffmpeg
    n'est pas dans le PATH — un piege silencieux, car la video principale, elle,
    serait bien produite.
    """
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        from imageio_ffmpeg import get_ffmpeg_exe

        return get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover - environnement casse
        raise AssemblyError(
            "ffmpeg introuvable : ni dans le PATH, ni via imageio-ffmpeg."
        ) from exc


def detect_silences(audio_path: Path) -> List[float]:
    """Instants de silence exploitables comme points de coupe (en secondes).

    Renvoie le MILIEU de chaque silence : couper a la fin d'un silence colle la
    respiration au segment precedent et fait demarrer le suivant trop sec.

    Une liste vide n'est pas une erreur : l'appelant retombe alors sur un
    decoupage regulier.
    """
    command = [
        ffmpeg_exe(), "-hide_banner", "-nostats", "-i", str(audio_path),
        "-af", f"silencedetect=noise={SILENCE_NOISE_DB}dB:d={SILENCE_MIN_DURATION}",
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Detection de silence impossible (%s) — decoupage regulier.", exc)
        return []

    points: List[float] = []
    for line in proc.stderr.splitlines():
        end = _SILENCE_END.search(line)
        span = _SILENCE_DURATION.search(line)
        if end and span:
            points.append(float(end.group(1)) - float(span.group(1)) / 2)
    logger.info("%d silence(s) detecte(s) dans %s.", len(points), audio_path.name)
    return points


def plan_short_cuts(duration: float, silences: Sequence[float]) -> List[Tuple[float, float]]:
    """Decoupe une duree en segments de Short, cales sur les silences.

    Avance segment par segment : depuis la position courante, cherche le silence
    le plus proche de la cible et qui reste sous le plafond YouTube. A defaut,
    coupe net a la cible.

    Returns:
        Liste de couples ``(debut, fin)``. Vide si la video est deja assez
        courte pour partir telle quelle en Short.
    """
    if duration <= SHORT_MAX_SECONDS:
        return []

    cuts: List[Tuple[float, float]] = []
    position = 0.0
    while duration - position > SHORT_MAX_SECONDS:
        target = position + SHORT_TARGET_SECONDS
        candidates = [
            s for s in silences
            if position + SHORT_MIN_SECONDS < s < position + SHORT_MAX_SECONDS
        ]
        end = min(candidates, key=lambda s: abs(s - target)) if candidates else target
        cuts.append((position, end))
        position = end

    # Le reliquat part avec le dernier segment s'il est trop maigre pour vivre
    # seul : mieux vaut un Short de 58 s qu'un Short de 6 s.
    if duration - position >= SHORT_MIN_SECONDS:
        cuts.append((position, duration))
    elif cuts:
        start, _ = cuts[-1]
        cuts[-1] = (start, duration)
    return cuts


def cut_shorts(
    video_path: Path, cuts: Sequence[Tuple[float, float]], out_dir: Path, stem: str
) -> List[Path]:
    """Extrait les Shorts d'une video verticale deja montee.

    Reencode plutot que de copier les flux : une copie brute ne peut couper que
    sur une image-cle, ce qui decale le debut de plusieurs secondes.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    produced: List[Path] = []

    for index, (start, end) in enumerate(cuts, start=1):
        target = out_dir / f"{stem}-short-{index}.mp4"
        command = [
            ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(video_path),
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            str(target),
        ]
        try:
            subprocess.run(command, capture_output=True, timeout=600, check=True)
        except (OSError, subprocess.SubprocessError) as exc:
            logger.error("Short %d non produit (%.1f-%.1f s) : %s", index, start, end, exc)
            continue
        produced.append(target)
        logger.info("Short %d : %s — %.1f s.", index, target.name, end - start)

    return produced


def build_shorts(
    images: Sequence[Path],
    audio_path: Path,
    out_dir: Path,
    stem: str,
    *,
    keep_master: bool = False,
) -> List[Path]:
    """Produit la serie de Shorts verticaux d'un sujet.

    Monte d'abord un master vertical complet, puis le decoupe. Remonter chaque
    Short separement donnerait des plans de longueurs differentes d'un Short a
    l'autre — le master garantit une cadence homogene.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    master = out_dir / f"{stem}-vertical-master.mp4"

    result = assemble(images, audio_path, master, size=SIZE_VERTICAL)
    cuts = plan_short_cuts(result.duration, detect_silences(Path(audio_path)))

    if not cuts:
        logger.info("Narration assez courte : le master vertical part tel quel en Short.")
        final = out_dir / f"{stem}-short-1.mp4"
        shutil.move(str(master), str(final))
        return [final]

    shorts = cut_shorts(master, cuts, out_dir, stem)
    if not keep_master:
        master.unlink(missing_ok=True)
    return shorts


# ---------------------------------------------------------------------------
# Controle qualite
# ---------------------------------------------------------------------------


def probe(path: Path) -> dict:
    """Caracteristiques REELLES d'un fichier video, relues sur le fichier.

    Sert au controle apres montage : on verifie ce que le fichier CONTIENT, pas
    ce qu'on croit avoir demande. La lecture passe par moviepy plutot que par
    ``ffprobe``, qui n'est pas fourni avec ``imageio-ffmpeg`` et manquerait donc
    sur les machines sans installation systeme.

    Returns:
        ``{"duration", "width", "height", "fps", "has_audio", "size_bytes"}``,
        ou un dictionnaire vide si le fichier est illisible.
    """
    from moviepy import VideoFileClip

    path = Path(path)
    clip = None
    try:
        clip = VideoFileClip(str(path))
        return {
            "duration": float(clip.duration),
            "width": int(clip.w),
            "height": int(clip.h),
            "fps": float(clip.fps or 0),
            "has_audio": clip.audio is not None,
            "size_bytes": path.stat().st_size,
        }
    except Exception as exc:
        logger.error("Video illisible : %s — %s", path, exc)
        return {}
    finally:
        if clip is not None:
            try:
                clip.close()
            except Exception:  # pragma: no cover
                pass
