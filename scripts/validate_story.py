import json
import re
from typing import Dict, Any, List, Tuple
from datetime import datetime


class StoryValidator:
    """故事驗證器"""
    
    REQUIRED_FIELDS = [
        'story_code', 'channel', 'title', 'subtitle', 'slug', 'summary',
        'content', 'horror_score', 'horror_type', 'fantasy_level',
        'narrative_style', 'pacing', 'ending_type', 'source_date',
        'source_hash', 'created_at'
    ]
    
    VALID_FANTASY_LEVELS = ['grounded', 'slightly_unreal', 'supernatural', 'reality_bending']
    VALID_HORROR_TYPES = [
        'psychological', 'urban_legend', 'supernatural', 'crime', 'suspense',
        'identity_horror', 'sci_fi_horror', 'surveillance_horror', 
        'unknown_phenomenon', 'reality_horror'
    ]
    
    def __init__(self, channel_config: Dict[str, Any]):
        self.channel_config = channel_config
        # channels.json 中 horror_types 和 fantasy_levels 是物件陣列，需提取 key
        horror_types_raw = channel_config.get('horror_types', self.VALID_HORROR_TYPES)
        fantasy_levels_raw = channel_config.get('fantasy_levels', self.VALID_FANTASY_LEVELS)
        
        # 若是物件陣列，提取 key；若已是字串陣列，直接使用
        if horror_types_raw and isinstance(horror_types_raw[0], dict):
            self.valid_horror_types = [h.get('key') for h in horror_types_raw if h.get('key')]
        else:
            self.valid_horror_types = horror_types_raw
            
        if fantasy_levels_raw and isinstance(fantasy_levels_raw[0], dict):
            self.valid_fantasy_levels = [f.get('key') for f in fantasy_levels_raw if f.get('key')]
        else:
            self.valid_fantasy_levels = fantasy_levels_raw
    
    def validate(self, story: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        驗證故事完整性
        返回：(is_valid, errors)
        """
        errors = []
        
        # 1. 必要欄位檢查
        for field in self.REQUIRED_FIELDS:
            if field not in story:
                errors.append(f"Missing required field: {field}")
            elif not story[field] and field not in ['subtitle', 'people']:
                errors.append(f"Empty required field: {field}")
        
        # 2. Horror Score 範圍
        horror_score = story.get('horror_score')
        if horror_score is not None:
            if not isinstance(horror_score, int):
                errors.append(f"horror_score must be integer, got {type(horror_score)}")
            elif horror_score < 0 or horror_score > 100:
                errors.append(f"horror_score must be 0-100, got {horror_score}")
        
        # 3. Horror Type 有效性
        horror_types = story.get('horror_type', [])
        if not isinstance(horror_types, list):
            errors.append("horror_type must be a list")
        else:
            for ht in horror_types:
                if ht not in self.valid_horror_types:
                    errors.append(f"Invalid horror_type: {ht}")
        
        # 4. Fantasy Level 有效性
        fantasy_level = story.get('fantasy_level')
        if fantasy_level and fantasy_level not in self.valid_fantasy_levels:
            errors.append(f"Invalid fantasy_level: {fantasy_level}")
        
        # 5. 內容品質檢查
        content = story.get('content', '')
        if content:
            if len(content) < 200:
                errors.append(f"Content too short ({len(content)} chars), minimum 200")
            # 檢查是否有明顯的新聞報導式語氣
            news_patterns = [r'據報導', r'警方表示', r'經調查', r'據悉', r'記者.*報導']
            for pattern in news_patterns:
                if re.search(pattern, content):
                    errors.append(f"Content appears to be news-report style (matched: {pattern})")
                    break
        
        # 6. Story Code 格式
        story_code = story.get('story_code', '')
        if story_code and not re.match(r'^CH-666-\d{4}$', story_code):
            errors.append(f"Invalid story_code format: {story_code} (expected CH-666-NNNN)")
        
        # 7. Slug 格式
        slug = story.get('slug', '')
        if slug and not re.match(r'^[a-z0-9-]+$', slug):
            errors.append(f"Invalid slug format: {slug}")
        
        # 8. Created_at 格式
        created_at = story.get('created_at', '')
        if created_at:
            try:
                datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            except ValueError:
                errors.append(f"Invalid created_at format: {created_at}")
        
        return len(errors) == 0, errors
    
    def validate_image_prompts(self, prompts: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
        """驗證 Image Prompts"""
        errors = []
        if not isinstance(prompts, list):
            return False, ["image_prompts must be a list"]
        
        for i, p in enumerate(prompts):
            if not isinstance(p, dict):
                errors.append(f"Prompt {i}: must be object")
                continue
            if 'type' not in p:
                errors.append(f"Prompt {i}: missing 'type'")
            if 'prompt' not in p:
                errors.append(f"Prompt {i}: missing 'prompt'")
            elif not p['prompt']:
                errors.append(f"Prompt {i}: empty prompt")
        
        return len(errors) == 0, errors