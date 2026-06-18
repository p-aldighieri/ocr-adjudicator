#!/bin/bash
# Build a self-contained, offline macOS .app for OCR Adjudicator.
#
#   tools/build_mac_app.sh [dataset.zip] [install-dir]
#
# Defaults: dataset.zip = /tmp/bb_scans.zip (or public/dataset.zip), install-dir = /Applications
# Produces "OCR Adjudicator.app": a native WKWebView window served by a bundled local
# (127.0.0.1) Python static server. No internet needed at run time.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
APP_NAME="OCR Adjudicator"
EXE="OCRAdjudicator"
WORK="$HOME/.ocr-adjudicator-appbuild"

# dataset source: arg 1, else the hydrated /tmp copy, else the repo copy
DATASET_ZIP="${1:-}"
if [ -z "$DATASET_ZIP" ]; then
  if [ -f /tmp/bb_scans.zip ]; then DATASET_ZIP=/tmp/bb_scans.zip
  else DATASET_ZIP="$ROOT/public/dataset.zip"; fi
fi
[ -f "$DATASET_ZIP" ] || { echo "dataset zip not found: $DATASET_ZIP"; exit 1; }
INSTALL_DIR="${2:-/Applications}"

echo "[1/6] building web app (OCR_COPY_PUBLIC=0 → vite leaves public/ untouched; dataset bundled later)…"
rm -rf dist
npx tsc -b
# On this machine `vite build` writes dist/ correctly but then sometimes never exits. Run it in the
# background, wait for the artifacts to appear, then stop it and continue. No dataset move needed.
OCR_COPY_PUBLIC=0 npx vite build > /tmp/macapp_vite.log 2>&1 &
vpid=$!
ready=0
for _ in $(seq 1 180); do
  if grep -q "built in" /tmp/macapp_vite.log 2>/dev/null && [ -f dist/index.html ] && ls dist/assets/*.js >/dev/null 2>&1; then
    ready=1; break
  fi
  sleep 1
done
sleep 1
kill "$vpid" 2>/dev/null || true
pkill -P "$vpid" 2>/dev/null || true
[ "$ready" = 1 ] || { echo "vite build did not finish:"; tail -20 /tmp/macapp_vite.log; exit 1; }
echo "      web build ready: $(ls dist/assets/*.js 2>/dev/null | xargs -n1 basename | tr '\n' ' ')"

echo "[2/6] compiling native app (swiftc)…"
rm -rf "$WORK"; mkdir -p "$WORK"
swiftc -O "$ROOT/tools/mac_app/main.swift" -o "$WORK/$EXE" -framework Cocoa -framework WebKit

echo "[3/6] assembling .app bundle…"
APP="$WORK/$APP_NAME.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$WORK/$EXE" "$APP/Contents/MacOS/$EXE"
cp "$ROOT/tools/mac_app/Info.plist" "$APP/Contents/Info.plist"

echo "[4/6] bundling site (built app + dataset)…"
SITE="$APP/Contents/Resources/site"
mkdir -p "$SITE"
cp -R dist/. "$SITE/"
mkdir -p "$SITE/dataset"
( cd "$SITE/dataset" && unzip -oq "$DATASET_ZIP" )
test -f "$SITE/dataset/dataset.json" || { echo "dataset.json missing after unzip"; exit 1; }
echo "      images bundled: $(ls "$SITE/dataset/images" | wc -l | tr -d ' ')"

echo "[5/6] icon + ad-hoc code signing…"
ICONSET="$WORK/AppIcon.iconset"; mkdir -p "$ICONSET"
SRC_ICON="$ROOT/public/pwa-512.png"
for s in 16 32 128 256 512; do
  sips -z $s $s   "$SRC_ICON" --out "$ICONSET/icon_${s}x${s}.png"     >/dev/null
  d=$((s*2)); sips -z $d $d "$SRC_ICON" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns"
codesign --force --deep --sign - "$APP"

echo "[6/6] installing to $INSTALL_DIR…"
target=""
for d in "$INSTALL_DIR" "$HOME/Applications" "$HOME/Desktop"; do
  if mkdir -p "$d" 2>/dev/null && rm -rf "$d/$APP_NAME.app" 2>/dev/null && cp -R "$APP" "$d/" 2>/dev/null; then
    target="$d/$APP_NAME.app"; break
  fi
done
[ -n "$target" ] || { echo "could not install (permissions?)"; exit 1; }
echo "DONE: $target"
