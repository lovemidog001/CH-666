#!/usr/bin/env python3
"""
ODDITY HUB / CH-666 - 圖片生成並 FTP 上傳到 Serv00
使用 Pollinations.ai (Flux) 免費生成 → 轉 WebP → FTP 上傳到 s13.serv00.com
若無 FTP 設定，回傳 Pollinations.ai 直接連結
"""

import os
import sys
import json
import argparse
import ftplib
import requests
import urllib.parse
from io import BytesIO
from pathlib import Path
from typing import List, Dict, Optional

# 確保能 import 同目錄模組
sys.path.insert(0, str(Path(__file__).parent))

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False
    print("WARNING: Pillow not installed, skipping WebP compression")


def generate_image_urls(prompt: str, story_code: str, ptype: str, site_url: str, use_ftp: bool, ftp_config: Dict) -> str:
    """
    生成圖片並回傳公開 URL
    - 有 FTP：上傳後回傳站點 URL
    - 無 FTP：回傳 Pollinations.ai 直接連結
    """
    filename = f"{story_code}_{ptype}.webp"
    
    # Pollinations.ai 參數
    encoded_prompt = urllib.parse.quote(prompt)
    params = {
        'model': 'flux',
        'width': 1024,
        'height': 1024,
        'nologo': 'true',
        'private': 'true',
        'enhance': 'true',
        'format': 'webp',
    }
    param_str = '&'.join([f'{k}={v}' for k, v in params.items()])
    pollinations_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?{param_str}"
    
    # 若無 FTP 設定，直接回傳 Pollinations.ai 連結
    if not use_ftp:
        print(f"  🎨 Generating {ptype} with Pollinations.ai (Flux)...")
        print(f"  🔗 Direct URL: {pollinations_url}")
        return pollinations_url
    
    # 有 FTP：下載 → 壓縮 → 上傳
    try:
        print(f"  🎨 Generating {ptype} with Pollinations.ai (Flux)...")
        resp = requests.get(pollinations_url, timeout=120, stream=True)
        resp.raise_for_status()
        img_bytes = resp.content
        print(f"     Downloaded {len(img_bytes)/1024:.1f} KB")
        
        # 壓縮轉 WebP
        if HAS_PILLOW:
            try:
                img = Image.open(BytesIO(img_bytes))
                img.thumbnail((1024, 1024), Image.LANCZOS)
                out_buf = BytesIO()
                img.save(out_buf, format='WEBP', quality=85, method=6)
                img_bytes = out_buf.getvalue()
                print(f"     Compressed to {len(img_bytes)/1024:.1f} KB (WebP)")
            except Exception as e:
                print(f"     WARNING: Compression failed: {e}")
        
        # FTP 上傳
        ftp_host = ftp_config.get('ftp_host', 's13.serv00.com')
        ftp_user = ftp_config.get('ftp_user', 'f3459_666')
        ftp_pass = ftp_config.get('ftp_pass')
        ftp_path = ftp_config.get('ftp_path', '/public_html/images/')
        site_url_clean = ftp_config.get('site_url', '').rstrip('/')
        filename = f"{story_code}_{ptype}.webp"
        
        print(f"  🔌 Connecting FTP: {ftp_host} as {ftp_user}")
        ftp = ftplib.FTP(ftp_host, timeout=30)
        ftp.login(ftp_user, ftp_pass)
        ftp.encoding = 'utf-8'
        try:
            ftp.mkd(ftp_path)
        except ftplib.error_perm:
            pass
        ftp.cwd(ftp_path)
        
        bio = BytesIO(img_bytes)
        print(f"  📤 Uploading to FTP: {filename}")
        ftp.storbinary(f'STOR {filename}', bio)
        ftp.quit()
        
        public_url = f"{site_url_clean}/images/{filename}"
        print(f"  ✅ FTP uploaded: {public_url} ({len(img_bytes)/1024:.1f} KB)")
        return public_url
        
    except Exception as e:
        print(f"  ❌ FTP upload failed, fallback to direct URL: {e}")
        return pollinations_url


def main():
    parser = argparse.ArgumentParser(description='Generate images and optionally upload via FTP')
    parser.add_argument('--content-dir', required=True, help='Content directory path')
    parser.add_argument('--story-codes', required=True, help='Comma-separated story codes')
    parser.add_argument('--ftp-host', default='s13.serv00.com', help='FTP host')
    parser.add_argument('--ftp-user', default='f3459_666', help='FTP username')
    parser.add_argument('--ftp-pass', default='', help='FTP password (optional)')
    parser.add_argument('--ftp-path', default='/public_html/images/', help='FTP images path')
    parser.add_argument('--site-url', required=True, help='Site URL (e.g. https://ailoom.ccwu.cc)')
    
    args = parser.parse_args()
    
    story_codes = [c.strip() for c in args.story_codes.split(',') if c.strip()]
    if not story_codes:
        print("ERROR: No story codes provided")
        sys.exit(1)
    
    # FTP 設定
    ftp_config = {
        'ftp_host': args.ftp_host,
        'ftp_user': args.ftp_user,
        'ftp_pass': args.ftp_pass,
        'ftp_path': args.ftp_path,
        'site_url': args.site_url,
    }
    use_ftp = bool(args.ftp_pass and args.site_url)
    
    if not use_ftp:
        print("  ℹ️ FTP credentials not provided, using Pollinations.ai direct URLs")
    
    # 載入儲存器
    from save_content import ContentSaver
    saver = ContentSaver(args.content_dir)
    
    success_count = 0
    for code in story_codes:
        print(f"\n=== Processing {code} ===")
        
        story = saver.get_story(code)
        if not story:
            print(f"  ❌ Story not found: {code}")
            continue
        
        prompts_file = Path(args.content_dir) / 'stories' / f"{code}_prompts.json"
        if not prompts_file.exists():
            print(f"  ❌ Prompts file not found: {prompts_file}")
            continue
        
        with open(prompts_file, 'r', encoding='utf-8') as f:
            prompts_data = json.load(f)
        image_prompts = prompts_data.get('image_prompts', [])
        
        if not image_prompts:
            print(f"  ⚠️ No image prompts for {code}")
            continue
        
        # 生成圖片 URL
        urls = {}
        for prompt_obj in image_prompts:
            ptype = prompt_obj['type']  # 'cover' 或 'scene'
            prompt = prompt_obj['prompt']
            urls[ptype] = generate_image_urls(prompt, code, ptype, args.site_url, use_ftp, ftp_config)
        
        # 更新故事 JSON
        story['cover_image'] = urls.get('cover')
        story['scene_images'] = urls.get('scene')
        
        saver.save_story(story)
        print(f"  💾 Updated story JSON with image URLs")
        
        if urls.get('cover') or urls.get('scene'):
            success_count += 1
    
    print(f"\n=== Summary: {success_count}/{len(story_codes)} stories updated with images ===")
    # 不再因 success_count 為 0 而 exit 1，圖片生成是加分項，非核心功能
    sys.exit(0)


if __name__ == '__main__':
    try:
        from PIL import Image
    except ImportError:
        print("WARNING: Pillow not installed, skipping WebP compression")
    
    main()