Organize pre-downloaded clips by keyword subfolder:

```
stock_library/
├── night/
│   └── clip1.mp4
├── rain/
│   └── clip2.mp4
├── mansion/
├── detective/
├── mystery/
├── yellow_room/
└── shadow/
```

## Fetch order (automatic)

1. **Local** `stock_library/{keyword}/` — highest priority
2. **Pixabay API** — set `PIXABAY_API_KEY` in `.env`
3. **Pexels API** — fallback

Configure in `config.yaml` → `video.stock_providers`.

## Seed library from Pixabay (free)

Downloads ~3 clips per theme folder (18 total):

```powershell
.\venv\Scripts\Activate.ps1
python scripts/seed_stock_library.py
```

Requires `PIXABAY_API_KEY` from https://pixabay.com/api/docs/

Manual sources (download once, drop into folders): Mixkit, Videvo, Pexels.
