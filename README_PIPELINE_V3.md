# CH-666 pipeline v3

This pipeline uses one GitHub Actions workflow and scripts/main.py.

- News: public GDELT index, no NewsAPI key needed. No mock news is generated.
- Classification: randomly assigns each collected source to a story category: CH-333 = supernatural, CH-666 = strange accounts, CH-999 = taboo. The code is metadata, not a story premise.
- Story direction: dice select the horror approach, narrative style, pacing, perspective, structure, and ending from the assigned category's options; source material supplies the core anomaly/clues to transform.
- Text providers: NVIDIA first, Agnes fallback.
- Images: best-effort NVIDIA image endpoint, WebP conversion, FTP upload. If the account does not support the configured image endpoint, the story is retained and the log reports the failure.
- Storage: individual JSON under content/stories plus dated/latest JSON under content/daily.
- Sync: uses the existing scripts/notify.py and SERV00_UPDATE_URL / SERV00_UPDATE_TOKEN.

Required Secrets: NVIDIA_API_KEY, AGNES_API_KEY, FTP_HOST, FTP_USER, FTP_PASS, FTP_PATH, SITE_URL, SERV00_UPDATE_URL, SERV00_UPDATE_TOKEN.

Story codes preserve CH-333-0001 / CH-666-0001 / CH-999-0001 as storage identifiers only. category remains "3", "6", or "9"; channel stores its CH code as metadata. Never use a category code or serial/file number as a story title: titles name the story's subject directly, and subtitles describe its story core. scene_images remains a single URL string or empty string.
