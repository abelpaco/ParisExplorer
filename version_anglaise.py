"""Ecrit la version anglaise des sujets qui n'en ont pas.

POURQUOI CE SCRIPT (decision Paco du 07/09/2026, option B)
---------------------------------------------------------
Le vivier n'ecrit qu'en francais. Dix-huit sujets — les neuf de septembre,
les cinq nes du vivier et quelques autres — n'avaient donc AUCUNE version
anglaise : ni video, ni Short, ni carte. Le desequilibre s'aggravait a
chaque cycle, alors que le calendrier alterne les deux langues.

Ce n'est pas un traducteur. Les narrations anglaises de la chaine sont
ECRITES, pas traduites : meme recit, memes faits, mais des phrases qui
sonnent anglaises. Un texte francais traduit mot a mot s'entend
immediatement a l'oreille, surtout dit par une voix de synthese.

Le bloc produit est complet — titre, sous-titre, narration, mots-cles et
les trois phrases de cartes — et s'ajoute a la fin du YAML du sujet. Un
sujet dont la version anglaise existe deja est saute.

    python version_anglaise.py --lister      dit ce qui manque, n'ecrit rien
    python version_anglaise.py --sujet <id>  un seul sujet
    python version_anglaise.py               tous les sujets qui manquent
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

import requests
import yaml

logger = logging.getLogger("version-en")

SECRET_ANTHROPIC = Path("anthropic.secret")
TOPICS_DIR = Path("content/topics")
MODELE = "claude-sonnet-5"
MAX_TOKENS = 4000

REGLES = """Tu ecris la version ANGLAISE d'un sujet de la chaine YouTube
« Paris Explorer », a partir de sa version francaise.

TU N'ES PAS UN TRADUCTEUR. Le texte anglais doit avoir ete PENSE en anglais :
mêmes faits, meme deroule, meme chute, mais des phrases qui sonnent
naturellement anglaises. Une traduction litterale s'entend immediatement,
surtout dite par une voix de synthese.

STYLE (identique a la version francaise) :
- 320 a 380 mots de narration, phrases courtes, present de narration.
- La PREMIERE phrase est l'accroche : le fait le plus etonnant, dit simplement.
- Jamais de superlatif creux, jamais de « did you know ».
- Les noms propres francais restent en francais (Champ-de-Mars, Sacre-Coeur),
  avec au besoin une glose courte pour un lecteur anglophone.
- Les chiffres et les dates doivent etre EXACTEMENT ceux du texte francais.

FORMAT : reponds UNIQUEMENT par un document YAML, sans cloture de code, avec
exactement cette forme et rien d'autre :

title: "Titre accrocheur, 90 caracteres maximum"
subtitle: "Sous-titre d'une ligne"
narration: |
  Le texte anglais...
tags:
  - "tag1"
  - "tag2"
cards:
  - "Trois phrases autonomes, une par carte. Chacune se tient seule, hors du recit, et nomme son sujet."
"""


def _cle() -> str:
    if not SECRET_ANTHROPIC.exists():
        raise SystemExit("anthropic.secret introuvable.")
    return SECRET_ANTHROPIC.read_text(encoding="utf-8").strip()


def manquants() -> List[str]:
    """Sujets sans narration anglaise."""
    trouves = []
    for chemin in sorted(glob.glob(str(TOPICS_DIR / "*.yaml"))):
        data = yaml.safe_load(open(chemin, encoding="utf-8")) or {}
        if not (data.get("en") or {}).get("narration"):
            trouves.append(os.path.basename(chemin)[:-5])
    return trouves


def _demander(cle: str, fr: dict, sujet: str) -> str:
    charge = yaml.safe_dump(
        {
            "title": fr.get("title", ""),
            "subtitle": fr.get("subtitle", ""),
            "narration": fr.get("narration", ""),
            "tags": fr.get("tags", []),
            "cards": fr.get("cards", []),
        },
        allow_unicode=True, sort_keys=False,
    )
    reponse = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": cle, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={
            "model": MODELE,
            "max_tokens": MAX_TOKENS,
            # Sans cela, Sonnet peut engloutir tout le budget de sortie en
            # reflexion et ne rien ecrire (vecu sur le vivier le 28/08).
            "thinking": {"type": "disabled"},
            "system": REGLES,
            "messages": [{"role": "user", "content":
                          f"Sujet « {sujet} ». Version francaise :\n\n{charge}"}],
        },
        timeout=300,
    )
    corps = reponse.json()
    if "content" not in corps:
        raise RuntimeError(f"API Claude : {corps}")
    texte = "".join(b.get("text", "") for b in corps["content"])
    logger.info("  API : stop=%s, %d caracteres", corps.get("stop_reason"), len(texte))
    return texte


def _valider(texte: str, mots_fr: int = 0) -> Optional[dict]:
    import re
    texte = re.sub(r"^```[a-z]*\s*$", "", texte, flags=re.MULTILINE).strip()
    try:
        data = yaml.safe_load(texte)
    except yaml.YAMLError as exc:
        logger.error("  YAML invalide : %s", exc)
        return None
    if not isinstance(data, dict):
        return None
    problemes = []
    if not data.get("title"):
        problemes.append("titre")
    # Longueur jugee PAR RAPPORT au francais, pas dans l'absolu. L'anglais
    # dit la meme chose en moins de mots ; un seuil fixe a 250 rejetait des
    # versions parfaitement completes de sujets dont le francais lui-meme
    # n'en faisait que 264 (vecu sur passage-pommeraye-fake et
    # pigalle-brasseries-a-femmes). Ce qu'on traque, c'est un texte tronque
    # ou bacle — donc un ECART avec la source, pas un nombre.
    mots = len(str(data.get("narration", "")).split())
    plancher = max(200, int(mots_fr * 0.85)) if mots_fr else 250
    if mots < plancher:
        problemes.append(f"narration courte ({mots} mots, attendu >= {plancher})")
    if len(data.get("cards") or []) != 3:
        problemes.append("cartes != 3")
    if not data.get("tags"):
        problemes.append("tags")
    if problemes:
        logger.error("  Rejete : %s", ", ".join(problemes))
        return None
    return data


def _inserer(chemin: Path, bloc: dict) -> None:
    """Ajoute le bloc `en:` a la fin du YAML, sans toucher au reste.

    Passer par yaml.safe_dump sur le fichier entier le reecrirait et
    emporterait sa mise en forme — narration en bloc litteral comprise.
    """
    lignes = [""]
    lignes.append("en:")
    lignes.append(f'  title: "{bloc["title"].replace(chr(34), chr(39))}"')
    if bloc.get("subtitle"):
        lignes.append(f'  subtitle: "{bloc["subtitle"].replace(chr(34), chr(39))}"')
    lignes.append("  narration: |")
    for ligne in str(bloc["narration"]).strip().splitlines():
        lignes.append(f"    {ligne}".rstrip())
    lignes.append("  tags:")
    for tag in bloc["tags"]:
        lignes.append(f'    - "{str(tag).replace(chr(34), chr(39))}"')
    lignes.append("  cards:")
    for phrase in bloc["cards"]:
        lignes.append(f'    - "{str(phrase).replace(chr(34), chr(39))}"')
    with open(chemin, "a", encoding="utf-8") as flux:
        flux.write("\n".join(lignes) + "\n")


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Ecrit la version anglaise des sujets.")
    parser.add_argument("--lister", action="store_true", help="dit ce qui manque")
    parser.add_argument("--sujet", help="ne traiter que ce sujet")
    args = parser.parse_args(argv)

    a_faire = [args.sujet] if args.sujet else manquants()
    if args.lister:
        print(f"{len(a_faire)} sujet(s) sans version anglaise :")
        for sujet in a_faire:
            print("  ", sujet)
        return 0

    cle = _cle()
    faits, rates = [], []
    for sujet in a_faire:
        chemin = TOPICS_DIR / f"{sujet}.yaml"
        data = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
        if (data.get("en") or {}).get("narration"):
            logger.info("[deja] %s", sujet)
            continue
        fr = data.get("fr") or {}
        if not fr.get("narration"):
            logger.error("[sans fr] %s", sujet)
            rates.append(sujet)
            continue
        logger.info("%s ...", sujet)
        try:
            bloc = _valider(_demander(cle, fr, sujet),
                            mots_fr=len(str(fr.get("narration", "")).split()))
        except Exception as exc:
            logger.error("  echec : %s", exc)
            bloc = None
        if not bloc:
            rates.append(sujet)
            continue
        _inserer(chemin, bloc)
        # Relecture : un YAML casse ne se verrait qu'a la production.
        relu = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
        if not (relu.get("en") or {}).get("narration"):
            logger.error("  ECRIT MAIS ILLISIBLE : %s", sujet)
            rates.append(sujet)
            continue
        faits.append(sujet)
        logger.info("  [ok] %s : %d mots, %d cartes",
                    sujet, len(bloc["narration"].split()), len(bloc["cards"]))

    print(f"\n{len(faits)} version(s) anglaise(s) ecrite(s)"
          + (f", {len(rates)} echec(s) : {', '.join(rates)}" if rates else "."))
    return 1 if rates and not faits else 0


if __name__ == "__main__":
    sys.exit(main())
