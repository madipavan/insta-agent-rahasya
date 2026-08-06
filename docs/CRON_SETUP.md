# cron-job.org setup (2 reels per day)

Each trigger runs the **full pipeline**: generate reel → publish to Instagram immediately.

GitHub `schedule` is not used (unreliable). Use [cron-job.org](https://cron-job.org) (free).

## 1. GitHub token

1. GitHub → **Settings** → **Developer settings** → **Personal access tokens**
2. Repo: `madipavan/insta-agent-rahasya`
3. Permission: **Actions: Read and write**
4. Copy token (`github_pat_...` or `ghp_...`)

## 2. Two cron jobs — same body, different times

Set cron-job.org account timezone to **Asia/Kolkata**.

| Job | Time (IST) | Cron expression |
|-----|------------|-----------------|
| **Morning reel** | 8:00 AM | `0 8 * * *` |
| **Evening reel** | 7:30 PM | `30 19 * * *` |

Both jobs use the **same** settings below.

## 3. cron-job.org settings (both jobs)

- **URL:**
  ```
  https://api.github.com/repos/madipavan/insta-agent-rahasya/actions/workflows/daily-rahasya.yml/dispatches
  ```
- **Method:** `POST`
- **Headers:**
  ```
  Accept: application/vnd.github+json
  Authorization: Bearer YOUR_GITHUB_TOKEN
  Content-Type: application/json
  ```
- **Body:**
  ```json
  {
    "ref": "master",
    "inputs": {
      "skip_episodes": "",
      "use_repo_state": "false"
    }
  }
  ```

## 4. What each run does

```
cron trigger → python main.py run --publish-now
             → next episode generated + posted to Instagram
```

Morning run → ep 3 (example)  
Evening run → ep 4  
= **2 reels per day**

## 5. Reset pipeline

Trigger once with:

```json
{
  "ref": "master",
  "inputs": {
    "skip_episodes": "",
    "use_repo_state": "true"
  }
}
```

Or manually in GitHub Actions → **Run workflow** → check **use_repo_state**.

## 6. Test

1. cron-job.org → **Test run**
2. GitHub → **Actions** → watch logs
3. Confirm reel on Instagram
