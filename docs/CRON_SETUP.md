# cron-job.org setup (reliable scheduling)

GitHub Actions `schedule` is removed. Use [cron-job.org](https://cron-job.org) (free) to trigger the workflow on time.

## 1. Create a GitHub token

1. GitHub → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained** (or classic)
2. Repo access: `madipavan/insta-agent-rahasya`
3. Permissions: **Actions: Read and write**, **Contents: Read**
4. Copy the token (starts with `github_pat_` or `ghp_`)

Store it in cron-job.org as a header — do **not** commit it to the repo.

## 2. Two cron jobs (IST)

| Job | When (IST) | Cron (UTC) | `mode` |
|-----|------------|------------|--------|
| **Generate** | 8:00 AM | `0 2 * * *` | `generate` |
| **Publish** | 7:30 PM | `0 14 * * *` | `publish` |

Adjust times in cron-job.org to your timezone (set account timezone to **Asia/Kolkata**).

## 3. cron-job.org job settings

For **each** job:

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
- **Body (morning — generate):**
  ```json
  {
    "ref": "master",
    "inputs": {
      "mode": "generate",
      "skip_episodes": "",
      "use_repo_state": "false"
    }
  }
  ```
- **Body (evening — publish):**
  ```json
  {
    "ref": "master",
    "inputs": {
      "mode": "publish",
      "skip_episodes": "",
      "use_repo_state": "false"
    }
  }
  ```

## 4. Cadence every 2 days

If you post every **2 days** (not daily), set cron-job.org schedule to:

- Generate: `0 2 */2 * *` (every 2 days at 8:00 AM IST)
- Publish: `0 14 */2 * *` (every 2 days at 7:30 PM IST)

Or offset publish to the **day after** generate if you want a review gap.

## 5. Reset pipeline state

Run workflow manually in GitHub Actions with:

- `mode`: `generate`
- `use_repo_state`: **true**

Or trigger via API with `"use_repo_state": "true"`.

## 6. Test

1. cron-job.org → **Test run** on generate job
2. GitHub → **Actions** → confirm workflow started
3. After generate succeeds, test publish job

## Flow

```
8:00 AM  cron-job.org → mode=generate → python main.py run → pipeline-db artifact
7:30 PM  cron-job.org → mode=publish  → python main.py publish --now
```

No wait step — publish runs immediately when the evening job fires.
