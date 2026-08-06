# Deploy with GitHub Actions (free)

Runs on **cron-job.org** triggers (morning generate, evening publish). See [docs/CRON_SETUP.md](../docs/CRON_SETUP.md).

Your PC can stay off.

## 1. Push code to GitHub

```bash
cd D:\insta_auto_page\Rahasya.exe
git add .
git commit -m "Add GitHub Actions daily pipeline"
git push -u origin main
```

Repo: https://github.com/madipavan/insta-agent-rahasya.git

## 2. Add secrets

GitHub → your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Secret | Required | Purpose |
|--------|----------|---------|
| `GROQ_API_KEY` or `GEMINI_API_KEY` | Yes (one LLM) | Script generation |
| `FISH_AUDIO_API_KEY` | Yes (voice) | Primary Hindi TTS (fish-audio) |
| `SARVAM_API_KEY` | Optional | Voice fallback if Fish fails |
| `PEXELS_API_KEY` | Yes (stock) | Stock footage |
| `PIXABAY_API_KEY` | Optional | Extra stock source |
| `META_ACCESS_TOKEN` | For auto-post | Instagram scheduling |
| `META_IG_USER_ID` | For auto-post | Instagram account ID |
| `META_PAGE_ID` | For auto-post | Facebook Page (cover upload) |
| `TMDB_API_KEY` | Optional | Novel discovery |
| `TELEGRAM_BOT_TOKEN` | Optional | Error notifications |
| `TELEGRAM_CHAT_ID` | Optional | Error notifications |

## 3. Enable workflow + cron-job.org

GitHub → **Actions** → **Daily Rahasya** → **Enable workflows**

Set up two jobs on [cron-job.org](https://cron-job.org) — full steps in **docs/CRON_SETUP.md**:

| Time (IST) | API body `mode` |
|------------|-----------------|
| 8:00 AM | `generate` |
| 7:30 PM | `publish` |

Test manually: **Actions** → **Run workflow** → choose `generate` or `publish`

## 4. Continue from episode 10 (optional)

Without your local database, GitHub starts at **episode 1**.

To keep episode progress:

```powershell
# One-time: force-add your local DB into the repo
git add -f data/rahasya.db
git add data/novels/
git commit -m "Bootstrap pipeline state"
git push
```

Run the workflow once manually. The cache will save `data/` for future runs.

Then remove DB from git (optional):

```powershell
git rm --cached data/rahasya.db
git commit -m "Stop tracking DB — state lives in Actions cache"
git push
```

## 5. Check results

- **Actions** tab → latest run → logs
- **Artifacts** → download `latest-episode-*` (reel, post details)
- Instagram → scheduled posts (after Meta credentials work)

## Schedule

| Event | Time (IST) |
|-------|------------|
| cron-job.org → generate | ~8:00 AM |
| cron-job.org → publish | ~7:30 PM |

Config: `config.yaml` → `post_time` is legacy; publish timing is set on cron-job.org.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Workflow not running | Enable Actions; check repo is public or you have free minutes |
| `GROQ_API_KEY` missing | Add secret in repo settings |
| Meta not posting | Add META_* secrets; run `python main.py meta-test` locally first |
| Started at ep 1 | Bootstrap `data/rahasya.db` (step 4) |
| `FISH_AUDIO_API_KEY` missing | Add secret from https://fish.audio/app/api-keys |
| Hindi font error | Noto fonts are in `assets/fonts/` — workflow installs system fonts too |
