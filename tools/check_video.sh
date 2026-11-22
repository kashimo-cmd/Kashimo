#!/usr/bin/env bash
# K10: run ON THE PI while mediamtx and pipeline.sh are running. Usage: check_video.sh [rtsp_url]
set -u
URL="${1:-rtsp://127.0.0.1:8554/cam}"
FRAMES="${FRAMES_DIR:-/run/kashimo/frames}"; [ -f "$FRAMES/latest.jpg" ] || FRAMES=/tmp/kashimo/frames
row() { printf '%-14s %s\n' "$1" "$2"; }
for p in mediamtx ffmpeg; do pgrep -x "$p" >/dev/null && row "$p" running || row "$p" "NOT RUNNING"; done
if [ -f "$FRAMES/latest.jpg" ]; then
  row latest.jpg "age $(( $(date +%s) - $(stat -c %Y "$FRAMES/latest.jpg") )) s, $(stat -c %s "$FRAMES/latest.jpg") bytes ($FRAMES)"
else row latest.jpg MISSING; fi
row stream "$(ffprobe -v error -rtsp_transport tcp -select_streams v:0 -show_entries stream=codec_name,width,height -of csv=p=0 "$URL" 2>&1 | head -n1)"
N="$(ffmpeg -hide_banner -loglevel error -rtsp_transport tcp -i "$URL" -t 10 -map 0:v:0 -f null - -progress pipe:1 -nostats 2>/dev/null | grep '^frame=' | tail -n1 | cut -d= -f2)"
FPS="$(awk -v n="${N:-0}" 'BEGIN{printf "%.1f", n/10}')"
row fps_10s "$FPS"
row cpu_ffmpeg "$(ps -C ffmpeg -o %cpu= | awk '{s+=$1} END{print s+0}') %"
row cpu_mediamtx "$(ps -C mediamtx -o %cpu= | awk '{s+=$1} END{print s+0}') %"
row temp "$(vcgencmd measure_temp 2>/dev/null)"
TH="$(vcgencmd get_throttled 2>/dev/null)"; row throttled "$TH"
IP="$(hostname -I | awk '{print $1}')"
echo
echo "open on the PC:  http://$IP:8889/cam"
echo "or:              ffplay -fflags nobuffer rtsp://$IP:8554/cam"
if awk -v f="$FPS" 'BEGIN{exit !(f>=14)}' && echo "$TH" | grep -q 0x0; then echo "RESULT: PASS (fps ok, no throttling)"; else echo "RESULT: CHECK (fps under 14 or throttled)"; fi
