import json
import os
import re
from typing import Dict, Any, List, Optional
from pathlib import Path

from ai_providers import get_providers, AIProvider
from config_loader import Config


class StoryGenerator:
    """故事生成器 - AI 直接輸出結構化 JSON，參考 news-bot 模式"""
    
    def __init__(self, providers_config: List[Dict[str, Any]], channel_config: Dict[str, Any]):
        self.providers = get_providers(providers_config)
        self.channel_config = channel_config
        
        if not self.providers:
            raise RuntimeError("No available AI providers (check API keys)")
    
    def generate(self, seed: Dict[str, Any], dice_result: Dict[str, Any], 
                 director_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成故事，AI 直接輸出 JSON 結構
        返回：{'story': dict, 'provider_used': str, 'success': bool}
        """
        system_prompt = self._build_system_prompt(dice_result, director_analysis)
        user_prompt = self._build_user_prompt(seed, dice_result, director_analysis)
        
        last_error = None
        for provider in self.providers:
            try:
                print(f"Trying provider: {provider.name} ({provider.model})")
                raw = provider.generate(user_prompt, system_prompt)
                
                story = self._safe_parse_json(raw)
                if not story:
                    last_error = "AI 回傳非合法 JSON"
                    print(f"  ⚠️ {provider.name}: JSON 解析失敗")
                    continue
                
                # 驗證必要欄位
                if not self._validate_story(story):
                    last_error = "AI 回傳 JSON 缺少必要欄位"
                    print(f"  ⚠️ {provider.name}: 缺少必要欄位")
                    continue
                
                print(f"  ✅ {provider.name} 成功")
                return {
                    'story': story,
                    'provider_used': provider.id,
                    'success': True,
                }
                    
            except Exception as e:
                last_error = str(e)
                print(f"  ❌ {provider.name} 失敗: {e}")
                continue
        
        return {
            'story': None,
            'provider_used': 'none',
            'success': False,
            'error': f'All providers failed. Last error: {last_error}',
        }
    
    def _safe_parse_json(self, text: str) -> Optional[Dict]:
        """安全解析 JSON，支援 markdown code block"""
        if not text:
            return None
        # 移除 markdown code block
        text = re.sub(r'^```(?:json)?\s*', '', text.strip())
        text = re.sub(r'\s*```$', '', text)
        # 嘗試直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 嘗試提取第一個完整 JSON 物件
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        return None
    
    def _validate_story(self, story: Dict) -> bool:
        """驗證故事必要欄位"""
        required = ['title', 'subtitle', 'content', 'slug']
        for field in required:
            if not story.get(field) or not str(story[field]).strip():
                print(f"    缺少欄位: {field}")
                return False
        return True
    
    def _build_system_prompt(self, dice_result: Dict[str, Any], 
                            director_analysis: Dict[str, Any]) -> str:
        analysis = director_analysis.get('analysis', {})
        
        return f"""你是 CH-666 怪聞頻道的故事導演。請根據參數創作一篇原創恐怖故事，**直接輸出 JSON**，不要任何額外文字。

【頻道風格】
- Retro CRT / Late-night TV / 廢棄監控系統 / 電影感恐怖 / 神秘資料庫
- 類型：心理恐怖、都市怪談、超自然、犯罪、懸疑、身份恐怖、科幻恐怖、監視器恐怖、未知現象、現實恐怖
- 色調：#0A0A0C (深空黑) #00FF88 (螢光綠) #FF0055 (警示紅) #E0E0E0 (磷光白)

【故事參數】
- Horror Score: {dice_result.get('horror_score')}/100
- Horror Type: {', '.join(dice_result.get('horror_type', []))}
- Fantasy Level: {dice_result.get('fantasy_level')}
- Narrative Style: {dice_result.get('narrative_style')}
- Pacing: {dice_result.get('pacing')}
- Ending Type: {dice_result.get('ending_type')}
- Perspective: {dice_result.get('perspective')}

【種子分析】
- 異常核心: {analysis.get('anomaly_core', '')}
- 人物核心: {analysis.get('character_core', '')}
- 場景核心: {analysis.get('setting_core', '')}
- 衝突核心: {analysis.get('conflict_core', '')}
- 未知核心: {analysis.get('unknown_core', '')}
- 現實程度: {analysis.get('reality_level', 50)}/100

【嚴格輸出格式 (JSON only)】
{{
  "title": "故事標題（不含新聞式前綴，15-40字，吸睛、具體、帶懸念）",
  "subtitle": "副標題（CH-666 檔案 // 核心異常描述，如：監視系統異常、記憶交換、遊樂設施自運）",
  "slug": "url-friendly-slug（小寫、連字號、不超過60字）",
  "content": "完整故事內容（可含段落換行、文件式格式、偽紀錄格式，至少 1500 字）"
}}

【核心原則】
1. **原創性**：新聞只是觸發點，必須重新設計人物、場景、事件、因果、異常、敘事角度、結局
2. **內部邏輯**：所有超自然元素必須有內在一致規則
3. **恐怖質感**：靠氛圍、心理、未知感營造，非靠血腥/驚嚇
4. **CH-666 風味**：像深夜電視台播放的檔案、監控紀錄、訪談筆錄、發現的錄影帶
5. **嚴禁**：新聞標題/地名/人名/機構名/確切時間/機關單位/「據報導」「警方表示」等新聞用語
6. **必須**：虛構場景/代號/原型角色/超自然規則系統/繁體中文
"""
    
    def _build_user_prompt(self, seed: Dict[str, Any], dice_result: Dict[str, Any],
                          director_analysis: Dict[str, Any]) -> str:
        location = seed.get('source_location', '')
        unusual = seed.get('unusual_detail', '')
        event_core = seed.get('event', '')
        people = seed.get('people', [])
        lang = seed.get('source_language', 'zh')
        
        lang_instruction = "請用繁體中文創作。" if lang == 'zh' else "請用繁體中文創作（素材來源為英文新聞）。"
        
        return f"""【Story Seed DNA（僅供提煉核心元素，嚴禁直接使用任何新聞原文）】
核心地點氛圍：{location}
核心異常現象：{unusual}
事件核心概念：{event_core}
關鍵人物原型：{', '.join(people) or '無具體人物，請自行設計原創角色'}

【任務】
以此 Seed DNA 為靈感觸發點，創作一篇**完全原創**的 CH-666 風格恐怖故事。

⚠️ 絕對禁止：
- 直接使用/改寫新聞標題（如「高雄市｜馬達未通電仍持續轉動超過 20 分鐘」）
- 保留具體地名/人名/機構名/確切時間/機關單位
- 新聞報導式敘述、「據報導」「警方表示」等新聞用語

✅ 必須：
- 完全重新設計：主角名字/身份/背景、虛構場景、時間線、因果鏈、異常機制、敘事結構、結局
- 只保留「核心異常性質」作為靈感核心
- 真實地點→虛構地標/區域代號，真實人物→代號/職業/關係網
- 建立內部一致的超自然規則系統
- {lang_instruction}
- **直接輸出 JSON**，不要任何額外文字、解釋、markdown 標記
"""