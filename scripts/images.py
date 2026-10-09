import os
import json
import base64
import hashlib
import time
from io import BytesIO
from pathlib import Path
from typing import Dict, Any, List
import requests
from ftplib import FTP
from PIL import Image


class ImageGenerator:
    """Agnes Image 2.5 Flash → WebP → FTP → URLs."""

    API_URL = 'https://apihub.agnes-ai.com/v1/images/generations'

    def __init__(self, api_key: str, ftp_host: str, ftp_user: str, ftp_pass: str,
                 ftp_path: str, site_url: str):
        self.api_key = api_key
        self.ftp_host = ftp_host
        self.ftp_user = ftp_user
        self.ftp_pass = ftp_pass
        self.ftp_path = ftp_path.rstrip('/')
        self.site_url = site_url.rstrip('/')

        self.negative_prompt = (
            "text, watermark, signature, logo, title, subtitle, caption, "
            "blurry, low quality, deformed, ugly, bad anatomy, extra limbs, "
            "jpeg artifacts, noise, grain, oversaturated, cartoon, anime, "
            "illustration, painting, drawing, sketch, 3d render, cgi, "
            "bright colors, neon, modern, clean, polished, professional photography"
        )

    def generate_prompts(self, story: Dict[str, Any], dice: Dict[str, Any]) -> List[Dict[str, str]]:
        """Build cover + scene prompts."""
        cat = story.get('category', '6')
        horror_types = ', '.join(story.get('horror_type', []))
        fantasy = story.get('fantasy_level', 'slightly_unreal')

        channel_visual = {
            '3': "candlelight flicker, incense smoke, talisman symbols, ritualistic atmosphere, warm amber tones",
            '6': "phosphor green glow, scanlines, VHS static, analog horror, surveillance aesthetic",
            '9': "harsh red warning lights, data corruption, glitch artifacts, cognitive hazard symbols, stark clinical lighting",
        }.get(cat, "phosphor green glow, scanlines, VHS static")

        fantasy_visual = {
            'grounded': "photorealistic, documentary style, gritty realism, natural lighting",
            'slightly_unreal': "slightly off-kilter, subtle wrongness, uncanny valley, muted colors",
            'supernatural': "ethereal glow, spectral presence, impossible geometry, otherworldly",
            'reality_bending': "reality distortion, fractal patterns, melting surfaces, glitch reality",
            'mythic': "divine radiance, ancient symbols, mythic scale, legendary atmosphere",
            'conceptual': "abstract concepts visualized, information as geometry, memetic patterns",
        }.get(fantasy, "")

        title = story.get('title', '')
        content = story.get('content', '')[:500]

        cover = (
            f"{channel_visual}, {fantasy_visual}, "
            f"CH-{cat} aesthetic, retro CRT, analog horror, scanlines, "
            f"Scene inspired by: {title}. Core: {horror_types}. "
            f"Composition: centered, ominous, negative space, rule of thirds. "
            f"Color: #0A0A0C bg, {self._cat_color(cat)} accent, #FF0055 warning."
        )

        scene = (
            f"{channel_visual}, {fantasy_visual}, "
            f"Key moment: {horror_types} manifesting. "
            f"Perspective: {story.get('perspective', 'witness')}. "
            f"Mood: dread, anticipation, the moment before revelation. "
            f"Analog texture: film grain, vignetting, chromatic aberration."
        )

        return [
            {'type': 'cover', 'prompt': cover.strip()},
            {'type': 'scene', 'prompt': scene.strip()},
        ]

    def _cat_color(self, cat: str) -> str:
        return {'3': '#ff6b35', '6': '#00ff88', '9': '#ff0044'}.get(cat, '#00ff88')

    def generate_image(self, prompt: str) -> bytes:
        """Call Agnes API, return WebP bytes."""
        headers = {'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json'}
        data = {
            'model': 'agnes-image-2.5-flash',
            'prompt': prompt,
            'negative_prompt': self.negative_prompt,
            'width': 1024,
            'height': 1024,
            'n': 1,
            'response_format': 'b64_json',
            'quality': 'high',
        }
        resp = requests.post(self.API_URL, headers=headers, json=data, timeout=180)
        resp.raise_for_status()
        b64 = resp.json()['data'][0]['b64_json']
        img_bytes = base64.b64decode(b64)

        # Convert to WebP
        img = Image.open(BytesIO(img_bytes))
        img.thumbnail((1024, 1024), Image.LANCZOS)
        out = BytesIO()
        img.save(out, format='WEBP', quality=85, method=6)
        return out.getvalue()

    def upload_ftp(self, filename: str, data: bytes) -> bool:
        """Upload to FTP, return success."""
        try:
            ftp = FTP(self.ftp_host, timeout=30)
            ftp.login(self.ftp_user, self.ftp_pass)
            ftp.cwd(self.ftp_path)
            ftp.storbinary(f'STOR {filename}', BytesIO(data))
            ftp.quit()
            return True
        except Exception as e:
            print(f"  FTP upload failed: {e}")
            return False

    def process_story(self, story: Dict[str, Any], dice: Dict[str, Any]) -> Dict[str, str]:
        """Generate cover+scene, upload, return URLs."""
        prompts = self.generate_prompts(story, dice)
        story_code = story.get('story_code', f"STORY-{story.get('seed_id', 'UNKNOWN')}")
        cat = story.get('category', '6')
        urls = {}

        for p in prompts:
            print(f"  Generating {p['type']} image...")
            img_data = self.generate_image(p['prompt'])
            filename = f"{story_code}_{p['type']}.webp"

            if self.upload_ftp(filename, img_data):
                urls[p['type']] = f"{self.site_url}/images/{filename}"
                print(f"  ✅ {p['type']}: {urls[p['type']]}")
            else:
                urls[p['type']] = ''

        return urls
