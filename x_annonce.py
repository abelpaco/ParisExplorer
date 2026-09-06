"""Publie les nouvelles videos sur X (@parisexplorer75), en video native.

POURQUOI CE SCRIPT EST AUSSI METHODIQUE
---------------------------------------
Le compte personnel de Paco a ete suspendu DEFINITIVEMENT en aout 2026 pour
« automatisation non autorisee » : des dizaines de posts par jour via un
outil non officiel. Ce script est ecrit avec cette suspension en tete. Il ne
cherche pas a publier le plus possible — il cherche a ne jamais franchir une
ligne.

LES CINQ LIGNES QU'IL NE FRANCHIT PAS
-------------------------------------
1. **API officielle uniquement.** OAuth 1.0a, application declaree sous le
   compte lui-meme. C'est le point qui a coute le compte perso.
2. **Jamais deux fois le meme texte.** X interdit « le meme gabarit avec des
   variations mineures ». Nos Shorts heritent tous du titre de leur video :
   17 publications sur 114 portaient un titre deja utilise. Le texte vient
   donc de ``texte_social`` (une phrase par publication), et l'empreinte de
   chaque texte publie est conservee — un doublon fait ABANDONNER l'envoi,
   il n'est pas « arrange ».
3. **Volume tenu.** Plafond par jour (avec montee en puissance sur trois
   semaines, cf. RAMPE), plafond mensuel large sous la limite du palier
   gratuit, et deux heures minimum entre deux posts.
4. **Zero engagement automatise.** Ni like, ni retweet, ni abonnement, ni
   reponse. Ces appels ne sont pas « desactives » : ils ne sont pas ecrits.
   C'est la seule garantie qui ne depend pas d'un reglage.
5. **Il s'arrete tout seul.** Deux echecs consecutifs et la boucle se
   desarme en prevenant Paco ; un 429 fait reculer, jamais insister.

    python x_annonce.py --sonde    verifie les cles et l'acces, ne publie rien
    python x_annonce.py --init     marque l'existant comme traite
    python x_annonce.py            publie ce qui est du (cron)

``x_annonce.secret`` (chmod 600, gitignore) :
    {"api_key": "...", "api_secret": "...",
     "access_token": "...", "access_secret": "...",
     "rampe": true}
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import requests
from requests_oauthlib import OAuth1

import texte_social
from telegram_annonce import _fichier_local

logger = logging.getLogger("x")

SECRET_FILE = Path("x_annonce.secret")
STATE_FILE = Path("content/metadata/x_annonces.json")
REGISTRY_FILE = Path("content/metadata/published_topics.json")
SECRET_TELEGRAM = Path("telegram_annonce.secret")

API_TWEETS = "https://api.x.com/2/tweets"
API_UPLOAD = "https://upload.x.com/1.1/media/upload.json"

# X compte un lien pour 23 caracteres quelle que soit sa longueur.
LIMITE_TEXTE = 280
LONGUEUR_LIEN = 23
# Une video native porte bien mieux qu'un lien sortant, que l'algorithme
# etrangle. Le lien vers la chaine vit dans la bio, pas dans chaque post.
TAILLE_MAX_VIDEO = 500 * 1024 * 1024
# Duree maximale d'une video pour un compte standard. Nos Shorts (30-60 s)
# passent ; nos videos longues (2-3 min) non — elles partent donc en texte
# accompagne du lien YouTube, ce qui a du sens : on veut justement que le
# spectateur aille les voir en entier sur la chaine. A confirmer au premier
# essai reel, la valeur pouvant differer selon le palier du compte.
DUREE_MAX_VIDEO_S = 140
MORCEAU = 4 * 1024 * 1024

# Les CARTES ne partent jamais d'ici : Paco les publie a la main, avec son
# propre texte (decision du 06/09/2026). Ce n'est pas une lubie — un compte
# dont toute l'activite est robotique attire l'oeil des filtres, et c'est
# exactement ce qui a coute le compte personnel. Une publication humaine par
# jour au milieu de deux publications automatiques, c'est un compte vivant.
KINDS_MANUELS = ("card",)

# Montee en puissance : un compte neuf qui publie trois fois par jour des le
# premier jour ressemble a ce que les filtres cherchent. Trois semaines pour
# atteindre le rythme de croisiere, c'est le prix de la tranquillite.
RAMPE = [(7, 1), (14, 2)]
PLAFOND_JOUR = 3
PLAFOND_MOIS = 400          # le palier gratuit autorise ~500
ESPACEMENT_MIN_H = 2

MOTS_CLES = {
    "fr": "#Paris #Histoire",
    "en": "#Paris #History",
}


# ---------------------------------------------------------------------------
# Etat
# ---------------------------------------------------------------------------

def _etat() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.error("Etat X illisible : on repart a vide.")
    return {"publies": {}, "echecs_consecutifs": 0}


def _sauver(etat: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(etat, ensure_ascii=False, indent=2),
                          encoding="utf-8")


def _secret() -> Optional[dict]:
    if not SECRET_FILE.exists():
        return None
    secret = json.loads(SECRET_FILE.read_text(encoding="utf-8"))
    manquants = [c for c in ("api_key", "api_secret", "access_token", "access_secret")
                 if not secret.get(c)]
    if manquants:
        raise SystemExit(f"x_annonce.secret : champs manquants {manquants}")
    return secret


def _auth(secret: dict) -> OAuth1:
    return OAuth1(secret["api_key"], secret["api_secret"],
                  secret["access_token"], secret["access_secret"])


def _dm(texte: str) -> None:
    """Previent Paco par le bot Telegram — le seul canal qui le joint."""
    if not SECRET_TELEGRAM.exists():
        return
    tg = json.loads(SECRET_TELEGRAM.read_text(encoding="utf-8"))
    if not tg.get("alerte_chat_id"):
        return
    try:
        requests.post(f"https://api.telegram.org/bot{tg['token']}/sendMessage",
                      data={"chat_id": tg["alerte_chat_id"], "text": texte[:4000]},
                      timeout=30)
    except requests.RequestException:
        logger.warning("Alerte Telegram non partie.")


# ---------------------------------------------------------------------------
# Regles de volume
# ---------------------------------------------------------------------------

def _vrais_envois(etat: dict) -> List[dict]:
    """Les posts REELLEMENT partis.

    ``--init`` inscrit tout l'existant avec la date du jour pour ne pas
    inonder le compte au demarrage. Compter ces lignes comme des envois
    ferait croire a cent quatorze posts en une journee, et plus rien ne
    partirait jamais : elles portent ``baseline`` et sont ecartees ici.
    """
    return [p for p in etat.get("publies", {}).values() if not p.get("baseline")]


def _plafond_du_jour(etat: dict, rampe: bool) -> int:
    if not rampe:
        return PLAFOND_JOUR
    envois = _vrais_envois(etat)
    if not envois:
        return RAMPE[0][1]
    debut = min(datetime.fromisoformat(p["at"]) for p in envois)
    age = (datetime.now(timezone.utc) - debut).days
    for seuil, plafond in RAMPE:
        if age < seuil:
            return plafond
    return PLAFOND_JOUR


def _peut_publier(etat: dict, rampe: bool) -> tuple[bool, str]:
    maintenant = datetime.now(timezone.utc)
    dates = [datetime.fromisoformat(p["at"]) for p in _vrais_envois(etat)]

    du_jour = [d for d in dates if d.date() == maintenant.date()]
    plafond = _plafond_du_jour(etat, rampe)
    if len(du_jour) >= plafond:
        return False, f"plafond du jour atteint ({len(du_jour)}/{plafond})"

    du_mois = [d for d in dates if (maintenant - d).days < 30]
    if len(du_mois) >= PLAFOND_MOIS:
        return False, f"plafond mensuel atteint ({len(du_mois)}/{PLAFOND_MOIS})"

    if dates:
        depuis = (maintenant - max(dates)).total_seconds() / 3600
        if depuis < ESPACEMENT_MIN_H:
            return False, f"dernier post il y a {depuis:.1f} h (< {ESPACEMENT_MIN_H} h)"
    return True, ""


def _kind(name: str) -> str:
    """« card », « short » ou « long », d'apres la cle du registre."""
    parts = name.split(":")
    if len(parts) < 3:
        return "long"
    return "card" if parts[2].startswith("card-") else "short"


def _duree(video: Path) -> Optional[float]:
    import subprocess
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(video)],
            capture_output=True, text=True, timeout=60,
        )
        return float(r.stdout.strip())
    except Exception:
        return None


def _composer(accroche: str, lang: str, lien: Optional[str] = None) -> str:
    """Accroche, lien eventuel et mots-cles, sous la limite, coupe au mot."""
    tags = MOTS_CLES.get(lang, MOTS_CLES["fr"])
    place = LIMITE_TEXTE - len(tags) - 2
    if lien:
        place -= LONGUEUR_LIEN + 1
    if len(accroche) > place:
        coupe = accroche[:place - 1]
        if " " in coupe:
            coupe = coupe[:coupe.rfind(" ")]
        accroche = coupe.rstrip(" ,;:.") + "…"
    corps = f"{accroche}\n{lien}" if lien else accroche
    return f"{corps}\n\n{tags}"


# ---------------------------------------------------------------------------
# Envoi
# ---------------------------------------------------------------------------

def _televerser(auth: OAuth1, video: Path) -> str:
    """Televerse une video en trois temps, puis attend son traitement."""
    taille = video.stat().st_size
    if taille > TAILLE_MAX_VIDEO:
        raise RuntimeError(f"video trop lourde pour X ({taille // 1024 // 1024} Mo)")

    debut = requests.post(API_UPLOAD, auth=auth, timeout=60, data={
        "command": "INIT", "total_bytes": taille,
        "media_type": "video/mp4", "media_category": "tweet_video",
    })
    debut.raise_for_status()
    media_id = debut.json()["media_id_string"]

    with open(video, "rb") as flux:
        index = 0
        while True:
            morceau = flux.read(MORCEAU)
            if not morceau:
                break
            r = requests.post(API_UPLOAD, auth=auth, timeout=180,
                              data={"command": "APPEND", "media_id": media_id,
                                    "segment_index": index},
                              files={"media": morceau})
            r.raise_for_status()
            index += 1

    fin = requests.post(API_UPLOAD, auth=auth, timeout=60,
                        data={"command": "FINALIZE", "media_id": media_id})
    fin.raise_for_status()

    # X transcode en differe : publier avant la fin donne un post casse.
    info = fin.json().get("processing_info")
    while info and info.get("state") in ("pending", "in_progress"):
        time.sleep(min(30, info.get("check_after_secs", 5)))
        r = requests.get(API_UPLOAD, auth=auth, timeout=60,
                         params={"command": "STATUS", "media_id": media_id})
        r.raise_for_status()
        info = r.json().get("processing_info")
        logger.info("Traitement video : %s", info.get("state") if info else "termine")
    if info and info.get("state") == "failed":
        raise RuntimeError(f"X a rejete la video : {info.get('error')}")
    return media_id


def _publier(auth: OAuth1, texte: str, video: Optional[Path]) -> str:
    charge = {"text": texte}
    if video:
        charge["media"] = {"media_ids": [_televerser(auth, video)]}
    reponse = requests.post(API_TWEETS, auth=auth, json=charge, timeout=120)
    if reponse.status_code == 429:
        raise RuntimeError("429 : limite de debit atteinte, on reessaiera plus tard")
    if reponse.status_code >= 300:
        raise RuntimeError(f"X a refuse ({reponse.status_code}) : {reponse.text[:300]}")
    return reponse.json()["data"]["id"]


# ---------------------------------------------------------------------------
# Cycle
# ---------------------------------------------------------------------------

def sonde(secret: dict) -> int:
    """Verifie les cles et l'identite du compte, sans rien publier."""
    auth = _auth(secret)
    r = requests.get("https://api.x.com/2/users/me", auth=auth, timeout=30)
    if r.status_code >= 300:
        print(f"[ECHEC] {r.status_code} : {r.text[:300]}")
        return 1
    compte = r.json().get("data", {})
    print(f"[ok] Authentifie comme @{compte.get('username')} ({compte.get('name')})")
    print("     Les cles sont bonnes. Reste a verifier l'envoi video, qui")
    print("     depend du palier de l'application (--essai-video).")
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Publie les nouvelles videos sur X.")
    parser.add_argument("--sonde", action="store_true", help="verifie les cles, ne publie rien")
    parser.add_argument("--init", action="store_true", help="marque l'existant comme traite")
    args = parser.parse_args(argv)

    publications = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))["published"]
    etat = _etat()

    if args.init:
        for e in publications:
            etat["publies"].setdefault(e["name"], {
                "at": datetime.now(timezone.utc).isoformat(),
                "tweet_id": None, "texte": None, "baseline": True,
            })
        _sauver(etat)
        logger.info("Baseline : %d publication(s) marquees, 0 envoi.", len(etat["publies"]))
        return 0

    secret = _secret()
    if secret is None:
        logger.info("Pas de x_annonce.secret : veille (rien a faire).")
        return 0

    if args.sonde:
        return sonde(secret)

    if etat.get("echecs_consecutifs", 0) >= 2:
        logger.error("Publieur X DESARME (2 echecs) : remettre echecs_consecutifs a 0.")
        return 1

    ok, motif = _peut_publier(etat, secret.get("rampe", True))
    if not ok:
        logger.info("Rien ne part maintenant : %s.", motif)
        return 0

    attente = [e for e in publications
               if e["name"] not in etat["publies"]
               and _kind(e["name"]) not in KINDS_MANUELS]
    if not attente:
        logger.info("Rien a publier automatiquement (les cartes sont manuelles).")
        return 0
    entree = attente[0]

    accroche = texte_social.texte_attribue(entree["name"], entree["title"])
    deja = {p.get("texte") for p in _vrais_envois(etat) if p.get("texte")}
    if accroche in deja:
        logger.error("Texte deja publie sur X pour %s : envoi ABANDONNE.", entree["name"])
        _dm(f"⚠️ X : texte en doublon pour {entree['name']}, envoi abandonné "
            f"(règle anti-duplication). Rien n'a été publié.")
        return 1

    lang = entree["name"].split(":")[1] if ":" in entree["name"] else "fr"
    # Video native quand elle tient dans la limite, sinon le lien : une video
    # tronquee par X vaut moins qu'un lien assume vers la version entiere.
    video = _fichier_local(entree["name"])
    duree = _duree(video) if video else None
    if video and duree and duree > DUREE_MAX_VIDEO_S:
        logger.info("%s dure %.0f s (> %d) : envoi en texte + lien.",
                    entree["name"], duree, DUREE_MAX_VIDEO_S)
        video = None
    lien = None if video else f"https://youtu.be/{entree['video_id']}"
    texte = _composer(accroche, lang, lien)
    try:
        tweet_id = _publier(_auth(secret), texte, video)
    except Exception as exc:
        etat["echecs_consecutifs"] = etat.get("echecs_consecutifs", 0) + 1
        _sauver(etat)
        logger.exception("Envoi X en echec (%d/2).", etat["echecs_consecutifs"])
        _dm(f"❌ X : envoi en échec ({etat['echecs_consecutifs']}/2) — {exc}")
        return 1

    etat["publies"][entree["name"]] = {
        "at": datetime.now(timezone.utc).isoformat(),
        "tweet_id": tweet_id, "texte": accroche,
    }
    etat["echecs_consecutifs"] = 0
    _sauver(etat)
    logger.info("Publie sur X : %s -> %s (%s)", entree["name"], tweet_id,
                "video native" if video else "texte seul")
    return 0


if __name__ == "__main__":
    sys.exit(main())
