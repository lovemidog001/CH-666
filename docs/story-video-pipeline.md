# Story, illustration and video pipeline

A manual run creates a story and its WebP illustrations first. The separate video job then tries to turn each illustration into a moving clip with Agnes Video 2.5. If that model fails, it tries Agnes Video 2.5 Flash. If both attempts fail, or `AGNES_API_KEY` is not configured, FFmpeg creates the existing pan/zoom illustration animation with the CRT look. Each clip is encoded as WebM and gets a WebP poster for the website.

Video generation is optional: the video job uses `continue-on-error`, so a video provider outage does not undo or block the story and illustration publication. The Agnes 2.5 model may incur charges according to the account's current plan and rates. Flash availability and pricing can change; check Agnes before running the workflow. The pipeline does not call xAI/Grok.

## Manual run

1. Open the repository's **Actions** tab and choose **Daily CH-666 Generation** on `main`.
2. For a normal run, leave `video_only_story_code` blank; the workflow creates a new story and its illustrations. To retry videos for an existing story without generating a new story or illustrations, enter its code (for example, `CH-999-0013`).

For a normal manual run, the workflow generates and syncs the story and illustrations before the video job starts. A video-only run reads the existing story JSON and skips story and illustration generation. Scheduled runs do not create videos. Starting the workflow is the point at which Agnes may be called and account usage may be charged; no workflow is started by editing these files.

## Keyframes

Scheduled runs create two illustrations per story (`_cover`, `_scene`). Manual runs (`SCENE_IMAGE_COUNT=3`) also create `_scene_open` and `_scene_end`, so the three clips start from three different moments: opening, escalation, ending. These two extra stills are not stored in the story JSON (the website keeps using `cover_image` and `scene_images` only). If they are missing, the video falls back to cover + scene.

The generation job hands its images to the video job as a workflow artifact (`story-images`), so a fresh story does not depend on the runner being able to download images from the website. A video-only retry for an older story has no artifact and downloads from the site instead, using a browser User-Agent and following same-host redirects.

## If the video fails

The video job is allowed to fail without blocking the story, so look at the **Generate and upload videos** step log and the job summary. The error is printed as one line:

- `HTTP 403 ... from <site>` or `not a valid image ... block page`: the website/CDN is refusing the GitHub runner. Use a normal run (images are passed as an artifact) or allow the runner in the site's firewall.
- `<model> failed for scene N: HTTPError: HTTP 4xx <body>`: Agnes rejected the request; the body says why (key, credit, unsupported field). The pipeline then uses FFmpeg for the remaining scenes. Agnes gets 30 minutes in total (`AGNES_VIDEO_BUDGET_SECONDS`).
- `FTP upload attempt N/3 failed`: check `VFTP_HOST`, `VFTP_USER`, `VFTP_PASS` and that the FTP root is the `video/` folder.
- `Missing GitHub Secrets: VFTP_...`: add the secrets in the repository settings.
- Scheduled runs never render videos; only manual runs do.

Offline tests (no network or keys needed): `python -m unittest discover -s tests -v`.

## Identifiers and published files

Each story receives a sequential code such as `CH-666-0001`. The JSON, `<story_code>_cover.webp`, `<story_code>_scene.webp`, video folder, and manifest all use that same code. The video folder contains `scene-01.webm` through `scene-03.webm`, matching `scene-01.webp` through `scene-03.webp`, and `manifest.json`. Scene numbers and `insert_after_paragraph` values are written into the manifest.

VFTP's login root is already the `video/` folder, so the uploader creates `<story_code>/` below it. The website should serve the resulting manifest at `/video/<story_code>/manifest.json`.

## Required GitHub secrets

Story and illustration generation needs `NVIDIA_API_KEY`, `AGNES_API_KEY`, `FTP_HOST`, `FTP_USER`, `FTP_PASS`, `FTP_PATH`, and `SITE_URL`. The existing Serv00 sync needs `SERV00_UPDATE_URL` and `SERV00_UPDATE_TOKEN`. Video upload needs `VFTP_HOST`, `VFTP_USER`, and `VFTP_PASS`. Agnes video generation uses the existing `AGNES_API_KEY`; it is optional for the video job, which falls back to FFmpeg if the key is absent. The video job itself does not need `SITE_URL`.

Only the manual Actions workflow generates and uploads video. This change does not start a workflow, call Agnes, connect to FTP, or deploy anything.
