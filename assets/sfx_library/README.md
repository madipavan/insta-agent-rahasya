# Retention SFX library

Short sound effects mixed under the voiceover for reel retention:

| File | When used | Default source |
|------|-----------|----------------|
| `hook_impact.wav` | Start of voiceover (0s) — stops the scroll | [Mixkit: Fast impact blow](https://mixkit.co/free-sound-effects/impact/) (#2884) |
| `whoosh_short.wav` | Each montage clip cut | [Mixkit: Quick air woosh](https://mixkit.co/free-sound-effects/woosh/) (#2568) |
| `cliffhanger_rumble.wav` | ~8s before end — cliffhanger sting | [Mixkit: Deep cinematic subtle drum impact](https://mixkit.co/free-sound-effects/impact/) (#549) |

All defaults are **royalty-free** under the [Mixkit SFX Free License](https://mixkit.co/license/#sfxFree). No ElevenLabs or paid APIs are used.

If these files are missing, the pipeline auto-generates simple versions via ffmpeg on first run (`src/visuals/sfx.py`).

## Download / refresh the library

From the repo root:

```bash
python scripts/download_sfx_library.py
```

Re-download and replace existing files:

```bash
python scripts/download_sfx_library.py --force
```

The script is idempotent: it skips files that already exist unless `--force` is passed.

**Source order per file:**

1. Mixkit CDN direct URLs (free, no API key)
2. ffmpeg synthesis (offline fallback, same as the pipeline)

`PIXABAY_API_KEY` in `.env` does **not** help here — Pixabay’s public API covers images and videos only, not sound effects.

## Customize

Replace any WAV with your own clip (keep the exact filename). Keep files short (under 2s) and normalized.

Other free sources:

- [Pixabay Sound Effects](https://pixabay.com/sound-effects/) (manual download)
- [VideoEditingSFX](https://videoeditingsfx.com/) (100 free WAV)
- [sfxreels](https://sfxreels.com/) (Reels-tuned pack)

Configure mix volumes in `config.yaml` under `video.sfx_*`:

- `sfx_enabled`
- `sfx_hook_volume` (default `0.35`)
- `sfx_whoosh_volume` (default `0.22`)
- `sfx_cliffhanger_volume` (default `0.30`)
- `sfx_cliffhanger_before_end_sec` (default `8.0`)
