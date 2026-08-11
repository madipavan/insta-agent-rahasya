# Cinematic BGM library (underscore / ambient)

Long-form **background music** mixed under the voiceover for reels — tense, moody,
cinematic **ambient underscore**, not short retention stingers.

## BGM library vs SFX library

| | `assets/bgm_library/` | `assets/sfx_library/` |
|---|----------------------|------------------------|
| **Purpose** | Cinematic ambient underscore for the whole reel | Short retention hits (hook, whoosh, cliffhanger) |
| **Duration** | ~30s–3min (loops under narration) | Under ~2s each |
| **When mixed** | Entire reel, ducked under voice | Specific timestamps (start, cuts, cliffhanger) |
| **Examples** | Tense synth pad, dark piano, suspense drone | `hook_impact.wav`, `whoosh_short.wav` |
| **Generation** | YouTube search, local files, or synthetic ffmpeg pad | Local ffmpeg synthesis or royalty-free SFX |

Do **not** put hook/whoosh/cliffhanger sounds here — those belong in `assets/sfx_library/`.
See `assets/sfx_library/README.md` for retention SFX.

## How the pipeline uses this folder

1. **ElevenLabs Music API** (when `video.elevenlabs_audio_enabled: true` + API key) —
   generates one instrumental bed per novel (~30s), cached at
   `data/novels/{id}_{slug}/bgm.mp3` and reused for **all episodes**.
2. If ElevenLabs is off/fails, `fetch_novel_bgm` tries YouTube for royalty-free cinematic tracks.
3. If YouTube fails, `_copy_library_track` picks a file from this folder
   (`.mp3`, `.wav`, `.m4a`, `.aac`).
4. Last resort: synthetic ffmpeg pad.
5. `ReelAssembler` loops the BGM under the voiceover with sidechain ducking.

Per-novel **SFX** are cached separately at `data/novels/{id}_{slug}/sfx/`
(hook / whoosh / cliffhanger). Regenerate with:

```bash
python scripts/generate_novel_audio.py --novel-id 1 --force
```

Requires: `pip install yt-dlp` (for YouTube search only — library files work without it).

## Adding ElevenLabs ambient tracks manually (no API credits)

ElevenLabs can generate **music / ambient** beds from the website UI using your
monthly quota — **no API call from this repo**, so pipeline runs do not spend credits.

1. Open [ElevenLabs](https://elevenlabs.io/) → **Music** or **Sound Effects** (long ambient prompts).
2. Generate something like: *"tense cinematic ambient underscore, no vocals, dark suspense, 30 seconds"*.
3. Download the WAV/MP3 from the UI.
4. Drop it in this folder with a descriptive name, e.g.:
   - `tense_cinematic_ambient.wav`
   - `dark_mystery_piano.mp3`
5. Avoid pop-song words in filenames (`vocal`, `remix`, `faded`, etc.) — those are hard-rejected.
6. Delete a novel's cached `data/novels/{id}_{slug}/bgm.mp3` (+ `bgm.json`) to force re-assignment.

**Included track:** `tense_cinematic_ambient.wav` — ElevenLabs-generated tense cinematic
ambient (30s, stereo 48 kHz). Source: user download from ElevenLabs UI.

Non-MP3 library files are converted to MP3 when assigned to a novel.

## Other sources

Royalty-free cinematic instrumentals also work:

- [Pixabay Music](https://pixabay.com/music/)
- [YouTube Audio Library](https://studio.youtube.com/) (download, then place here)
- Any safe instrumental `.mp3` / `.wav` you own rights to use

BGM must be **cinematic / instrumental storytelling** — never pop songs
(e.g. Faded, vocal covers, TikTok remixes).

Search prefers titles with: `cinematic`, `soundtrack`, `underscore`,
`instrumental`, `no vocals`, `mystery`, `suspense`, `royalty free`.

Hard-rejects: vocals, lyrics, covers, remixes, famous chart songs.
