#!/usr/bin/env python3
"""Orchestrate the story-video pipeline; generation and FTP upload are opt-in."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> int:
    result = subprocess.run(command, check=False)
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("story_json", type=Path, help="existing story JSON; read-only")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--generate", action="store_true", help="render WebM/WebP clips from existing story illustrations")
    parser.add_argument("--upload", action="store_true", help="upload media and manifest to VFTP")
    args = parser.parse_args()

    try:
        story = json.loads(args.story_json.read_text(encoding="utf-8"))
        story_code = story.get("story_code") if isinstance(story, dict) else None
        if not isinstance(story_code, str):
            raise ValueError("story JSON must contain story_code")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = args.output_dir / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("story_code") != story_code:
                raise ValueError("output manifest belongs to a different story; choose another output directory")
            result = run([sys.executable, str(ROOT / "scripts/story_video.py"), "check", str(manifest_path)])
        else:
            result = run([
                sys.executable, str(ROOT / "scripts/story_video.py"), "plan",
                str(args.story_json), "--output", str(manifest_path),
            ])
        if result:
            return result

        generator = [
            sys.executable, str(ROOT / "scripts/generate_story_videos.py"),
            str(manifest_path), "--story-json", str(args.story_json), "--output-dir", str(args.output_dir),
        ]
        if args.generate:
            generator.append("--execute")
        result = run(generator)
        if result:
            return result

        if args.upload:
            uploader = [
                sys.executable, str(ROOT / "scripts/upload_story_video.py"),
                story_code, "--input-dir", str(args.output_dir), "--execute",
            ]
            return run(uploader)

        assets = [args.output_dir / f"scene-{i:02d}.{ext}"
                  for i in range(1, 4) for ext in ("webm", "webp")]
        if all(path.is_file() and path.stat().st_size > 0 for path in assets):
            return run([
                sys.executable, str(ROOT / "scripts/upload_story_video.py"),
                story_code, "--input-dir", str(args.output_dir),
            ])
        print("Upload preview skipped: media files are not generated yet. Add --upload only after reviewing the generated assets.")
        print("No illustration animation or FTP upload was performed." if not args.generate else "No FTP upload was performed.")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
