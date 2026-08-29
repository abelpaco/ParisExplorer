"""Garde du calendrier : alerte quand le plan a moins de deux jours devant lui.

POURQUOI CE SCRIPT
------------------
Le 28/08/2026, la chaine a passe une journee sans publier : le plan etait
arrive au bout la veille et personne ne l'avait vu venir — la regeneration
reposait sur la memoire humaine. Ce script regarde chaque jour la date du
dernier creneau du plan ; s'il reste moins de RESERVE_HEURES devant, il
alerte Paco en message prive Telegram (jamais sur le canal public : les
soucis d'intendance ne regardent pas les abonnes).

L'alerte passe par le bot du canal (``telegram_annonce.secret``), champ
``alerte_chat_id`` — le chat prive de Paco avec le bot (il faut avoir
envoye /start au bot une fois pour qu'il puisse ecrire). Sans ce champ,
la garde se contente d'un warning dans son journal.

Une seule alerte par jour : etre prevenu, pas harcele.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

logger = logging.getLogger("garde-plan")

PLAN_FILE = Path("content/metadata/publication_plan.json")
SECRET_FILE = Path("telegram_annonce.secret")
STATE_FILE = Path("content/metadata/garde_plan.json")

RESERVE_HEURES = 48


def _alerter(texte: str) -> bool:
    if not SECRET_FILE.exists():
        return False
    secret = json.loads(SECRET_FILE.read_text(encoding="utf-8"))
    chat = secret.get("alerte_chat_id")
    if not chat:
        return False
    reponse = requests.post(
        f"https://api.telegram.org/bot{secret['token']}/sendMessage",
        data={"chat_id": chat, "text": texte},
        timeout=30,
    )
    return bool(reponse.json().get("ok"))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not PLAN_FILE.exists():
        dernier = None
    else:
        plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
        dernier = max(
            (datetime.fromisoformat(s["when"]) for s in plan), default=None
        )

    maintenant = datetime.now(timezone.utc)
    # Trou de couverture immediate : une reserve confortable au bout du plan
    # ne sert a rien si les prochaines 24 h sont vides — vecu DEUX fois (28 et
    # 29/08) : une regeneration lancee apres minuit UTC demarre au lendemain
    # et efface le jour courant.
    prochain = None
    if dernier is not None:
        futurs = [datetime.fromisoformat(s["when"]) for s in plan
                  if datetime.fromisoformat(s["when"]) > maintenant]
        prochain = min(futurs, default=None)
    trou_24h = prochain is None or (prochain - maintenant).total_seconds() > 24 * 3600

    if dernier is not None:
        reste = (dernier - maintenant).total_seconds() / 3600
        if reste >= RESERVE_HEURES and not trou_24h:
            logger.info("Plan couvert jusqu'au %s (%.0f h de reserve), prochain creneau %s.",
                        dernier, reste, prochain)
            return 0
    else:
        reste = 0.0

    aujourdhui = maintenant.strftime("%Y-%m-%d")
    etat = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    if etat.get("derniere_alerte") == aujourdhui:
        logger.info("Reserve basse (%.0f h) mais deja alerte aujourd'hui.", reste)
        return 0

    if dernier is None:
        detail = "est VIDE"
    elif trou_24h:
        detail = (
            f"a un TROU : aucun creneau dans les prochaines 24 h "
            f"(prochain : {prochain:%d/%m %H:%M} UTC)" if prochain else
            "n'a plus aucun creneau futur"
        )
    else:
        detail = f"se termine le {dernier:%d/%m a %H:%M} ({reste:.0f} h de reserve)"
    texte = (
        "⚠️ Paris Explorer : le calendrier de publication " + detail
        + ".\nRegenerer : cd ~/parisexplorer && .venv/bin/python plan_week.py"
    )
    if _alerter(texte):
        logger.warning("Alerte envoyee a Paco : %.0f h de reserve.", reste)
    else:
        logger.warning(
            "RESERVE BASSE (%.0f h) et pas d'alerte_chat_id dans le secret : "
            "alerte visible ici seulement.", reste,
        )
    etat["derniere_alerte"] = aujourdhui
    STATE_FILE.write_text(json.dumps(etat, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
