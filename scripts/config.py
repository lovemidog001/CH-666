import json
import os
from typing import Dict, Any, List
from pathlib import Path


def load_json(path: str) -> Dict[str, Any]:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


class Config:
    """Unified config loader for generation, providers, channels."""

    def __init__(self, gen_path: str, providers_path: str, channels_path: str):
        self.gen = load_json(gen_path).get('daily_generation', {})
        self.providers = [p for p in load_json(providers_path) if p.get('enabled')]
        self.providers.sort(key=lambda x: x.get('priority', 999))

        ch = load_json(channels_path)
        self.channel_code = ch.get('code', 'CH')
        self.channel_name = ch.get('name', 'CH-666')
        self.genres = ch.get('genres', {})
        self.valid_categories = ch.get('valid_categories', ['3', '6', '9'])

    @property
    def enabled(self) -> bool:
        return self.gen.get('enabled', True)

    @property
    def articles_per_day(self) -> int:
        return self.gen.get('articles_per_day', 6)

    def get_category_config(self, cat: str) -> Dict[str, Any]:
        """Get merged config for a category (3, 6, or 9)."""
        genre = self.genres.get(cat, {})
        return {
            'code': self.channel_code,
            'category': cat,
            'name': genre.get('name', f'CH-{cat}{cat}{cat}'),
            'label': genre.get('label', ''),
            'description': genre.get('description', ''),
            'color': genre.get('color', '#00ff88'),
            'genre': genre.get('genre', 'anomalous'),
            'horror_types': [h['key'] for h in genre.get('horror_types', [])],
            'fantasy_levels': [f['key'] for f in genre.get('fantasy_levels', [])],
            'narrative_styles': [n['key'] for n in genre.get('narrative_styles', [])],
            'pacing_options': [p['key'] for p in genre.get('pacing_options', [])],
            'ending_types': [e['key'] for e in genre.get('ending_types', [])],
            'perspectives': [p['key'] for p in genre.get('perspectives', [])],
            'story_code_prefix': f"{self.channel_code}-{cat}",
        }

    def get_genre_labels(self, cat: str) -> Dict[str, str]:
        """Get key->label mappings for a category."""
        genre = self.genres.get(cat, {})
        labels = {}
        for h in genre.get('horror_types', []):
            labels[h['key']] = h.get('label', h['key'])
        for f in genre.get('fantasy_levels', []):
            labels[f['key']] = f.get('label', f['key'])
        return labels


def load_config() -> Config:
    """Load from env vars (for GitHub Actions)."""
    return Config(
        os.environ['GENERATION_CONFIG'],
        os.environ['PROVIDERS_CONFIG'],
        os.environ['CHANNELS_CONFIG'],
    )


if __name__ == '__main__':
    # Used by load_config.py in workflow
    cfg = load_config()
    out = os.environ.get('GITHUB_OUTPUT')
    with open(out, 'a', encoding='utf-8') as f:
        f.write(f"enabled={cfg.enabled}\n")
        f.write(f"articles_per_day={cfg.articles_per_day}\n")
        f.write(f"categories={','.join(cfg.valid_categories)}\n")
    print(f"enabled={cfg.enabled}")
    print(f"articles_per_day={cfg.articles_per_day}")