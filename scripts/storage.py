import json
import re
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional


class ContentStorage:
    """Save story JSON, prompts, daily merged files."""

    def __init__(self, content_dir: str = 'content'):
        self.root = Path(content_dir)
        self.stories_dir = self.root / 'stories'
        self.prompts_dir = self.root / 'prompts'
        self.daily_dir = self.root / 'daily'

        for d in [self.stories_dir, self.prompts_dir, self.daily_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self.counters = {}  # per-prefix counter

    def _counter_file(self, prefix: str) -> Path:
        return self.root / f'.counter_{prefix}'

    def _load_counter(self, prefix: str) -> int:
        cf = self._counter_file(prefix)
        if cf.exists():
            try:
                return int(cf.read_text().strip())
            except:
                pass
        # Scan existing
        max_n = 0
        for f in self.stories_dir.glob(f"{prefix}-*.json"):
            try:
                n = int(f.stem.split('-')[-1])
                max_n = max(max_n, n)
            except:
                pass
        return max_n

    def _save_counter(self, prefix: str, val: int):
        self._counter_file(prefix).write_text(str(val))

    def _next_code(self, prefix: str) -> str:
        if prefix not in self.counters:
            self.counters[prefix] = self._load_counter(prefix)
        self.counters[prefix] += 1
        self._save_counter(prefix, self.counters[prefix])
        return f"{prefix}-{self.counters[prefix]:04d}"

    def _slugify(self, title: str) -> str:
        slug = re.sub(r'[^\w\s-]', '', title.lower())
        slug = re.sub(r'[\s_]+', '-', slug).strip('-')
        return (slug[:60].rstrip('-') or 'untitled')

    def build_story(self, seed: Dict[str, Any], ai_story: Dict[str, Any],
                    dice: Dict[str, Any], provider: str, image_urls: Dict[str, str]) -> Dict[str, Any]:
        """Construct full story JSON with auto-assigned code."""
        prefix = f"CH-{seed['category']}"
        story_code = self._next_code(prefix)

        title = ai_story.get('title', '').strip()
        subtitle = ai_story.get('subtitle', '').strip()
        slug = ai_story.get('slug', '').strip() or self._slugify(title)
        content = ai_story.get('content', '').strip()

        if not title:
            title = f"{prefix} 案件檔案 #{seed['source_hash'][:4].upper()}"
        if not subtitle:
            subtitle = f"{prefix} 檔案 // {seed.get('unusual_detail', '未知異常')}"
        if not slug:
            slug = self._slugify(title)

        summary = content[:200].rsplit('。', 1)[0] + '。' if '。' in content[:200] else content[:200] + '…'

        return {
            'story_code': story_code,
            'category': seed['category'],
            'channel': f"CH-{seed['category']}{seed['category']}{seed['category']}",
            'title': title,
            'subtitle': subtitle,
            'slug': slug,
            'summary': summary,
            'content': content,
            'horror_score': dice.get('horror_score', 50),
            'horror_type': dice.get('horror_type', []),
            'fantasy_level': dice.get('fantasy_level', 'slightly_unreal'),
            'narrative_style': dice.get('narrative_style', 'third_person_limited'),
            'pacing': dice.get('pacing', 'steady'),
            'ending_type': dice.get('ending_type', 'open'),
            'perspective': dice.get('perspective', 'witness'),
            'source_date': seed.get('source_date', ''),
            'source_hash': seed.get('source_hash', ''),
            'event_hash': seed.get('event_hash', ''),
            'source_url': seed.get('source_url', ''),
            'provider_used': provider,
            'dice_seed': dice.get('dice_seed'),
            'director_analysis': {},
            'created_at': datetime.utcnow().isoformat() + 'Z',
            'cover_image': image_urls.get('cover', ''),
            'scene_images': image_urls.get('scene', ''),
        }

    def save_story(self, story: Dict[str, Any]):
        """Save story JSON."""
        path = self.stories_dir / f"{story['story_code']}.json"
        path.write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding='utf-8')

    def save_prompts(self, story_code: str, prompts: List[Dict[str, str]]):
        """Save image prompts."""
        path = self.prompts_dir / f"{story_code}_prompts.json"
        data = {'story_code': story_code, 'image_prompts': prompts,
                'created_at': datetime.utcnow().isoformat() + 'Z'}
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    def save_daily(self, date: str, stories: List[Dict[str, Any]]):
        """Save merged daily JSON + latest.json."""
        path = self.daily_dir / f"{date}.json"
        data = {'date': date, 'count': len(stories), 'stories': stories,
                'generated_at': datetime.utcnow().isoformat() + 'Z'}
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

        # latest.json
        latest = self.daily_dir / 'latest.json'
        latest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    def get_story(self, story_code: str) -> Optional[Dict[str, Any]]:
        path = self.stories_dir / f"{story_code}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding='utf-8'))

    def list_codes(self, prefix: str = 'CH-') -> List[str]:
        codes = []
        for f in self.stories_dir.glob(f"{prefix}*.json"):
            codes.append(f.stem)
        return sorted(codes)