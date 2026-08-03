# Per-novel storytelling BGM

BGM must be **cinematic / instrumental storytelling** music — never pop songs
(e.g. Faded, vocal covers, TikTok remixes).

Search prefers titles with: `cinematic`, `soundtrack`, `underscore`,
`instrumental`, `no vocals`, `mystery`, `suspense`, `royalty free`.

Hard-rejects: vocals, lyrics, covers, remixes, famous chart songs.

Downloaded once to:
`data/novels/{id}_{slug}/bgm.mp3`

Same track is reused for every episode of that novel.

Requires: `pip install yt-dlp`

Optional: delete `data/novels/{id}_{slug}/bgm.mp3` (+ `.json`) to force a re-search.

You can also drop safe instrumental `.mp3` files into this folder as a library fallback
(filenames must not look like pop songs).
