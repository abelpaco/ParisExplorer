"""Un texte UNIQUE par publication, pour les reseaux sociaux.

POURQUOI CE MODULE (mesure du 06/09/2026)
-----------------------------------------
Les reseaux sanctionnent le contenu duplique. X interdit explicitement de
publier « le meme gabarit avec des variations mineures », et c'est le motif
qui coute des comptes. Or nos publications ne sont PAS uniques par nature :
les Shorts decoupes dans une meme video heritent tous du titre de la video.
Mesure sur le registre : **17 publications sur 114 portaient un titre deja
utilise**, dont un titre TROIS fois. Publier ces textes tels quels, en
automatique, revient a programmer notre propre suspension.

D'OU VIENT LE TEXTE
-------------------
- **carte** : sa phrase, ecrite a la main dans le bloc ``cards`` du sujet et
  stockee en clair dans ses metadonnees ;
- **Short** : une phrase de la NARRATION, prise a la position que le Short
  occupe dans la video (le Short 2 sur 3 puise vers le milieu). C'est la
  source la plus juste — le Short EST un extrait de cette narration — et
  surtout elle ne croise pas le reservoir des cartes ;
- **video longue** : titre et sous-titre, deja distincts.

L'UNICITE EST GARANTIE ICI, PAS ESPEREE
---------------------------------------
Premiere version : cartes et Shorts puisaient dans le meme bloc ``cards`` au
meme rang — ``card-1`` et ``short-1`` recevaient donc la MEME phrase, et la
mesure comptait 18 doublons au lieu de 17. Corrige en deux temps : des
sources distinctes, et surtout ``deja_vus`` — l'appelant passe l'ensemble
des textes deja publies, et on descend la liste des candidats jusqu'a en
trouver un libre. Esperer l'unicite ne suffit pas quand la sanction est la
suspension du compte.
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable, List, Optional, Set

logger = logging.getLogger("texte-social")

VIDEOS_ROOT = Path("content/videos")
CARDS_ROOT = Path("content/cards")

# Bornes d'une phrase publiable. En dessous, elle ne dit rien ; au-dessus,
# elle ne tient pas dans un post X une fois le lien (23 caracteres) et les
# mots-cles ajoutes.
PHRASE_MIN, PHRASE_MAX = 60, 240


def _premiere_ligne(texte: str) -> str:
    for ligne in (texte or "").splitlines():
        ligne = ligne.strip()
        if ligne:
            return ligne
    return ""


@lru_cache(maxsize=1)
def _sujets() -> dict:
    """Cartes et narrations de tous les sujets, par (id, langue).

    Charge une fois : le publieur appelle ce module a chaque publication.
    """
    table = {}
    try:
        import topic_loader
        for sujet in topic_loader.load_topics(only_ready=False):
            for lang in sujet.langs:
                texte = sujet.text(lang)
                table[(sujet.id, lang)] = {
                    "cards": list(getattr(texte, "cards", None) or []),
                    "narration": getattr(texte, "narration", "") or "",
                }
    except Exception as exc:  # un sujet illisible ne doit pas bloquer un post
        logger.warning("Sujets video illisibles (%s) : repli sur les titres.", exc)
    try:
        import bd_topics
        for sujet in bd_topics.load_subjects(only_ready=False):
            for lang in ("fr", "en"):
                try:
                    texte = sujet.text(lang)
                except Exception:
                    continue
                bribes = [b for b in (texte.hook, texte.fact) if b]
                scenes = [s.text for s in getattr(texte, "scenes", []) if s.text]
                if bribes or scenes:
                    table.setdefault((sujet.id, lang), {
                        "cards": bribes,
                        "narration": " ".join(scenes),
                    })
    except Exception as exc:
        logger.debug("Sujets BD indisponibles (%s).", exc)
    return table


def _phrases(narration: str) -> List[str]:
    """Decoupe la narration en phrases publiables, dans l'ordre du recit."""
    brut = re.split(r"(?<=[.!?])\s+", (narration or "").replace("\n", " "))
    return [
        p.strip() for p in brut
        if PHRASE_MIN <= len(p.strip()) <= PHRASE_MAX
    ]


def _lire(chemin: Path) -> Optional[dict]:
    if chemin.exists():
        try:
            return json.loads(chemin.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("Metadonnees illisibles : %s", chemin)
    return None


def candidats(name: str, titre_de_repli: str = "") -> List[str]:
    """Textes possibles pour ``name``, du plus juste au plus generique."""
    parts = name.split(":")
    sujet, lang = parts[0], (parts[1] if len(parts) > 1 else "fr")
    suffixe = parts[2] if len(parts) > 2 else ""
    source = _sujets().get((sujet, lang), {})
    cartes = source.get("cards", [])
    phrases = _phrases(source.get("narration", ""))
    liste: List[str] = []

    if suffixe.startswith("card-"):
        index = int(suffixe.split("-")[1])
        meta = _lire(CARDS_ROOT / sujet / f"{sujet}-{lang}-story-{index:02d}.json")
        if meta:
            phrase = _premiere_ligne(meta.get("description", ""))
            if phrase:
                liste.append(phrase)
        if 0 < index <= len(cartes):
            liste.append(cartes[index - 1])
        liste.extend(cartes)
        liste.extend(phrases)

    elif suffixe.startswith("short-"):
        index = int(suffixe.split("-")[1])
        meta = _lire(VIDEOS_ROOT / sujet / f"{sujet}-{lang}.json") or {}
        total = max(1, len(meta.get("shorts") or []) or 1)
        if phrases:
            # Le Short n sur m est decoupe vers le n-ieme tiers de la
            # narration : on y puise sa phrase, puis on s'en eloigne.
            pivot = min(len(phrases) - 1,
                        int((index - 0.5) / total * len(phrases)))
            ordre = sorted(range(len(phrases)), key=lambda i: (abs(i - pivot), i))
            liste.extend(phrases[i] for i in ordre)
        liste.extend(cartes)

    else:  # video longue
        meta = _lire(VIDEOS_ROOT / sujet / f"{sujet}-{lang}.json")
        if meta:
            titre = (meta.get("title") or "").strip()
            sous_titre = _premiere_ligne(meta.get("description", ""))
            if titre and sous_titre and sous_titre != titre:
                liste.append(f"{titre} — {sous_titre}")
            if titre:
                liste.append(titre)
        liste.extend(phrases)
        liste.extend(cartes)

    liste.append((titre_de_repli or name).replace(" #Shorts", "").strip())
    # Dedoublonne en gardant l'ordre de preference.
    vus, propres = set(), []
    for texte in liste:
        texte = (texte or "").strip()
        if texte and texte not in vus:
            vus.add(texte)
            propres.append(texte)
    return propres


def texte_pour(name: str, titre_de_repli: str = "",
               deja_vus: Optional[Iterable[str]] = None) -> str:
    """Le meilleur texte disponible pour ``name`` qui ne soit pas deja pris.

    Args:
        deja_vus: textes deja publies. Le premier candidat libre est retenu ;
            si tous sont pris, on rend le meilleur et c'est au publieur de
            refuser l'envoi — mieux vaut un trou qu'un doublon.
    """
    pris: Set[str] = set(deja_vus or ())
    liste = candidats(name, titre_de_repli)
    for texte in liste:
        if texte not in pris:
            return texte
    logger.warning("Aucun texte libre pour %s : le publieur doit refuser.", name)
    return liste[0] if liste else name


# ---------------------------------------------------------------------------
# Attribution stable
# ---------------------------------------------------------------------------
#
# Un texte doit rester attache a SA publication : sans cela, le pack reseaux,
# le depot du jour et le publieur X inventeraient chacun leur version, et le
# meme Short partirait sous trois formulations — exactement l'inconstance
# qu'on cherche a eviter. Le journal ci-dessous fixe l'attribution une fois
# pour toutes, et sert de reserve de textes deja pris.

JOURNAL_TEXTES = Path("content/metadata/textes_sociaux.json")


def _charger_journal() -> dict:
    if JOURNAL_TEXTES.exists():
        try:
            return json.loads(JOURNAL_TEXTES.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.error("Journal des textes illisible : on repart a vide.")
    return {}


def texte_attribue(name: str, titre_de_repli: str = "") -> str:
    """Le texte de ``name``, choisi a la premiere demande puis inchange."""
    journal = _charger_journal()
    if name in journal:
        return journal[name]
    texte = texte_pour(name, titre_de_repli, deja_vus=journal.values())
    journal[name] = texte
    JOURNAL_TEXTES.parent.mkdir(parents=True, exist_ok=True)
    JOURNAL_TEXTES.write_text(
        json.dumps(journal, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return texte


def deja_publie(texte: str) -> bool:
    """Ce texte a-t-il deja ete attribue a une autre publication ?"""
    return texte in set(_charger_journal().values())


def titre_court(name: str, titre_de_repli: str = "", limite: int = 90) -> str:
    """Le texte de ``name``, ramene a la longueur d'un titre YouTube.

    Les cartes procedent ainsi depuis toujours — leur titre est leur phrase,
    tronquee au mot. Les Shorts heritaient au contraire du titre de leur
    video longue : trois Shorts d'un meme sujet portaient donc le MEME titre
    dans le fil vertical, ce qui dessert autant le referencement que le
    spectateur, qui croit avoir deja vu la video.
    """
    texte = texte_attribue(name, titre_de_repli)
    if len(texte) <= limite:
        return texte

    # Couper au compteur donne des titres estropies (« ... la ville est tenue
    # par les »). On cherche d'abord une frontiere de sens : une ponctuation
    # forte, sinon une virgule, a condition qu'elle laisse un titre d'une
    # longueur decente. La proposition ainsi obtenue se suffit a elle-meme et
    # ne porte pas de points de suspension — ce n'est pas un texte coupe,
    # c'est une accroche.
    plancher = max(30, int(limite * 0.4))
    for signes in (":.!?;", ","):
        coupure = max(
            (texte.rfind(s, 0, limite) for s in signes),
            default=-1,
        )
        if coupure >= plancher:
            return texte[:coupure].rstrip(" ,;:.")

    coupe = texte[:limite - 1]
    if " " in coupe:
        coupe = coupe[:coupe.rfind(" ")]
    return coupe.rstrip(" ,;:.") + "…"
