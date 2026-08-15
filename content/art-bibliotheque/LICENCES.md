# Registre de provenance de l'artothèque

Règle d'entrée : **CC0 / domaine public uniquement** — ce dépôt est public,
aucun asset sous licence à attribution ou à redistribution restreinte n'y
entre. Une ligne par source, datée. Ta copie locale + cette ligne font foi
si la source disparaît ou change de conditions.

| Source | Contenu | Licence | Téléchargé le | URL |
|---|---|---|---|---|
| Open Peeps (Pablo Stanley), via le miroir `react-peeps` (CeamKrier, branche master) | 174 pièces SVG : 26 poses debout, 11 assises, 28 bustes, 51 chevelures, 33 visages, 16 pilosités, 9 accessoires | Artwork **CC0 1.0** (le code du miroir est MIT ; seuls les tracés SVG sont repris, pas le code) | 14/08/2026 | https://www.openpeeps.com/ · https://github.com/CeamKrier/react-peeps |

Notes :
- Les TSX du miroir ont été convertis en SVG bruts par
  `extract_peeps.py` (attributs JSX → SVG, couleurs par défaut figées :
  trait #000000, fond #FFFFFF). Aucune modification des tracés.
- Le paquet `@dicebear/open-peeps` 9.4.2 (npm) a été évalué puis écarté :
  il ne contient que les têtes, `react-peeps` couvre tout.
