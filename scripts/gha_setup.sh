#!/usr/bin/env bash
# CI setup for GitHub Actions (Ubuntu)
# Usage: bash scripts/gha_setup.sh [all|system|python|env]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

STEP="${1:-all}"
INSTALL_ML="${INSTALL_ML:-1}"
PIP_TIMEOUT="${PIP_TIMEOUT:-120}"
PIP_RETRIES="${PIP_RETRIES:-3}"

log() { echo "[gha_setup] $*"; }
warn() { echo "::warning::$*"; }

run_with_retry() {
  local max="$1"
  shift
  local attempt=1
  until "$@"; do
    if (( attempt >= max )); then
      return 1
    fi
    log "retry ${attempt}/${max}: $*"
    attempt=$((attempt + 1))
    sleep 5
  done
}

install_system_packages() {
  export DEBIAN_FRONTEND=noninteractive
  log "installing system packages (ffmpeg, fonts)"
  run_with_retry 3 timeout 300 sudo apt-get update -qq \
    -o Acquire::Retries=3 \
    -o Acquire::http::Timeout=30
  run_with_retry 3 timeout 600 sudo apt-get install -y -qq \
    -o Dpkg::Options::=--force-confdef \
    -o Dpkg::Options::=--force-confold \
    ffmpeg fonts-noto-core fonts-noto-extra
}

download_font() {
  local dest="$1"
  local url="$2"
  local fallback_url="${3:-}"

  if [[ -f "$dest" ]]; then
    log "font exists: $dest"
    return 0
  fi

  log "downloading font: $dest"
  if curl -fsSL --connect-timeout 20 --max-time 120 --retry 3 --retry-delay 2 \
    -o "$dest" "$url"; then
    return 0
  fi

  if [[ -n "$fallback_url" ]]; then
    log "font primary URL failed, trying fallback"
    if curl -fsSL --connect-timeout 20 --max-time 120 --retry 3 --retry-delay 2 \
      -o "$dest" "$fallback_url"; then
      return 0
    fi
  fi

  warn "Font download failed: $dest (pipeline will use system fallback fonts)"
  return 0
}

install_fonts() {
  mkdir -p assets/fonts
  download_font \
    "assets/fonts/BebasNeue-Regular.ttf" \
    "https://github.com/google/fonts/raw/main/ofl/bebasneue/BebasNeue-Regular.ttf" \
    "https://raw.githubusercontent.com/google/fonts/main/ofl/bebasneue/BebasNeue-Regular.ttf"
  download_font \
    "assets/fonts/Inter-Regular.ttf" \
    "https://github.com/google/fonts/raw/main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf" \
    "https://raw.githubusercontent.com/google/fonts/main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf"
}

install_python_packages() {
  export PIP_DISABLE_PIP_VERSION_CHECK=1
  export PIP_DEFAULT_TIMEOUT="${PIP_TIMEOUT}"

  log "upgrading pip"
  run_with_retry "${PIP_RETRIES}" python -m pip install --upgrade pip

  log "installing core Python dependencies"
  run_with_retry "${PIP_RETRIES}" timeout 900 python -m pip install \
    -r requirements.txt \
    --prefer-binary \
    --timeout "${PIP_TIMEOUT}" \
    --retries 3

  if [[ "${INSTALL_ML}" == "1" ]]; then
    log "installing optional ML dependencies (faster-whisper)"
    if run_with_retry 2 timeout 900 python -m pip install \
      -r requirements-ml.txt \
      --prefer-binary \
      --timeout "${PIP_TIMEOUT}" \
      --retries 3; then
      log "ML dependencies installed"
    else
      warn "faster-whisper install failed or timed out — captions will use timing fallback"
    fi
  else
    log "skipping ML dependencies (INSTALL_ML=0)"
  fi
}

write_env_file() {
  : "${GROQ_API_KEY:=}"
  cat > .env <<EOF
GROQ_API_KEY=${GROQ_API_KEY}
GEMINI_API_KEY=${GEMINI_API_KEY:-}
MISTRAL_API_KEY=${MISTRAL_API_KEY:-}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
OPENAI_API_KEY=${OPENAI_API_KEY:-}
ELEVENLABS_API_KEY=${ELEVENLABS_API_KEY:-}
PEXELS_API_KEY=${PEXELS_API_KEY:-}
META_ACCESS_TOKEN=${META_ACCESS_TOKEN:-}
META_IG_USER_ID=${META_IG_USER_ID:-}
META_PAGE_ID=${META_PAGE_ID:-}
META_APP_ID=${META_APP_ID:-}
META_APP_SECRET=${META_APP_SECRET:-}
TMDB_API_KEY=${TMDB_API_KEY:-}
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-}
TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID:-}
METRICOOL_API_KEY=${METRICOOL_API_KEY:-}
METRICOOL_USER_ID=${METRICOOL_USER_ID:-}
EOF
  mkdir -p data output logs output/stock_cache
}

case "${STEP}" in
  system)
    install_system_packages
    install_fonts
    ;;
  python)
    install_python_packages
    ;;
  env)
    write_env_file
    ;;
  all)
    install_system_packages
    install_fonts
    install_python_packages
    write_env_file
    ;;
  *)
    echo "Unknown step: ${STEP} (use all|system|python|env)" >&2
    exit 1
    ;;
esac

log "done (${STEP})"
