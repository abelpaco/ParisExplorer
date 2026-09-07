#!/bin/bash
# Production ANGLAISE des dix-huit sujets qui n avaient que le francais
# (decision Paco du 07/09/2026, option B, videos longues comprises).
# Idempotent : un sujet dont la video EN existe est saute.
cd ~/parisexplorer || exit 1
SUJETS="bataillon-poste-aerienne-1870 bievre bras-henri4 colonne-vendome-deboulonnee
fontaine-innocents-cimetiere jeanne-darc-paris lac-opera maison-flamel
manufacture-gobelins-teinture marche-aux-puces-clignancourt medailles-arago
metre-etalon obelisque-luxor-transport passage-pommeraye-fake
pigalle-brasseries-a-femmes sainte-chapelle-reliques-prix siege-de-paris zola-mort"
for id in $SUJETS; do
  if [ -f "content/videos/$id/$id-en.mp4" ]; then
    echo "[skip video] $id"
  else
    echo "=== VIDEO $id — $(date -u) ==="
    .venv/bin/python produce_topic.py "$id" --lang en || echo "[ECHEC video] $id"
  fi
  if ls content/cards/$id/$id-en-story-*.mp4 >/dev/null 2>&1; then
    echo "[skip cartes] $id"
  else
    echo "=== CARTES $id — $(date -u) ==="
    .venv/bin/python visual_cards.py "$id" --lang en --format story --animate --count 3 || echo "[ECHEC cartes] $id"
  fi
done
echo "=== PRODUCTION EN TERMINEE $(date -u) ==="
