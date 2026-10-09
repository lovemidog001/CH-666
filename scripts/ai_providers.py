import os
import json
import time
import requests
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod


class AIProvider(ABC):
    """AI Provider 抽象基類"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.id = config.get('id')
        self.name = config.get('name')
        self.model = config.get('model')
        self.api_key_env = config.get('api_key_env')
        self.base_url = config.get('base_url')
        self.timeout = config.get('timeout', 30)
        self.max_tokens = config.get('max_tokens', 8000)
        self.temperature = config.get('temperature', 0.7)
        self.api_key = os.environ.get(self.api_key_env, '')
        # Retry 設定
        self.max_retries = config.get('max_retries', 3)
        self.retry_delay = config.get('retry_delay', 5)  # 秒
    
    @abstractmethod
    def generate(self, prompt: str, system_prompt: str = '') -> str:
        """生成故事內容"""
        pass
    
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    def _make_request_with_retry(self, request_func):
        """帶重試機制的請求執行"""
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return request_func()
            except requests.exceptions.Timeout as e:
                last_error = f"Timeout after {self.timeout}s: {e}"
                print(f"  ⚠️ {self.name} 請求超時 (嘗試 {attempt + 1}/{self.max_retries})")
            except requests.exceptions.ConnectionError as e:
                last_error = f"Connection error: {e}"
                print(f"  ⚠️ {self.name} 連線錯誤 (嘗試 {attempt + 1}/{self.max_retries})")
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response else 'unknown'
                last_error = f"HTTP {status}: {e}"
                # 5xx 錯誤重試，4xx 不重試
                if e.response and 500 <= e.response.status_code < 600:
                    print(f"  ⚠️ {self.name} 伺服器錯誤 {status} (嘗試 {attempt + 1}/{self.max_retries})")
                else:
                    raise
            except Exception as e:
                last_error = str(e)
                print(f"  ⚠️ {self.name} 未預期錯誤: {e} (嘗試 {attempt + 1}/{self.max_retries})")
            
            if attempt < self.max_retries - 1:
                delay = self.retry_delay * (2 ** attempt)  # 指數退避
                print(f"  ⏳ 等待 {delay}s 後重試...")
                time.sleep(delay)
        
        raise Exception(f"All retries failed. Last error: {last_error}")


class NVIDIAProvider(AIProvider):
    def generate(self, prompt: str, system_prompt: str = '') -> str:
        if not self.api_key:
            raise ValueError("NVIDIA_API_KEY not set")
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }
        
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': prompt})
        
        data = {
            'model': self.model,
            'messages': messages,
            'max_tokens': self.max_tokens,
            'temperature': self.temperature,
            'stream': False,
        }
        
        def make_request():
            response = requests.post(
                f'{self.base_url}/chat/completions',
                headers=headers,
                json=data,
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()
            return result['choices'][0]['message']['content']
        
        return self._make_request_with_retry(make_request)


class OpenAIProvider(AIProvider):
    def generate(self, prompt: str, system_prompt: str = '') -> str:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set")
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }
        
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': prompt})
        
        data = {
            'model': self.model,
            'messages': messages,
            'max_tokens': self.max_tokens,
            'temperature': self.temperature,
        }
        
        def make_request():
            response = requests.post(
                f'{self.base_url}/chat/completions',
                headers=headers,
                json=data,
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()
            return result['choices'][0]['message']['content']
        
        return self._make_request_with_retry(make_request)


class GoogleProvider(AIProvider):
    def generate(self, prompt: str, system_prompt: str = '') -> str:
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY not set")
        
        # Gemini API 格式
        url = f'{self.base_url}/models/{self.model}:generateContent?key={self.api_key}'
        
        parts = []
        if system_prompt:
            parts.append({'text': f'System: {system_prompt}'})
        parts.append({'text': prompt})
        
        data = {
            'contents': [{'parts': parts}],
            'generationConfig': {
                'maxOutputTokens': self.max_tokens,
                'temperature': self.temperature,
            }
        }
        
        def make_request():
            response = requests.post(url, json=data, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
            return result['candidates'][0]['content']['parts'][0]['text']
        
        return self._make_request_with_retry(make_request)


class AgnesProvider(AIProvider):
    def generate(self, prompt: str, system_prompt: str = '') -> str:
        if not self.api_key:
            raise ValueError("AGNES_API_KEY not set")
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }
        
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': prompt})
        
        data = {
            'model': self.model,
            'messages': messages,
            'max_tokens': self.max_tokens,
            'temperature': self.temperature,
        }
        
        def make_request():
            response = requests.post(
                f'{self.base_url}/chat/completions',
                headers=headers,
                json=data,
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()
            return result['choices'][0]['message']['content']
        
        return self._make_request_with_retry(make_request)


PROVIDER_MAP = {
    'nvidia': NVIDIAProvider,
    'openai': OpenAIProvider,
    'google': GoogleProvider,
    'agnes': AgnesProvider,
}


def create_provider(config: Dict[str, Any]) -> AIProvider:
    """Factory: 建立 Provider 實例"""
    provider_class = PROVIDER_MAP.get(config.get('id'))
    if not provider_class:
        raise ValueError(f"Unknown provider: {config.get('id')}")
    return provider_class(config)


def get_providers(providers_config: List[Dict[str, Any]]) -> List[AIProvider]:
    """取得所有可用的 Provider 實例，依 priority 排序"""
    enabled = [p for p in providers_config if p.get('enabled', False)]
    sorted_providers = sorted(enabled, key=lambda x: x.get('priority', 999))
    return [create_provider(p) for p in sorted_providers if create_provider(p).is_available()]