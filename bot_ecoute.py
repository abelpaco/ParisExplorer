"""Le droit de retrait de Paco : le bot ecoute son chat prive, et lui seul.

POURQUOI CE SCRIPT
------------------
La boucle vivier produit et publie sans attendre de validation — c'est son
edge. La contrepartie (decision Paco du 28/08/2026) : un droit de retrait
permanent, non bloquant. Paco repond « retire <sujet> » au bot ; le sujet
saute de tous ses creneaux futurs, entre dans la liste noire que plan_week
et vivier consultent, et Paco recoit le bilan — y compris le nombre de
publications DEJA en ligne, qui restent a passer en prive dans Studio (le
retrait automatique de contenus publies serait un pouvoir trop grand pour
un message texte).

SECURITE : seuls les messages du chat ``alerte_chat_id`` sont lus. Tout le
reste — canal, inconnus — est ignore et marque lu. L'offset getUpdates est
persiste : un message n'est traite qu'une fois.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import requests

logger = logging.getLogger("bot-ecoute")

SECRET_FILE = Path("telegram_annonce.secret")
OFFSET_FILE = Path("content/metadata/bot_offset.json")
PLAN_FILE = Path("content/metadata/publication_plan.json")
REGISTRY_FILE = Path("content/metadata/published_topics.json")
RETIRES_FILE = Path("content/metadata/sujets_retires.json")
TOPICS_DIR = Path("content/topics")

AIDE = (
    "Commandes :\n"
    "• retire <sujet> — retire un sujet du calendrier (ex. retire bievre)\n"
    "• reserve — l'etat du calendrier\n"
    "Le retrait n'agit que sur les creneaux futurs ; ce qui est deja en "
    "ligne se passe en prive dans YouTube Studio."
)


def _retirer(topic_id: str) -> str:
    connu = (TOPICS_DIR / f"{topic_id}.yaml").exists()
    plan = json.loads(PLAN_FILE.read_text(encoding="utf-8")) if PLAN_FILE.exists() else []
    garde = [s for s in plan if not s["key"].startswith(f"{topic_id}:")]
    retires_du_plan = len(plan) - len(garde)
    if not connu and retires_du_plan == 0:
        return f"Sujet inconnu : « {topic_id} ». Rien n'a change."
    PLAN_FILE.write_text(json.dumps(garde, ensure_ascii=False, indent=2), encoding="utf-8")

    noire = json.loads(RETIRES_FILE.read_text(encoding="utf-8")) if RETIRES_FILE.exists() else {"retires": []}
    if topic_id not in noire["retires"]:
        noire["retires"].append(topic_id)
    RETIRES_FILE.write_text(json.dumps(noire, ensure_ascii=False, indent=2), encoding="utf-8")

    en_ligne = 0
    if REGISTRY_FILE.exists():
        registre = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))["published"]
        en_ligne = sum(1 for e in registre if e["name"].startswith(f"{topic_id}:"))

    logger.warning("RETRAIT %s : %d creneau(x) supprimes, %d deja en ligne.",
                   topic_id, retires_du_plan, en_ligne)
    return (
        f"✂️ « {topic_id} » retiré : {retires_du_plan} créneau(x) déprogrammé(s), "
        f"liste noire mise à jour (plan_week et vivier l'ignoreront)."
        + (f"\n⚠️ {en_ligne} publication(s) déjà en ligne : à passer en privé "
           f"dans Studio si tu le souhaites." if en_ligne else "")
    )


def _reserve() -> str:
    from datetime import datetime, timezone
    plan = json.loads(PLAN_FILE.read_text(encoding="utf-8")) if PLAN_FILE.exists() else []
    if not plan:
        return "Calendrier VIDE."
    fin = max(s["when"] for s in plan)
    heures = (datetime.fromisoformat(fin) - datetime.now(timezone.utc)).total_seconds() / 3600
    return f"Calendrier : {len(plan)} créneaux, couvert jusqu'au {fin[:16]} ({heures:.0f} h de réserve)."


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not SECRET_FILE.exists():
        return 0
    secret = json.loads(SECRET_FILE.read_text(encoding="utf-8"))
    chat_paco = secret.get("alerte_chat_id")
    if not chat_paco:
        return 0
    base = f"https://api.telegram.org/bot{secret['token']}"

    offset = 0
    if OFFSET_FILE.exists():
        offset = json.loads(OFFSET_FILE.read_text(encoding="utf-8")).get("offset", 0)

    corps = requests.get(f"{base}/getUpdates", params={"offset": offset, "timeout": 0},
                         timeout=30).json()
    for update in corps.get("result", []):
        offset = update["update_id"] + 1
        message = update.get("message") or {}
        if message.get("chat", {}).get("id") != chat_paco:
            continue  # tout le reste est ignore, mais marque lu
        texte = (message.get("text") or "").strip()
        mots = texte.lower().split()
        if len(mots) == 2 and mots[0] in ("retire", "retirer", "/retire"):
            reponse = _retirer(mots[1])
        elif mots and mots[0] in ("reserve", "réserve", "/reserve"):
            reponse = _reserve()
        elif mots and mots[0] in ("/start", "aide", "/aide", "/help"):
            reponse = AIDE
        else:
            reponse = "Commande inconnue.\n\n" + AIDE
        requests.post(f"{base}/sendMessage",
                      data={"chat_id": chat_paco, "text": reponse}, timeout=30)
        logger.info("Commande traitee : %s", texte[:60])

    OFFSET_FILE.write_text(json.dumps({"offset": offset}), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
