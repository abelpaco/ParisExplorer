#!/bin/bash
# Production FR des 10 sujets de septembre (28/08/2026). Idempotent : saute
# les sujets dont la video FR existe deja.
cd ~/parisexplorer
for id in jeanne-darc-paris siege-de-paris zola-mort lac-opera maison-flamel metre-etalon medailles-arago bievre bras-henri4 louvre-forteresse; do
  if [ -f "content/videos/$id/$id-fr.mp4" ]; then echo "[skip] $id"; continue; fi
  echo "=== $id — $(date -u) ==="
  .venv/bin/python produce_topic.py "$id" --lang fr || echo "[ECHEC] $id"
done
echo "=== BATCH TERMINE $(date -u) ==="
