#!/usr/bin/env python3
"""Trigger GitHub Actions workflow (used by Task Scheduler or manual test)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

REPO = os.getenv("GITHUB_REPO", "madipavan/insta-agent-rahasya")
WORKFLOW = os.getenv("GITHUB_WORKFLOW", "daily-rahasya.yml")
REF = os.getenv("GITHUB_REF", "master")
URL = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches"


def main() -> int:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        print("Missing GITHUB_TOKEN in .env")
        print("Create a PAT: GitHub → Settings → Developer settings → Personal access tokens")
        print("Scopes: repo + workflow")
        return 1

    body = {
        "ref": REF,
        "inputs": {
            "skip_episodes": os.getenv("GITHUB_SKIP_EPISODES", ""),
            "use_repo_state": os.getenv("GITHUB_USE_REPO_STATE", "false"),
            "next_novel": os.getenv("GITHUB_NEXT_NOVEL", "false"),
        },
    }
    resp = requests.post(
        URL,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json=body,
        timeout=30,
    )
    if resp.status_code == 204:
        print(f"Triggered workflow {WORKFLOW} on {REF}")
        return 0
    print(f"Failed ({resp.status_code}): {resp.text}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
