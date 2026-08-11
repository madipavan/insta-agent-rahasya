#!/usr/bin/env bash
# Restore data/ + output/review/ from the latest successful pipeline-state artifact.
set -euo pipefail

mkdir -p data output/review

if ! command -v gh >/dev/null 2>&1; then
  echo "[restore] gh CLI not available — using checkout data/"
  exit 0
fi

BRANCH="${GITHUB_REF_NAME:-master}"
RUN_ID=""

for id in $(gh run list \
  --workflow=daily-rahasya.yml \
  --branch="$BRANCH" \
  --limit=20 \
  --json databaseId,conclusion \
  -q '.[] | select(.conclusion != "cancelled" and .conclusion != "skipped") | .databaseId' 2>/dev/null); do
  [ -z "$id" ] && continue
  TMP="$(mktemp -d)"
  if gh run download "$id" -n pipeline-state -D "$TMP" 2>/dev/null; then
    RUN_ID="$id"
    rm -rf "$TMP"
    break
  fi
  rm -rf "$TMP"
done

if [ -z "$RUN_ID" ]; then
  echo "[restore] no pipeline-state artifact found — using checkout data/"
  exit 0
fi

echo "[restore] downloading pipeline-state from run $RUN_ID"
TMP="$(mktemp -d)"
if gh run download "$RUN_ID" -n pipeline-state -D "$TMP" 2>/dev/null; then
  for db in "$TMP/data/rahasya.db" "$TMP/rahasya.db"; do
    [ -f "$db" ] && cp -f "$db" data/rahasya.db && echo "[restore] restored data/rahasya.db" && break
  done
  for cp in "$TMP/data/checkpoint.json" "$TMP/checkpoint.json"; do
    [ -f "$cp" ] && cp -f "$cp" data/checkpoint.json && echo "[restore] restored data/checkpoint.json" && break
  done
  if [ -d "$TMP/data/novels" ]; then
    mkdir -p data/novels
    # Preserve committed/manual/youtube audio from checkout; only fill missing novels from artifact.
    for novel_art in "$TMP/data/novels"/*; do
      [ -d "$novel_art" ] || continue
      name="$(basename "$novel_art")"
      dest="data/novels/$name"
      mkdir -p "$dest"
      keep=0
      if [ -f "$dest/bgm.json" ] && grep -Eq '"source": "(manual|youtube|elevenlabs_music|library)"' "$dest/bgm.json" 2>/dev/null; then
        keep=1
      fi
      if [ -f "$dest/sfx/sfx.json" ] && grep -Eq '"source": "(manual|elevenlabs_sfx)"' "$dest/sfx/sfx.json" 2>/dev/null; then
        keep=1
      fi
      if [ "$keep" = "1" ]; then
        for f in "$novel_art"/*; do
          [ -e "$f" ] || continue
          base="$(basename "$f")"
          case "$base" in
            bgm.mp3|bgm.json|sfx) continue ;;
          esac
          if [ -d "$f" ]; then
            cp -a "$f" "$dest/" 2>/dev/null || true
          else
            cp -f "$f" "$dest/" 2>/dev/null || true
          fi
        done
        echo "[restore] kept local audio for $name"
      else
        cp -a "$novel_art/." "$dest/"
      fi
    done
    echo "[restore] restored data/novels/ (BGM/SFX cache)"
  fi
  if [ -d "$TMP/output/review" ]; then
    cp -a "$TMP/output/review/." output/review/
    echo "[restore] restored output/review/"
  elif [ -d "$TMP/review" ]; then
    cp -a "$TMP/review/." output/review/
    echo "[restore] restored review/ bundle files"
  fi
else
  echo "[restore] artifact download failed — using checkout data/"
fi
rm -rf "$TMP"
