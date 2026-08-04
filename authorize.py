"""Autorise la chaine aupres de YouTube, et rien d'autre.

POURQUOI CE SCRIPT EXISTE
-------------------------
``automation.py --mode channel-info`` fait le travail, mais il importe toute la
chaine de production au passage : montage video, synthese vocale, traitement
d'images. Pour la seule autorisation, c'est plusieurs centaines de megaoctets de
dependances a installer avant de pouvoir cliquer sur un bouton Google.

Ici, on ne charge que les bibliotheques Google. L'autorisation redevient une
etape de trente secondes, y compris sur une machine fraiche.

CE QUE FAIT CE SCRIPT
---------------------
1. Ouvre la fenetre de consentement Google dans le navigateur.
2. Ecrit ``token.json`` une fois l'acces accorde.
3. Interroge la chaine et affiche son nom et ses compteurs — la preuve que
   l'autorisation porte bien sur LE BON compte. C'est le piege classique : on
   valide avec le mauvais compte Google et on s'en apercoit apres avoir publie.

Usage :
    python authorize.py
    python authorize.py --check    (verifie sans jamais ouvrir de navigateur)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Le script s'ancre sur SON dossier, pas sur celui d'ou on l'appelle. Sans ca,
# `client_secrets.json` est cherche dans le repertoire courant et `token.json`
# ecrit a cote : lance depuis ailleurs, l'autorisation semble reussir puis le
# jeton reste introuvable. On deplace donc le repertoire courant une fois pour
# toutes, ce qui couvre aussi `youtube_uploader`, qui utilise lui aussi des
# chemins relatifs.
PROJECT_DIR = Path(__file__).resolve().parent
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(PROJECT_DIR))

CREDENTIALS_FILE = Path("client_secrets.json")
TOKEN_FILE = Path("token.json")

def scopes() -> list:
    """Droits demandes, lus dans ``youtube_uploader``, qui en est la source.

    Les redeclarer ici les ferait diverger en silence : le jeton serait demande
    avec une liste et relu avec une autre. L'import est PARESSEUX pour que
    ``--check`` puisse encore expliquer proprement qu'il manque les
    bibliotheques Google, au lieu de mourir sur une pile d'appels.
    """
    from youtube_uploader import SCOPES

    return list(SCOPES)


def _fail(message: str) -> int:
    print(f"\n[ECHEC] {message}")
    return 1


def check_only() -> int:
    """Etat de l'autorisation, sans jamais ouvrir de navigateur."""
    if not CREDENTIALS_FILE.exists():
        return _fail(
            f"{CREDENTIALS_FILE} absent. Telecharge le JSON du client OAuth "
            "depuis la console Google Cloud (API et services > Identifiants)."
        )
    print(f"[ok] {CREDENTIALS_FILE} present.")

    if not TOKEN_FILE.exists():
        print(f"[a faire] {TOKEN_FILE} absent : lance `python authorize.py`.")
        return 1

    from google.oauth2.credentials import Credentials

    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), scopes())
    except Exception as exc:
        return _fail(f"{TOKEN_FILE} illisible : {exc}")

    # Les droits se lisent dans le FICHIER, pas sur l'objet : la construction
    # ecrase ceux du jeton par ceux qu'on lui passe, et comparer l'objet a la
    # demande reviendrait a comparer une valeur avec elle-meme.
    granted = set(json.loads(TOKEN_FILE.read_text(encoding="utf-8")).get("scopes") or [])
    asked = set(scopes())
    if granted and granted != asked:
        missing = ", ".join(sorted(s.rsplit("/", 1)[-1] for s in asked - granted))
        extra = ", ".join(sorted(s.rsplit("/", 1)[-1] for s in granted - asked))
        return _fail(
            "Les droits demandes ont change depuis la derniere autorisation.\n"
            f"    manquants dans le jeton : {missing or '(aucun)'}\n"
            f"    en trop dans le jeton   : {extra or '(aucun)'}\n"
            "Google refuse de rafraichir un jeton dont les droits ne "
            "correspondent plus (invalid_scope). Relance `python authorize.py`."
        )

    if creds.valid:
        print("[ok] Jeton valide.")
        return 0

    if creds.expired and creds.refresh_token:
        # On TENTE le rafraichissement au lieu de le supposer possible. Annoncer
        # « renouvelable » sans essayer, c'est promettre un resultat sur la
        # simple presence d'un champ : un jeton dont les droits ont change, ou
        # revoque cote Google, presente exactement les memes apparences.
        from google.auth.transport.requests import Request

        try:
            creds.refresh(Request())
        except Exception as exc:
            return _fail(
                f"Jeton non renouvelable : {exc}\n"
                "Relance `python authorize.py`. Si cela se reproduit tous les "
                "sept jours, c'est que l'application OAuth est restee en mode "
                "Test — passe-la en Production."
            )
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        print("[ok] Jeton rafraichi et reenregistre.")
        return 0

    return _fail(
        "Jeton expire et sans moyen de renouvellement. Supprime token.json et "
        "relance `python authorize.py`."
    )


def authorize() -> int:
    """Ouvre le consentement Google puis verifie sur quelle chaine on est tombe."""
    if not CREDENTIALS_FILE.exists():
        return _fail(
            f"{CREDENTIALS_FILE} absent. Telecharge le JSON du client OAuth "
            "depuis la console Google Cloud (API et services > Identifiants)."
        )

    try:
        from youtube_uploader import YouTubeUploader
    except ImportError as exc:
        return _fail(
            f"Bibliotheques Google manquantes ({exc}). Installe-les :\n"
            "    pip install google-auth google-auth-oauthlib google-api-python-client"
        )

    print("Une fenetre Google va s'ouvrir dans le navigateur.")
    print("IMPORTANT : choisis le compte qui possede la chaine Paris Explorer.\n")

    try:
        uploader = YouTubeUploader(str(CREDENTIALS_FILE))
    except Exception as exc:
        message = str(exc)
        if "access_denied" in message or "403" in message:
            return _fail(
                "Google a refuse l'acces. En mode Test, ton compte doit figurer "
                "dans « Ecran de consentement OAuth > Utilisateurs test ».\n"
                f"Detail : {message}"
            )
        return _fail(f"Autorisation impossible : {message}")

    info = uploader.get_channel_info()
    if not info:
        return _fail(
            "Autorisation obtenue, mais aucune chaine trouvee sur ce compte. "
            "Tu as probablement valide avec le mauvais compte Google : supprime "
            "token.json et recommence."
        )

    snippet = info.get("snippet", {})
    stats = info.get("statistics", {})
    print("\n[ok] Autorisation enregistree dans token.json")
    print(f"     Chaine     : {snippet.get('title', '?')}")
    print(f"     Videos     : {stats.get('videoCount', '?')}")
    print(f"     Abonnes    : {stats.get('subscriberCount', '?')}")
    print(f"     Vues       : {stats.get('viewCount', '?')}")
    print("\nVerifie que c'est bien la chaine Paris Explorer avant d'aller plus loin.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Autorise la chaine aupres de YouTube.")
    parser.add_argument(
        "--check", action="store_true",
        help="verifier l'etat de l'autorisation sans ouvrir de navigateur",
    )
    args = parser.parse_args(argv)
    return check_only() if args.check else authorize()


if __name__ == "__main__":
    raise SystemExit(main())
