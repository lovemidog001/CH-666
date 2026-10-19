# Story, illustration and video pipeline

A manual run creates a story and its WebP illustrations first. The separate video job then tries to turn each illustration into a moving clip with Agnes Video 2.5. If that model fails, it tries Agnes Video 2.5 Flash. If both attempts fail, or `AGNES_API_KEY` is not configured, FFmpeg creates the existing pan/zoom illustration animation with the CRT look. Each clip is encoded as WebM and gets a WebP poster for the website.

Video generation is optional: the video job uses `continue-on-error`, so a video provider outage does not undo or block the story and illustration publication. The Agnes 2.5 model may incur charges according to the account's current plan and rates. Flash availability and pricing can change; check Agnes before running the workflow. The pipeline does not call xAI/Grok.

## Manual run

1. Open the repository's **Actions** tab and choose **Daily CH-666 Generation** on `main`.
2. For a normal run, leave `video_only_story_code` blank; the workflow creates a new story and its illustrations. To retry videos for an existing story without generating a new story or illustrations, enter its code (for example, `CH-999-0013`).

For a normal manual run, the workflow generates and syncs the story and illustrations before the video job starts. A video-only run reads the existing story JSON and skips story and illustration generation. Scheduled runs do not create videos. Starting the workflow is the point at which Agnes may be called and account usage may be charged; no workflow is started by editing these files.

## Identifiers and published files

Each story receives a sequential code such as `CH-666-0001`. The JSON, `<story_code>_cover.webp`, `<story_code>_scene.webp`, video folder, and manifest all use that same code. The video folder contains `scene-01.webm` through `scene-03.webm`, matching `scene-01.webp` through `scene-03.webp`, and `manifest.json`. Scene numbers and `insert_after_paragraph` values are written into the manifest.

VFTP's login root is already the `video/` folder, so the uploader creates `<story_code>/` below it. The website should serve the resulting manifest at `/video/<story_code>/manifest.json`.

## Required GitHub secrets

Story and illustration generation needs `NVIDIA_API_KEY`, `AGNES_API_KEY`, `FTP_HOST`, `FTP_USER`, `FTP_PASS`, `FTP_PATH`, and `SITE_URL`. The existing Serv00 sync needs `SERV00_UPDATE_URL` and `SERV00_UPDATE_TOKEN`. Video upload needs `VFTP_HOST`, `VFTP_USER`, and `VFTP_PASS`. Agnes video generation uses the existing `AGNES_API_KEY`; it is optional for the video job, which falls back to FFmpeg if the key is absent. The video job itself does not need `SITE_URL`.

Only the manual Actions workflow generates and uploads video. This change does not start a workflow, call Agnes, connect to FTP, or deploy anything.
