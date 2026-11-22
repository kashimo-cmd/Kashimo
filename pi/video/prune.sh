#!/usr/bin/env bash
# K10: delete the oldest recording segments while the folder is above rec_cap_gb.
# Usage: prune.sh [--loop SECONDS]   env: REC_DIR REC_CAP_GB
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIR="${REC_DIR:-$ROOT/runs/rec}"
if [ -z "${REC_CAP_GB:-}" ]; then
  REC_CAP_GB="$(python3 - "$ROOT/config/config.yaml" 2>/dev/null <<'PY' || echo 8
import sys, yaml
print(yaml.safe_load(open(sys.argv[1]))["rec_cap_gb"])
PY
)"
fi
CAP_KB="$(awk -v g="$REC_CAP_GB" 'BEGIN{printf "%d", g*1024*1024}')"

prune_once() {
  [ -d "$DIR" ] || return 0
  local n=0 used oldest
  while :; do
    used="$(du -sk "$DIR" | cut -f1)"
    [ "$used" -le "$CAP_KB" ] && break
    [ "$(find "$DIR" -type f | wc -l)" -le 1 ] && break
    oldest="$(find "$DIR" -type f -printf '%T@ %p\n' | sort -n | head -n1 | cut -d' ' -f2-)"
    [ -n "$oldest" ] || break
    rm -f -- "$oldest"; n=$((n + 1))
  done
  [ "$n" -gt 0 ] && echo "[prune] removed $n old segment(s), cap ${REC_CAP_GB} GB"
  return 0
}

if [ "${1:-}" = "--loop" ]; then
  while :; do prune_once; sleep "${2:-30}"; done
else
  prune_once
fi
