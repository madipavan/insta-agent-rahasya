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

Or run from repo root (requires curl):

```powershell
cd assets/fonts
curl.exe -fsSL -o AnekDevanagari-ExtraBold.ttf "https://github.com/googlefonts/anek-devanagari/raw/main/fonts/ttf/AnekDevanagari-ExtraBold.ttf"
```

Configure paths in `config.yaml` under `brand:`.
