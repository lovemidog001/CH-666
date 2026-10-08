import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path


class ContentSaver:
    """儲存生成內容到 content/ 目錄結構"""
    
    def __init__(self, content_dir: str = 'content', channel_code: str = 'CH-666'):
        self.content_dir = Path(content_dir)
        self.channel_code = channel_code
        self.stories_dir = self.content_dir / 'stories'
        self.seeds_dir = self.content_dir / 'seeds'
        self.daily_dir = self.content_dir / 'daily'
        self.logs_dir = self.content_dir / 'logs'
        
        # 建立目錄
        for d in [self.stories_dir, self.seeds_dir, self.daily_dir, self.logs_dir]:
            d.mkdir(parents=True, exist_ok=True)
    
    def _story_file(self, story_code: str) -> Path:
        """故事 JSON 檔案路徑"""
        return self.stories_dir / f"{story_code}.json"
    
    def _prompts_file(self, story_code: str) -> Path:
        """Image Prompts JSON 檔案路徑"""
        return self.stories_dir / f"{story_code}_prompts.json"
    
    def _daily_file(self, date: str) -> Path:
        """每日合併 JSON 檔案路徑"""
        return self.daily_dir / f"{date}.json"
    
    def save_story(self, story: Dict[str, Any]):
        """儲存單一故事 JSON"""
        story_code = story['story_code']
        filepath = self._story_file(story_code)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(story, f, ensure_ascii=False, indent=2)
    
    def save_image_prompts(self, story_code: str, prompts: List[Dict[str, Any]]):
        """儲存 Image Prompts JSON"""
        filepath = self._prompts_file(story_code)
        data = {
            'story_code': story_code,
            'channel': self.channel_code,
            'image_prompts': prompts,
            'created_at': datetime.utcnow().isoformat() + 'Z',
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def save_stories_merged(self, date: str, stories: List[Dict[str, Any]]):
        """儲存每日合併 JSON"""
        filepath = self._daily_file(date)
        data = {
            'date': date,
            'channel': self.channel_code,
            'count': len(stories),
            'stories': stories,
            'generated_at': datetime.utcnow().isoformat() + 'Z',
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # 同時更新 latest.json（供前端快速讀取最新）
        latest_file = self.daily_dir / 'latest.json'
        with open(latest_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def get_story(self, story_code: str) -> Optional[Dict[str, Any]]:
        """讀取單一故事 JSON"""
        filepath = self._story_file(story_code)
        if not filepath.exists():
            return None
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_latest_stories(self, limit: int = 10) -> List[Dict[str, Any]]:
        """讀取最新故事列表（跨頻道）"""
        stories = []
        if not self.stories_dir.exists():
            return stories
        
        # 掃描所有故事檔案（排除 _prompts.json）
        for f in self.stories_dir.glob("*.json"):
            if f.name.endswith('_prompts.json'):
                continue
            try:
                with open(f, 'r', encoding='utf-8') as fp:
                    story = json.load(fp)
                    stories.append(story)
            except:
                continue
        
        # 依 created_at 排序，最新優先
        stories.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return stories[:limit]
    
    def get_channel_stories(self, channel_code: str, limit: int = 10) -> List[Dict[str, Any]]:
        """讀取特定頻道的最新故事"""
        stories = []
        prefix = f"{channel_code}-"
        if not self.stories_dir.exists():
            return stories
        
        for f in self.stories_dir.glob(f"{prefix}*.json"):
            if f.name.endswith('_prompts.json'):
                continue
            try:
                with open(f, 'r', encoding='utf-8') as fp:
                    story = json.load(fp)
                    stories.append(story)
            except:
                continue
        
        stories.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return stories[:limit]
    
    def list_all_story_codes(self) -> List[str]:
        """列出所有故事代碼"""
        codes = []
        if not self.stories_dir.exists():
            return codes
        for f in self.stories_dir.glob("*.json"):
            if f.name.endswith('_prompts.json'):
                continue
            codes.append(f.stem)
        return sorted(codes)
    
    def log_generation(self, date: str, channel: str, log_data: Dict[str, Any]):
        """記錄生成日誌"""
        log_file = self.logs_dir / f"{date}_{channel}.json"
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)