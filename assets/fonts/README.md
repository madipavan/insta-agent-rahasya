Place display and caption fonts here.

## Cinematic stack (free — Google Fonts)

| File | Use |
|------|-----|
| `AnekDevanagari-ExtraBold.ttf` | Reel Hindi captions + hook text |
| `TiroDevanagariHindi-Regular.ttf` | Carousel quote slides (or `NotoSerifDevanagari-Regular.ttf`) |
| `BebasNeue-Regular.ttf` | Intro/outro English titles |
| `Inter-Regular.ttf` | Watermark / body (optional) |
| `NotoSansDevanagari-Bold.ttf` | Fallback Hindi |

Download:
- https://fonts.google.com/specimen/Anek+Devanagari
- https://fonts.google.com/specimen/Tiro+Devanagari
- https://fonts.google.com/specimen/Bebas+Neue

Or run from repo root:

```bash
bash scripts/download_fonts.sh
```

On Windows (PowerShell):

```powershell
curl.exe -fsSL -o assets/fonts/AnekDevanagari-ExtraBold.ttf "https://github.com/googlefonts/anek-devanagari/raw/main/fonts/ttf/AnekDevanagari-ExtraBold.ttf"
```

**Square boxes in Hindi text?** Scripts use `…` and emoji that Devanagari fonts lack — the pipeline now normalizes these to `...` before rendering.

Configure paths in `config.yaml` under `brand:`.
