#!/usr/bin/env python3
"""Create and validate sidecar manifests for optional story video scenes.

This tool does not call an AI provider, upload files, modify story JSON, or deploy anything.
The video pipeline renders clips from existing story illustrations with FFmpeg.
"""
from __future__ import annotations

import argparse
import json
from html.parser import HTMLParser
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

SCHEMA_VERSION = 1
SCENE_COUNT = 3
DEFAULT_DURATIONS = (6, 6, 6)
DEFAULT_INSERT_AFTER = (2, 5, 8)
STATUSES = {"planned", "generating", "ready", "failed"}


def _is_safe_asset_url(value: str, extension: str) -> bool:
    """Allow HTTPS CDN URLs or safe site-relative paths with the expected extension."""
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    if any(ord(char) < 32 or char.isspace() for char in value):
        return False

    parsed = urlparse(value)
    if parsed.scheme:
        # Remote assets must be HTTPS, have a hostname, and contain no userinfo.
        if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
            return False
        try:
            port = parsed.port
        except ValueError:
            return False
        if port is not None and not 1 <= port <= 65535:
            return False
        asset_path = parsed.path
    else:
        # Relative assets must be site-rooted or live under assets/, never protocol-relative.
        if parsed.netloc or parsed.query or parsed.fragment or value.startswith("//"):
            return False
        asset_path = parsed.path
        if not (asset_path.startswith("/") or asset_path.startswith("assets/")):
            return False

    # Reject traversal and encoded traversal in path segments.
    from urllib.parse import unquote
    decoded_path = unquote(asset_path)
    if any(part in {".", ".."} for part in decoded_path.split("/")):
        return False
    return Path(decoded_path).suffix.lower() == extension


def build_manifest(story_code: str) -> dict:
    """Build a sidecar manifest template; no media is generated or uploaded."""
    if not re.fullmatch(r"CH-(?:333|666|999)-\d{4}", story_code):
        raise ValueError("story_code must look like CH-666-0001")
    scenes = []
    for index in range(SCENE_COUNT):
        scenes.append({
            "scene": index + 1,
            "insert_after_paragraph": DEFAULT_INSERT_AFTER[index],
            "duration_seconds": DEFAULT_DURATIONS[index],
            "status": "planned",
            "prompt": "",
            "video_url": "",
            "poster_url": "",
            "alt": f"故事場景 {index + 1}",
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "story_code": story_code,
        "media_format": "webm",
        "poster_format": "webp",
        "scenes": scenes,
    }


def validate_manifest(manifest: object) -> list[str]:
    """Return validation errors for a story-video sidecar manifest."""
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest must be a JSON object"]
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    story_code = manifest.get("story_code")
    if not isinstance(story_code, str) or not re.fullmatch(r"CH-(?:333|666|999)-\d{4}", story_code):
        errors.append("story_code must look like CH-666-0001")
    if manifest.get("media_format") != "webm":
        errors.append("media_format must be webm")
    if manifest.get("poster_format") != "webp":
        errors.append("poster_format must be webp")

    scenes = manifest.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != SCENE_COUNT:
        errors.append(f"scenes must contain exactly {SCENE_COUNT} entries")
        return errors

    seen = set()
    for index, scene in enumerate(scenes, start=1):
        prefix = f"scenes[{index - 1}]"
        if not isinstance(scene, dict):
            errors.append(f"{prefix} must be an object")
            continue
        number = scene.get("scene")
        if number not in (1, 2, 3):
            errors.append(f"{prefix}.scene must be 1, 2, or 3")
        elif number in seen:
            errors.append(f"duplicate scene number: {number}")
        else:
            seen.add(number)

        paragraph = scene.get("insert_after_paragraph")
        if not isinstance(paragraph, int) or isinstance(paragraph, bool) or paragraph < 1:
            errors.append(f"{prefix}.insert_after_paragraph must be a positive integer")

        duration = scene.get("duration_seconds")
        if not isinstance(duration, int) or isinstance(duration, bool) or not 4 <= duration <= 8:
            errors.append(f"{prefix}.duration_seconds must be an integer from 4 to 8")

        status = scene.get("status")
        if status not in STATUSES:
            errors.append(f"{prefix}.status must be one of: {', '.join(sorted(STATUSES))}")

        for field in ("prompt", "alt"):
            if not isinstance(scene.get(field), str):
                errors.append(f"{prefix}.{field} must be a string")

        video_url = scene.get("video_url", "")
        poster_url = scene.get("poster_url", "")
        if not isinstance(video_url, str) or not isinstance(poster_url, str):
            errors.append(f"{prefix}.video_url and poster_url must be strings")
            continue
        if status == "ready":
            if not _is_safe_asset_url(video_url, ".webm"):
                errors.append(f"{prefix}.video_url must be an HTTPS or relative .webm asset URL when ready")
            if not _is_safe_asset_url(poster_url, ".webp"):
                errors.append(f"{prefix}.poster_url must be an HTTPS or relative .webp asset URL when ready")
        else:
            if video_url and not _is_safe_asset_url(video_url, ".webm"):
                errors.append(f"{prefix}.video_url must be empty or an HTTPS/relative .webm asset URL")
            if poster_url and not _is_safe_asset_url(poster_url, ".webp"):
                errors.append(f"{prefix}.poster_url must be empty or an HTTPS/relative .webp asset URL")
    return errors



class _ParagraphExtractor(HTMLParser):
    """Extract readable paragraph text from the story's HTML content."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.paragraphs = []
        self._depth = 0
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "p":
            if self._depth == 0:
                self._parts = []
            self._depth += 1

    def handle_endtag(self, tag):
        if tag.lower() == "p" and self._depth:
            self._depth -= 1
            if self._depth == 0:
                text = re.sub(r"\s+", " ", "".join(self._parts)).strip()
                if text:
                    self.paragraphs.append(text)

    def handle_data(self, data):
        if self._depth:
            self._parts.append(data)


def _story_paragraphs(content: str) -> list[str]:
    """Return non-empty paragraph text from a story's HTML content."""
    parser = _ParagraphExtractor()
    parser.feed(content if isinstance(content, str) else "")
    parser.close()
    return parser.paragraphs


def build_story_manifest(story: object) -> dict:
    """Create three scene prompts from an existing story JSON object, without AI calls."""
    if not isinstance(story, dict):
        raise ValueError("story JSON must be an object")
    story_code = story.get("story_code")
    manifest = build_manifest(story_code) if isinstance(story_code, str) else None
    if manifest is None:
        raise ValueError("story JSON must contain a valid story_code")
    title = story.get("title")
    summary = story.get("summary")
    paragraphs = _story_paragraphs(story.get("content", ""))
    if not isinstance(title, str) or not title.strip():
        raise ValueError("story JSON must contain a non-empty title")
    if len(paragraphs) < SCENE_COUNT:
        raise ValueError("story JSON content must contain at least three non-empty HTML paragraphs")

    # Pick paragraph anchors spread across the story, preserving their source order.
    count = len(paragraphs)
    anchors = sorted({max(1, min(count, round(count * fraction))) for fraction in (0.2, 0.55, 0.9)})
    while len(anchors) < SCENE_COUNT:
        for candidate in range(1, count + 1):
            if candidate not in anchors:
                anchors.append(candidate)
                anchors.sort()
                if len(anchors) == SCENE_COUNT:
                    break
    anchors = anchors[:SCENE_COUNT]
    scene_roles = (
        ("ESTABLISHING SHOT", "Build dread through an ordinary location before the anomaly becomes clear."),
        ("ESCALATING ANOMALY", "Show one unsettling, story-grounded detail that violates normal reality."),
        ("CLIMACTIC REVEAL", "End on the most disturbing implication supported by the selected passage; do not invent a new plot event."),
    )
    for scene, anchor, (role, direction) in zip(manifest["scenes"], anchors, scene_roles):
        excerpt = paragraphs[anchor - 1][:420]
        scene["insert_after_paragraph"] = anchor
        scene["alt"] = f"{title.strip()}：場景 {scene['scene']}"
        scene["prompt"] = (
            f"Create a 6-second cinematic analog-horror shot for the story \"{title.strip()}\". "
            f"Scene role: {role}. Story excerpt: \"{excerpt}\". {direction} "
            "Visual style: realistic Taiwanese night-time setting, muted colors, practical lighting, "
            "subtle VHS scanlines and tape noise, slow deliberate camera movement, oppressive atmosphere. "
            "No subtitles, no readable text, no logos, no gore, 16:9 composition. "
            "Keep character and location details consistent with the excerpt."
        )
    manifest["story_title"] = title.strip()
    manifest["story_summary"] = summary.strip() if isinstance(summary, str) else ""
    return manifest

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="write a blank three-scene manifest")
    init_parser.add_argument("story_code", help="e.g. CH-666-0001")
    init_parser.add_argument("--output", required=True, help="sidecar JSON output path")

    check_parser = subparsers.add_parser("check", help="validate an existing manifest")
    check_parser.add_argument("manifest", help="path to manifest JSON")

    plan_parser = subparsers.add_parser("plan", help="create three scene prompts from a story JSON file")
    plan_parser.add_argument("story_json", help="path to an existing story JSON file")
    plan_parser.add_argument("--output", required=True, help="new manifest output path; existing files are never overwritten")

    args = parser.parse_args()
    if args.command == "init":
        try:
            manifest = build_manifest(args.story_code)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        output = Path(args.output)
        if output.exists():
            print(f"ERROR: refusing to overwrite existing file: {output}", file=sys.stderr)
            return 2
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Created template: {output}")
        print("This template command did not call AI APIs, FTP, or deployment.")
        return 0

    if args.command == "plan":
        try:
            story = json.loads(Path(args.story_json).read_text(encoding="utf-8"))
            manifest = build_story_manifest(story)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"ERROR: cannot plan story: {exc}", file=sys.stderr)
            return 2
        output = Path(args.output)
        if output.exists():
            print(f"ERROR: refusing to overwrite existing file: {output}", file=sys.stderr)
            return 2
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Created three-scene plan: {output}")
        print("The next step renders clips from existing illustrations with FFmpeg; no video-generation API is called.")
        return 0

    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read valid JSON: {exc}", file=sys.stderr)
        return 2
    errors = validate_manifest(manifest)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: {manifest['story_code']} has a valid three-scene video manifest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
