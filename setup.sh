#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEDIAMTX_VERSION="v1.21.4"
DRY=0
ENABLE=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --enable) ENABLE=1 ;;
    *) echo "usage: bash setup.sh [--dry-run] [--enable]" >&2; exit 2 ;;
  esac
done
RUN_USER="${SUDO_USER:-${USER:-pi}}"

run() { echo "+ $*"; if [ "$DRY" -eq 0 ]; then "$@"; fi; }

if [ "$DRY" -eq 0 ]; then
  # CHECK ON PI
  . /etc/os-release
  [ "${VERSION_CODENAME:-}" = "bookworm" ] || { echo "Need Raspberry Pi OS Bookworm (Python 3.11), found: ${VERSION_CODENAME:-unknown}" >&2; exit 1; }
  [ "$(uname -m)" = "aarch64" ] || { echo "Need a 64-bit OS (aarch64), found: $(uname -m)" >&2; exit 1; }
  [ "$(id -u)" -ne 0 ] || { echo "Run as the normal user, not root" >&2; exit 1; }
  python3 -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 11) else 1)' || { echo "Need Python 3.11" >&2; exit 1; }
fi

echo "== 1/6 apt packages"
run sudo apt-get update
run sudo apt-get install -y git ffmpeg iw i2c-tools python3-venv python3-pip python3-dev python3-gpiozero python3-lgpio

echo "== 2/6 I2C and groups"
run sudo raspi-config nonint do_i2c 0
run sudo usermod -aG gpio,i2c,video "$RUN_USER"

echo "== 3/6 virtual environment"
run python3 -m venv --system-site-packages "$ROOT/venv"
run "$ROOT/venv/bin/pip" install --upgrade pip
run "$ROOT/venv/bin/pip" install -r "$ROOT/requirements-pi.txt"

echo "== 4/6 folders"
run mkdir -p "$ROOT/runs" "$ROOT/model"
if [ "$DRY" -eq 0 ]; then echo "d /run/kashimo/frames 0755 $RUN_USER $RUN_USER -" > /tmp/kashimo-tmpfiles.conf; fi
run sudo install -m 644 /tmp/kashimo-tmpfiles.conf /etc/tmpfiles.d/kashimo.conf
run sudo systemd-tmpfiles --create /etc/tmpfiles.d/kashimo.conf

echo "== 5/6 MediaMTX $MEDIAMTX_VERSION"
if [ -x /usr/local/bin/mediamtx ]; then
  echo "mediamtx already installed (delete /usr/local/bin/mediamtx to upgrade)"
else
  TARBALL="mediamtx_${MEDIAMTX_VERSION}_linux_arm64.tar.gz"
  run curl -fsSL -o "/tmp/$TARBALL" "https://github.com/bluenviron/mediamtx/releases/download/${MEDIAMTX_VERSION}/$TARBALL"
  run tar -xzf "/tmp/$TARBALL" -C /tmp mediamtx
  run sudo install -m 755 /tmp/mediamtx /usr/local/bin/mediamtx
fi

echo "== 6/6 systemd units"
for f in "$ROOT"/systemd/kashimo-*.service; do
  name="$(basename "$f")"
  echo "+ install $name"
  if [ "$DRY" -eq 0 ]; then
    sed -e "s|@ROOT@|$ROOT|g" -e "s|@USER@|$RUN_USER|g" "$f" | sudo tee "/etc/systemd/system/$name" > /dev/null
  fi
done
run sudo systemctl daemon-reload
if [ "$ENABLE" -eq 1 ]; then
  run sudo systemctl enable --now kashimo-mediamtx kashimo-video kashimo-controller kashimo-ai
else
  echo "Units installed, not enabled. After K09-K11 exist: bash setup.sh --enable"
fi

echo "Done. Log out and back in (new groups), then: python tools/verify.py"
