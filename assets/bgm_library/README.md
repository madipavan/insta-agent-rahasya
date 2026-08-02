# Per-novel BGM

BGM is **searched and downloaded per novel** based on the novel title + episode keywords.

Example for *The Thirty-Nine Steps* with keywords `spy, chase, london`:
```
NCS epic cinematic spy chase london thirty steps
```

The best matching NCS/epic track is downloaded once to:
`data/novels/{id}_{slug}/bgm.mp3`

Same track is reused for every episode of that novel.

Requires: `pip install yt-dlp`

Optional: delete `data/novels/{id}_{slug}/bgm.mp3` to force a re-search.
