# ParisExplorer

ParisExplorer est un prototype Python explorant et présentant des données, services ou points d’intérêt propres à la région parisienne.

## Objectifs

- Preuve de Concept (PoC) ou MVP pour la collecte, l’analyse et la présentation de données sur Paris.
- Projet modulaire, évolutif et documenté permettant de tester de nouvelles sources ou services sans dette technique excessive.

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