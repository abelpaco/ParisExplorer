#!/bin/bash
# Rattrapage des cartes ANGLAISES (07/09/2026). Le rattrapage de la veille
# n avait produit que du francais : 114 cartes FR pour 27 EN, alors que le
# calendrier alterne les deux langues — les EN se seraient epuisees les
# premieres. Ne portent ici que les sujets dotes d une narration ET d un
# bloc cards en anglais ; les autres demandent d abord une version anglaise.
cd ~/parisexplorer || exit 1
for id in catacombes gustave-eiffel metro-parisien notre-dame opera-garnier parc-des-princes pere-lachaise rungis; do
  if ls content/cards/$id/$id-en-story-*.mp4 >/dev/null 2>&1; then
    echo "[skip] $id"
    continue
  fi
  echo "=== $id — $(date -u) ==="
  .venv/bin/python visual_cards.py "$id" --lang en --format story --animate --count 3 || echo "[ECHEC] $id"
done
echo "=== TERMINE $(date -u) ==="
