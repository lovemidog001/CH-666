import os
import json
import re
import time
import requests
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod


class AIProvider(ABC):
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.id = config['id']
        self.name = config['name']
        self.model = config['model']
        self.api_key = os.environ.get(config['api_key_env'], '')
        self.base_url = config['base_url']
        self.timeout = config.get('timeout', 120)
        self.max_tokens = config.get('max_tokens', 8000)
        self.temperature = config.get('temperature', 0.7)
        self.max_retries = config.get('max_retries', 3)
        self.retry_delay = config.get('retry_delay', 5)

    @abstractmethod
    def _make_request(self, messages: List[Dict], system: str) -> str:
        pass

    def generate(self, prompt: str, system: str = '') -> str:
        if not self.api_key:
            raise ValueError(f"{self.name}: API key not set")

        messages = []
        if system:
            messages.append({'role': 'system', 'content': system})
        messages.append({'role': 'user', 'content': prompt})

        last_err = None
        for attempt in range(self.max_retries):
            try:
                return self._make_request(messages, system)
            except requests.exceptions.Timeout as e:
                last_err = f"Timeout: {e}"
            except requests.exceptions.ConnectionError as e:
                last_err = f"Connection: {e}"
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response else 0
                last_err = f"HTTP {status}: {e}"
                if not (500 <= status < 600):
                    raise
            except Exception as e:
                last_err = str(e)

            if attempt < self.max_retries - 1:
                delay = self.retry_delay * (2 ** attempt)
                print(f"  ⚠️ {self.name} retry {attempt+1}/{self.max_retries} after {delay}s: {last_err}")
                time.sleep(delay)

        raise Exception(f"{self.name} failed after {self.max_retries} retries: {last_err}")

    def is_available(self) -> bool:
        return bool(self.api_key)


class NVIDIAProvider(AIProvider):
    def _make_request(self, messages: List[Dict], system: str) -> str:
        headers = {'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json'}
        data = {'model': self.model, 'messages': messages, 'max_tokens': self.max_tokens,
                'temperature': self.temperature, 'stream': False}
        resp = requests.post(f'{self.base_url}/chat/completions', headers=headers, json=data, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()['choices'][0]['message']['content']


class OpenAIProvider(AIProvider):
    def _make_request(self, messages: List[Dict], system: str) -> str:
        headers = {'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json'}
        data = {'model': self.model, 'messages': messages, 'max_tokens': self.max_tokens,
                'temperature': self.temperature}
        resp = requests.post(f'{self.base_url}/chat/completions', headers=headers, json=data, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()['choices'][0]['message']['content']


class GoogleProvider(AIProvider):
    def _make_request(self, messages: List[Dict], system: str) -> str:
        url = f'{self.base_url}/models/{self.model}:generateContent?key={self.api_key}'
        parts = []
        if system:
            parts.append({'text': f'System: {system}'})
        parts.append({'text': messages[-1]['content']})
        data = {'contents': [{'parts': parts}],
                'generationConfig': {'maxOutputTokens': self.max_tokens, 'temperature': self.temperature}}
        resp = requests.post(url, json=data, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()['candidates'][0]['content']['parts'][0]['text']


class AgnesProvider(AIProvider):
    def _make_request(self, messages: List[Dict], system: str) -> str:
        headers = {'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json'}
        data = {'model': self.model, 'messages': messages, 'max_tokens': self.max_tokens,
                'temperature': self.temperature}
        resp = requests.post(f'{self.base_url}/chat/completions', headers=headers, json=data, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()['choices'][0]['message']['content']


PROVIDER_MAP = {
    'nvidia': NVIDIAProvider,
    'openai': OpenAIProvider,
    'google': GoogleProvider,
    'agnes': AgnesProvider,
}


def create_provider(config: Dict[str, Any]) -> AIProvider:
    cls = PROVIDER_MAP.get(config['id'])
    if not cls:
        raise ValueError(f"Unknown provider: {config['id']}")
    return cls(config)


def get_providers(configs: List[Dict]) -> List[AIProvider]:
    enabled = [c for c in configs if c.get('enabled')]
    enabled.sort(key=lambda x: x.get('priority', 999))
    return [create_provider(c) for c in enabled if create_provider(c).is_available()]


class StoryGenerator:
    """Generate story JSON from seed + dice params using AI."""

    def __init__(self, providers: List[AIProvider], cat_config: Dict[str, Any]):
        self.providers = providers
        self.cat = cat_config
        self.category = cat_config['category']
        self.genre_labels = self._build_labels()

    def _build_labels(self) -> Dict[str, str]:
        labels = {}
        # Handle both formats: [{'key': 'x', 'label': 'y'}] or ['x', 'y']
        for h in self.cat.get('horror_types', []):
            if isinstance(h, dict):
                labels[h['key']] = h.get('label', h['key'])
            else:
                labels[h] = h  # string key
        for f in self.cat.get('fantasy_levels', []):
            if isinstance(f, dict):
                labels[f['key']] = f.get('label', f['key'])
            else:
                labels[f] = f
        return labels

    def _build_system_prompt(self, dice: Dict[str, Any]) -> str:
        horror_types = ', '.join(self.genre_labels.get(h, h) for h in dice.get('horror_type', []))
        fantasy = self.genre_labels.get(dice.get('fantasy_level', ''), dice.get('fantasy_level', ''))
        style = dice.get('narrative_style', '')
        pacing = dice.get('pacing', '')
        ending = dice.get('ending_type', '')
        persp = dice.get('perspective', '')

        genre_styles = {
            'occult': 'Candlelight / Incense / Talismans / Ritualistic / Ancient Archives',
            'anomalous': 'Retro CRT / Late-night TV / 廢棄監控系統 / 電影感恐怖 / 神秘資料庫',
            'forbidden': 'Harsh Red Alerts / Data Corruption / Cognitive Hazards / Clinical Archives / Stark Lighting',
        }
        style_desc = genre_styles.get(self.cat.get('genre', 'anomalous'), genre_styles['anomalous'])
        color = self.cat.get('color', '#00ff88')

        return f"""你是 {self.cat['name']} ({self.cat['label']}) 的故事導演。請根據參數創作一篇原創恐怖故事，**直接輸出 JSON**，不要任何額外文字。
【頻道風格】
- 描述：{style_desc}
- 類型：{horror_types}
- 色調視覺：#0A0A0C (深空黑) | {color} (主色) | #FF0055 (警示紅) | #E0E0E0 (磷光白)

【故事參數】
- 恐怖指數：{dice.get('horror_score')}/100
- 恐怖類型：{horror_types_str}
- 奇幻/超自然程度：{dice.get('fantasy_level')}
- 敘事風格：{style}
- 節奏：{pacing}
- 結局類型：{ending}
- 敘事視角：{persp}

【核心寫作原則】
1. 原創轉化：新聞僅為靈感觸發點，必須徹底重構人物、場景、事件因果與超自然規則。
2. 內部邏輯：超自然異常必須具備一套「自洽且一致」的運作規則。
3. 氛圍優先：著重於心理壓迫、未知感與環境異樣感，嚴禁依賴血腥/純嚇人手法。
4. 文件質感：呈現深夜檔案、機密紀錄、研究日誌、遺留錄音/錄影帶文本的真實感。

【內文易讀性與排版規範（極重要）】
- 嚴禁出現大篇幅未分段的文字牆！
- 每段長度控制在 2-4 句話內，段落之間必須使用雙換行（\\n\\n）隔開。
- 善用文件結構標籤（例如：`[記錄開始]`、`【異常觀察日記 #02】`、`[錄音檔結束]`）劃分單元。
- 重要資訊或超自然規則可適度使用清單/列點（- 或 1.）呈現，大幅提升閱讀體驗。

【嚴格禁止（Negative Constraints）】
- 嚴禁出現新聞報導用語（如：「據報導」、「警方表示」、「新聞記者」、「本報訊」）。
- 严禁保留真實地名、人名、機構名、確切年代/日期、官方單位名稱。
- 嚴禁直接引用或輕度改寫新聞原文。

【輸出格式規範】
- 必須僅輸出合法單一 JSON 物件，嚴禁包含任何額外的開頭/結尾說明文字或 Markdown 程式碼塊標籤（如 ```json）。
- 所有故事內容請使用「繁體中文」。

JSON Schema：
{{
  "title": "故事標題（15-40字，具懸念、吸睛、具體，嚴禁新聞標題格式）",
  "subtitle": "副標題（格式：{self.cat['name']} 檔案 // 核心異常短述）",
  "slug": "url-friendly-slug（僅限小寫英文字母、數字與連字號 -，長度 <= 60 字）",
  "content": "完整故事內文（須包含顯著段落換行 \\n\\n、文件章節標籤，版面舒適易讀，字數至少 1500 字，繁體中文）"
}}"""

    def _build_user_prompt(self, seed: Dict[str, Any], dice: Dict[str, Any]) -> str:
        """構建用戶層級 Prompt，提供 Seed DNA 並觸發故事生成"""

        people_info = (
            ", ".join(seed.get("people", []))
            if seed.get("people")
            else "無具體人物，請自行設計原創角色與原型"
        )

        return f"""【Story Seed DNA】
- 核心地點氛圍：{seed.get('source_location', '')}
- 核心異常現象：{seed.get('unusual_detail', '')}
- 事件核心概念：{seed.get('event', '')}
- 關鍵人物原型：{people_info}

【生成任務】
請以此 Seed DNA 為「純粹靈感」，創作一篇完全原創的 {self.cat['name']} 風格恐怖怪談故事。

【執行檢查清單】
1. 地點轉化：真實地點 ➔ 虛構區域代號/模糊化地標（例：S區7號水塘）。
2. 人物轉化：真實人物 ➔ 原創姓名/代號/職業背景。
3. 規則設計：構建一套專屬該異常現象的內部運作邏輯與禁忌。
4. 排版確認：內文必須段落分明（\\n\\n），使用檔案結構標籤劃分章節，禁止文字黏在一起！
5. 格式確認：確保內容長度 > 1500 字，並完全符合 JSON 結構。

⚠️ 絕對禁止：
- 直接使用/改寫新聞標題
- 保留具體地名/人名/機構名/確切時間/機關單位
- 新聞報導式敘述、「據報導」「警方表示」等新聞用語

✅ 必須：
- 完全重新設計：主角名字/身份/背景、虛構場景、時間線、因果鏈、異常機制、敘事結構、結局
- 只保留「核心異常性質」作為靈感核心
- 真實地點→虛構地標/區域代號，真實人物→代號/職業/關係網
- 建立內部一致的超自然規則系統
- 請用繁體中文創作
- **直接輸出 JSON**，不要任何額外文字、解釋、markdown 標記
"""

    def _safe_parse_json(self, text: str) -> Optional[Dict]:
        if not text:
            return None
        text = re.sub(r'^```(?:json)?\s*', '', text.strip())
        text = re.sub(r'\s*```$', '', text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except:
                    pass
        return None

    def _validate_fields(self, story: Dict) -> bool:
        for f in ['title', 'subtitle', 'content', 'slug']:
            if not story.get(f) or not str(story[f]).strip():
                print(f"    缺少欄位: {f}")
                return False
        if len(story.get('content', '')) < 1000:
            print(f"    內容過短: {len(story.get('content', ''))} 字")
            return False
        return True

    def generate(self, seed: Dict[str, Any], dice: Dict[str, Any]) -> Dict[str, Any]:
        system = self._build_system_prompt(dice)
        user = self._build_user_prompt(seed, dice)

        for provider in self.providers:
            print(f"Trying provider: {provider.name} ({provider.model})")
            try:
                raw = provider.generate(user, system)
                story = self._safe_parse_json(raw)
                if not story:
                    print(f"  ⚠️ JSON parse failed")
                    continue
                if not self._validate_fields(story):
                    continue
                print(f"  ✅ {provider.name} 成功")
                return {'story': story, 'provider_used': provider.id, 'success': True}
            except Exception as e:
                print(f"  ❌ {provider.name} 失敗: {e}")
                continue

        return {'story': None, 'provider_used': 'none', 'success': False,
                'error': 'All providers failed'}
