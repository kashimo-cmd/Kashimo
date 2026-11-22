#!/usr/bin/env bash
# K10: camera -> ONE ffmpeg -> RTSP (MediaMTX) + 2 fps JPEG for the AI. Run from anywhere.
# Usage: pipeline.sh [--test-source] [--dry-run]   env: CAM_DEV CAM_W CAM_H CAM_FPS KBPS FRAMES_DIR PUBLISH_URL
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
TEST=0; DRY=0
for a in "$@"; do
  case "$a" in
    --test-source) TEST=1 ;;
    --dry-run) DRY=1 ;;
    *) echo "usage: pipeline.sh [--test-source] [--dry-run]" >&2; exit 2 ;;
  esac
done

cfg() { # cfg dotted.key default  (reads config/config.yaml, falls back to default)
  python3 - "$ROOT/config/config.yaml" "$1" "$2" 2>/dev/null <<'PY' || echo "$2"
import sys
try:
    import yaml
    d = yaml.safe_load(open(sys.argv[1])) or {}
    for k in sys.argv[2].split("."):
        d = d[k]
    print(d)
except Exception:
    print(sys.argv[3])
PY
}

W="${CAM_W:-$(cfg video.w 1280)}"; H="${CAM_H:-$(cfg video.h 720)}"
FPS="${CAM_FPS:-$(cfg video.fps 15)}"; KBPS="${KBPS:-$(cfg video.kbps 2500)}"
PUBLISH_URL="${PUBLISH_URL:-rtsp://127.0.0.1:8554/cam}"
FRAMES_DIR="${FRAMES_DIR:-/run/kashimo/frames}"

if [ -z "${CAM_DEV:-}" ]; then
  CAM_DEV="$(ls /dev/v4l/by-id/*video-index0 2>/dev/null | head -n1)"
  [ -n "$CAM_DEV" ] || CAM_DEV=/dev/video0
fi

# input: MJPEG at the configured size if the camera offers it, else raw YUYV (best size it has)
if [ "$TEST" -eq 1 ]; then
  [ "$W" -le 640 ] 2>/dev/null || { W=640; H=480; }
  INPUT=(-f lavfi -i "testsrc2=size=${W}x${H}:rate=${FPS}")
  echo "[video] test source ${W}x${H} @ ${FPS} fps" >&2
else
  LIST="$(v4l2-ctl -d "$CAM_DEV" --list-formats-ext 2>/dev/null || true)"
  if echo "$LIST" | grep -q "'MJPG'" && echo "$LIST" | grep -q "${W}x${H}"; then
    FMT=mjpeg
  else
    FMT=yuyv422
    if ! echo "$LIST" | grep -q "${W}x${H}"; then
      echo "$LIST" | grep -q "640x480" && { W=640; H=480; } || { echo "[video] no usable mode on $CAM_DEV" >&2; exit 1; }
    fi
    echo "[video] WARN: no MJPEG ${W}x${H} on $CAM_DEV, using raw YUYV ${W}x${H}" >&2
  fi
  INPUT=(-f v4l2 -input_format "$FMT" -video_size "${W}x${H}" -framerate "$FPS" -i "$CAM_DEV")
  echo "[video] camera $CAM_DEV $FMT ${W}x${H} @ ${FPS} fps" >&2
fi

CMD=(ffmpeg -y -hide_banner -loglevel warning -nostdin "${INPUT[@]}"
  -filter_complex "[0:v]format=yuv420p,split=2[a][b];[b]fps=2[c]"
  -map "[a]" -c:v libx264 -preset ultrafast -tune zerolatency -profile:v baseline
    -b:v "${KBPS}k" -maxrate "${KBPS}k" -bufsize "$((KBPS / 2))k" -g "$FPS" -an
    -f rtsp -rtsp_transport tcp "$PUBLISH_URL"
  -map "[c]" -q:v 3 -f image2 -update 1 -atomic_writing 1 "$FRAMES_DIR/latest.jpg")

if [ "$DRY" -eq 1 ]; then printf '%q ' "${CMD[@]}"; echo; exit 0; fi

if ! mkdir -p "$FRAMES_DIR" 2>/dev/null || [ ! -w "$FRAMES_DIR" ]; then
  echo "[video] WARN: cannot write $FRAMES_DIR, using /tmp/kashimo/frames (the AI must read the same folder)" >&2
  echo "[video] fix once: sudo mkdir -p /run/kashimo/frames && sudo chown \$USER /run/kashimo/frames" >&2
  FRAMES_DIR=/tmp/kashimo/frames; mkdir -p "$FRAMES_DIR"
  CMD[${#CMD[@]}-1]="$FRAMES_DIR/latest.jpg"
fi

bash "$HERE/prune.sh" --loop 30 &
PRUNE=$!; FF=""
trap 'kill $FF $PRUNE 2>/dev/null; exit 0' INT TERM
while true; do
  "${CMD[@]}" & FF=$!
  wait "$FF"; rc=$?
  echo "[video] ffmpeg exited ($rc), restart in 2 s (camera busy? run: fuser -v $CAM_DEV)" >&2
  sleep 2 & wait $!
done
