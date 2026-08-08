#!/usr/bin/env python3
"""Create morning + evening cron-job.org triggers for Rahasya GitHub Actions."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

API = "https://api.cron-job.org"
REPO = os.getenv("GITHUB_REPO", "madipavan/insta-agent-rahasya")
WORKFLOW_URL = (
    f"https://api.github.com/repos/{REPO}/actions/workflows/daily-rahasya.yml/dispatches"
)
BODY = json.dumps(
    {
        "ref": os.getenv("GITHUB_REF", "master"),
        "inputs": {
            "skip_episodes": "",
            "use_repo_state": "false",
            "next_novel": "false",
        },
    }
)

JOBS = [
    ("Rahasya Morning Reel", 8, 0),
    ("Rahasya Evening Reel", 19, 30),
]


def _headers(api_key: str, gh_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _job_payload(title: str, hour: int, minute: int, gh_token: str) -> dict:
    return {
        "job": {
            "title": title,
            "url": WORKFLOW_URL,
            "enabled": True,
            "saveResponses": True,
            "requestMethod": 1,
            "requestTimeout": 120,
            "extendedData": {
                "headers": {
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {gh_token}",
                    "Content-Type": "application/json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                "body": BODY,
            },
            "schedule": {
                "timezone": "Asia/Kolkata",
                "expiresAt": 0,
                "hours": [hour],
                "minutes": [minute],
                "mdays": [-1],
                "months": [-1],
                "wdays": [-1],
            },
        }
    }


def _list_jobs(api_key: str) -> list[dict]:
    resp = requests.get(f"{API}/jobs", headers=_headers(api_key, ""), timeout=30)
    resp.raise_for_status()
    return resp.json().get("jobs", [])


def main() -> int:
    api_key = os.getenv("CRONJOB_API_KEY", "").strip()
    gh_token = os.getenv("GITHUB_TOKEN", "").strip()
    if not api_key:
        print("Missing CRONJOB_API_KEY in .env")
        print("Get it: cron-job.org → Console → Settings → API key")
        return 1
    if not gh_token:
        print("Missing GITHUB_TOKEN in .env")
        return 1

    existing = {j.get("title"): j.get("jobId") for j in _list_jobs(api_key)}

    for title, hour, minute in JOBS:
        payload = _job_payload(title, hour, minute, gh_token)
        if title in existing:
            job_id = existing[title]
            resp = requests.patch(
                f"{API}/jobs/{job_id}",
                headers=_headers(api_key, gh_token),
                data=json.dumps(payload),
                timeout=30,
            )
            action = "Updated"
        else:
            resp = requests.put(
                f"{API}/jobs",
                headers=_headers(api_key, gh_token),
                data=json.dumps(payload),
                timeout=30,
            )
            action = "Created"
        if resp.status_code not in (200, 201):
            print(f"{action} failed for {title}: {resp.status_code} {resp.text}")
            return 1
        print(f"{action} {title} — daily {hour:02d}:{minute:02d} IST")

    print("Done. Test: cron-job.org → job → Run now")
    return 0


if __name__ == "__main__":
    sys.exit(main())
