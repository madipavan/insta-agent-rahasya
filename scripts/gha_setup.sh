#!/usr/bin/env bash
# CI setup for GitHub Actions (Ubuntu)
set -euo pipefail

sudo apt-get update -qq
sudo apt-get install -y -qq ffmpeg fonts-noto-core fonts-noto-extra

mkdir -p assets/fonts

if [ ! -f assets/fonts/BebasNeue-Regular.ttf ]; then
  curl -fsSL -o assets/fonts/BebasNeue-Regular.ttf \
    "https://github.com/google/fonts/raw/main/ofl/bebasneue/BebasNeue-Regular.ttf"
fi

if [ ! -f assets/fonts/Inter-Regular.ttf ]; then
  curl -fsSL -o assets/fonts/Inter-Regular.ttf \
    "https://github.com/google/fonts/raw/main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf"
fi

python -m pip install --upgrade pip
pip install -r requirements.txt

# Write .env from CI environment variables (set in workflow)
: "${GROQ_API_KEY:=}"
cat > .env <<EOF
GROQ_API_KEY=${GROQ_API_KEY}
GEMINI_API_KEY=${GEMINI_API_KEY:-}
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
