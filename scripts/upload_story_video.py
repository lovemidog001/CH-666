#!/usr/bin/env python3
"""Upload three generated WebM/WebP story clips and their manifest to VFTP."""
from __future__ import annotations

import argparse
import ftplib
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ASSETS = [f"scene-{i:02d}.{ext}" for i in range(1, 4) for ext in ("webm", "webp")]


def is_public_asset_url(value: object, story_code: str, filename: str) -> bool:
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    if any(ord(char) < 32 or char.isspace() for char in value):
        return False
    try:
        parsed = urlsplit(value)
        if parsed.scheme:
            if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
                return False
            parsed.port  # Force validation of malformed ports.
        elif parsed.netloc or parsed.query or parsed.fragment or not (parsed.path.startswith("/") or parsed.path.startswith("video/")):
            return False
        path = unquote(parsed.path)
    except (ValueError, UnicodeError):
        return False
    if any(part in {".", ".."} for part in path.split("/")):
        return False
    return path.endswith(f"/{story_code}/{filename}")


def validate_manifest(manifest: object, story_code: str) -> list[str]:
    if not isinstance(manifest, dict):
        return ["manifest must be a JSON object"]
    if manifest.get("schema_version") != 1:
        return ["manifest schema_version must be 1"]
    if manifest.get("story_code") != story_code:
        return ["manifest story_code does not match upload"]
    scenes = manifest.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != 3:
        return ["manifest must contain exactly three scenes"]
    errors = []
    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            errors.append(f"scene {index} must be an object")
            continue
        if scene.get("scene") != index:
            errors.append("manifest scenes must be ordered 1, 2, 3")
        if scene.get("status") != "ready":
            errors.append(f"scene {index} is not ready")
        if not is_public_asset_url(scene.get("video_url"), story_code, f"scene-{index:02d}.webm"):
            errors.append(f"scene {index} video_url must point to its public WebM file")
        if not is_public_asset_url(scene.get("poster_url"), story_code, f"scene-{index:02d}.webp"):
            errors.append(f"scene {index} poster_url must point to its public WebP file")
    return errors


def has_media_signature(path: Path, extension: str) -> bool:
    try:
        with path.open("rb") as media:
            header = media.read(12)
    except OSError:
        return False
    if extension == ".webm":
        return header.startswith(b"\x1aE\xdf\xa3")
    if extension == ".webp":
        return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("story_code")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, help="manifest.json to upload with the media")
    parser.add_argument("--execute", action="store_true", help="perform FTP upload")
    args = parser.parse_args()

    if not re.fullmatch(r"CH-(?:333|666|999)-\d{4}", args.story_code):
        print("error: invalid story code", file=sys.stderr)
        return 2

    missing = [name for name in ASSETS if not (args.input_dir / name).is_file() or (args.input_dir / name).stat().st_size == 0]
    if missing:
        print("error: missing or empty assets: " + ", ".join(missing), file=sys.stderr)
        return 2
    invalid = [name for name in ASSETS if not has_media_signature(args.input_dir / name, Path(name).suffix)]
    if invalid:
        print("error: invalid WebM/WebP file signature: " + ", ".join(invalid), file=sys.stderr)
        return 2

    manifest_path = args.manifest or (args.input_dir / "manifest.json")
    if not manifest_path.is_file():
        print("error: manifest.json is required; refusing to upload unindexed clips", file=sys.stderr)
        return 2
    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: invalid manifest: {exc}", file=sys.stderr)
        return 2
    errors = validate_manifest(manifest_data, args.story_code)
    if errors:
        for error in errors:
            print("error: " + error, file=sys.stderr)
        return 2

    print("Mode: " + ("UPLOAD" if args.execute else "DRY RUN"))
    print(f"Remote folder: video/{args.story_code}/ (FTP login root is already video/)")
    for name in ASSETS:
        print(f"{args.input_dir / name} -> {args.story_code}/{name}")
    print(f"{manifest_path} -> {args.story_code}/manifest.json")
    if not args.execute:
        return 0

    host, user, password = (os.environ.get(key) for key in ("VFTP_HOST", "VFTP_USER", "VFTP_PASS"))
    if not all((host, user, password)):
        print("error: VFTP_HOST, VFTP_USER and VFTP_PASS are required", file=sys.stderr)
        return 2
    try:
        with ftplib.FTP(host, timeout=30) as ftp:
            ftp.login(user, password)
            try:
                ftp.mkd(args.story_code)
            except ftplib.error_perm as exc:
                if not str(exc).startswith("550"):
                    raise
            ftp.cwd(args.story_code)
            for name in ASSETS:
                with (args.input_dir / name).open("rb") as source:
                    ftp.storbinary(f"STOR {name}", source)
            with manifest_path.open("rb") as source:
                ftp.storbinary("STOR manifest.json", source)
        print("Upload complete.")
        return 0
    except (OSError, ftplib.Error) as exc:
        print(f"error: FTP upload failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
