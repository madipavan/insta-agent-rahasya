#!/usr/bin/env bash
# Download brand fonts (Hindi + display). Safe to re-run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p assets/fonts

log() { echo "[download_fonts] $*"; }

download_font() {
  local dest="$1"
  local url="$2"
  local fallback_url="${3:-}"

  if [[ -f "$dest" && -s "$dest" ]]; then
    log "exists: $dest"
    return 0
  fi

  log "fetch: $dest"
  if curl -fsSL --connect-timeout 20 --max-time 120 --retry 3 --retry-delay 2 \
    -o "$dest" "$url"; then
    return 0
  fi
  if [[ -n "$fallback_url" ]]; then
    curl -fsSL --connect-timeout 20 --max-time 120 --retry 3 --retry-delay 2 \
      -o "$dest" "$fallback_url"
  fi
}

download_font "assets/fonts/BebasNeue-Regular.ttf" \
  "https://github.com/google/fonts/raw/main/ofl/bebasneue/BebasNeue-Regular.ttf"

download_font "assets/fonts/Inter-Regular.ttf" \
  "https://github.com/google/fonts/raw/main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf"

download_font "assets/fonts/AnekDevanagari-ExtraBold.ttf" \
  "https://github.com/googlefonts/anek-devanagari/raw/main/fonts/ttf/AnekDevanagari-ExtraBold.ttf"

download_font "assets/fonts/NotoSansDevanagari-Bold.ttf" \
  "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf"

download_font "assets/fonts/NotoSansDevanagari-Regular.ttf" \
  "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Regular.ttf"

download_font "assets/fonts/NotoSerifDevanagari-Regular.ttf" \
  "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSerifDevanagari/NotoSerifDevanagari-Regular.ttf"

download_font "assets/fonts/TiroDevanagariHindi-Regular.ttf" \
  "https://github.com/googlefonts/tiro-devanagari/raw/main/fonts/TiroDevanagariHindi-Regular.ttf"

log "done"
