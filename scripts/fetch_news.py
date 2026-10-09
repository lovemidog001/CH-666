import os
import json
import hashlib
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
import requests


class NewsFetcher:
    """Fetch latest news from NewsAPI, with local caching & dedup."""

    BASE_URL = 'https://newsapi.org/v2/everything'

    def __init__(self, api_key: str = '', content_dir: str = 'content'):
        self.api_key = api_key or os.environ.get('NEWSAPI_KEY', '')
        self.content_dir = Path(content_dir)
        self.seeds_dir = self.content_dir / 'seeds'
        self.seeds_dir.mkdir(parents=True, exist_ok=True)
        self.used_file = self.seeds_dir / 'used_sources.json'
        self.used_sources = self._load_used()

    def _load_used(self) -> Dict[str, Any]:
        if self.used_file.exists():
            try:
                return json.loads(self.used_file.read_text(encoding='utf-8'))
            except Exception:
                return {}
        return {}

    def _save_used(self):
        self.used_file.write_text(json.dumps(self.used_sources, ensure_ascii=False, indent=2), encoding='utf-8')

    def _is_used(self, url: str) -> bool:
        return url in self.used_sources

    def _mark_used(self, url: str, source_hash: str, event_hash: str):
        self.used_sources[url] = {
            'source_hash': source_hash,
            'event_hash': event_hash,
            'used_at': datetime.utcnow().isoformat() + 'Z'
        }
        self._save_used()

    def fetch_latest_news(self, max_results: int = 20, days_back: int = 3) -> List[Dict[str, Any]]:
        """Fetch latest articles, filter used, return up to max_results."""
        if not self.api_key:
            print("  WARNING: NEWSAPI_KEY not set, returning mock data")
            return self._mock_articles(max_results)

        from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        params = {
            'apiKey': self.api_key,
            'language': 'zh',
            'sortBy': 'publishedAt',
            'from': from_date,
            'pageSize': min(100, max_results * 3),
        }

        try:
            resp = requests.get(self.BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            articles = data.get('articles', [])
        except Exception as e:
            print(f"  NewsAPI error: {e}, using mock")
            return self._mock_articles(max_results)

        # Filter & deduplicate
        seen_hashes = set()
        results = []
        for art in articles:
            url = art.get('url', '')
            if not url or self._is_used(url):
                continue

            title = art.get('title', '') or ''
            desc = art.get('description', '') or ''
            content = art.get('content', '') or ''

            # Build source hash for dedup
            src_text = f"{title}{desc}{url}"
            source_hash = hashlib.md5(src_text.encode()).hexdigest()[:12]
            if source_hash in seen_hashes:
                continue
            seen_hashes.add(source_hash)

            # Extract key elements
            event_hash = hashlib.md5(f"{title}{desc}".encode()).hexdigest()[:12]

            results.append({
                'source_title': title,
                'source_summary': desc,
                'source_content': content,
                'source_url': url,
                'source_date': art.get('publishedAt', '')[:10],
                'source_location': self._extract_location(title, desc),
                'source_language': 'zh',
                'unusual_detail': self._extract_unusual(title, desc),
                'event': self._extract_event(title, desc),
                'people': self._extract_people(title, desc),
                'source_hash': source_hash,
                'event_hash': event_hash,
            })

            if len(results) >= max_results:
                break

        return results

    def _extract_location(self, title: str, desc: str) -> str:
        # Simple location extraction - can be enhanced
        locations = ['台灣', '台北', '新北', '桃園', '台中', '台南', '高雄', '基隆', '新竹', '嘉義',
                     '花蓮', '台東', '宜蘭', '澎湖', '金門', '馬祖', '中國', '北京', '上海', '香港', '澳門',
                     '日本', '東京', '大阪', '韓國', '首爾', '美國', '紐約', '洛杉磯']
        text = f"{title} {desc}"
        for loc in locations:
            if loc in text:
                return loc
        return '未知地點'

    def _extract_unusual(self, title: str, desc: str) -> str:
        keywords = ['失蹤', '死亡', '命案', '自殺', '靈異', '鬼', '怪', '詭', '不明', '神秘',
                    '幻覺', '幻聽', '震動', '低頻', '監視器', '白影', '血跡', '廢棄', '老舊',
                    '集體', '無人', '怪聲', '怪響', '離奇', '詭異', '不可思議']
        text = f"{title} {desc}"
        for kw in keywords:
            if kw in text:
                return kw
        return '未明異常'

    def _extract_event(self, title: str, desc: str) -> str:
        events = ['失蹤案', '命案', '自殺案', '靈異事件', '怪聲', '震動', '監視器異常', '集體事件',
                  '不明飛行物', '時間扭曲', '記憶消失', '身分錯置']
        text = f"{title} {desc}"
        for ev in events:
            if ev in text:
                return ev
        return '未知事件'

    def _extract_people(self, title: str, desc: str) -> List[str]:
        # Simplified - real impl would use NER
        return []

    def _mock_articles(self, n: int) -> List[Dict[str, Any]]:
        """Fallback mock data when no API key."""
        mock = [
            {
                'source_title': '深夜公園傳詭異哭聲 民眾驚見白影竄入叢林',
                'source_summary': '多名民眾回報深夜聽見嬰兒哭聲，監視器拍到不明白影快速移動。',
                'source_url': 'https://mock.news/1',
                'source_date': datetime.utcnow().strftime('%Y-%m-%d'),
                'source_location': '台北',
                'source_language': 'zh',
                'unusual_detail': '白影',
                'event': '靈異事件',
                'people': [],
                'source_hash': 'mockhash001',
                'event_hash': 'mockevent1',
            },
            {
                'source_title': '廢棄醫院驚傳集體失蹤 7名探險者同夜人間蒸發',
                'source_summary': '探險團隊進入廢棄精神病院後失聯，手機定位顯示同一地點卻無人跡。',
                'source_url': 'https://mock.news/2',
                'source_date': datetime.utcnow().strftime('%Y-%m-%d'),
                'source_location': '高雄',
                'source_language': 'zh',
                'unusual_detail': '集體失蹤',
                'event': '失蹤案',
                'people': ['探險隊員'],
                'source_hash': 'mockhash002',
                'event_hash': 'mockevent2',
            },
            {
                'source_title': '古井封印百年突自行開啟 井底傳出不可名狀低語',
                'source_summary': '村落古井鐵蓋無故彈開，錄音設備捕捉到非人類頻率聲波。',
                'source_url': 'https://mock.news/3',
                'source_date': datetime.utcnow().strftime('%Y-%m-%d'),
                'source_location': '台東',
                'source_language': 'zh',
                'unusual_detail': '古井異常',
                'event': '靈異事件',
                'people': [],
                'source_hash': 'mockhash003',
                'event_hash': 'mockevent3',
            },
        ]
        return mock[:n]

    def mark_sources_used(self, stories: List[Dict[str, Any]]):
        """Mark source URLs as used after successful generation."""
        for s in stories:
            url = s.get('source_url', '')
            if url:
                self._mark_used(url, s.get('source_hash', ''), s.get('event_hash', ''))