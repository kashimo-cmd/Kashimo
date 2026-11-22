#!/usr/bin/env bash
# K10: download the latest MediaMTX arm64 build, check its checksum, install to /usr/local/bin. Run on the Pi.
set -euo pipefail
[ "$(uname -m)" = aarch64 ] || { echo "run this on the Pi (aarch64), this is $(uname -m)"; exit 1; }
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
curl -fsSL https://api.github.com/repos/bluenviron/mediamtx/releases/latest -o "$TMP/rel.json"
URL="$(grep -o 'https://[^"]*linux_arm64[^"]*\.tar\.gz' "$TMP/rel.json" | head -n1 || true)"
SUMS="$(grep -o 'https://[^"]*checksums\.sha256' "$TMP/rel.json" | head -n1 || true)"
[ -n "$URL" ] || { echo "no linux_arm64 asset in the latest release"; exit 1; }
NAME="$(basename "$URL")"
echo "downloading $URL"
curl -fsSL "$URL" -o "$TMP/$NAME"
if [ -n "$SUMS" ]; then
  curl -fsSL "$SUMS" -o "$TMP/sums"
  (cd "$TMP" && grep -F "$NAME" sums > one && sha256sum -c one)
else
  echo "WARN: no checksum file in this release, download not verified"
fi
tar -xzf "$TMP/$NAME" -C "$TMP" mediamtx
sudo install -m 755 "$TMP/mediamtx" /usr/local/bin/mediamtx
/usr/local/bin/mediamtx --version
