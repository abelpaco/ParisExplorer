# Copilot Instructions for ParisExplorer

## Language and Runtime

- **Python** est le seul langage utilisé dans ce projet.
- Toujours cibler une compatibilité **Python 3.10+**.
- Utiliser les fonctionnalités modernes de Python (f-strings, type hints, dataclasses, walrus operator, etc.) dans la limite de la version cible.

## Project Overview

ParisExplorer est un prototype Python qui collecte, analyse et présente des données liées à la région parisienne (points d'intérêt, services, etc.). Le projet vise la modularité, la lisibilité et l'évolutivité.

## Code Style and Formatting

- Formater le code avec **Black** (longueur de ligne maximale : 88 caractères).
- Linter avec **Flake8** (configuration dans `.flake8`).
- Trier les imports avec **isort** si disponible.
- Documenter toutes les fonctions et classes avec des docstrings (style Google ou NumPy).
- Utiliser des **type hints** pour tous les paramètres de fonctions et les valeurs de retour.

## Dependency Management

- Les dépendances sont listées dans `requirements.txt`.
- Ne pas ajouter de nouvelles dépendances sans justification explicite dans la PR.
- Préférer les bibliothèques déjà présentes (ex. `requests`, `PyYAML`, `python-dotenv`, `Pillow`, `schedule`, Google API client).

## Testing

- Les tests sont dans `test_system.py`.
- Tout nouveau code doit être accompagné de tests dans `test_system.py` ou dans un fichier de test dédié.
- Lancer les tests avec :
  ```bash
  python -m pytest test_system.py
  ```

## Architecture

- `content_manager.py`, `automation.py`, `scheduler.py`, `youtube_uploader.py`, `utils.py` : modules principaux.
- `quickstart.py` : point d'entrée principal.
- `content/` : ressources et données statiques.
- `config.yaml` : configuration centralisée.
- `.env` (basé sur `.env.example`) : variables d'environnement sensibles — ne jamais committer.

## Security

- Ne jamais inclure de secrets, clés API ou identifiants dans le code source.
- Toutes les valeurs sensibles doivent provenir de variables d'environnement (via `python-dotenv`).

## Pull Requests

- Créer une branche dédiée (`feature/nom-de-la-fonctionnalité` ou `fix/description`).
- Vérifier le formatage et le lint avant de soumettre (`black . && flake8 .`).
- Documenter les changements dans le README ou les fichiers concernés si nécessaire.
