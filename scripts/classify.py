import random
import hashlib
from typing import Dict, Any, List


class DiceRoller:
    """Director Dice - deterministic dice rolls based on seed."""

    def __init__(self, category_config: Dict[str, Any]):
        self.cat = category_config
        self.category = category_config['category']  # '3', '6', or '9'

    def _seed_rng(self, seed_id: str, event_hash: str) -> random.Random:
        """Deterministic RNG from seed_id + event_hash."""
        h = hashlib.md5(f"{seed_id}{event_hash}".encode()).hexdigest()[:8]
        return random.Random(int(h, 16))

    def roll(self, seed: Dict[str, Any]) -> Dict[str, Any]:
        """Roll all story parameters."""
        rng = self._seed_rng(seed['seed_id'], seed.get('event_hash', ''))

        # Reality level from seed (0-100)
        reality = seed.get('reality_level', 50)

        # Horror Score based on reality
        if reality > 70:
            horror_score = rng.randint(20, 55)
        elif reality > 40:
            horror_score = rng.randint(40, 75)
        else:
            horror_score = rng.randint(60, 95)

        # Horror Type (1-3 from category's allowed list)
        allowed_horror = self.cat.get('horror_types', ['psychological'])
        k = rng.randint(1, min(3, len(allowed_horror)))
        horror_type = rng.sample(allowed_horror, k)

        # Fantasy Level
        allowed_fantasy = self.cat.get('fantasy_levels', ['slightly_unreal'])
        fantasy_level = rng.choice(allowed_fantasy)

        # Narrative Style
        allowed_style = self.cat.get('narrative_styles', ['third_person_limited'])
        narrative_style = rng.choice(allowed_style)

        # Pacing
        allowed_pacing = self.cat.get('pacing_options', ['steady'])
        pacing = rng.choice(allowed_pacing)

        # Ending
        allowed_ending = self.cat.get('ending_types', ['open'])
        ending_type = rng.choice(allowed_ending)

        # Perspective
        allowed_persp = self.cat.get('perspectives', ['witness'])
        perspective = rng.choice(allowed_persp)

        # Logic validation
        horror_score, horror_type, fantasy_level = self._validate_logic(
            horror_score, horror_type, fantasy_level, reality, rng
        )

        return {
            'horror_score': horror_score,
            'horror_type': horror_type,
            'fantasy_level': fantasy_level,
            'narrative_style': narrative_style,
            'pacing': pacing,
            'ending_type': ending_type,
            'perspective': perspective,
            'dice_seed': rng.randint(0, 2**31 - 1),
            'category': self.category,
        }

    def _validate_logic(self, score: int, htypes: List[str], fantasy: str, reality: int, rng: random.Random) -> tuple:
        # High reality + high fantasy -> lower fantasy
        if reality > 70 and fantasy in ['supernatural', 'reality_bending', 'mythic', 'conceptual']:
            fantasy = rng.choice(['grounded', 'slightly_unreal'])

        # Low reality + low score -> raise score
        if reality < 30 and score < 50:
            score = rng.randint(55, 85)

        # Supernatural horror_type but grounded fantasy -> raise fantasy
        if 'supernatural' in htypes and fantasy == 'grounded':
            fantasy = rng.choice(['slightly_unreal', 'supernatural'])

        return max(0, min(100, score)), htypes, fantasy


def assign_category(seed: Dict[str, Any], categories: List[str]) -> str:
    """Deterministic category assignment from seed hash."""
    h = hashlib.md5(f"{seed['seed_id']}{seed.get('event_hash', '')}".encode()).hexdigest()
    idx = int(h, 16) % len(categories)
    return categories[idx]


def build_seed(article: Dict[str, Any], cat_config: Dict[str, Any]) -> Dict[str, Any]:
    """Build seed from article + category config."""
    seed_id = f"SEED-{cat_config['category']}-{article['source_hash'][:8]}"
    return {
        'seed_id': seed_id,
        'category': cat_config['category'],
        'source_title': article['source_title'],
        'source_summary': article['source_summary'],
        'source_content': article.get('source_content', ''),
        'source_url': article['source_url'],
        'source_date': article['source_date'],
        'source_location': article['source_location'],
        'source_language': article['source_language'],
        'unusual_detail': article['unusual_detail'],
        'event': article['event'],
        'people': article.get('people', []),
        'source_hash': article['source_hash'],
        'event_hash': article['event_hash'],
        'reality_level': 50,  # default, can be enhanced
    }