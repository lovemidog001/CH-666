import random
import hashlib
from typing import Dict, Any, List


class DirectorDice:
    """Director Dice - 受 Story Seed 限制的方向控制"""
    
    def __init__(self, channel_config: Dict[str, Any]):
        self.channel_config = channel_config
        # channels.json 中為物件陣列，需提取 key
        def extract_keys(arr):
            if arr and isinstance(arr[0], dict):
                return [item.get('key') for item in arr if item.get('key')]
            return arr
        
        self.horror_types = extract_keys(channel_config.get('horror_types', []))
        self.fantasy_levels = extract_keys(channel_config.get('fantasy_levels', []))
        self.narrative_styles = extract_keys(channel_config.get('narrative_styles', []))
        self.pacing_options = extract_keys(channel_config.get('pacing_options', []))
        self.ending_types = extract_keys(channel_config.get('ending_types', []))
        self.perspectives = extract_keys(channel_config.get('perspectives', []))
    
    def roll(self, seed: Dict[str, Any], director_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        擲骰決定故事參數
        原則：Randomness × Story Seed Compatibility × Narrative Quality × Internal Logic
        """
        # 使用 seed_id 作為隨機種子基礎，確保同一 Seed 可復現
        seed_id = seed.get('seed_id', '')
        event_hash = seed.get('event_hash', '')
        base_seed = int(hashlib.md5(f"{seed_id}{event_hash}".encode()).hexdigest()[:8], 16)
        rng = random.Random(base_seed)
        
        # 取得 Director 偏好
        preferred_horror = director_analysis.get('preferred_horror_types', self.horror_types)
        preferred_fantasy = director_analysis.get('preferred_fantasy_levels', self.fantasy_levels)
        analysis = director_analysis.get('analysis', {})
        reality_level = analysis.get('reality_level', 50)
        
        # Horror Score: 受現實程度影響
        # 現實程度高 -> 心理恐怖為主 -> 分數中等偏低
        # 現實程度低 -> 超自然為主 -> 分數較高
        base_horror = 50
        if reality_level > 70:
            base_horror = rng.randint(20, 55)
        elif reality_level > 40:
            base_horror = rng.randint(40, 75)
        else:
            base_horror = rng.randint(60, 95)
        
        # Horror Type: 從偏好中選 1-3 個
        horror_type_count = rng.randint(1, 3)
        horror_type = rng.sample(preferred_horror, min(horror_type_count, len(preferred_horror)))
        
        # Fantasy Level
        fantasy_level = rng.choice(preferred_fantasy)
        
        # Narrative Style
        narrative_style = rng.choice(self.narrative_styles)
        
        # Pacing
        pacing = rng.choice(self.pacing_options)
        
        # Ending Type
        ending_type = rng.choice(self.ending_types)
        
        # Perspective
        perspective = rng.choice(self.perspectives)
        
        # 內部邏輯檢查：若組合不合理則微調
        horror_score, horror_type, fantasy_level = self._validate_logic(
            horror_score=base_horror,
            horror_type=horror_type,
            fantasy_level=fantasy_level,
            reality_level=reality_level,
            rng=rng
        )
        
        return {
            'horror_score': horror_score,
            'horror_type': horror_type,
            'fantasy_level': fantasy_level,
            'narrative_style': narrative_style,
            'pacing': pacing,
            'ending_type': ending_type,
            'perspective': perspective,
            'dice_seed': base_seed,
        }
    
    def _validate_logic(self, horror_score: int, horror_type: List[str], 
                        fantasy_level: str, reality_level: int, rng: random.Random) -> tuple:
        """內部邏輯驗證與微調"""
        # 現實程度高但幻想等級太高 -> 降低幻想等級
        if reality_level > 70 and fantasy_level in ['supernatural', 'reality_bending']:
            fantasy_level = rng.choice(['grounded', 'slightly_unreal'])
        
        # 現實程度低但恐怖分數太低 -> 提高恐怖分數
        if reality_level < 30 and horror_score < 50:
            horror_score = rng.randint(55, 85)
        
        # 某些 horror type 與 fantasy level 衝突
        if 'supernatural' in horror_type and fantasy_level == 'grounded':
            # 如果有超自然類型但幻想等級是寫實，提升幻想等級
            fantasy_level = rng.choice(['slightly_unreal', 'supernatural'])
        
        # 確保 horror_score 在 0-100
        horror_score = max(0, min(100, horror_score))
        
        return horror_score, horror_type, fantasy_level