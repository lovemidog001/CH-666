# Story, illustration and video pipeline

The feature branch runs one workflow: `.github/workflows/daily-generation.yml`. A manual run generates one story and its WebP illustrations, then animates those still illustrations into three WebM clips and uploads them to VFTP. Video rendering uses FFmpeg and does not call a video-generation API.

## Manual run

1. Open the repository's **Actions** tab and choose **Daily CH-666 Generation**.
2. Choose `feature/story-video-pipeline` in the branch selector.
3. For a normal run, leave `video_only_story_code` blank; the workflow creates a new story and its illustrations. To render clips for an existing story without generating a new story or illustrations, enter its code (for example, `CH-999-0013`).

For a normal manual run, the workflow generates and syncs the story and illustrations, then creates three subtle pan/zoom clips with CRT scanlines and noise using FFmpeg. The existing cover and scene illustrations are used as source images. A video-only run reads the existing story JSON and skips story and illustration generation. This video-rendering step uses no video API and adds no video-generation charge; story and illustration generation may still use their existing paid APIs. The workflow is limited to the feature branch. Scheduled runs do not create videos.

## Identifiers and published files

Each story receives a sequential code such as `CH-666-0001`. The JSON, `<story_code>_cover.webp`, `<story_code>_scene.webp`, video folder, and manifest all use that same code. The video folder contains `scene-01.webm` through `scene-03.webm`, matching `scene-01.webp` through `scene-03.webp`, and `manifest.json`. Scene numbers and `insert_after_paragraph` values are written into the manifest.

VFTP's login root is already the `video/` folder, so the uploader creates `<story_code>/` below it. The website should serve the resulting manifest at `/video/<story_code>/manifest.json`.

## Required GitHub secrets

Story and illustration generation needs `NVIDIA_API_KEY`, `AGNES_API_KEY`, `FTP_HOST`, `FTP_USER`, `FTP_PASS`, `FTP_PATH`, and `SITE_URL`. The existing Serv00 sync needs `SERV00_UPDATE_URL` and `SERV00_UPDATE_TOKEN`. Video rendering uses the HTTPS image URLs saved in the story JSON. Video upload needs `VFTP_HOST`, `VFTP_USER`, and `VFTP_PASS`; the video job does not need `SITE_URL` or `AGNES_API_KEY`.

Generation and upload run only after you manually start the workflow on `feature/story-video-pipeline`. No workflow was started while making these changes.
