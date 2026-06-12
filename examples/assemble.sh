#!/bin/bash
# assemble.sh — Assemble les corrections par livre, applique, produit diff HTML + epub final.
# Usage: bash assemble.sh <id> "<titre>"
set -u
id="$1"; titre="$2"
cd /tmp/segur

# 1) fusionner anomalies + toutes les fenêtres de lecture de ce livre
merged="corrections-$id-all.jsonl"
: > "$merged"
[ -f "corrections-anom-$id.jsonl" ] && cat "corrections-anom-$id.jsonl" >> "$merged"
for f in corrections-lecture-$id-*.jsonl; do [ -f "$f" ] && cat "$f" >> "$merged"; done

n=$(grep -c chercher "$merged" 2>/dev/null || echo 0)

# 2) appliquer (budget large : domaine public, beaucoup de "...." → "…")
python3 ~/src/bp/epub-typo-fr/ocr_apply.py "$id-strip.epub" "$id-final.epub" "$merged" \
  --report-html "diff-$id.html" --titre "$titre (#$id)" --budget-pct 1.5 2>&1 | sed "s/^/[$id] /"

echo "[$id] $n corrections proposées"
