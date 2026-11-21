#!/usr/bin/env bash
# K00: read-only Pi probe. Changes nothing. Usage: bash tools/pi_probe.sh | tee probe.txt
run() { echo; echo "== $*"; if command -v "$1" >/dev/null 2>&1; then "$@" 2>&1 || echo "(command failed)"; else echo "(not installed: $1)"; fi; }
sh_run() { echo; echo "== $1"; bash -c "$1" 2>&1 || echo "(command failed)"; }

echo "KASHIMO PI PROBE $(date -Is)"
sh_run "cat /etc/os-release | grep -E 'PRETTY_NAME|VERSION_CODENAME'"
run uname -m
run python3 --version
sh_run "cat /proc/device-tree/model; echo"
sh_run "ls -l /dev/video* 2>&1"
if command -v v4l2-ctl >/dev/null 2>&1; then
  for d in /dev/video*; do
    [ -e "$d" ] || continue
    echo; echo "== v4l2-ctl --device $d --info"; v4l2-ctl --device "$d" --info 2>&1 | head -12
    echo; echo "== v4l2-ctl --device $d --list-formats-ext"; v4l2-ctl --device "$d" --list-formats-ext 2>&1 | head -60
  done
else
  echo; echo "== v4l2-ctl"; echo "(not installed: v4l2-ctl, run: sudo apt install -y v4l-utils)"
fi
sh_run "ffmpeg -hide_banner -version | head -1"
sh_run "df -h /"
run free -m
run vcgencmd measure_temp
run vcgencmd get_throttled
sh_run "vcgencmd get_config int 2>&1 | head -5"
sh_run "iw dev wlan0 link"
sh_run "ip -4 addr show | grep -E 'inet |^[0-9]+:' "
run lsusb
sh_run "lsusb -t"
sh_run "i2cdetect -y 1"
sh_run "nproc"
