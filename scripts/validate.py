import re
from datetime import datetime
from typing import Dict, Any, List, Tuple


class StoryValidator:
    """Validate story JSON against schema + category rules."""

    REQUIRED = [
        'story_code', 'category', 'title', 'subtitle', 'slug', 'summary',
        'content', 'horror_score', 'horror_type', 'fantasy_level',
        'narrative_style', 'pacing', 'ending_type', 'perspective',
        'source_date', 'source_hash', 'event_hash', 'source_url',
        'provider_used', 'dice_seed', 'director_analysis', 'created_at',
    ]

    def __init__(self, cat_config: Dict[str, Any]):
        self.cat = cat_config
        self.category = cat_config['category']
        self.prefix = cat_config['story_code_prefix']  # CH-3, CH-6, CH-9
        self.valid_horror = cat_config.get('horror_types', [])
        self.valid_fantasy = cat_config.get('fantasy_levels', [])
        self.valid_style = cat_config.get('narrative_styles', [])
        self.valid_pacing = cat_config.get('pacing_options', [])
        self.valid_ending = cat_config.get('ending_types', [])
        self.valid_persp = cat_config.get('perspectives', [])

    def validate(self, story: Dict[str, Any]) -> Tuple[bool, List[str]]:
        errors = []

        # Required fields
        for f in self.REQUIRED:
            if f not in story:
                errors.append(f"Missing: {f}")
            elif not story[f] and f not in ['subtitle', 'source_url', 'cover_image', 'scene_images']:
                errors.append(f"Empty: {f}")

        # story_code format
        code = story.get('story_code', '')
        if code and not re.match(rf'^{re.escape(self.prefix)}-\d{{4}}$', code):
            errors.append(f"Invalid story_code: {code} (expected {self.prefix}-NNNN)")

        # category match
        if story.get('category') != self.category:
            errors.append(f"Category mismatch: expected {self.category}, got {story.get('category')}")

        # horror_score
        hs = story.get('horror_score')
        if hs is not None:
            if not isinstance(hs, int) or hs < 0 or hs > 100:
                errors.append(f"horror_score must be 0-100 int, got {hs}")

        # horror_type
        htypes = story.get('horror_type', [])
        if not isinstance(htypes, list):
            errors.append("horror_type must be list")
        else:
            for h in htypes:
                if h not in self.valid_horror:
                    errors.append(f"Invalid horror_type for cat {self.category}: {h}")

        # fantasy_level
        fl = story.get('fantasy_level')
        if fl and fl not in self.valid_fantasy:
            errors.append(f"Invalid fantasy_level for cat {self.category}: {fl}")

        # narrative_style
        ns = story.get('narrative_style')
        if ns and ns not in self.valid_style:
            errors.append(f"Invalid narrative_style: {ns}")

        # pacing
        p = story.get('pacing')
        if p and p not in self.valid_pacing:
            errors.append(f"Invalid pacing: {p}")

        # ending_type
        e = story.get('ending_type')
        if e and e not in self.valid_ending:
            errors.append(f"Invalid ending_type: {e}")

        # perspective
        persp = story.get('perspective')
        if persp and persp not in self.valid_persp:
            errors.append(f"Invalid perspective: {persp}")

        # content length
        content = story.get('content', '')
        if content and len(content) < 1000:
            errors.append(f"Content too short: {len(content)} chars (min 1000)")

        # slug format
        slug = story.get('slug', '')
        if slug and not re.match(r'^[a-z0-9-]+$', slug):
            errors.append(f"Invalid slug: {slug}")

        # created_at ISO format
        ca = story.get('created_at', '')
        if ca:
            try:
                datetime.fromisoformat(ca.replace('Z', '+00:00'))
            except ValueError:
                errors.append(f"Invalid created_at: {ca}")

        # no news-style language
        if content:
            news_patterns = [r'據報導', r'警方表示', r'經調查', r'據悉', r'記者.*報導', r'本報訊']
            for pat in news_patterns:
                if re.search(pat, content):
                    errors.append(f"News-style language detected: {pat}")
                    break

        return len(errors) == 0, errors