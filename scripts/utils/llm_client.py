"""
Shared LLM Client — unified interface for all memory optimization scripts.

Provides a single LLMClient implementation used by:
- kg_extractor.py
- preference_engine.py
- consolidation_engine.py
- working_memory.py
- longmemeval_adapter.py
- qa_reader.py
- eval_bridge.py
"""

import json
import logging
import os
import random
import time
import warnings

import requests
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class LLMClient:
    """Shared LLM client — supports OpenAI compatible API.

    Priority: constructor arg > environment variable > default
    """

    DEFAULT_MODEL = 'glm-5'
    DEFAULT_BASE_URL = 'https://open.bigmodel.cn/api/paas/v4'
    # Embedding 模型配置 — 默认本地 Ollama qwen3-embedding
    # 可通过环境变量 OPENAI_EMBED_BASE_URL / OPENAI_EMBED_MODEL 覆盖
    DEFAULT_EMBED_MODEL = 'qwen3-embedding'
    DEFAULT_EMBED_BASE_URL = 'http://localhost:11434/api'

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get('OPENAI_API_KEY', '')
        self.base_url = base_url or os.environ.get(
            'OPENAI_BASE_URL', self.DEFAULT_BASE_URL
        )
        self.model = model or os.environ.get('OPENAI_MODEL', self.DEFAULT_MODEL)
        # Embedding-specific settings (may differ from chat model)
        self.embed_base_url = os.environ.get(
            'OPENAI_EMBED_BASE_URL', self.DEFAULT_EMBED_BASE_URL
        )
        self.embed_model = os.environ.get(
            'OPENAI_EMBED_MODEL', self.DEFAULT_EMBED_MODEL
        )

    @property
    def _is_local(self) -> bool:
        """Check if the base URL points to localhost."""
        return self.base_url.startswith('http://localhost')

    def call(
        self, messages: List[Dict], temperature: float = 0.7,
        mock_data=None
    ) -> Optional[str]:
        """Call LLM with messages and retry on transient failures.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0.0-2.0)
            mock_data: Fallback data returned when API is unavailable.
                Can be a dict (JSON-serialized) or a callable returning a str.
                If None, returns None on failure.

        Returns:
            LLM response text, or mock_data (or None) on failure
        """
        is_local = self._is_local

        # Local Ollama doesn't need an API key
        if not is_local and not self.api_key:
            if mock_data is not None:
                return mock_data() if callable(mock_data) else json.dumps(mock_data)
            warnings.warn("No API key configured and no mock_data provided — returning None")
            return None

        # Transient error codes that warrant retry
        TRANSIENT_CODES = {429, 500, 502, 503, 504}
        max_retries = 3
        backoff = 1.0  # seconds

        for attempt in range(max_retries + 1):
            try:
                headers = {'Content-Type': 'application/json'}
                if self.api_key and not is_local:
                    headers['Authorization'] = f'Bearer {self.api_key}'

                # Detect DashScope Anthropic endpoint
                is_dashscope_anthropic = (
                    'dashscope' in self.base_url.lower() and
                    'anthropic' in self.base_url.lower()
                )

                # Detect MiniMax API endpoint
                is_minimax = (
                    'minimaxi' in self.base_url.lower() or
                    os.environ.get('MINIMAX_API_KEY')
                ) and 'anthropic' in self.base_url.lower()

                if is_minimax:
                    # Use MiniMax Anthropic API format (x-api-key auth)
                    minimax_headers = {
                        'Content-Type': 'application/json',
                        'anthropic-version': '2023-06-01',
                    }
                    if self.api_key:
                        minimax_headers['x-api-key'] = self.api_key

                    # Extract system message if present (MiniMax uses 'system' field)
                    system_message = None
                    minimax_messages = []
                    for msg in messages:
                        if msg.get('role') == 'system':
                            system_message = msg.get('content', '')
                        else:
                            minimax_messages.append(msg)

                    minimax_payload = {
                        'model': self.model,
                        'messages': minimax_messages,
                        'max_tokens': 4096,
                    }
                    if system_message:
                        minimax_payload['system'] = system_message

                    response = requests.post(
                        f'{self.base_url}/messages',
                        headers=minimax_headers,
                        json=minimax_payload,
                        timeout=120,
                    )

                    if response.status_code == 200:
                        result = response.json()
                        # Extract text from response
                        for block in result.get('content', []):
                            if block.get('type') == 'text':
                                return block.get('text', '')
                        return ''
                    elif response.status_code in TRANSIENT_CODES and attempt < max_retries:
                        jitter = random.uniform(0, 0.5 * backoff)
                        time.sleep(backoff + jitter)
                        backoff = min(backoff * 2, 30)
                        continue
                    else:
                        logger.error("API returned %d: %s", response.status_code, response.text[:200])
                        if mock_data is not None:
                            return mock_data() if callable(mock_data) else json.dumps(mock_data)
                        warnings.warn(f"API error {response.status_code} and no mock_data — returning None")
                        return None
                elif is_dashscope_anthropic:
                    # Use DashScope Anthropic Messages API format (Bearer auth)
                    anthropic_headers = {
                        'Content-Type': 'application/json',
                        'anthropic-version': '2023-06-01',
                    }
                    if self.api_key:
                        anthropic_headers['Authorization'] = f'Bearer {self.api_key}'

                    # Extract system message if present (DashScope uses 'system' field)
                    system_message = None
                    anthropic_messages = []
                    for msg in messages:
                        if msg.get('role') == 'system':
                            system_message = msg.get('content', '')
                        else:
                            anthropic_messages.append(msg)

                    anthropic_payload = {
                        'model': self.model,
                        'messages': anthropic_messages,
                        'max_tokens': 4096,
                    }
                    if system_message:
                        anthropic_payload['system'] = system_message

                    response = requests.post(
                        f'{self.base_url}/messages',
                        headers=anthropic_headers,
                        json=anthropic_payload,
                        timeout=120,
                    )

                    if response.status_code == 200:
                        result = response.json()
                        # Extract text from response
                        for block in result.get('content', []):
                            if block.get('type') == 'text':
                                return block.get('text', '')
                        return ''
                    elif response.status_code in TRANSIENT_CODES and attempt < max_retries:
                        jitter = random.uniform(0, 0.5 * backoff)
                        time.sleep(backoff + jitter)
                        backoff = min(backoff * 2, 30)
                        continue
                    else:
                        logger.error("API returned %d: %s", response.status_code, response.text[:200])
                        if mock_data is not None:
                            return mock_data() if callable(mock_data) else json.dumps(mock_data)
                        warnings.warn(f"API error {response.status_code} and no mock_data — returning None")
                        return None
                else:
                    # Use OpenAI Chat Completions format
                    payload = {
                        'model': self.model,
                        'messages': messages,
                        'temperature': temperature
                    }

                    completion_path = os.environ.get(
                        'OPENAI_COMPLETION_PATH', '/chat/completions'
                    )
                    response = requests.post(
                        f'{self.base_url}{completion_path}',
                        headers=headers,
                        json=payload,
                        timeout=120,
                        proxies={'http': None, 'https': None} if is_local else None
                    )

                    if response.status_code == 200:
                        result = response.json()
                        return result['choices'][0]['message']['content']
                    elif response.status_code in TRANSIENT_CODES and attempt < max_retries:
                        jitter = random.uniform(0, 0.5 * backoff)
                        time.sleep(backoff + jitter)
                        backoff = min(backoff * 2, 30)  # cap at 30s
                        continue
                    else:
                        logger.error("API returned %d: %s", response.status_code, response.text[:200])
                        if mock_data is not None:
                            return mock_data() if callable(mock_data) else json.dumps(mock_data)
                        warnings.warn(f"API error {response.status_code} and no mock_data — returning None")
                        return None

            except Exception as e:
                if attempt < max_retries:
                    time.sleep(backoff + random.uniform(0, 0.5 * backoff))
                    backoff = min(backoff * 2, 30)
                    continue
                logger.error("Error calling LLM: %s", e)
                if mock_data is not None:
                    return mock_data() if callable(mock_data) else json.dumps(mock_data)
                warnings.warn(f"LLM call failed after {max_retries} retries and no mock_data — returning None")
                return None

        if mock_data is not None:
            return mock_data() if callable(mock_data) else json.dumps(mock_data)
        warnings.warn(f"LLM call exhausted {max_retries} retries and no mock_data — returning None")
        return None

    def call_json(
        self, messages: List[Dict], temperature: float = 0.3
    ) -> Optional[Dict]:
        """Call LLM and parse JSON response.

        Args:
            messages: List of message dicts
            temperature: Lower temperature for structured output

        Returns:
            Parsed JSON dict, or None on failure
        """
        response = self.call(messages, temperature)
        if not response:
            return None
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return None

    def embed(self, text: str) -> Optional[List[float]]:
        """Compute embedding vector for text using the embeddings API.

        Args:
            text: Text to embed

        Returns:
            List of floats (embedding vector), or None on failure
        """
        # Skip API key check for local Ollama (no auth needed)
        is_local = self.embed_base_url.startswith('http://localhost')
        if not is_local and not self.api_key:
            warnings.warn("No API key — cannot compute embedding")
            return None

        try:
            headers = {'Content-Type': 'application/json'}
            if self.api_key and not is_local:
                headers['Authorization'] = f'Bearer {self.api_key}'

            # Ollama uses 'prompt', OpenAI-compatible APIs use 'input'
            if is_local:
                payload = {'model': self.embed_model, 'prompt': text}
            else:
                payload = {'model': self.embed_model, 'input': text}

            response = requests.post(
                f'{self.embed_base_url}/embeddings',
                headers=headers,
                json=payload,
                timeout=30,
                proxies={'http': None, 'https': None} if is_local else None
            )

            if response.status_code == 200:
                result = response.json()
                # OpenAI format: {"data":[{"embedding": [...]}]}
                # Ollama format: {"embedding": [...]}
                if 'data' in result:
                    return result['data'][0]['embedding']
                elif 'embedding' in result:
                    return result['embedding']
                else:
                    logger.error("Embedding error: unexpected response format: %s", response.text[:200])
                    return None
            else:
                logger.error("Embedding error: API returned %d: %s", response.status_code, response.text[:200])
                return None

        except Exception as e:
            logger.error("Error computing embedding: %s", e)
            return None

    def mock_response(self, mock_data: Dict) -> str:
        """Generate a mock response for testing.

        Args:
            mock_data: Dict to JSON-serialize as the mock response

        Returns:
            JSON string of mock_data
        """
        return json.dumps(mock_data)
