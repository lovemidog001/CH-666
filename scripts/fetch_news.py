import os
import json
import hashlib
import requests
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from pathlib import Path


class NewsFetcher:
    """取得昨日新聞"""
    
    def __init__(self, api_key: str, content_dir: str):
        self.api_key = api_key
        self.content_dir = Path(content_dir)
        self.used_sources_file = self.content_dir / 'seeds' / 'used_sources.json'
        self.used_sources = self._load_used_sources()
    
    def _load_used_sources(self) -> Dict[str, Any]:
        """載入已使用的新聞來源"""
        if self.used_sources_file.exists():
            with open(self.used_sources_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {'source_urls': [], 'source_hashes': [], 'event_hashes': []}
    
    def _save_used_sources(self):
        """儲存已使用的新聞來源"""
        self.used_sources_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.used_sources_file, 'w', encoding='utf-8') as f:
            json.dump(self.used_sources, f, ensure_ascii=False, indent=2)
    
    def _compute_hash(self, text: str) -> str:
        """計算 SHA256 雜湊"""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]
    
    def _is_duplicate(self, article: Dict[str, Any]) -> bool:
        """檢查是否重複"""
        source_url = article.get('source_url', '')
        source_hash = self._compute_hash(source_url)
        event_text = f"{article.get('source_title', '')}{article.get('event', '')}{article.get('source_location', '')}"
        event_hash = self._compute_hash(event_text)
        
        if source_url in self.used_sources['source_urls']:
            return True
        if source_hash in self.used_sources['source_hashes']:
            return True
        if event_hash in self.used_sources['event_hashes']:
            return True
        return False
    
    def _mark_used(self, article: Dict[str, Any]):
        """標記為已使用"""
        source_url = article.get('source_url', '')
        source_hash = self._compute_hash(source_url)
        event_text = f"{article.get('source_title', '')}{article.get('event', '')}{article.get('source_location', '')}"
        event_hash = self._compute_hash(event_text)
        
        self.used_sources['source_urls'].append(source_url)
        self.used_sources['source_hashes'].append(source_hash)
        self.used_sources['event_hashes'].append(event_hash)
        self._save_used_sources()
    
    def fetch_latest_news(self, max_results: int = 20, days_back: int = 3) -> List[Dict[str, Any]]:
        """
        取得最新新聞（預設最近 3 天），不限定特定日期
        max_results: 最大回傳筆數
        days_back: 往前搜尋天數（預設 3 天）
        """
        if not self.api_key:
            print("WARNING: NEWSAPI_KEY not set, using mock data")
            # 用今天日期生成 mock
            target_date = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')
            return self._mock_news(target_date)
        
        # 計算日期範圍（Asia/Taipei = UTC+8）
        tz = timezone(timedelta(hours=8))
        now = datetime.now(tz)
        from_time = (now - timedelta(days=days_back)).isoformat()
        to_time = now.isoformat()
        
        # NewsAPI 請求 - 支援多語言 (中文、英文、日文等)
        url = 'https://newsapi.org/v2/everything'
        languages = ['zh', 'en', 'ja']
        all_articles = []
        
        for lang in languages:
            params = {
                'apiKey': self.api_key,
                'language': lang,
                'from': from_time,
                'to': to_time,
                'sortBy': 'publishedAt',
                'pageSize': max_results // len(languages) + 1,
            }
            
            try:
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                for item in data.get('articles', []):
                    if not item.get('title') or item.get('title') == '[Removed]':
                        continue
                    
                    article = {
                        'source_title': item.get('title', ''),
                        'source_summary': item.get('description', '') or item.get('content', ''),
                        'source_date': item.get('publishedAt', '')[:10],
                        'source_location': self._extract_location(item),
                        'source_url': item.get('url', ''),
                        'people': self._extract_people(item),
                        'event': self._extract_event(item),
                        'unusual_detail': self._extract_unusual(item),
                        'source_language': lang,
                    }
                    
                    if not self._is_duplicate(article):
                        all_articles.append(article)
                        
            except Exception as e:
                print(f"Error fetching {lang} news: {e}")
                continue
        
        # 隨機打亂並限制數量
        import random
        random.shuffle(all_articles)
        return all_articles[:max_results]
    
    # 相容舊版呼叫
    def fetch_yesterday_news(self, target_date: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """相容舊版：忽略 target_date，直接抓最新新聞"""
        return self.fetch_latest_news(max_results=max_results)
    
    def _extract_location(self, item: Dict) -> str:
        """簡易地點擷取"""
        text = f"{item.get('title', '')} {item.get('description', '')}"
        # 簡單關鍵字匹配，實際可用 NER
        locations = ['台北', '新北', '桃園', '台中', '台南', '高雄', '基隆', '新竹', '苗栗', 
                     '彰化', '南投', '雲林', '嘉義', '屏東', '宜蘭', '花蓮', '台東', '澎湖', '金門', '馬祖']
        for loc in locations:
            if loc in text:
                return loc
        return '未知地點'
    
    def _extract_people(self, item: Dict) -> List[str]:
        """簡易人物擷取"""
        # 實際應用可接 NER，這裡回傳空列表
        return []
    
    def _extract_event(self, item: Dict) -> str:
        """擷取事件核心"""
        title = item.get('title', '')
        desc = item.get('description', '') or ''
        return f"{title}。{desc}"[:200]
    
    def _extract_unusual(self, item: Dict) -> str:
        """擷取異常細節"""
        # 尋找關鍵字
        text = f"{item.get('title', '')} {item.get('description', '')}"
        keywords = ['離奇', '詭異', '神秘', '不明', '怪異', '異常', '失蹤', '死亡', '命案', 
                    '自殺', '謀殺', '詐騙', '邪教', '靈異', '鬼', '怪', '詭']
        for kw in keywords:
            if kw in text:
                return f"含關鍵字：{kw}"
        return '無明顯異常關鍵字'
    
    def _mock_news(self, target_date: str) -> List[Dict[str, Any]]:
        """測試用模擬新聞（含中英文混合）"""
        return [
            {
                'source_title': f'{target_date} 神秘失蹤案：深夜山區發現廢棄車輛',
                'source_summary': '警方在某山區發現一輛廢棄轎車，車內有疑似血跡，駕駛卻無影無蹤。監視器最後捕捉到一道白影閃過。',
                'source_date': target_date,
                'source_location': '新北市',
                'source_url': f'https://mock-news.example.com/{target_date}-case-001',
                'people': ['失蹤者陳○○', '發現者警員'],
                'event': '山區廢棄車輛疑似命案，駕駛失蹤',
                'unusual_detail': '監視器捕捉白影，車內血跡不符車禍特徵',
                'source_language': 'zh',
            },
            {
                'source_title': f'{target_date} 老舊公寓傳出不明低頻震動 住民集體失眠',
                'source_summary': '某棟 40 年公寓近期頻傳低頻嗡鳴聲，多戶住民回報失眠、幻聽，甚至出現集體幻覺。專家檢測卻查不出震源。',
                'source_date': target_date,
                'source_location': '台中市',
                'source_url': f'https://mock-news.example.com/{target_date}-case-002',
                'people': ['住民群體', '物理學家'],
                'event': '公寓不明低頻震動導致集體身心症狀',
                'unusual_detail': '儀器偵測不到聲源，住民描述聲音「像從牆壁裡面傳出」',
                'source_language': 'zh',
            },
            {
                'source_title': f'{target_date} 兒童遊樂設施自動運轉 監視器拍下無人推動畫面',
                'source_summary': '深夜公園監視器拍到旋轉木馬自行轉動，現場無人操作。警方調閱錄影發現畫面中有模糊人影在設施間穿梭。',
                'source_date': target_date,
                'source_location': '高雄市',
                'source_url': f'https://mock-news.example.com/{target_date}-case-003',
                'people': ['巡邏警員', '公園管理員'],
                'event': '遊樂設施無人自轉，監視器拍到不明人影',
                'unusual_detail': '馬達未通電仍持續轉動超過 20 分鐘',
                'source_language': 'zh',
            },
            {
                'source_title': f'{target_date} Abandoned Amusement Park Ride Activates on Its Own',
                'source_summary': 'Security cameras at a closed theme park captured a Ferris wheel rotating without power. Witnesses report hearing calliope music from the abandoned structure.',
                'source_date': target_date,
                'source_location': 'Ohio, USA',
                'source_url': f'https://mock-news.example.com/{target_date}-case-004',
                'people': ['Night watchman', 'Local police'],
                'event': 'Defunct Ferris wheel operates without electricity, eerie music heard',
                'unusual_detail': 'Motor disconnected for 5 years, yet rotated for 40 minutes',
                'source_language': 'en',
            },
            {
                'source_title': f'{target_date} Entire Town Reports Same Dream for 7 Consecutive Nights',
                'source_summary': 'Residents of a small coastal town all describe dreaming of a lighthouse that does not exist. Local university sleep lab confirms synchronized REM patterns.',
                'source_date': target_date,
                'source_location': 'Cornwall, UK',
                'source_url': f'https://mock-news.example.com/{target_date}-case-005',
                'people': ['Town residents', 'Sleep researchers'],
                'event': 'Collective shared dreaming of non-existent lighthouse',
                'unusual_detail': 'EEG shows identical neural signatures across 200+ subjects',
                'source_language': 'en',
            },
        ]
    
    def mark_sources_used(self, articles: List[Dict[str, Any]]):
        """批次標記已使用來源"""
        for article in articles:
            self._mark_used(article)