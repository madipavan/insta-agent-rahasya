# Retention SFX library

Short sound effects mixed under the voiceover for reel retention:

| File | When used |
|------|-----------|
| `hook_impact.wav` | Start of voiceover (0s) — stops the scroll |
| `whoosh_short.wav` | Each montage clip cut |
| `cliffhanger_rumble.wav` | ~8s before end — cliffhanger sting |

If these files are missing, the pipeline auto-generates simple versions via ffmpeg on first run.

You can replace them with royalty-free SFX from:

- [Pixabay Sound Effects](https://pixabay.com/sound-effects/)
- [VideoEditingSFX](https://videoeditingsfx.com/) (100 free WAV)
- [sfxreels](https://sfxreels.com/) (Reels-tuned pack)

Keep files short (under 2s) and normalized. WAV or MP3 both work if named as above.

Configure volumes in `config.yaml` under `video.sfx_*`.
