# Rahasya.exe Content Pipeline

Automated Instagram content pipeline for **Rahasya.exe** — foreign suspense/thriller novels that Bollywood forgot to adapt.

Generates daily **reel + static feed post** pairs from the same episode, with branded templates, Telegram review, and Metricool scheduling.

## Features

- **Auto novel discovery** from public-domain sources (Gutenberg) with TMDB adaptation filtering
- **SQLite progress tracking** — no manual episode management
- **14–21 day pacing** per novel, auto-advance to next book
- **LangGraph + multi-agent crews** — Writer/Editor script pipeline with validation loop; Arc Strategist for episode planning
- **Short-form optimized** — reels under 90s total, carousel capped at 10 slides
- **Episode-ready briefs** — pre-planned hooks, cliffhangers, and retention angles per episode
- **Groq / OpenAI / Anthropic** via LangChain
- **ElevenLabs voiceover** with fixed narrator voice
- **Branded reel assembly** — intro/outro cards, captions, watermark
- **Static post generator** — quote/teaser cards matching reel aesthetic
- **Telegram review** — approve/reject before posting
- **Metricool integration** — queue posts at fixed daily time

## Prerequisites

- Python 3.11+
- **ffmpeg** installed and on PATH ([download](https://ffmpeg.org/download.html))
- API keys (see `.env.example`)

## Setup

```bash
cd D:\insta_auto_page\Rahasya.exe
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` with your API keys and `config.yaml` with your ElevenLabs `voice_id`.

### Required API keys

| Key | Purpose |
|-----|---------|
| `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` | Script generation |
| `ELEVENLABS_API_KEY` | Voiceover |
| `PEXELS_API_KEY` | Stock footage fallback |
| `METRICOOL_API_KEY` + `METRICOOL_USER_ID` | Scheduling |
| `TMDB_API_KEY` | Adaptation checks |
| `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | Review notifications |

### One-time content setup

1. Add 5–10 sample scripts to `data/sample_scripts/` (see folder README)
2. Optional: seed novels via `data/novels_seed.json` (auto-discovery fills queue otherwise)
3. Optional: add noir clips to `assets/stock_library/{keyword}/` (e.g. `night/`, `rain/`)
4. Optional: add fonts to `assets/fonts/` and logo to `assets/brand/logo.png`

## Usage

```bash
# Generate today's content (script + voiceover + reel + static post)
python main.py run

# Check current novel and episode progress
python main.py status

# View novel queue
python main.py queue

# Force novel discovery
python main.py discover

# Manually add a novel
python main.py add-novel --title "Title" --author "Author" --country "France" --chapters 20

# Approve a review bundle (queues to Metricool)
python main.py approve 20260731_the_thirty_nine_steps_ep1

# Reject a bundle
python main.py reject 20260731_the_thirty_nine_steps_ep1 --reason "tone off"

# Start Telegram bot for /approve and /reject commands
python main.py bot
```

## Daily workflow

1. **17:00** — Task Scheduler runs `python main.py run`
2. Pipeline generates reel + static post → saves to `output/review/`
3. **Telegram** sends preview with approve/reject instructions
4. You approve via CLI or Telegram bot
5. **19:30** — Metricool posts reel + static at configured time

## Review gate

`config.yaml`:

```yaml
review_required: true   # set false when you trust output quality
```

When `false`, content auto-queues to Metricool without approval.

## Output structure

```
output/
├── review/          # Pending approval
├── approved/        # Approved bundles
├── posted/          # Successfully posted
├── ready_to_upload/ # Manual Metricool fallback
└── work/            # Temp build files
```

## Windows Task Scheduler

1. Open Task Scheduler → Create Basic Task
2. Trigger: Daily at 17:00
3. Action: Start a program
   - Program: `D:\insta_auto_page\Rahasya.exe\venv\Scripts\python.exe`
   - Arguments: `main.py run`
   - Start in: `D:\insta_auto_page\Rahasya.exe`

Run `python main.py bot` as a separate always-on task or manually when reviewing.

## Manual Instagram setup (not automated)

### Bio
```
Foreign thrillers Bollywood forgot to adapt 👀
New episode every day at 7:30 PM
📚 Currently reading: [novel name]
```

### Story highlights
Organize by novel name so visitors can catch up mid-series:
- `39 Steps` — all episodes for current novel
- `Archive` — completed novels

### Link in bio
Use a consistent link-in-bio tool (Metricool, Linktree, etc.)

## Legal notes

- Scripts are **original paraphrases** — never verbatim book text
- Auto-discovery prefers **public-domain** works
- TMDB adaptation checks are best-effort, not legally perfect
- Review generated content before publishing

## Project structure

```
src/
├── book_queue/      # Novel queue, discovery, SQLite store
├── episode_planner/ # Episode outline generation
├── script_gen/      # LLM script generation
├── voiceover/       # ElevenLabs TTS
├── brand/           # Shared visual templates
├── static_post/     # Feed post graphics
├── visuals/         # Stock, captions, reel assembly
├── review/          # Review bundles + Telegram
├── scheduler/       # Metricool integration
└── pipeline/        # Orchestrator + logging
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `ffmpeg failed` | Install ffmpeg and ensure it's on PATH |
| Empty voiceover | Check `ELEVENLABS_API_KEY` and `voice_id` in config |
| No novels in queue | Run `python main.py discover` |
| Metricool not posting | Check API keys; fallback saves to `output/ready_to_upload/` |
| Whisper slow | Uses CPU by default; optional GPU with CUDA |
