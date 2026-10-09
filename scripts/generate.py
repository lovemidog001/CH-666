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
- {style_desc}
- 類型：{horror_types}
- 色調：#0A0A0C (深空黑) {color} (主色) #FF0055 (警示紅) #E0E0E0 (磷光白)

【故事參數】
- Horror Score: {dice.get('horror_score')}/100
- Horror Type: {', '.join(dice.get('horror_type', []))}
- Fantasy Level: {dice.get('fantasy_level')}
- Narrative Style: {style}
- Pacing: {pacing}
- Ending Type: {ending}
- Perspective: {persp}

【種子分析】(將由用戶提示提供)

【嚴格輸出格式 (JSON only)】
{{
  "title": "故事標題（15-40字，吸睛、具體、帶懸念，不含新聞式前綴）",
  "subtitle": "副標題（{self.cat['name']} 檔案 // 核心異常描述）",
  "slug": "url-friendly-slug（小寫、連字號、不超過60字）",
  "content": "完整故事內容（段落換行、文件式格式、偽紀錄格式，至少 1500 字，繁體中文）"
}}

【核心原則】
1. 原創性：新聞只是觸發點，必須重新設計人物、場景、事件、因果、異常、敘事角度、結局
2. 內部邏輯：所有超自然元素必須有內在一致規則
3. 恐怖質感：靠氛圍、心理、未知感營造，非靠血腥/驚嚇
4. 風味：像深夜檔案、機密記錄、研究日誌、發現的錄影帶
5. 嚴禁：新聞標題/地名/人名/機構名/確切時間/機關單位/「據報導」「警方表示」等新聞用語
6. 必須：虛構場景/代號/原型角色/超自然規則系統/繁體中文
"""

    def _build_user_prompt(self, seed: Dict[str, Any], dice: Dict[str, Any]) -> str:
        return f"""【Story Seed DNA（僅供提煉核心元素，嚴禁直接使用任何新聞原文）】
核心地點氛圍：{seed.get('source_location', '')}
核心異常現象：{seed.get('unusual_detail', '')}
事件核心概念：{seed.get('event', '')}
關鍵人物原型：{', '.join(seed.get('people', [])) or '無具體人物，請自行設計原創角色'}

【任務】
以此 Seed DNA 為靈感觸發點，創作一篇**完全原創**的 {self.cat['name']} 風格恐怖故事。

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