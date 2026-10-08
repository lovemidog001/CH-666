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


def get_channel_config(channels_path: str, channel_code: str) -> Dict[str, Any]:
    """取得頻道設定"""
    config = load_json_config(channels_path)
    for ch in config.get('channels', []):
        if ch.get('code') == channel_code:
            return ch
    raise ValueError(f"Channel {channel_code} not found")


def get_all_enabled_channels(channels_path: str) -> List[Dict[str, Any]]:
    """取得所有啟用的頻道"""
    config = load_json_config(channels_path)
    return [ch for ch in config.get('channels', []) if ch.get('enabled', True)]


class Config:
    """統一設定存取（單一頻道）"""
    
    def __init__(self, generation_path: str, providers_path: str, channels_path: str, channel_code: str = 'CH-666'):
        self.generation = get_generation_config(generation_path)
        self.providers = get_ai_providers(providers_path)
        self.channel = get_channel_config(channels_path, channel_code)
        self.channel_code = channel_code
        
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