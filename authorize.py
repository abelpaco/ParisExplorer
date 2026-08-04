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

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


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
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    except Exception as exc:
        return _fail(f"{TOKEN_FILE} illisible : {exc}")

    if creds.valid:
        print("[ok] Jeton valide.")
        return 0
    if creds.expired and creds.refresh_token:
        # En mode Test, Google revoque le jeton de rafraichissement au bout de
        # sept jours. C'est LA raison pour laquelle une chaine automatisee
        # s'arrete toute seule sans que rien n'ait change dans le code.
        print("[info] Jeton expire mais renouvelable — il se rafraichira tout seul.")
        return 0
    return _fail(
        "Jeton expire et non renouvelable. Supprime token.json et relance "
        "`python authorize.py`. Si ca recommence tous les sept jours, c'est que "
        "l'application OAuth est encore en mode Test."
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
