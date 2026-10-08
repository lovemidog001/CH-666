import json
import hashlib
from datetime import datetime
from typing import Dict, Any, List
from pathlib import Path


class SeedBuilder:
    """將新聞轉為 Story Seed"""
    
    def __init__(self, content_dir: str):
        self.content_dir = Path(content_dir)
        self.seeds_dir = self.content_dir / 'seeds'
        self.seeds_dir.mkdir(parents=True, exist_ok=True)
    
    def build_seed(self, article: Dict[str, Any], channel_config: Dict[str, Any]) -> Dict[str, Any]:
        """建立 Story Seed"""
        source_url = article.get('source_url', '')
        source_hash = hashlib.sha256(source_url.encode('utf-8')).hexdigest()[:12]
        event_text = f"{article.get('source_title', '')}{article.get('event', '')}{article.get('source_location', '')}"
        event_hash = hashlib.sha256(event_text.encode('utf-8')).hexdigest()[:12]
        
        seed = {
            'seed_id': f"SEED-{source_hash}",
            'source_title': article.get('source_title', ''),
            'source_summary': article.get('source_summary', ''),
            'source_date': article.get('source_date', ''),
            'source_location': article.get('source_location', ''),
            'source_url': source_url,
            'source_hash': source_hash,
            'event_hash': event_hash,
            'people': article.get('people', []),
            'event': article.get('event', ''),
            'unusual_detail': article.get('unusual_detail', ''),
            'channel': channel_config.get('code', 'CH-666'),
            'created_at': datetime.utcnow().isoformat() + 'Z',
        }
        return seed
    
    def save_seed(self, seed: Dict[str, Any]) -> str:
        """儲存 Seed 到檔案"""
        seed_file = self.seeds_dir / f"{seed['seed_id']}.json"
        with open(seed_file, 'w', encoding='utf-8') as f:
            json.dump(seed, f, ensure_ascii=False, indent=2)
        return str(seed_file)
    
    def load_seed(self, seed_id: str) -> Dict[str, Any]:
        """載入 Seed"""
        seed_file = self.seeds_dir / f"{seed_id}.json"
        with open(seed_file, 'r', encoding='utf-8') as f:
            return json.load(f)