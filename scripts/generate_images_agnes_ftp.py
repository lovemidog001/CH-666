#!/usr/bin/env python3
"""
ODDITY HUB / CH-666 - 圖片生成並 FTP 上傳到 Serv00
使用 Agnes Image 2.5 Flash (OpenAI 兼容 API) 生成 → 轉 WebP → FTP 上傳
失敗時拋出異常，不靜默返回空字串
"""

import os
import sys
import json
import argparse
import ftplib
import requests
import base64
from io import BytesIO
from pathlib import Path
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent))

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False
    print("WARNING: Pillow not installed, skipping WebP compression")


AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"
IMAGE_MODEL = "agnes-image-2.5-flash"

HEADERS = {
    "Authorization": f"Bearer {AGNES_API_KEY}",
    "Content-Type": "application/json"
} if AGNES_API_KEY else {}


def generate_image_agnes(prompt: str, width: int = 1024, height: int = 1024, 
                         negative_prompt: str = "", model: str = IMAGE_MODEL) -> bytes:
    """呼叫 Agnes 圖像生成 API，回傳圖片 bytes；失敗拋出異常"""
    if not AGNES_API_KEY:
        raise RuntimeError("AGNES_API_KEY not set in environment")
    
    url = f"{AGNES_BASE_URL}/images/generations"
    payload = {
        "model": model,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "n": 1,
        "response_format": "b64_json",
        "quality": "high",
    }
    
    print(f"  📡 Calling Agnes API: {url}")
    print(f"     Model: {model}, Size: {width}x{height}")
    
    resp = requests.post(url, headers=HEADERS, json=payload, timeout=180)
    
    if resp.status_code != 200:
        raise RuntimeError(f"Agnes API HTTP {resp.status_code}: {resp.text}")
    
    data = resp.json()
    
    if "data" not in data or not data["data"] or "b64_json" not in data["data"][0]:
        raise RuntimeError(f"Agnes API unexpected response: {json.dumps(data)[:500]}")
    
    b64 = data["data"][0]["b64_json"]
    img_bytes = base64.b64decode(b64)
    print(f"  ✅ Agnes API success: {len(img_bytes)/1024:.1f} KB")
    return img_bytes


def compress_to_webp(img_bytes: bytes, max_dim: int = 1024, quality: int = 85) -> bytes:
    """壓縮轉 WebP"""
    if not HAS_PILLOW:
        print("  ⚠️ Pillow not available, skipping compression")
        return img_bytes
    try:
        img = Image.open(BytesIO(img_bytes))
        original_size = img.size
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
        out_buf = BytesIO()
        img.save(out_buf, format='WEBP', quality=quality, method=6)
        compressed = out_buf.getvalue()
        print(f"  🗜️ Compressed: {original_size} → {img.size}, {len(img_bytes)/1024:.1f} KB → {len(compressed)/1024:.1f} KB (WebP q{quality})")
        return compressed
    except Exception as e:
        print(f"  ⚠️ Compression failed: {e}, using original")
        return img_bytes


def upload_ftp(img_bytes: bytes, filename: str, ftp_config: Dict) -> str:
    """FTP 上傳，回傳公開 URL；失敗拋出異常"""
    ftp_host = ftp_config.get('ftp_host', 's13.serv00.com')
    ftp_user = ftp_config.get('ftp_user', 'f3459_666')
    ftp_pass = ftp_config.get('ftp_pass')
    ftp_path = ftp_config.get('ftp_path', '/public_html/images/')
    site_url = ftp_config.get('site_url', '').rstrip('/')
    
    if not ftp_pass:
        raise RuntimeError("FTP password not provided")
    if not site_url:
        raise RuntimeError("SITE_URL not provided")
    
    print(f"  🔌 Connecting FTP: {ftp_host} as {ftp_user}")
    print(f"     Remote path: {ftp_path}")
    print(f"     Filename: {filename}")
    
    ftp = ftplib.FTP(ftp_host, timeout=30)
    ftp.login(ftp_user, ftp_pass)
    ftp.encoding = 'utf-8'
    
    # 確保目錄存在
    try:
        ftp.mkd(ftp_path)
        print(f"  📁 Created remote directory: {ftp_path}")
    except ftplib.error_perm as e:
        if "550" not in str(e):  # 目錄已存在是正常的
            raise
    
    ftp.cwd(ftp_path)
    
    bio = BytesIO(img_bytes)
    print(f"  📤 Uploading...")
    ftp.storbinary(f'STOR {filename}', bio)
    ftp.quit()
    
    public_url = f"{site_url}/images/{filename}"
    print(f"  ✅ FTP upload success: {public_url} ({len(img_bytes)/1024:.1f} KB)")
    return public_url


NEGATIVE_PROMPT = (
    "bright, colorful, cheerful, anime, cartoon, sketch, drawing, illustration, "
    "watermark, text, signature, blurry, low quality, ugly, deformed, noise, "
    "grain, oversaturated, modern, clean, sharp focus, high key lighting"
)


def generate_image_url(prompt: str, story_code: str, ptype: str, 
                       site_url: str, ftp_config: Dict,
                       negative_prompt: str = "") -> str:
    """
    生成單張圖片並上傳，回傳公開 URL
    任何步驟失敗都拋出異常
    """
    filename = f"{story_code}_{ptype}.webp"
    
    print(f"\n  🎨 [{ptype}] Generating with Agnes Image 2.5 Flash...")
    print(f"     Prompt length: {len(prompt)} chars")
    
    # 1. 生成圖片
    img_bytes = generate_image_agnes(prompt, 1024, 1024, negative_prompt)
    
    # 2. 壓縮 WebP
    img_bytes = compress_to_webp(img_bytes)
    
    # 3. FTP 上傳
    public_url = upload_ftp(img_bytes, filename, ftp_config)
    
    return public_url


def main():
    parser = argparse.ArgumentParser(description='Generate images with Agnes and upload via FTP')
    parser.add_argument('--content-dir', required=True, help='Content directory path')
    parser.add_argument('--story-codes', required=True, help='Comma-separated story codes')
    parser.add_argument('--ftp-host', default='s13.serv00.com', help='FTP host')
    parser.add_argument('--ftp-user', default='f3459_666', help='FTP username')
    parser.add_argument('--ftp-pass', default='', help='FTP password (required)')
    parser.add_argument('--ftp-path', default='/public_html/images/', help='FTP images path')
    parser.add_argument('--site-url', required=True, help='Site URL (e.g. https://ailoom.ccwu.cc)')
    
    args = parser.parse_args()
    
    story_codes = [c.strip() for c in args.story_codes.split(',') if c.strip()]
    if not story_codes:
        print("ERROR: No story codes provided")
        sys.exit(1)
    
    ftp_config = {
        'ftp_host': args.ftp_host,
        'ftp_user': args.ftp_user,
        'ftp_pass': args.ftp_pass,
        'ftp_path': args.ftp_path,
        'site_url': args.site_url,
    }
    
    if not args.ftp_pass:
        print("  ❌ FTP password is required for Agnes Image (no persistent URL from API)")
        sys.exit(1)
    
    if not args.site_url:
        print("  ❌ Site URL is required")
        sys.exit(1)
    
    if not AGNES_API_KEY:
        print("  ❌ AGNES_API_KEY environment variable not set!")
        sys.exit(1)
    
    print(f"=== Agnes Image Generation ===")
    print(f"Model: {IMAGE_MODEL}")
    print(f"Stories: {story_codes}")
    print(f"FTP: {args.ftp_host} as {args.ftp_user}")
    print(f"Site: {args.site_url}")
    
    from save_content import ContentSaver
    saver = ContentSaver(args.content_dir)
    
    success_count = 0
    failed_stories = []
    
    for code in story_codes:
        print(f"\n{'='*50}")
        print(f"=== Processing {code} ===")
        
        story = saver.get_story(code)
        if not story:
            print(f"  ❌ Story not found: {code}")
            failed_stories.append((code, "Story not found"))
            continue
        
        prompts_file = Path(args.content_dir) / 'stories' / f"{code}_prompts.json"
        if not prompts_file.exists():
            print(f"  ❌ Prompts file not found: {prompts_file}")
            failed_stories.append((code, "Prompts file not found"))
            continue
        
        with open(prompts_file, 'r', encoding='utf-8') as f:
            prompts_data = json.load(f)
        image_prompts = prompts_data.get('image_prompts', [])
        
        if not image_prompts:
            print(f"  ⚠️ No image prompts for {code}")
            failed_stories.append((code, "No image prompts"))
            continue
        
        urls = {}
        story_failed = False
        
        for prompt_obj in image_prompts:
            ptype = prompt_obj['type']  # 'cover' 或 'scene'
            prompt = prompt_obj['prompt']
            
            try:
                urls[ptype] = generate_image_url(
                    prompt, code, ptype, args.site_url, ftp_config, NEGATIVE_PROMPT
                )
            except Exception as e:
                print(f"  ❌ [{ptype}] FAILED: {e}")
                story_failed = True
                failed_stories.append((code, f"{ptype}: {e}"))
                break
        
        if story_failed:
            continue
        
        # 更新故事 JSON
        story['cover_image'] = urls.get('cover', '')
        story['scene_images'] = urls.get('scene', '')
        
        saver.save_story(story)
        print(f"  💾 Updated story JSON with image URLs")
        
        if urls.get('cover') and urls.get('scene'):
            success_count += 1
        else:
            print(f"  ⚠️ Missing cover or scene image")
            failed_stories.append((code, "Missing cover or scene"))
    
    print(f"\n{'='*50}")
    print(f"=== Summary: {success_count}/{len(story_codes)} stories fully updated with images ===")
    
    if failed_stories:
        print(f"\n❌ Failed stories:")
        for code, reason in failed_stories:
            print(f"   - {code}: {reason}")
    
    if success_count == 0:
        print("\n❌ All stories failed to generate images")
        sys.exit(1)
    
    sys.exit(0)


if __name__ == '__main__':
    main()