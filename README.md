# ParisExplorer

ParisExplorer est l'outil interne de la chaîne YouTube **Paris Explorer** :
il produit de courtes vidéos documentaires sur l'histoire de Paris (narration
originale, illustrations « ligne claire » originales ou photos sous licence
créditées) et les publie sur la chaîne selon un calendrier fixe, en français
et en anglais. Un seul utilisateur : le propriétaire de la chaîne.

## Confidentialité et services API YouTube

Cet outil utilise les **services API YouTube** (YouTube API Services) pour
publier sur notre propre chaîne et lire ses statistiques.

- **Politique de confidentialité : [PRIVACY.md](PRIVACY.md)**
- Conditions d'utilisation de YouTube : <https://www.youtube.com/t/terms>
- Règles de confidentialité de Google : <http://www.google.com/policies/privacy>

## Objectifs

- Production automatisée : narration, voix off, montage, cartes visuelles et Shorts BD.
- Publication planifiée et registre anti-republication.
- Projet modulaire, évolutif et documenté.

## Installation

Cloner le dépôt, puis installer les dépendances :
```bash
git clone https://github.com/abelpaco/ParisExplorer.git
cd ParisExplorer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

Lancer l’explorateur ou les scripts principaux (exemple) :
```bash
python quickstart.py
```
Consultez EXAMPLES.md pour quelques exemples d’utilisation.  

## Structure du projet

- `content_manager.py`, `automation.py`... : modules principaux
- `requirements.txt` : dépendances Python
- `content/` : ressources et données
- `test_system.py` : tests automatisés

## Documentation

- Voir `CONTRIBUTING.md` pour les règles de style et les contributions.
- Voir `SETUP.md` pour la configuration avancée.

## Licence

Ce projet est sous licence MIT (modifiable dans `LICENSE`).