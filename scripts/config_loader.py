import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path


def load_json_config(path: str) -> Dict[str, Any]:
    """載入 JSON 設定檔"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_generation_config(config_path: str) -> Dict[str, Any]:
    """取得每日產出設定"""
    config = load_json_config(config_path)
    return config.get('daily_generation', {})


def get_ai_providers(providers_path: str) -> List[Dict[str, Any]]:
    """取得已啟用的 AI Provider，依 priority 排序"""
    providers = load_json_config(providers_path)
    enabled = [p for p in providers if p.get('enabled', False)]
    return sorted(enabled, key=lambda x: x.get('priority', 999))


def get_channel_config(channel_path: str) -> Dict[str, Any]:
    """取得統一頻道設定（包含 3/6/9 三種分類）"""
    return load_json_config(channel_path)


def get_genre_config(channel_config: Dict[str, Any], category: str) -> Dict[str, Any]:
    """取得特定分類（3/6/9）的設定"""
    genres = channel_config.get('genres', {})
    if category not in genres:
        raise ValueError(f"Category {category} not found in genres")
    return genres[category]


def get_all_categories(channel_config: Dict[str, Any]) -> List[str]:
    """取得所有可用分類代碼"""
    return channel_config.get('valid_categories', ['3', '6', '9'])


class Config:
    """統一設定存取（單一頻道，多種分類）"""
    
    def __init__(self, generation_path: str, providers_path: str, channel_path: str):
        self.generation = get_generation_config(generation_path)
        self.providers = get_ai_providers(providers_path)
        self.channel = get_channel_config(channel_path)
        self.categories = get_all_categories(self.channel)
        
    @property
    def articles_per_day(self) -> int:
        return self.generation.get('articles_per_day', 3)
    
    @property
    def enabled(self) -> bool:
        return self.generation.get('enabled', True)
    
    @property
    def schedule(self) -> str:
        return self.generation.get('schedule', '06:00')
    
    @property
    def timezone(self) -> str:
        return self.generation.get('timezone', 'Asia/Taipei')
    
    def get_category_config(self, category: str) -> Dict[str, Any]:
        """取得特定分類的完整設定（合併基礎設定與分類設定）"""
        base = {
            'code': self.channel.get('code', 'CH'),
            'name': self.channel.get('name', 'CH-666'),
            'description': self.channel.get('description', ''),
            'enabled': self.channel.get('enabled', True),
            'story_code_prefix': f"{self.channel.get('code', 'CH')}-{category}",
            'color': self.channel.get('color', '#00ff88'),
        }
        genre = get_genre_config(self.channel, category)
        # 合併：分類設定覆蓋基礎設定
        merged = {**base, **genre}
        merged['category'] = category
        return merged