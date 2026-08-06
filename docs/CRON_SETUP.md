# cron-job.org setup (cloud only — 2 reels per day)

Each trigger runs the **full pipeline** on GitHub Actions: generate reel → publish to Instagram.

Your PC can stay off. No local scheduler needed.

## Fastest setup (one command)

1. Create a **GitHub PAT**: Settings → Developer settings → Personal access tokens → scopes **repo** + **workflow**
2. Sign up at [cron-job.org](https://cron-job.org) → Console → **Settings** → copy **API key**
3. Add both to `.env` (not committed):
   ```
   GITHUB_TOKEN=ghp_...
   CRONJOB_API_KEY=...
   ```
4. Run once:
   ```powershell
   cd D:\insta_auto_page\Rahasya.exe
   .\venv\Scripts\python.exe scripts\setup_cron_jobs.py
   ```

This creates two cloud cron jobs:

| Job | Time (IST) |
|-----|------------|
| Rahasya Morning Reel | 8:00 AM |
| Rahasya Evening Reel | 7:30 PM |

Each run → `python main.py run --publish-now` on GitHub → **1 reel posted**.

## Manual setup (cron-job.org website)

If you prefer the UI, create **two** jobs with the same body, different times.

**URL:**
```
https://api.github.com/repos/madipavan/insta-agent-rahasya/actions/workflows/daily-rahasya.yml/dispatches
```

**Method:** POST

**Headers:**
```
Accept: application/vnd.github+json
Authorization: Bearer YOUR_GITHUB_TOKEN
Content-Type: application/json
X-GitHub-Api-Version: 2022-11-28
```

**Body:**
```json
{
  "ref": "master",
  "inputs": {
    "skip_episodes": "",
    "use_repo_state": "false"
  }
}
```

**Schedules** (timezone: Asia/Kolkata):

| Job | Cron |
|-----|------|
| Morning | `0 8 * * *` |
| Evening | `30 19 * * *` |

## Reset pipeline

Trigger once with `"use_repo_state": "true"` in the body, or run workflow manually in GitHub Actions with that checkbox.

## Test

cron-job.org → job → **Run now** → check GitHub **Actions** tab.
