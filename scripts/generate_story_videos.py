#!/usr/bin/env python3
"""Render three story clips from existing WebP illustrations; dry-run is the default."""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

import requests
from PIL import Image

WIDTH = 1280
HEIGHT = 720
FPS = 24
MAX_IMAGE_BYTES = 20 * 1024 * 1024


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
        "noise=alls=4:allf=t,"
        "drawgrid=w=iw:h=4:t=1:c=black@0.24,"
        "vignette=PI/5,format=yuv420p"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-loop", "1", "-i", str(source), "-vf", vf,
         "-frames:v", str(frames), "-an", "-c:v", "libvpx-vp9",
         "-deadline", "good", "-cpu-used", "4", "-crf", "34", "-b:v", "0",
         "-row-mt", "1", "-pix_fmt", "yuv420p", str(webm)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-ss", "1", "-i", str(webm), "-frames:v", "1",
         "-c:v", "libwebp", "-quality", "82", str(poster)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    if not webm.is_file() or webm.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg did not create a valid WebM file: {webm.name}")
    if not poster.is_file() or poster.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg did not create a valid WebP poster: {poster.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--story-json", type=Path, help="existing story JSON containing cover and scene illustration URLs")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--execute", action="store_true", help="render WebM clips from story illustrations; otherwise print the plan only")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--public-video-root", default="/video", help="public URL path where the VFTP video/ directory is served")
    args = parser.parse_args()

    try:
        manifest = load_manifest(args.manifest)
        plan = [{"scene": s["scene"], "seconds": s.get("duration_seconds", 6),
                 "insert_after_paragraph": s["insert_after_paragraph"], "alt": s["alt"]}
                for s in manifest["scenes"]]
        if not args.execute:
            print(json.dumps({"mode": "illustration-animation-preview",
                              "output_dir": str(args.output_dir), "scenes": plan},
                             ensure_ascii=False, indent=2))
            return 0

        if not args.story_json:
            raise ValueError("--story-json is required to render from the story illustrations")
        if not shutil.which("ffmpeg"):
            raise ValueError("ffmpeg is required to render WebM clips and WebP posters")
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
        with tempfile.TemporaryDirectory(prefix="story-video-source-") as temp_name:
            temp_dir = Path(temp_name)
            sources = []
            with requests.Session() as session:
                for index, (kind, url) in enumerate(urls, start=1):
                    image_path = temp_dir / f"source-{kind}-{index}.webp"
                    download_image(session, url, image_path)
                    sources.append(image_path)
            for scene in manifest["scenes"]:
                number = scene["scene"]
                duration = scene.get("duration_seconds", 6)
                source = sources[(number - 1) % len(sources)]
                print(f"Rendering scene {number}/3 ({duration}s) from story illustration with CRT effects...", flush=True)
                webm_path = args.output_dir / f"scene-{number:02d}.webm"
                poster_path = args.output_dir / f"scene-{number:02d}.webp"
                render_scene(source, webm_path, poster_path, duration, number)
                scene["status"] = "ready"
                scene["video_url"] = f"{public_dir}/{webm_path.name}"
                scene["poster_url"] = f"{public_dir}/{poster_path.name}"
                (args.output_dir / "manifest.json").write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
        print(f"Rendered 3 WebM clips and 3 WebP posters from the existing illustrations; manifest.json is in {args.output_dir}")
        print("No video-generation AI API was called.")
        return 0
    except (OSError, ValueError, RuntimeError, requests.RequestException,
            subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
