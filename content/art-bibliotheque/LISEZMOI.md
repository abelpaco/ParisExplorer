# Artothèque — éléments réutilisables pour les cartes de lieux

Bibliothèque d'éléments vectoriels dans laquelle on puise pour composer
les cartes Communauté (quartiers, places, lieux urbains). Principe :
**matière première, jamais signature** — chaque pièce est renormalisée au
style de la carte (trait, palette) au moment de la composition ; les
décors signature restent dessinés main. Toute nouvelle source passe par
`LICENCES.md` (CC0/domaine public uniquement : dépôt public).

## open-peeps/ — personnages en briques

Chaque pièce est un SVG autonome dans le repère commun du personnage
assemblé. Le viewBox à utiliser dépend de la pose (mesuré au rendu) :
**bustes** `0 0 850 1200` · **poses debout** `-300 -50 1600 3050` ·
**poses assises** `-300 -50 1600 2400` (à ajuster selon la pose). La
tête reste au même endroit quel que soit le corps. Assemblage
(transformations du kit d'origine) :

```
<g>                                 corps : poses-debout | poses-assis | bustes (0,0)
<g transform="translate(225 0)">    chevelure (inclut le crâne)
<g transform="translate(384 186)">  visage        (225+159, 0+186)
<g transform="translate(348 338)">  pilosité      (225+123, 0+338)
<g transform="translate(272 241)">  accessoires   (225+47,  0+241)
```

- Couleurs par défaut : trait `#000000`, remplissages `#FFFFFF` — faits
  pour être remplacés (recherche/remplacement des deux valeurs) par la
  palette de la carte cible.
- Les poses assises sont dessinées pour un support d'environ la moitié
  de la hauteur ; prévoir le banc/muret dans le décor.
- Échelle indicative dans une carte 1080×1920 : un personnage debout de
  premier plan ≈ 300–420 px de haut (viewBox complète), silhouette de
  fond ≈ 120–200 px.
