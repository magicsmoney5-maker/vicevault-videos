#!/bin/bash
# One-time setup for a fresh run workspace. Usage: bash setup.sh [sources...]
# sources: t1 t2 launch pre ext (default: all). Footage comes from the Owner's public Drive files.
set -e
pip install --break-system-packages -q faster-whisper >/dev/null 2>&1 || pip install -q faster-whisper
mkdir -p ~/.fonts ~/foot ~/vvc-work
[ -s ~/.fonts/Anton-Regular.ttf ] || curl -sSL -o ~/.fonts/Anton-Regular.ttf "https://raw.githubusercontent.com/google/fonts/main/ofl/anton/Anton-Regular.ttf"
fc-cache -f >/dev/null 2>&1 || true
declare -A ID=( [pre]=1b3Zf-PYwOs7SJGOLgp__JBQkir0FARsj [t1]=1M3Fuwy-JmZF1Ht9IVufc4ddup2wLlBhk [launch]=10Vxwl1RT187Ln2sofZRP32JJNQm8fEmg [t2]=1W-iK4qdL7XMJIgYR04mvHyGAP2fNMJSj [ext]=1Pg1mzghJFns-KkJms_vy5DJnLSbjQ2DG )
SRC=("$@"); [ ${#SRC[@]} -eq 0 ] && SRC=(pre t1 launch t2 ext)
for s in "${SRC[@]}"; do
  [ -s ~/foot/$s.mp4 ] && continue
  curl -sS -L -o ~/foot/$s.mp4 "https://drive.usercontent.google.com/download?id=${ID[$s]}&export=download&confirm=t"
  echo "footage $s: $(stat -c %s ~/foot/$s.mp4) bytes"
done
python3 -c "import faster_whisper" && echo "setup ok"
