#!/usr/bin/env bash
# Restore data/rahasya.db + checkpoint.json from the latest successful workflow artifact.
set -euo pipefail

mkdir -p data
NEED_RESTORE=0
if [ ! -f data/rahasya.db ]; then NEED_RESTORE=1; fi
if [ ! -f data/checkpoint.json ]; then NEED_RESTORE=1; fi

if [ "$NEED_RESTORE" -eq 0 ]; then
  echo "[restore] local data + checkpoint present — skip artifact download"
  exit 0
fi

echo "[restore] missing data/rahasya.db or data/checkpoint.json — trying artifact"

if ! command -v gh >/dev/null 2>&1; then
  echo "[restore] gh CLI not available — skip"
  exit 0
fi

BRANCH="${GITHUB_REF_NAME:-master}"
RUN_ID="$(gh run list --workflow=daily-rahasya.yml --branch="$BRANCH" --status=success --limit 5 --json databaseId,conclusion -q '.[] | select(.conclusion=="success") | .databaseId' 2>/dev/null | head -n1 || true)"

if [ -z "$RUN_ID" ] || [ "$RUN_ID" = "null" ]; then
  echo "[restore] no successful prior run found"
  exit 0
fi

echo "[restore] downloading pipeline-db from run $RUN_ID"
TMP="$(mktemp -d)"
if gh run download "$RUN_ID" -n pipeline-db -D "$TMP" 2>/dev/null; then
  [ -f "$TMP/rahasya.db" ] && cp -f "$TMP/rahasya.db" data/rahasya.db && echo "[restore] restored data/rahasya.db"
  [ -f "$TMP/checkpoint.json" ] && cp -f "$TMP/checkpoint.json" data/checkpoint.json && echo "[restore] restored data/checkpoint.json"
else
  echo "[restore] artifact download failed"
fi
rm -rf "$TMP"
