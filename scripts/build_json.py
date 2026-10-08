import json
import hashlib
import re
from datetime import datetime
from typing import Dict, Any, List
from pathlib import Path


class JSONBuilder:
    """建構 Story JSON 與 Image Prompt JSON"""
    
    def __init__(self, channel_config: Dict[str, Any], content_dir: str = 'content'):
        self.channel_config = channel_config
        self.channel_code = channel_config.get('code', 'CH-666')
        self.content_dir = Path(content_dir)
        self.stories_dir = self.content_dir / 'stories'
        self.counter = self._load_counter()
    
    def _get_counter_file(self) -> Path:
        """每頻道獨立計數器檔案"""
        return Path(f'.story_counter_{self.channel_code}')
    
    def _load_counter(self) -> int:
        """從現有故事檔案找最大編號，避免重複"""
        # 先嘗試讀取頻道專屬 .story_counter（若存在）
        counter_file = self._get_counter_file()
        if counter_file.exists():
            try:
                with open(counter_file, 'r') as f:
                    return int(f.read().strip())
            except:
                pass
        
        # 從現有檔案掃描最大編號（僅掃描該頻道前綴）
        max_num = 0
        prefix = f"{self.channel_code}-"
        if self.stories_dir.exists():
            for f in self.stories_dir.glob(f"{prefix}*.json"):
                if f.name.endswith('_prompts.json'):
                    continue
                try:
                    num = int(f.stem.split('-')[-1])
                    max_num = max(max_num, num)
                except:
                    continue
        return max_num
    
    def _save_counter(self):
        with open(self._get_counter_file(), 'w') as f:
            f.write(str(self.counter))
    
    def _next_story_code(self) -> str:
        self.counter += 1
        self._save_counter()
        return f"{self.channel_code}-{self.counter:04d}"
    
    def _generate_slug(self, title: str) -> str:
        """從標題生成 slug"""
        slug = re.sub(r'[^\w\s-]', '', title.lower())
        slug = re.sub(r'[\s_]+', '-', slug)
        slug = slug.strip('-')
        if len(slug) > 60:
            slug = slug[:60].rstrip('-')
        return slug or 'untitled'
    
    def build_story_json(self, seed: Dict[str, Any], content: str, 
                        dice_result: Dict[str, Any], 
                        director_analysis: Dict[str, Any],
                        provider_used: str) -> Dict[str, Any]:
        """建構完整 Story JSON（舊版：從純文字內容提取欄位）"""
        story_code = self._next_story_code()
        
        title = self._extract_title(content, seed)
        subtitle = self._extract_subtitle(content, seed)
        summary = self._extract_summary(content)
        
        story = {
            'story_code': story_code,
            'channel': self.channel_code,
            'title': title,
            'subtitle': subtitle,
            'slug': self._generate_slug(title),
            'summary': summary,
            'content': content,
            'horror_score': dice_result.get('horror_score', 50),
            'horror_type': dice_result.get('horror_type', []),
            'fantasy_level': dice_result.get('fantasy_level', 'slightly_unreal'),
            'narrative_style': dice_result.get('narrative_style', 'third_person_limited'),
            'pacing': dice_result.get('pacing', 'steady'),
            'ending_type': dice_result.get('ending_type', 'open'),
            'perspective': dice_result.get('perspective', 'witness'),
            'source_date': seed.get('source_date', ''),
            'source_hash': seed.get('source_hash', ''),
            'event_hash': seed.get('event_hash', ''),
            'source_url': seed.get('source_url', ''),
            'provider_used': provider_used,
            'dice_seed': dice_result.get('dice_seed'),
            'director_analysis': director_analysis.get('analysis', {}),
            'created_at': datetime.utcnow().isoformat() + 'Z',
        }
        return story
    
    def build_story_json_from_ai(self, seed: Dict[str, Any], ai_story: Dict[str, Any],
                        dice_result: Dict[str, Any], 
                        director_analysis: Dict[str, Any],
                        provider_used: str) -> Dict[str, Any]:
        """建構完整 Story JSON（新版：直接使用 AI 產生的結構化欄位）"""
        story_code = self._next_story_code()
        
        # 直接使用 AI 產生的欄位，必要時做兜底
        title = ai_story.get('title', '').strip()
        subtitle = ai_story.get('subtitle', '').strip()
        slug = ai_story.get('slug', '').strip()
        content = ai_story.get('content', '').strip()
        
        if not title:
            title = self._extract_title(content, seed)
        if not subtitle:
            subtitle = self._extract_subtitle(content, seed)
        if not slug:
            slug = self._generate_slug(title)
        
        summary = self._extract_summary(content)
        
        story = {
            'story_code': story_code,
            'channel': self.channel_code,
            'title': title,
            'subtitle': subtitle,
            'slug': slug,
            'summary': summary,
            'content': content,
            'horror_score': dice_result.get('horror_score', 50),
            'horror_type': dice_result.get('horror_type', []),
            'fantasy_level': dice_result.get('fantasy_level', 'slightly_unreal'),
            'narrative_style': dice_result.get('narrative_style', 'third_person_limited'),
            'pacing': dice_result.get('pacing', 'steady'),
            'ending_type': dice_result.get('ending_type', 'open'),
            'perspective': dice_result.get('perspective', 'witness'),
            'source_date': seed.get('source_date', ''),
            'source_hash': seed.get('source_hash', ''),
            'event_hash': seed.get('event_hash', ''),
            'source_url': seed.get('source_url', ''),
            'provider_used': provider_used,
            'dice_seed': dice_result.get('dice_seed'),
            'director_analysis': director_analysis.get('analysis', {}),
            'created_at': datetime.utcnow().isoformat() + 'Z',
        }
        return story

    def _extract_title(self, content: str, seed: Dict[str, Any]) -> str:
        """從生成內容中提煉標題（完全不使用新聞標題）"""
        lines = content.strip().split('\n')
        for line in lines[:5]:
            line = line.strip()
            if line and 4 < len(line) < 80 and not line.endswith(('。', '！', '？', '.', '」', '』')):
                if not any(line.startswith(kw) for kw in ['【', '（', '(', '[', '{', '#', '*', '-', '>', '第', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '我', '他', '她', '它']):
                    return line
        
        keywords = ['監視器', '錄影', '影像', '木馬', '旋轉', '夢境', '記憶', '公園', '公寓', '車輛',
                    '失蹤', '命案', '靈異', '鬼', '怪', '詭', '異常', '不明', '神秘',
                    '監控', '鏡頭', '螢幕', '訊號', '頻率', '波', '聲音', '音樂',
                    '燈', '光', '影', '人影', '輪廓', '面孔', '名字', '身份','鏡', '鏡子',
                    '牆', '牆壁', '電梯', '走廊', '地下室', '廢墟', '房間',
                    '門', '窗', '樓梯', '古宅', '凶宅', '祭壇', '陣法', '迷宮', '井',
                    '人形', '洋娃娃', '人偶', '傀儡', '畫', '肖像', '古董', '時鐘', '鐘',
                    '符咒', '儀式', '魔導', '面具', '白骨', '骸骨', '遺物', '詛咒物',
                    '腳步', '敲擊', '低語', '耳語', '哭聲', '笑聲', '氣味', '霧', '濃霧',
                    '血', '骨', '眼睛', '視線', '心臟', '脈動', '雙胞胎', '分身', '幻覺',
                    '時間', '循環', '停滯', '裂縫', '門扉', '重疊', '維度', '消失', '抹消',
                    '預言', '詛咒', '啟示', '異界', '結界', '怪物', '巨獸', '倒錯']
        
        for kw in keywords:
            if kw in content:
                sentences = re.split(r'[。！？]', content)
                for s in sentences:
                    if kw in s and 10 < len(s) < 60:
                        return s.strip() + '…'
        
        return f"{self.channel_code} 案件檔案 #{seed.get('source_hash', 'XXXX')[:4].upper()}"
    
    def _extract_subtitle(self, content: str, seed: Dict[str, Any]) -> str:
        """從生成內容提煉副標題（不使用新聞地名/細節）"""
        scene_keywords = {
            '監視器': '監視系統異常', '監控': '監控系統異常', '錄影': '錄影異常', '影像': '影像異常',
            '木馬': '遊樂設施自運', '旋轉': '旋轉異常', '夢境': '共享夢境', '夢': '夢境異常',
            '記憶': '記憶交換', '公園': '公園異象', '公寓': '住宅異象', '車輛': '車輛異象',
            '失蹤': '失蹤事件', '命案': '命案疑雲', '靈異': '靈異現象', '鬼': '鬼影現蹤',
            '怪': '怪異事件', '詭': '詭譎現象', '異常': '異常現象', '不明': '不明現象',
            '神秘': '神秘事件', '監控室': '監控室異象', '螢幕': '螢幕異象', '訊號': '訊號干擾',
            '頻率': '頻率異常', '聲音': '聲音異常', '音樂': '音樂異象', '燈': '燈光異象',
            '人影': '人影異象', '面孔': '面孔消失', '名字': '名字遺忘', '身份': '身份瓦解',
            '鏡': '鏡像異界', '鏡子': '鏡中世界', '牆壁': '牆面滲水', '電梯': '未知樓層',
            '走廊': '無盡迴廊', '地下室': '禁忌空間', '廢墟': '遺構異變', '房間': '密室異象',
            '門': '虛無之門', '窗': '窗外窺視', '樓梯': '迴旋階梯', '古宅': '凶宅怪譚',
            '人形': '活化傀儡', '洋娃娃': '詛咒人形', '人偶': '肢體異變', '畫': '畫像顯靈',
            '肖像': '詛咒畫作', '古董': '遺物附魔', '時鐘': '逆行時針', '鐘': '異界鐘聲',
            '符咒': '封印破裂', '儀式': '召喚陣式', '祭壇': '血祭異象', '書': '禁忌魔導',
            '影子': '影跡分離', '腳步': '未知足音', '敲擊': '牆內敲擊', '低語': '耳語呢喃',
            '哭聲': '夜半啼哭', '笑聲': '詭異笑聲', '氣味': '腐朽異味', '霧': '迷霧籠罩',
            '血': '血色異象', '骨': '骸骨現形', '眼睛': '複數視線', '心臟': '異樣脈動',
            '雙胞胎': '分身現象', '影子人': '黑影徘徊', '幻覺': '感知扭曲',
            '時間': '時間循環', '停滯': '時空停滯', '裂縫': '空間裂隙', '門扉': '異界入口',
            '重疊': '維度重疊', '消失': '存在抹消', '預言': '末日啟示', '詛咒': '古老詛咒',
            # CH-333 關鍵字
            '附身': '附身憑依', '憑依': '附身憑依', '鬧鬼': '鬧鬼糾纏', '儀式': '禁忌儀式',
            '詛咒': '詛咒傳承', '通靈': '通靈媒介', '祖業': '祖業因果', '契約': '靈體契約',
            '驅魔': '驅魔對抗', '陰間': '陰間窺見', '民間': '民間信仰',
            # CH-999 關鍵字
            '認知': '認知危害', '模因': '模因傳染', '本體': '本體論恐怖', '宇宙': '宇宙恐怖',
            '極端': '極端體驗恐怖', '時間閉環': '時間閉環', '禁忌知識': '禁忌知識', '末世': '末世啟示',
        }
        
        for kw, desc in scene_keywords.items():
            if kw in content:
                return f"{self.channel_code} 檔案 // {desc}"
        
        return f"{self.channel_code} 檔案 // 未知異常現象"
    
    def _extract_summary(self, content: str, max_len: int = 200) -> str:
        """提煉摘要（前 200 字）"""
        text = re.sub(r'\s+', ' ', content.strip())
        if len(text) <= max_len:
            return text
        truncated = text[:max_len]
        last_period = max(truncated.rfind('。'), truncated.rfind('！'), truncated.rfind('？'))
        if last_period > max_len * 0.5:
            return truncated[:last_period + 1]
        return truncated + '…'
    
    def build_image_prompts(self, story: Dict[str, Any], 
                           director_analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """建構 Image Prompts"""
        analysis = director_analysis.get('analysis', {})
        setting = analysis.get('setting_core', '')
        anomaly = analysis.get('anomaly_core', '')
        fantasy = story.get('fantasy_level', '')
        horror_types = story.get('horror_type', [])
        
        # 基礎風格關鍵字
        style_keywords = [
            "CH-666 aesthetic", "retro CRT", "analog horror", "scanlines",
            "static noise", "VHS tracking error", "phosphor green glow",
            "deep shadows", "cinematic lighting", "unsettling atmosphere"
        ]
        
        # 不同頻道的視覺風格調整
        channel_visual = {
            'CH-666': "phosphor green glow, scanlines, VHS static, analog horror, surveillance aesthetic",
            'CH-333': "candlelight flicker, incense smoke, talisman symbols, ritualistic atmosphere, warm amber tones",
            'CH-999': "harsh red warning lights, data corruption, glitch artifacts, cognitive hazard symbols, stark clinical lighting",
        }.get(self.channel_code, style_keywords[0])
        
        fantasy_visual = {
            'grounded': "photorealistic, documentary style, gritty realism, natural lighting",
            'slightly_unreal': "slightly off-kilter, subtle wrongness, uncanny valley, muted colors",
            'supernatural': "ethereal glow, spectral presence, impossible geometry, otherworldly",
            'reality_bending': "reality distortion, fractal patterns, melting surfaces, glitch reality",
            'mythic': "divine radiance, ancient symbols, mythic scale, legendary atmosphere",
            'conceptual': "abstract concepts visualized, information as geometry, memetic patterns",
        }.get(fantasy, "")
        
        prompts = []
        
        cover_prompt = f"""
{channel_visual}, {style_keywords[3]}, {style_keywords[4]}, {fantasy_visual}.
Scene: {setting}. Core anomaly: {anomaly}.
Horror types: {', '.join(horror_types)}.
Composition: centered, ominous, negative space, rule of thirds.
Color palette: #0A0A0C background, #00FF88 accent, #FF0055 warning, #E0E0E0 highlights.
""".strip()
        
        prompts.append({'type': 'cover', 'prompt': cover_prompt})
        
        scene_prompt = f"""
{channel_visual}, {style_keywords[5]}, {style_keywords[6]}, {fantasy_visual}.
Key moment from story: {anomaly} manifesting in {setting}.
Perspective: {story.get('perspective', 'witness')}.
Mood: dread, anticipation, the moment before revelation.
Analog texture: film grain, vignetting, chromatic aberration.
""".strip()
        
        prompts.append({'type': 'scene', 'prompt': scene_prompt})
        
        return prompts