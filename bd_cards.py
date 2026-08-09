"""Shorts BD « ligne claire » : du sujet YAML au MP4 vertical raconte.

POURQUOI CE MODULE EXISTE
-------------------------
Les Shorts photo racontent des lieux ; celui-ci raconte des PERSONNES et des
DATES : naissance d'un(e) Parisien(ne) celebre, anniversaire d'un evenement.
Chaque sujet devient une petite BD verticale de 45 a 90 secondes : une carte
de couverture au portrait, une carte par scene, une carte finale — chacune
affichee le temps exact de sa phrase dite par la voix off.

LA CHAINE, ET OU ELLE PEUT CASSER
---------------------------------
1. ``bd_topics`` charge et valide le sujet (vocabulaire ferme, echec bruyant).
2. ``bd_style`` compose les SVG — deterministe, aucune reseau.
3. Un rasteriseur transforme SVG en PNG. C'est LE maillon dependant de la
   machine : rsvg-convert sur le VPS (apt-get install librsvg2-bin),
   Chrome/Edge en secours sur un poste. On cherche, on dit ce qu'on a trouve,
   et on echoue clairement si rien n'existe.
4. ``narration`` synthetise UNE piste par carte : c'est ce qui permet de caler
   chaque carte sur sa phrase, au lieu d'estimer des durees.
5. ffmpeg assemble : zoom lent par carte, fondus, concat. Le zoom part d'un
   PNG rendu a 2x — zoompan sur un PNG a taille finale produit un tremblement
   sous-pixel visible sur les aplats de la ligne claire.

CE QUE CA REJOINT
-----------------
Le MP4 est declare comme Short d'un sujet : metadonnees dans
``content/videos/<id>/``, au format que ``plan_week`` recense et que
``publish`` sait envoyer (cle de registre ``<id>:<lang>:short-1``). Les PNG
alimentent un pack de posts Communaute, comme les cartes photo. Aucun credit
d'image : tout est dessine ici.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

PROJECT_DIR = Path(__file__).resolve().parent
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(PROJECT_DIR))

import bd_style
import bd_topics

logger = logging.getLogger("bd")

BD_ROOT = Path("content/bd")
VIDEOS_ROOT = Path("content/videos")
POSTS_ROOT = Path("content/posts")

# Rendu a 2x pour le zoom (voir docstring du module), livre a 1x pour les posts.
RASTER_SCALE = 2
FPS = 30

# Respirations autour de chaque phrase : un depart de voix colle a la coupe
# fait un montage essouffle.
LEAD_SECONDS = 0.35
TAIL_SECONDS = 0.55

# Fenetre visee. On previent hors bornes, on ne bloque pas : YouTube accepte
# jusqu'a 3 minutes en Short, et une histoire de 40 s reste publiable.
TARGET_MIN, TARGET_MAX = 45.0, 90.0

# Le meme plafond de titre que card_pack : YouTube tronque a 100, publish
# ajoute «  #Shorts ».
TITLE_MAX = 92


class BdCardError(RuntimeError):
    """La production BD n'a pas pu aboutir."""


# ---------------------------------------------------------------------------
# Rasterisation SVG -> PNG
# ---------------------------------------------------------------------------

_CHROME_CANDIDATES = (
    "chromium", "chromium-browser", "google-chrome", "chrome", "msedge",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
)

_rasterizer: Optional[Tuple[str, str]] = None  # (outil, chemin)


def _find_rasterizer() -> Tuple[str, str]:
    """Trouve un rasteriseur SVG, une fois pour toutes.

    L'ordre est celui de la PRODUCTION : rsvg-convert d'abord (leger, celui du
    VPS), Inkscape ensuite, un navigateur headless en dernier recours — il
    marche partout mais demarre en une seconde par carte.
    """
    global _rasterizer
    if _rasterizer:
        return _rasterizer
    for tool in ("rsvg-convert", "inkscape"):
        found = shutil.which(tool)
        if found:
            _rasterizer = (tool, found)
            logger.info("Rasteriseur SVG : %s", found)
            return _rasterizer
    for candidate in _CHROME_CANDIDATES:
        found = shutil.which(candidate) or (candidate if Path(candidate).exists() else None)
        if found:
            _rasterizer = ("chrome", found)
            logger.info("Rasteriseur SVG : navigateur headless %s", found)
            return _rasterizer
    raise BdCardError(
        "Aucun rasteriseur SVG trouve. Installe librsvg (apt-get install "
        "librsvg2-bin) sur le VPS, ou Chrome/Edge sur un poste."
    )


def rasterize(svg_path: Path, png_path: Path, width: int, height: int) -> None:
    """Rend un SVG en PNG aux dimensions demandees, ou leve BdCardError."""
    tool, exe = _find_rasterizer()
    if tool == "rsvg-convert":
        command = [exe, "-w", str(width), "-h", str(height),
                   "-o", str(png_path), str(svg_path)]
    elif tool == "inkscape":
        command = [exe, str(svg_path), "--export-type=png",
                   f"--export-filename={png_path}",
                   f"--export-width={width}", f"--export-height={height}"]
    else:
        # Chemins ABSOLUS des deux cotes : le navigateur n'herite pas de notre
        # repertoire de travail. --virtual-time-budget force une fin de rendu
        # deterministe au lieu d'attendre une « fin de chargement ».
        url = svg_path.resolve().as_uri()
        command = [exe, "--headless=new", "--disable-gpu", "--no-sandbox",
                   "--hide-scrollbars", "--virtual-time-budget=10000",
                   f"--screenshot={png_path.resolve()}",
                   f"--window-size={width},{height}", url]

    if tool == "chrome":
        # PIEGE VECU : capturer la sortie de Chrome par des tubes bloque
        # ``communicate()`` pour toujours sous Windows — le processus crashpad
        # herite du tube et ne le ferme jamais, meme apres la fin du rendu.
        # On redirige donc vers un FICHIER, relu seulement en cas d'echec.
        log = png_path.with_suffix(".chrome.log")
        with open(log, "w", encoding="utf-8", errors="replace") as sink:
            proc = subprocess.run(command, stdout=sink, stderr=subprocess.STDOUT,
                                  timeout=180)
        if proc.returncode != 0 or not png_path.exists():
            # Les Chromium anterieurs a 112 ne connaissent pas --headless=new.
            command[1] = "--headless"
            with open(log, "a", encoding="utf-8", errors="replace") as sink:
                proc = subprocess.run(command, stdout=sink,
                                      stderr=subprocess.STDOUT, timeout=180)
        detail = log.read_text(encoding="utf-8", errors="replace").strip()[-800:]
        try:
            log.unlink()
        except OSError:
            pass  # crashpad peut garder le fichier ouvert quelques secondes
    else:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=120)
        detail = ((proc.stderr or "") + (proc.stdout or "")).strip()[-800:]

    if proc.returncode != 0 or not png_path.exists() or png_path.stat().st_size == 0:
        raise BdCardError(
            f"Rasterisation echouee ({tool}, code {proc.returncode}) pour "
            f"{svg_path.name} :\n{detail}"
        )


def _downscale(src: Path, dest: Path, size: Tuple[int, int]) -> None:
    """Version 1x pour les posts Communaute, reduite proprement du rendu 2x."""
    from PIL import Image

    with Image.open(src) as img:
        img.convert("RGB").resize(size, Image.LANCZOS).save(dest, "PNG", optimize=True)


# ---------------------------------------------------------------------------
# Composition des cartes d'un sujet
# ---------------------------------------------------------------------------


@dataclass
class BoardCard:
    """Une carte du storyboard : son SVG, et la phrase dite pendant elle."""

    stem: str          # nom de fichier sans extension
    svg: str
    spoken: str


def storyboard(subject: bd_topics.BdSubject, lang: str) -> List[BoardCard]:
    """Toutes les cartes du sujet, dans l'ordre de lecture."""
    text = subject.text(lang)
    accent = subject.accent
    footer = subject.footer(lang)
    total = len(text.scenes)

    cards = [BoardCard(
        stem=f"{subject.id}-{lang}-bd-00",
        svg=bd_style.cover_card(
            header=subject.header(lang),
            name=text.name,
            real_name=text.real_name,
            date_line=text.date_line,
            place_line=text.place_line,
            band_text=text.hook,
            portrait=subject.portrait,
            icon=None if subject.portrait else subject.icon,
            accent=accent,
        ),
        spoken=text.hook,
    )]
    for position, scene in enumerate(text.scenes, start=1):
        cards.append(BoardCard(
            stem=f"{subject.id}-{lang}-bd-{position:02d}",
            svg=bd_style.scene_card(
                text=scene.text, icon=scene.icon,
                index=position, total=total,
                footer=footer, header=subject.header(lang), accent=accent,
            ),
            spoken=scene.text,
        ))
    cards.append(BoardCard(
        stem=f"{subject.id}-{lang}-bd-{total + 1:02d}",
        svg=bd_style.final_card(
            fact=text.fact, cta=subject.cta(lang), footer=footer,
            header=subject.header(lang),
            portrait=subject.portrait,
            icon=None if subject.portrait else subject.icon,
            accent=accent,
        ),
        spoken=text.fact,
    ))
    return cards


# ---------------------------------------------------------------------------
# Montage
# ---------------------------------------------------------------------------


def _segment(
    png_2x: Path, audio: Path, audio_seconds: float, out_path: Path,
    *, first: bool, last: bool,
) -> float:
    """Monte UNE carte : zoom lent, fondus, phrase calee. Renvoie sa duree."""
    import video_assembly

    seconds = LEAD_SECONDS + audio_seconds + TAIL_SECONDS
    frames = max(1, int(round(seconds * FPS)))
    # +12 % sur toute la carte la plus longue ; le pas par image est calcule
    # pour que la vitesse du zoom soit la MEME quelle que soit la duree.
    step = 0.12 / max(frames, 1)
    fade_in = 0.45 if first else 0.28
    fade_out = 0.55 if last else 0.28
    delay_ms = int(LEAD_SECONDS * 1000)

    graph = (
        f"[0:v]zoompan=z='min(zoom+{step:.6f},1.12)'"
        f":x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2'"
        f":d=1:s={bd_style.WIDTH}x{bd_style.HEIGHT}:fps={FPS},format=yuv420p,"
        f"fade=t=in:st=0:d={fade_in:.2f},"
        f"fade=t=out:st={max(0.0, seconds - fade_out):.3f}:d={fade_out:.2f}[v];"
        f"[1:a]adelay={delay_ms}|{delay_ms},apad,"
        f"aformat=sample_rates=44100:channel_layouts=stereo[a]"
    )
    command = [
        video_assembly.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
        "-loop", "1", "-framerate", str(FPS), "-t", f"{seconds:.3f}", "-i", str(png_2x),
        "-i", str(audio),
        "-filter_complex", graph,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-threads", str(video_assembly.FFMPEG_THREADS),
        "-t", f"{seconds:.3f}", str(out_path),
    ]
    proc = subprocess.run(command, capture_output=True, text=True)
    if proc.returncode != 0:
        raise BdCardError(
            f"ffmpeg a echoue sur {png_2x.name} (code {proc.returncode}) :\n"
            f"{proc.stderr.strip()[-1200:]}"
        )
    return seconds


def _concat(segments: Sequence[Path], out_path: Path) -> None:
    """Concatene les segments sans re-encoder : memes codecs, memes formats."""
    import video_assembly

    listing = out_path.parent / f"{out_path.stem}-concat.txt"
    listing.write_text(
        "".join(f"file '{p.resolve().as_posix()}'\n" for p in segments),
        encoding="utf-8",
    )
    command = [
        video_assembly.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(listing),
        "-c", "copy", "-movflags", "+faststart", str(out_path),
    ]
    proc = subprocess.run(command, capture_output=True, text=True)
    listing.unlink(missing_ok=True)
    if proc.returncode != 0 or not out_path.exists() or out_path.stat().st_size == 0:
        raise BdCardError(
            f"Concatenation echouee (code {proc.returncode}) :\n"
            f"{proc.stderr.strip()[-1200:]}"
        )


# ---------------------------------------------------------------------------
# Metadonnees et pack de posts
# ---------------------------------------------------------------------------


def _fit_title(text: str, limit: int = TITLE_MAX) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,;:.") + "…"


def _description(subject: bd_topics.BdSubject, lang: str) -> str:
    import card_pack

    text = subject.text(lang)
    art_line = (
        "Illustrations : dessins originaux « ligne claire » Paris Explorer."
        if lang == "fr" else
        "Artwork: original ligne claire illustrations by Paris Explorer."
    )
    return f"{text.hook}\n\n{text.fact}\n\n{card_pack._channel_line(lang)}\n\n{art_line}"


def write_meta(subject: bd_topics.BdSubject, lang: str, video: Path) -> Path:
    """Declare le MP4 comme Short du sujet, la ou plan_week le recensera."""
    text = subject.text(lang)
    meta = {
        "topic_id": subject.id,
        "lang": lang,
        "style": "bd",
        "title": _fit_title(text.title),
        "description": _description(subject, lang),
        "tags": list(dict.fromkeys(text.tags + [text.name, "Paris"])),
        "shorts": [str(video)],
    }
    meta_dir = VIDEOS_ROOT / subject.id
    meta_dir.mkdir(parents=True, exist_ok=True)
    meta_path = meta_dir / f"{subject.id}-{lang}.json"
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return meta_path


def write_posts_pack(
    subject: bd_topics.BdSubject, lang: str, pngs: Sequence[Path]
) -> Path:
    """Pack de posts Communaute : un PNG par carte, legende prete a coller."""
    text = subject.text(lang)
    spoken = [text.hook] + [s.text for s in text.scenes] + [text.fact]
    art_credit = (
        "Dessin original Paris Explorer — style ligne claire."
        if lang == "fr" else
        "Original artwork by Paris Explorer — ligne claire style."
    )
    sections = []
    for position, (png, caption) in enumerate(zip(pngs, spoken)):
        sections.append(
            f"## Carte {position} — {png.name}\n\n"
            f"Image a joindre : {png}\n\n"
            f"Legende a coller :\n\n"
            f"{caption}\n\n"
            f"— Paris Explorer\n{art_credit}\n"
        )
    pack_dir = POSTS_ROOT / subject.id
    pack_dir.mkdir(parents=True, exist_ok=True)
    pack_path = pack_dir / f"{subject.id}-{lang}-posts.md"
    header = (
        f"# Posts Communaute — {text.title} [{lang}]\n\n"
        "Mode d'emploi : YouTube Studio > Communaute > Creer un post, joindre "
        "le PNG indique, coller la legende. Dessins originaux : aucun credit "
        "photo a reporter.\n\n"
    )
    pack_path.write_text(header + "\n".join(sections), encoding="utf-8")
    return pack_path


# ---------------------------------------------------------------------------
# Production d'un sujet
# ---------------------------------------------------------------------------


@dataclass
class BdResult:
    """Ce que la production a ecrit sur le disque."""

    video: Optional[Path]
    meta: Optional[Path]
    pack: Path
    pngs: List[Path]
    seconds: float


def produce(
    subject: bd_topics.BdSubject, lang: str, *, video: bool = True,
    force: bool = False,
) -> BdResult:
    """Produit un sujet BD dans une langue : cartes, voix off, MP4, pack.

    Idempotent par construction : les SVG et PNG sont re-ecrits (c'est une
    seconde de calcul), la voix off sort du cache de ``narration`` si le texte
    n'a pas change, et ``force`` resynthetise tout.
    """
    if lang not in subject.langs:
        raise BdCardError(
            f"« {subject.id} » n'a pas de textes '{lang}'. "
            f"Langues disponibles : {', '.join(subject.langs)}"
        )
    out_dir = BD_ROOT / subject.id
    svg_dir = out_dir / "svg"
    svg_dir.mkdir(parents=True, exist_ok=True)

    cards = storyboard(subject, lang)
    logger.info("« %s » [%s] : %d cartes a rendre", subject.id, lang, len(cards))

    # 1. SVG puis PNG (2x pour le montage, 1x pour les posts).
    pngs_1x: List[Path] = []
    pngs_2x: List[Path] = []
    for card in cards:
        svg_path = svg_dir / f"{card.stem}.svg"
        svg_path.write_text(card.svg, encoding="utf-8")
        png_2x = svg_dir / f"{card.stem}-2x.png"
        rasterize(svg_path, png_2x,
                  bd_style.WIDTH * RASTER_SCALE, bd_style.HEIGHT * RASTER_SCALE)
        png_1x = out_dir / f"{card.stem}.png"
        _downscale(png_2x, png_1x, (bd_style.WIDTH, bd_style.HEIGHT))
        pngs_1x.append(png_1x)
        pngs_2x.append(png_2x)

    pack = write_posts_pack(subject, lang, pngs_1x)

    if not video:
        return BdResult(video=None, meta=None, pack=pack, pngs=pngs_1x, seconds=0.0)

    # 2. Une piste de voix par carte : c'est elle qui donne la duree.
    import narration

    audio_dir = out_dir / "audio"
    tracks: List[Tuple[Path, float]] = []
    for card in cards:
        result = narration.synthesize(
            card.spoken, lang, audio_dir / f"{card.stem}.mp3", force=force,
        )
        tracks.append((result.path, result.duration))

    # 3. Montage segment par segment, puis concatenation.
    out_path = out_dir / f"{subject.id}-{lang}.mp4"
    workdir = Path(tempfile.mkdtemp(prefix="pe-bd-"))
    total_seconds = 0.0
    try:
        segments: List[Path] = []
        for position, (card, png_2x, (audio, duration)) in enumerate(
            zip(cards, pngs_2x, tracks)
        ):
            segment = workdir / f"seg-{position:02d}.mp4"
            total_seconds += _segment(
                png_2x, audio, duration, segment,
                first=(position == 0), last=(position == len(cards) - 1),
            )
            segments.append(segment)
        _concat(segments, out_path)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    if not TARGET_MIN <= total_seconds <= TARGET_MAX:
        logger.warning(
            "« %s » [%s] dure %.0f s, hors de la fenetre %d-%d s visee. "
            "Ajuste le nombre ou la longueur des scenes.",
            subject.id, lang, total_seconds, int(TARGET_MIN), int(TARGET_MAX),
        )

    meta = write_meta(subject, lang, out_path)
    logger.info(
        "« %s » [%s] : %.0f s, %d cartes — %s",
        subject.id, lang, total_seconds, len(cards), out_path,
    )
    return BdResult(video=out_path, meta=meta, pack=pack, pngs=pngs_1x,
                    seconds=total_seconds)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Produit le Short BD ligne claire d'un sujet de content/bd/."
    )
    parser.add_argument("subject_id", nargs="?", help="identifiant du sujet BD")
    parser.add_argument("--lang", default="fr", choices=list(bd_topics.SUPPORTED_LANGS))
    parser.add_argument("--no-video", action="store_true",
                        help="ne rendre que les cartes PNG et le pack de posts")
    parser.add_argument("--force", action="store_true",
                        help="resynthetiser la voix meme si le texte n'a pas change")
    parser.add_argument("--list", action="store_true", dest="list_subjects",
                        help="lister les sujets BD disponibles")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stdout
    )

    subjects = {s.id: s for s in bd_topics.load_subjects(only_ready=False)}
    if args.list_subjects or not args.subject_id:
        for subject in sorted(subjects.values(), key=lambda s: s.id):
            marker = "ready" if subject.is_ready else "draft"
            langs = ",".join(subject.langs)
            anchor = f"  ancre {subject.anchor_date}" if subject.anchor_date else ""
            print(f"  {subject.id:32s} {subject.kind:12s} {marker:6s} [{langs}]{anchor}")
        return 0

    subject = subjects.get(args.subject_id)
    if subject is None:
        logger.error(
            "Sujet BD inconnu : %s. Disponibles : %s",
            args.subject_id, ", ".join(sorted(subjects)) or "(aucun)",
        )
        return 1

    try:
        result = produce(subject, args.lang, video=not args.no_video, force=args.force)
    except (BdCardError, bd_style.StyleError) as exc:
        logger.error("%s", exc)
        return 1

    print()
    for png in result.pngs:
        print(f"  carte : {png}")
    print(f"  pack  : {result.pack}")
    if result.video:
        print(f"  short : {result.video}  ({result.seconds:.0f} s)")
        print(f"  meta  : {result.meta}")
        print("\nProchaines etapes : `python plan_week.py` pour le placer au "
              "calendrier ; le pack de posts se colle a la main dans YouTube Studio.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
