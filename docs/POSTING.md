# Posting cadence (Rahasya.exe free stack)

## Schedule

Triggered twice daily by **cron-job.org** — each run does **generate + publish**. See [CRON_SETUP.md](CRON_SETUP.md).

| Trigger | Time (IST) | Result |
|---------|------------|--------|
| Morning | ~8:00 AM | 1 reel generated + posted |
| Evening | ~7:30 PM | 1 reel generated + posted |

**2 reels per day** (~60/month max; tune cron if you want fewer).
| Novels | **One arc at a time** — finish before starting the next |
| Review | `auto_publish: false` — watch `reel.mp4` before publishing |

## Monthly workflow

1. **Week start:** Ensure `assets/stock_library/` has clips for the current novel (run `python scripts/seed_stock_library.py` if needed).
2. **Generate batch:** Run pipeline every 2 days or batch 3–4 episodes, then publish on schedule.
3. **Publish:** `python main.py publish` queues Meta posts for `post_time`.
4. **Skip delay (testing only):** `python main.py publish --force` bypasses `min_publish_delay_hours`.

## Quality checklist before publish

- [ ] Fish voice pacing feels slow and dramatic
- [ ] Hook text visible in first 3 seconds (red accent)
- [ ] Hindi captions bold and readable
- [ ] Stock clips match scene mood (not repetitive)
- [ ] Cliffhanger SFX ~8s before end

## API keys (free tier)

- `FISH_AUDIO_API_KEY` — primary voice
- `GEMINI_API_KEY` — scripts
- `REPLICATE_API_TOKEN` — fictional stills (try free → billing)
- `PIXABAY_API_KEY` — stock video (optional; Pexels fallback)
- `PEXELS_API_KEY` — stock video fallback
- `SARVAM_API_KEY` — voice backup only when Fish fails
