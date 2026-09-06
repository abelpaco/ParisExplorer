#!/bin/bash
# Rattrapage des cartes manquantes (06/09/2026). Vingt-huit sujets sur
# quarante et un n'en avaient aucune : la boucle ne produisait que la video
# et ses Shorts, si bien que le stock de cartes ne se renouvelait jamais.
#
# Idempotent : un sujet qui a deja son dossier de cartes est saute.
# N'inclut QUE les sujets dotes d'un bloc `cards:` redige a la main —
# ailleurs, les phrases seraient echantillonnees dans la narration et
# risqueraient d'etre orphelines hors contexte.
cd ~/parisexplorer || exit 1

SUJETS="bataillon-poste-aerienne-1870 bievre bras-henri4 catacombes
colonne-vendome-deboulonnee fontaine-innocents-cimetiere gustave-eiffel
jeanne-darc-paris lac-opera manufacture-gobelins-teinture
marche-aux-puces-clignancourt medailles-arago metre-etalon metro-parisien
notre-dame obelisque-luxor-transport opera-garnier parc-des-princes
passage-pommeraye-fake pere-lachaise pigalle-brasseries-a-femmes rungis
sainte-chapelle-reliques-prix siege-de-paris zola-mort"

for id in $SUJETS; do
  if [ -d "content/cards/$id" ]; then
    echo "[skip] $id"
    continue
  fi
  echo "=== $id — $(date -u) ==="
  .venv/bin/python visual_cards.py "$id" --lang fr --format story \
      --animate --count 3 || echo "[ECHEC] $id"
done
echo "=== RATTRAPAGE TERMINE $(date -u) ==="
