"""Le vivier auto-renouvele : la boucle qui empeche le catalogue de s'epuiser.

POURQUOI CE SCRIPT (decision Paco du 28/08/2026 — « le vrai edge »)
-------------------------------------------------------------------
Le 28/08, la chaine a passe une journee muette : plus de plan, et la
regeneration reposait sur une memoire humaine. Ce script ferme la boucle :
quand la reserve du calendrier passe sous RESERVE_DECLENCHEMENT_H, il
ECRIT de nouveaux sujets (API Claude), previent Paco en DM (validation en
supplement, jamais en goulot — il peut repondre « retire <sujet> » au bot),
PRODUIT les videos, et REGENERE le plan en preservant les creneaux restants
du jour. Le tout journalise, borne, et froussard : au moindre doute, il
s'arrete et le dit, plutot que de publier n'importe quoi sous la marque.

GARDE-FOUS
----------
- Un cycle au plus tous les COOLDOWN_JOURS, verrou flock dans le cron.
- Deux echecs consecutifs => la boucle se DESARME et alerte : la relancer
  demande d'effacer `echecs_consecutifs` de vivier_etat.json a la main.
- Chaque sujet genere est valide (YAML, champs, longueur, collision d'id
  contre topics/ ET le registre — la lecon louvre-forteresse) ; un sujet
  invalide est jete, jamais rafistole.
- L'ecriture exige des faits etablis et le conditionnel sur le debattu ;
  un doute sur un fait vaut abandon du sujet (consigne dans le prompt).

    python vivier.py             cycle si la reserve est basse (cron)
    python vivier.py --simuler   generation + DM seulement, rien d'ecrit
    python vivier.py --forcer    cycle complet meme si la reserve est haute
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

logger = logging.getLogger("vivier")

PLAN_FILE = Path("content/metadata/publication_plan.json")
REGISTRY_FILE = Path("content/metadata/published_topics.json")
TOPICS_DIR = Path("content/topics")
ETAT_FILE = Path("content/metadata/vivier_etat.json")
RETIRES_FILE = Path("content/metadata/sujets_retires.json")
SECRET_TELEGRAM = Path("telegram_annonce.secret")
SECRET_ANTHROPIC = Path("anthropic.secret")

RESERVE_DECLENCHEMENT_H = 168   # 7 jours : la boucle a le temps de tout faire
COOLDOWN_JOURS = 3
N_SUJETS = 10
# Autant que de phrases dans le bloc ``cards`` d'un sujet : elles sont
# ecrites a la main, une par carte.
CARTES_PAR_SUJET = 3
MODELE = "claude-sonnet-5"      # l'ecriture est le produit : pas d'economie ici
MAX_TOKENS = 16000

REGLES = """Tu ecris des sujets pour la chaine YouTube « Paris Explorer » : l'histoire,
les monuments et les secrets de Paris, racontes en francais.

STYLE MAISON (imperatif) :
- 320 a 380 mots de narration, phrases courtes, present de narration.
- La PREMIERE phrase est l'accroche : le fait le plus etonnant, dit simplement.
- Une seule anecdote forte par sujet, un debut, un developpement, une chute.
- Angle qui gagne : le cache, l'insolite, le « ce jour-la a Paris ».
- JAMAIS de superlatif creux, jamais de « saviez-vous que » dans la narration.

RIGUEUR FACTUELLE (non negociable) :
- Uniquement des faits historiques ETABLIS et datables. Si un point est
  debattu, l'ecrire au conditionnel en le disant. Si tu n'es pas certain
  d'un fait central, ABANDONNE le sujet et proposes-en un autre.
- Les dates, noms et lieux doivent etre exacts.

FORMAT : chaque sujet est un document YAML complet, precede d'une ligne
exactement egale a « === SUJET === ». Schema :

=== SUJET ===
id: identifiant-kebab-court
category: histoire   # ou decouverte
status: ready
# anchor_date: "MM-JJ"   # SEULEMENT si anniversaire precis et verifiable
image_queries:
  - "requete Wikimedia Commons en anglais"   # 6 requetes, sujets photographiables
fr:
  title: "Titre accrocheur, 90 caracteres max"
  subtitle: "Sous-titre d'une ligne"
  narration: |
    Le texte...
  tags:
    - "tag1"
  cards:
    - "Trois phrases autonomes, une par carte, la premiere = l'accroche."
"""


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------

def _dm(texte: str) -> None:
    if not SECRET_TELEGRAM.exists():
        logger.warning("Pas de secret Telegram : DM impossible.")
        return
    secret = json.loads(SECRET_TELEGRAM.read_text(encoding="utf-8"))
    chat = secret.get("alerte_chat_id")
    if not chat:
        return
    requests.post(
        f"https://api.telegram.org/bot{secret['token']}/sendMessage",
        data={"chat_id": chat, "text": texte[:4000]},
        timeout=30,
    )


def _reserve_heures() -> float:
    if not PLAN_FILE.exists():
        return 0.0
    plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    dernier = max((datetime.fromisoformat(s["when"]) for s in plan), default=None)
    if dernier is None:
        return 0.0
    return (dernier - datetime.now(timezone.utc)).total_seconds() / 3600


def _ids_existants() -> set:
    ids = {p.stem for p in TOPICS_DIR.glob("*.yaml")}
    if REGISTRY_FILE.exists():
        registre = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))["published"]
        ids |= {e["name"].split(":")[0] for e in registre}
    if RETIRES_FILE.exists():
        ids |= set(json.loads(RETIRES_FILE.read_text(encoding="utf-8"))["retires"])
    return ids


def _generer(existants: set) -> str:
    cle = SECRET_ANTHROPIC.read_text(encoding="utf-8").strip()
    demande = (
        f"Ecris {N_SUJETS} nouveaux sujets.\n\n"
        "INTERDIT de reprendre ou frole ces sujets deja traites (id) :\n"
        + ", ".join(sorted(existants))
        + "\n\nReponds UNIQUEMENT avec les blocs YAML separes par « === SUJET === »."
    )
    reponse = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": cle,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": MODELE,
            "max_tokens": MAX_TOKENS,
            # Sans ceci, Sonnet 5 peut engloutir TOUT le budget de sortie en
            # reflexion interne et ne rien ecrire (vecu : stop=max_tokens,
            # 16 000 tokens, 0 caractere). L'ecriture n'en a pas besoin.
            "thinking": {"type": "disabled"},
            "system": REGLES,
            "messages": [{"role": "user", "content": demande}],
        },
        timeout=600,
    )
    corps = reponse.json()
    if "content" not in corps:
        raise RuntimeError(f"API Claude : {corps}")
    txt = "".join(b.get("text", "") for b in corps["content"])
    logger.info(
        "API : stop=%s, %d caracteres, %s tokens de sortie.",
        corps.get("stop_reason"), len(txt),
        (corps.get("usage") or {}).get("output_tokens"),
    )
    return txt


def _valider(texte: str, existants: set) -> list:
    """Retourne les sujets valides [(id, yaml_dict, source_texte)] ; jette le reste."""
    # Le modele emballe parfois sa reponse dans des clotures de code — vecu
    # au premier essai (0/10 valide). On les retire avant de decouper.
    texte = re.sub(r"^```[a-z]*\s*$", "", texte, flags=re.MULTILINE)
    valides = []
    for bloc in texte.split("=== SUJET ==="):
        bloc = bloc.strip()
        if not bloc:
            continue
        try:
            data = yaml.safe_load(bloc)
        except yaml.YAMLError as exc:
            logger.warning("Bloc YAML invalide, jete : %s", exc)
            continue
        if not isinstance(data, dict):
            continue
        tid = data.get("id", "")
        fr = data.get("fr") or {}
        problemes = []
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,40}", str(tid)):
            problemes.append("id")
        if tid in existants:
            problemes.append("collision")
        if len(str(fr.get("narration", "")).split()) < 250:
            problemes.append("narration courte")
        if len(fr.get("cards") or []) != 3:
            problemes.append("cartes != 3")
        if len(data.get("image_queries") or []) < 4:
            problemes.append("image_queries")
        if not fr.get("title"):
            problemes.append("titre")
        ancre = data.get("anchor_date")
        if ancre is not None and not re.fullmatch(r"\d{2}-\d{2}", str(ancre)):
            problemes.append("anchor_date")
        if problemes:
            logger.warning("Sujet « %s » jete : %s", tid, ", ".join(problemes))
            continue
        data["status"] = "ready"
        valides.append((tid, data, bloc))
        existants.add(tid)
    return valides


def _produire(tid: str, langue: str, sans_cartes: list) -> bool:
    """Produit la video d'un sujet dans une langue, puis ses cartes.

    Renvoie False si la VIDEO a echoue — le sujet n'a alors rien de
    publiable dans cette langue. Un echec des seules cartes est note et
    n'empeche pas de continuer : une video sans ses cartes se publie tres
    bien, la perdre en entier serait disproportionne.
    """
    r = subprocess.run(
        [".venv/bin/python", "produce_topic.py", tid, "--lang", langue],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        # Sans cette trace, un echec restait muet : il a fallu rejouer la
        # production a la main pour savoir ce qui avait lache.
        logger.error("Production %s [%s] : ECHEC\n%s", tid, langue, r.stderr[-800:])
        return False
    logger.info("Production %s [%s] : ok", tid, langue)

    # Les cartes. Sans elles un sujet n'a ni carte animee ni pack
    # Communaute — et le stock de cartes ne se renouvelle JAMAIS, alors que
    # le calendrier en reclame une par jour. Vingt-huit sujets sur quarante
    # et un s'etaient ainsi retrouves sans la moindre carte.
    rc = subprocess.run(
        [".venv/bin/python", "visual_cards.py", tid, "--lang", langue,
         "--format", "story", "--animate", "--count", str(CARTES_PAR_SUJET)],
        capture_output=True, text=True,
    )
    if rc.returncode == 0:
        logger.info("Cartes %s [%s] : ok", tid, langue)
    else:
        sans_cartes.append(f"{tid}:{langue}")
        logger.error("Cartes %s [%s] : ECHEC\n%s", tid, langue, rc.stderr[-800:])
    return True


def _preserver_aujourdhui(sauvegarde: list) -> None:
    """plan_week demarre demain : re-greffe les creneaux restants du jour."""
    maintenant = datetime.now(timezone.utc)
    plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    presents = {s["key"] for s in plan}
    greffes = 0
    for s in sauvegarde:
        quand = datetime.fromisoformat(s["when"])
        if quand > maintenant and quand.date() == maintenant.astimezone(quand.tzinfo).date() \
                and s["key"] not in presents:
            plan.append(s)
            greffes += 1
    if greffes:
        plan.sort(key=lambda s: s["when"])
        PLAN_FILE.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("%d creneau(x) du jour preserves apres regeneration.", greffes)


# ---------------------------------------------------------------------------
# Cycle
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Regenere le vivier de sujets quand la reserve baisse.")
    parser.add_argument("--simuler", action="store_true", help="generation + DM, rien d'ecrit")
    parser.add_argument("--forcer", action="store_true", help="cycle meme si la reserve est haute")
    args = parser.parse_args(argv)

    etat = json.loads(ETAT_FILE.read_text(encoding="utf-8")) if ETAT_FILE.exists() else {}
    if etat.get("echecs_consecutifs", 0) >= 2:
        logger.error("Boucle DESARMEE (2 echecs) : effacer echecs_consecutifs pour relancer.")
        return 1

    reserve = _reserve_heures()
    if not args.forcer and not args.simuler and reserve >= RESERVE_DECLENCHEMENT_H:
        logger.info("Reserve %.0f h >= %d h : rien a faire.", reserve, RESERVE_DECLENCHEMENT_H)
        return 0

    dernier = etat.get("dernier_cycle")
    if dernier and not args.forcer and not args.simuler:
        age_j = (datetime.now(timezone.utc) - datetime.fromisoformat(dernier)).days
        if age_j < COOLDOWN_JOURS:
            logger.info("Dernier cycle il y a %d j (< %d) : on attend.", age_j, COOLDOWN_JOURS)
            return 0

    try:
        existants = _ids_existants()
        logger.info("Cycle : reserve %.0f h, %d sujets existants, generation...", reserve, len(existants))
        texte = _generer(existants)
        sujets = _valider(texte, set(existants))
        if len(sujets) < 4:
            # Autopsie : garder la copie exacte de ce qui a ete refuse.
            Path("logs/vivier-refuse.txt").write_text(texte, encoding="utf-8")
            raise RuntimeError(
                f"Seulement {len(sujets)} sujet(s) valide(s) sur {N_SUJETS} : "
                f"lot refuse (copie dans logs/vivier-refuse.txt)."
            )

        lignes = [f"• {tid} — {data['fr']['title']}" for tid, data, _ in sujets]
        _dm(
            ("🧪 SIMULATION vivier" if args.simuler else "📚 Nouveau vivier en route")
            + f" ({len(sujets)} sujets, réserve {reserve:.0f} h) :\n\n"
            + "\n".join(lignes)
            + "\n\nPour en écarter un : réponds « retire <id> »."
        )
        if args.simuler:
            logger.info("Simulation terminee : %d sujets valides, rien d'ecrit.", len(sujets))
            return 0

        for tid, data, _ in sujets:
            (TOPICS_DIR / f"{tid}.yaml").write_text(
                yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
            )
        logger.info("%d sujet(s) ecrits dans %s.", len(sujets), TOPICS_DIR)

        produits, echecs, sans_cartes, sans_anglais = [], [], [], []
        for tid, _, _ in sujets:
            if not _produire(tid, "fr", sans_cartes):
                echecs.append(tid)
                continue
            produits.append(tid)

            # L'anglais, dans la foulee. Le vivier n'ecrivait qu'en francais :
            # dix-huit sujets se sont retrouves sans la moindre version
            # anglaise, et le desequilibre repartait a chaque cycle alors que
            # le calendrier alterne les deux langues. Un echec ici ne coute
            # que la version anglaise — le sujet francais reste publiable.
            ra = subprocess.run(
                [".venv/bin/python", "version_anglaise.py", "--sujet", tid],
                capture_output=True, text=True,
            )
            if ra.returncode != 0:
                sans_anglais.append(tid)
                logger.error("Version anglaise %s : ECHEC\n%s", tid, ra.stderr[-800:])
            elif not _produire(tid, "en", sans_cartes):
                sans_anglais.append(tid)

        sauvegarde = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
        r = subprocess.run([".venv/bin/python", "plan_week.py", "--days", "21"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"plan_week a echoue : {r.stderr[-500:]}")
        _preserver_aujourdhui(sauvegarde)
        plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
        fin = max(s["when"] for s in plan)

        etat.update({"dernier_cycle": datetime.now(timezone.utc).isoformat(),
                     "echecs_consecutifs": 0})
        ETAT_FILE.write_text(json.dumps(etat, indent=2), encoding="utf-8")
        _dm(
            f"✅ Vivier régénéré : {len(produits)} sujet(s) produits"
            + (f", {len(echecs)} échec(s) ({', '.join(echecs)})" if echecs else "")
            + (f", {len(sans_anglais)} sans version anglaise "
               f"({', '.join(sans_anglais)})" if sans_anglais else "")
            + (f", {len(sans_cartes)} sans cartes ({', '.join(sans_cartes)})"
               if sans_cartes else "")
            + f". Plan : {len(plan)} créneaux jusqu'au {fin[:10]}."
        )
        return 0

    except Exception as exc:
        etat["echecs_consecutifs"] = etat.get("echecs_consecutifs", 0) + 1
        ETAT_FILE.write_text(json.dumps(etat, indent=2), encoding="utf-8")
        logger.exception("Cycle en echec (%d consecutif(s)).", etat["echecs_consecutifs"])
        _dm(f"❌ Boucle vivier en échec ({etat['echecs_consecutifs']}/2) : {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
