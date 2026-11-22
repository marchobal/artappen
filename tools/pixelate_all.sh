#!/bin/zsh
# Friläggning och pixelfigurer för alla foton i <labbmapp>/src som inte redan är gjorda.
# Användning: tools/pixelate_all.sh [labbmapp]   (kompilerar tools/pixelate.swift vid behov)
set -u
LAB=${1:-lab/pixel}
BIN=${TMPDIR:-/tmp}/artappen-pixelate
[[ -x $BIN && $BIN -nt tools/pixelate.swift ]] || swiftc -O tools/pixelate.swift -o $BIN || exit 1
mkdir -p $LAB/out
ok=0; fail=0
for f in $LAB/src/*.jpg; do
  b=${f:t:r}
  [[ -s $f ]] || continue
  [[ -f $LAB/out/$b-16.png ]] && continue
  if $BIN $f $LAB/out 16,24 8 >/dev/null 2>&1; then ((ok++)); else ((fail++)); echo "misslyckades: $b"; fi
done
echo "klara: $ok, misslyckade: $fail"
