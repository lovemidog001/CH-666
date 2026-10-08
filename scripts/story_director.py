import json
import random
from typing import Dict, Any, List
from pathlib import Path


class StoryDirector:
    """AI Story Director - 分析 Story Seed 決定故事方向"""
    
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
    
    def analyze_seed(self, seed: Dict[str, Any]) -> Dict[str, Any]:
        """
        分析 Story Seed 核心元素
        返回：異常核心、人物核心、場景核心、衝突核心、未知核心、現實程度
        """
        source_title = seed.get('source_title', '')
        source_summary = seed.get('source_summary', '')
        event = seed.get('event', '')
        unusual = seed.get('unusual_detail', '')
        location = seed.get('source_location', '')
        people = seed.get('people', [])
        
        # 異常核心：從 unusual_detail 與標題推導
        anomaly_core = self._extract_anomaly_core(source_title, source_summary, unusual)
        
        # 人物核心：從 people 與事件推導
        character_core = self._extract_character_core(people, event)
        
        # 場景核心：從地點與事件推導
        setting_core = self._extract_setting_core(location, event, source_summary)
        
        # 衝突核心：核心張力
        conflict_core = self._extract_conflict_core(event, anomaly_core, character_core)
        
        # 未知核心：無法解釋的部分
        unknown_core = self._extract_unknown_core(unusual, anomaly_core)
        
        # 現實程度：0-100，越高越寫實
        reality_level = self._assess_reality_level(anomaly_core, unknown_core, setting_core)
        
        return {
            'anomaly_core': anomaly_core,
            'character_core': character_core,
            'setting_core': setting_core,
            'conflict_core': conflict_core,
            'unknown_core': unknown_core,
            'reality_level': reality_level,
        }
    
    def _extract_anomaly_core(self, title: str, summary: str, unusual: str) -> str:
        """提煉異常核心"""
        combined = f"{title} {summary} {unusual}"
        # 關鍵字映射
        anomaly_map = {
            '失蹤': '人員神秘消失',
            '死亡': '非自然死亡',
            '命案': '謀殺案件',
            '自殺': '可疑自殺',
            '靈異': '超自然現象',
            '鬼': '鬼魂實體',
            '怪': '未知生物',
            '詭': '詭異現象',
            '不明': '未知力量',
            '神秘': '神秘事件',
            '幻覺': '感知扭曲',
            '幻聽': '聽覺異常',
            '震動': '物理法則異常',
            '低頻': '聲波異常',
            '監視器': '監控影像異常',
            '白影': '不明實體',
            '血跡': '暴力痕跡',
            '廢棄': '被遺棄空間',
            '老舊': '時空扭曲',
            '集體': '群體性異常',
            '無人': '自發性現象',
        }
        
        for kw, core in anomaly_map.items():
            if kw in combined:
                return core
        return '未明異常現象'
    
    def _extract_character_core(self, people: List[str], event: str) -> str:
        """提煉人物核心"""
        if not people:
            return '無名目擊者'
        # 取第一個關鍵人物
        return people[0]
    
    def _extract_setting_core(self, location: str, event: str, summary: str) -> str:
        """提煉場景核心"""
        settings = {
            '山區': '深山廢棄路段',
            '公寓': '老舊公寓走廊',
            '公園': '深夜荒涼公園',
            '醫院': '廢棄醫療設施',
            '學校': '夜間校園',
            '隧道': '幽長隧道',
            '湖邊': '霧鎖湖畔',
            '廟宇': '古老廟宇',
            '井': '枯竭古井',
            '鏡子': '破碎鏡面',
        }
        for kw, setting in settings.items():
            if kw in location or kw in event or kw in summary:
                return setting
        return f'{location}某處'
    
    def _extract_conflict_core(self, event: str, anomaly: str, character: str) -> str:
        """提煉衝突核心"""
        conflicts = [
            '真相與生存的抉擇',
            '理智與瘋狂的邊界',
            '記憶與現實的撕裂',
            '人性與非人性的對峙',
            '逃離與面對的掙扎',
            '信任與背叛的迷宮',
            '時間循環中的掙扎',
            '身份認同的崩解',
        ]
        # 簡單哈希選擇
        idx = hash(event + anomaly + character) % len(conflicts)
        return conflicts[idx]
    
    def _extract_unknown_core(self, unusual: str, anomaly: str) -> str:
        """提煉未知核心"""
        unknowns = [
            '幕後操控者的真實身分',
            '異常現象的物理機制',
            '倖存者失去的記憶',
            '事件與傳說的關聯',
            '現實裂縫的擴散範圍',
            '被遺忘的歷史真相',
            '觀測者效應的反噬',
            '時間線的錯位點',
        ]
        idx = hash(unusual + anomaly) % len(unknowns)
        return unknowns[idx]
    
    def _assess_reality_level(self, anomaly: str, unknown: str, setting: str) -> int:
        """評估現實程度 0-100"""
        # 基礎分數
        base = 50
        
        # 異常類型影響
        supernatural_kw = ['鬼', '靈', '超自然', '詛咒', '魔法', '異界', '實體']
        sci_fi_kw = ['實驗', '基因', 'AI', '機器', '外星', '維度', '量子']
        crime_kw = ['命案', '謀殺', '詐騙', '綁架', '毒品', '黑道']
        
        text = f"{anomaly} {unknown} {setting}"
        
        if any(kw in text for kw in supernatural_kw):
            base -= 30
        if any(kw in text for kw in sci_fi_kw):
            base -= 10
        if any(kw in text for kw in crime_kw):
            base += 20
        
        return max(0, min(100, base))
    
    def decide_direction(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        根據分析結果決定故事方向（供 Director Dice 參考）
        """
        reality = analysis.get('reality_level', 50)
        
        # 現實程度影響 Horror Type 傾向
        if reality > 70:
            preferred_horror = ['psychological', 'crime', 'suspense', 'reality_horror', 'identity_horror']
            preferred_fantasy = ['grounded', 'slightly_unreal']
        elif reality > 40:
            preferred_horror = ['psychological', 'urban_legend', 'surveillance_horror', 'unknown_phenomenon']
            preferred_fantasy = ['slightly_unreal', 'supernatural']
        else:
            preferred_horror = ['supernatural', 'urban_legend', 'sci_fi_horror', 'unknown_phenomenon']
            preferred_fantasy = ['supernatural', 'reality_bending']
        
        return {
            'preferred_horror_types': preferred_horror,
            'preferred_fantasy_levels': preferred_fantasy,
            'analysis': analysis,
        }