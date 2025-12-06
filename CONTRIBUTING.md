# Guide de Contribution

Merci de votre intérêt pour ParisExplorer !

## Workflow de contribution

1. Forkez le dépôt et créez une branche dédiée (`feature/nom-de-la-fonctionnalité`).
2. Respectez le style et la qualité du code Python (voir ci-dessous).
3. Documentez vos ajouts dans le README ou des fichiers spécifiques.
4. Soumettez une Pull Request détaillée.

## Outils de style

- **Black** (formatage automatique)
- **Flake8** (linter)
- **isort** (optionnel, pour tri des imports)

Avant de soumettre votre PR :
```bash
black .
flake8 .
```

## Tests

Incluez des tests dans `test_system.py` ou dans la structure de test qui sera proposée.

## Bonnes pratiques

- Gardez un style clair et un découpage modulaire des fonctionnalités.
- Documentez les fonctions et classes.
- Référencez les évolutions dans le changelog (si présent).

## Contact / Support

Problèmes majeurs : ouvrez une Issue sur GitHub ou contactez le mainteneur principal.