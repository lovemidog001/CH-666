#!/usr/bin/env python3
"""Generate story clips with Agnes image-to-video, then fall back to FFmpeg animation."""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

import requests
from PIL import Image

WIDTH = 1280
HEIGHT = 720
FPS = 24
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_VIDEO_BYTES = 200 * 1024 * 1024
AGNES_API = "https://apihub.agnes-ai.com"
VIDEO_MODELS = ("agnes-video-2.5", "agnes-video-2.5-flash")
POLL_INTERVAL_SECONDS = 10
MODEL_TIMEOUT_SECONDS = 8 * 60


def load_manifest(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("scenes"), list) or len(data["scenes"]) != 3:
        raise ValueError("manifest must contain exactly three scenes")
    for index, scene in enumerate(data["scenes"], start=1):
        if not isinstance(scene, dict):
            raise ValueError(f"scene {index} must be an object")
        if scene.get("scene") != index:
            raise ValueError("scene numbers must be ordered 1, 2, 3")
        if not isinstance(scene.get("prompt"), str) or not scene["prompt"].strip():
            raise ValueError(f"scene {index} is missing its story scene description")
        duration = scene.get("duration_seconds", 6)
        if isinstance(duration, bool) or not isinstance(duration, int) or not 4 <= duration <= 8:
            raise ValueError("scene duration_seconds must be an integer from 4 to 8")
    return data


def image_url(value: object, story_code: str, kind: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"story is missing its {kind} illustration")
    value = value.strip()
    candidate = urlsplit(value)
    if candidate.scheme.lower() != "https" or not candidate.hostname:
        raise ValueError(f"{kind} illustration must use an absolute HTTPS URL")
    if candidate.username or candidate.password or candidate.query or candidate.fragment:
        raise ValueError(f"{kind} illustration URL must not contain credentials, a query, or a fragment")
    try:
        port = candidate.port
    except ValueError as exc:
        raise ValueError(f"{kind} illustration URL has an invalid port") from exc
    try:
        ipaddress.ip_address(candidate.hostname)
    except ValueError:
        pass
    else:
        raise ValueError(f"{kind} illustration URL must use a public hostname, not an IP address")
    if port not in (None, 443) or "." not in candidate.hostname or candidate.hostname.lower().endswith((".localhost", ".local")):
        raise ValueError(f"{kind} illustration URL must use a public HTTPS hostname")
    expected_path = f"/images/{story_code}_{kind}.webp"
    if unquote(candidate.path) != expected_path:
        raise ValueError(f"{kind} illustration URL must use the expected story image path")
    return value


def download_image(session: requests.Session, url: str, target: Path) -> None:
    with session.get(url, stream=True, timeout=60, allow_redirects=False) as response:
        response.raise_for_status()
        declared = response.headers.get("Content-Length")
        if declared and int(declared) > MAX_IMAGE_BYTES:
            raise ValueError("story illustration exceeds the 20 MB download limit")
        total = 0
        with target.open("wb") as output:
            for chunk in response.iter_content(chunk_size=256 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_IMAGE_BYTES:
                    raise ValueError("story illustration exceeds the 20 MB download limit")
                output.write(chunk)
    if total == 0:
        raise ValueError(f"empty illustration downloaded from {url}")
    with Image.open(target) as image:
        image.verify()


def find_video_url(value: object) -> str | None:
    if isinstance(value, dict):
        for key in ("video_url", "url"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.startswith("https://"):
                return candidate
        for key in ("video", "data", "result", "output", "results"):
            found = find_video_url(value.get(key))
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_video_url(item)
            if found:
                return found
    return None


def find_task_id(value: object) -> str | None:
    if isinstance(value, dict):
        for key in ("video_id", "request_id", "task_id", "id"):
            candidate = value.get(key)
            if isinstance(candidate, (str, int)) and str(candidate).strip():
                return str(candidate)
        for key in ("data", "result", "task"):
            found = find_task_id(value.get(key))
            if found:
                return found
    return None


def generate_with_agnes(
    session: requests.Session,
    api_key: str,
    model: str,
    prompt: str,
    source_url: str,
    duration: int,
) -> str:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "prompt": (
            f"{prompt.strip()}\n"
            "Animate this supplied story illustration as the first frame. Preserve the original "
            "characters, clothing, composition, and art style. Add restrained natural motion and "
            "subtle camera movement, with no cuts, no new characters, and no captions or text."
        ),
        "mode": "keyframe",
        "first_frame": source_url,
        "seconds": str(duration),
        "size": "720P",
        "aspect_ratio": "16:9",
        "n": 1,
    }
    response = session.post(
        f"{AGNES_API}/v1/videos", headers=headers, json=payload, timeout=(20, 90)
    )
    response.raise_for_status()
    result = response.json()
    video_url = find_video_url(result)
    if video_url:
        return video_url
    task_id = find_task_id(result)
    if not task_id:
        raise RuntimeError(f"{model} response did not contain a video URL or task ID")

    deadline = time.monotonic() + MODEL_TIMEOUT_SECONDS
    poll_url = f"{AGNES_API}/agnesapi"
    while time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL_SECONDS)
        try:
            poll = session.get(
                poll_url,
                headers={"Authorization": f"Bearer {api_key}"},
                params={"video_id": task_id, "model_name": model},
                timeout=(20, 60),
            )
            poll.raise_for_status()
            result = poll.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"{model} status check failed temporarily ({type(exc).__name__}); will retry.", flush=True)
            continue
        video_url = find_video_url(result)
        if video_url:
            return video_url
        status = ""
        if isinstance(result, dict):
            status_value = result.get("status")
            nested = result.get("data")
            if not status_value and isinstance(nested, dict):
                status_value = nested.get("status")
            status = str(status_value or "").lower()
        if status in {"failed", "error", "expired", "cancelled", "canceled"}:
            raise RuntimeError(f"{model} generation ended with status {status}")
    raise TimeoutError(f"{model} generation did not finish within {MODEL_TIMEOUT_SECONDS // 60} minutes")


def download_generated_video(session: requests.Session, url: str, target: Path) -> None:
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Agnes returned a video URL that is not a valid HTTPS URL")
    total = 0
    with session.get(url, stream=True, timeout=(20, 120), allow_redirects=True) as response:
        response.raise_for_status()
        final_url = urlsplit(response.url)
        if final_url.scheme.lower() != "https":
            raise ValueError("Agnes video download redirected away from HTTPS")
        declared = response.headers.get("Content-Length")
        if declared and int(declared) > MAX_VIDEO_BYTES:
            raise ValueError("generated video exceeds the 200 MB download limit")
        with target.open("wb") as output:
            for chunk in response.iter_content(chunk_size=512 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_VIDEO_BYTES:
                    raise ValueError("generated video exceeds the 200 MB download limit")
                output.write(chunk)
    if total == 0:
        raise ValueError("Agnes returned an empty video file")


def add_crt_filter(input_path: Path, webm: Path, poster: Path) -> None:
    vf = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,"
        "eq=contrast=1.06:saturation=0.86:brightness=-0.008,"
        "noise=alls=2:allf=t,drawgrid=w=iw:h=4:t=1:c=black@0.18,"
        "vignette=PI/5,format=yuv420p"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(input_path), "-vf", vf, "-an",
         "-c:v", "libvpx-vp9", "-deadline", "good", "-cpu-used", "4",
         "-crf", "32", "-b:v", "0", "-row-mt", "1", "-pix_fmt", "yuv420p",
         str(webm)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    create_poster(webm, poster)


def create_poster(webm: Path, poster: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-ss", "1", "-i", str(webm), "-frames:v", "1",
         "-c:v", "libwebp", "-quality", "82", str(poster)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    if not webm.is_file() or webm.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg did not create a valid WebM file: {webm.name}")
    if not poster.is_file() or poster.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg did not create a valid WebP poster: {poster.name}")


def render_scene(source: Path, webm: Path, poster: Path, duration: int, scene_number: int) -> None:
    frames = duration * FPS
    drift = (scene_number - 1) * 5 + 8
    vf = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},"
        f"zoompan=z='min(zoom+0.0008,1.12)':"
        f"x='iw/2-(iw/zoom/2)+sin(on/38)*{drift}':"
        f"y='ih/2-(ih/zoom/2)+cos(on/47)*{drift / 2}':"
        f"d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS},"
        "eq=contrast=1.10:saturation=0.78:brightness=-0.015,"
        "noise=alls=4:allf=t,drawgrid=w=iw:h=4:t=1:c=black@0.24,"
        "vignette=PI/5,format=yuv420p"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-loop", "1", "-i", str(source), "-vf", vf,
         "-frames:v", str(frames), "-an", "-c:v", "libvpx-vp9",
         "-deadline", "good", "-cpu-used", "4", "-crf", "34", "-b:v", "0",
         "-row-mt", "1", "-pix_fmt", "yuv420p", str(webm)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    create_poster(webm, poster)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--story-json", type=Path, help="existing story JSON containing cover and scene illustration URLs")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--execute", action="store_true", help="generate video clips; otherwise print the plan only")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--public-video-root", default="/video", help="public URL path where the VFTP video/ directory is served")
    args = parser.parse_args()

    try:
        manifest = load_manifest(args.manifest)
        plan = [{"scene": s["scene"], "seconds": s.get("duration_seconds", 6),
                 "insert_after_paragraph": s["insert_after_paragraph"], "alt": s["alt"]}
                for s in manifest["scenes"]]
        if not args.execute:
            print(json.dumps({"mode": "agnes-image-to-video-with-ffmpeg-fallback",
                              "output_dir": str(args.output_dir), "scenes": plan}, ensure_ascii=False, indent=2))
            return 0

        if not args.story_json:
            raise ValueError("--story-json is required to generate clips from story illustrations")
        if not shutil.which("ffmpeg"):
            raise ValueError("ffmpeg is required to encode WebM clips and WebP posters")
        story = json.loads(args.story_json.read_text(encoding="utf-8"))
        if not isinstance(story, dict) or story.get("story_code") != manifest.get("story_code"):
            raise ValueError("story JSON and manifest story_code do not match")
        if args.timeout <= 0:
            raise ValueError("timeout must be positive")

        image_candidates = [
            ("cover", story.get("cover_image")),
            ("scene", story.get("scene_images")),
        ]
        urls = [
            (kind, image_url(value, manifest["story_code"], kind))
            for kind, value in image_candidates if isinstance(value, str) and value.strip()
        ]
        if not urls:
            raise ValueError("story has no generated cover or scene illustration to animate")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        public_dir = args.public_video_root.rstrip("/") + "/" + manifest["story_code"]
        api_key = os.getenv("AGNES_API_KEY", "").strip()
        if not api_key:
            print("AGNES_API_KEY is not configured; using FFmpeg illustration animation for all scenes.", flush=True)

        with tempfile.TemporaryDirectory(prefix="story-video-source-") as temp_name:
            temp_dir = Path(temp_name)
            sources: list[tuple[Path, str]] = []
            with requests.Session() as session:
                for index, (kind, url) in enumerate(urls, start=1):
                    image_path = temp_dir / f"source-{kind}-{index}.webp"
                    download_image(session, url, image_path)
                    sources.append((image_path, url))

                for scene in manifest["scenes"]:
                    number = scene["scene"]
                    duration = scene.get("duration_seconds", 6)
                    source, source_url = sources[(number - 1) % len(sources)]
                    webm_path = args.output_dir / f"scene-{number:02d}.webm"
                    poster_path = args.output_dir / f"scene-{number:02d}.webp"
                    generated = False

                    if api_key:
                        for model in VIDEO_MODELS:
                            try:
                                print(f"Generating scene {number}/3 ({duration}s) with {model}...", flush=True)
                                remote_url = generate_with_agnes(
                                    session, api_key, model, scene["prompt"], source_url, duration
                                )
                                raw_path = temp_dir / f"agnes-scene-{number:02d}.mp4"
                                download_generated_video(session, remote_url, raw_path)
                                add_crt_filter(raw_path, webm_path, poster_path)
                                print(f"Scene {number}/3 generated with {model}.", flush=True)
                                generated = True
                                break
                            except (requests.RequestException, ValueError, RuntimeError, TimeoutError,
                                    subprocess.CalledProcessError) as exc:
                                print(f"{model} unavailable for scene {number}: {type(exc).__name__}; trying next option.", flush=True)

                    if not generated:
                        print(f"Using FFmpeg animated illustration for scene {number}/3 ({duration}s).", flush=True)
                        render_scene(source, webm_path, poster_path, duration, number)

                    scene["status"] = "ready"
                    scene["video_url"] = f"{public_dir}/{webm_path.name}"
                    scene["poster_url"] = f"{public_dir}/{poster_path.name}"
                    (args.output_dir / "manifest.json").write_text(
                        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                    )

        print(f"Prepared 3 WebM clips and 3 WebP posters; manifest.json is in {args.output_dir}")
        return 0
    except (OSError, ValueError, RuntimeError, TimeoutError, requests.RequestException,
            subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
