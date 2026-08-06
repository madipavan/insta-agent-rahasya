#!/usr/bin/env bash
# Restore data/rahasya.db + checkpoint.json from the latest successful workflow artifact.
set -euo pipefail

mkdir -p data

if ! command -v gh >/dev/null 2>&1; then
  echo "[restore] gh CLI not available — using checkout data/"
  exit 0
fi

BRANCH="${GITHUB_REF_NAME:-master}"
RUN_ID="$(gh run list --workflow=daily-rahasya.yml --branch="$BRANCH" --status=success --limit 5 --json databaseId,conclusion -q '.[] | select(.conclusion=="success") | .databaseId' 2>/dev/null | head -n1 || true)"

if [ -z "$RUN_ID" ] || [ "$RUN_ID" = "null" ]; then
  echo "[restore] no successful prior run — using checkout data/"
  exit 0
fi

echo "[restore] downloading pipeline-db from run $RUN_ID"
TMP="$(mktemp -d)"
if gh run download "$RUN_ID" -n pipeline-db -D "$TMP" 2>/dev/null; then
  [ -f "$TMP/rahasya.db" ] && cp -f "$TMP/rahasya.db" data/rahasya.db && echo "[restore] restored data/rahasya.db"
  [ -f "$TMP/checkpoint.json" ] && cp -f "$TMP/checkpoint.json" data/checkpoint.json && echo "[restore] restored data/checkpoint.json"
else
  echo "[restore] artifact download failed — using checkout data/"
fi
rm -rf "$TMP"
