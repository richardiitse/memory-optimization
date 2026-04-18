"""
Shared LLM Client — unified interface for all memory optimization scripts.

Supports multiple backends, auto-detected from base_url:
- Ollama (local, no auth)
- MiniMax Anthropic (Bearer auth)
- DashScope Anthropic (Bearer auth)
- OpenAI-compatible (Bearer auth, default)

Usage:
    from utils.llm_client import LLMClient

    # Auto-detect from .env / environment variables
    client = LLMClient()

    # Explicit backend
    client = LLMClient(
        base_url='https://api.minimaxi.com/anthropic/v1',
        api_key='your-key',
        model='MiniMax-M2.7-highspeed',
    )

    response = client.call([{"role": "user", "content": "Hello"}])
    embedding = client.embed("some text")
"""

import json
import logging
import os
import random
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from typing import Dict, List, Optional, Tuple

from utils import load_dotenv

logger = logging.getLogger(__name__)

# Load .env once at module import
load_dotenv()


class LLMClient:
    """Shared LLM client — supports multiple API backends.

    Backend auto-detection from base_url:
    - 'ollama': localhost URLs, no auth
    - 'minimax_anthropic': minimaxi.com + anthropic path, Bearer auth
    - 'dashscope_anthropic': dashscope + anthropic path, Bearer auth
    - 'openai': everything else, Bearer auth

    Priority: constructor arg > environment variable > default
    """

    DEFAULT_MODEL = 'glm-5'
    DEFAULT_BASE_URL = 'https://open.bigmodel.cn/api/paas/v4'
    DEFAULT_EMBED_MODEL = 'qwen3-embedding'
    DEFAULT_EMBED_BASE_URL = 'http://localhost:11434/api'

    # API parameters
    DEFAULT_MAX_TOKENS = 4096
    MAX_RETRIES = 3
    MAX_BACKOFF_SECONDS = 30
    CHAT_TIMEOUT_SECONDS = 120
    EMBED_TIMEOUT_SECONDS = 30

    TRANSIENT_CODES = {429, 500, 502, 503, 504}

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
        self.embed_base_url = os.environ.get(
            'OPENAI_EMBED_BASE_URL', self.DEFAULT_EMBED_BASE_URL
        )
        self.embed_model = os.environ.get(
            'OPENAI_EMBED_MODEL', self.DEFAULT_EMBED_MODEL
        )
        # Cache backend detection
        self._backend = self._detect_backend()

    # ========== Backend Detection ==========

    def _detect_backend(self) -> str:
        """Detect API backend from base_url and env vars.

        Returns one of: 'ollama', 'minimax_anthropic', 'dashscope_anthropic', 'openai'
        """
        url = self.base_url.lower()
        if url.startswith('http://localhost'):
            return 'ollama'
        if 'minimaxi' in url and 'anthropic' in url:
            return 'minimax_anthropic'
        if 'dashscope' in url and 'anthropic' in url:
            return 'dashscope_anthropic'
        return 'openai'

    # ========== Request Building ==========

    def _build_request(
        self,
        messages: List[Dict],
        temperature: float,
    ) -> Tuple[Dict, Dict, str]:
        """Build headers, payload, and URL for the detected backend.

        Returns:
            (headers, payload, url) tuple ready for requests.post
        """
        backend = self._backend

        if backend in ('minimax_anthropic', 'dashscope_anthropic'):
            # Anthropic Messages API format
            headers = {
                'Content-Type': 'application/json',
                'anthropic-version': '2023-06-01',
            }
            # MiniMax and DashScope both use Bearer auth for Anthropic API
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'

            # Extract system message into top-level 'system' field
            system_message = None
            api_messages = []
            for msg in messages:
                if msg.get('role') == 'system':
                    system_message = msg.get('content', '')
                else:
                    api_messages.append(msg)

            payload = {
                'model': self.model,
                'messages': api_messages,
                'max_tokens': self.DEFAULT_MAX_TOKENS,
                'temperature': temperature,
            }
            if system_message:
                payload['system'] = system_message

            url = f'{self.base_url}/messages'

        else:
            # OpenAI Chat Completions format (also used by Ollama)
            headers = {'Content-Type': 'application/json'}
            if self.api_key and backend != 'ollama':
                headers['Authorization'] = f'Bearer {self.api_key}'

            payload = {
                'model': self.model,
                'messages': messages,
                'temperature': temperature,
            }

            completion_path = os.environ.get(
                'OPENAI_COMPLETION_PATH', '/chat/completions'
            )
            url = f'{self.base_url}{completion_path}'

        return headers, payload, url

    def _parse_response(self, response_json: Dict) -> Optional[str]:
        """Parse response content based on backend format."""
        backend = self._backend

        if backend in ('minimax_anthropic', 'dashscope_anthropic'):
            # Anthropic Messages API: {"content": [{"type": "text", "text": "..."}]}
            for block in response_json.get('content', []):
                if block.get('type') == 'text':
                    return block.get('text', '')
            return ''
        else:
            # OpenAI format: {"choices": [{"message": {"content": "..."}}]}
            choices = response_json.get('choices', [])
            if not choices:
                return ''
            msg = choices[0].get('message', {})
            return msg.get('content', '')

    # ========== Chat Completion ==========

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
        # Local Ollama doesn't need an API key
        if self._backend != 'ollama' and not self.api_key:
            if mock_data is not None:
                return mock_data() if callable(mock_data) else json.dumps(mock_data)
            warnings.warn("No API key configured and no mock_data provided — returning None")
            return None

        max_retries = self.MAX_RETRIES
        backoff = 1.0
        headers, payload, url = self._build_request(messages, temperature)
        proxies = (
            {'http': None, 'https': None}
            if self._backend == 'ollama' else None
        )

        for attempt in range(max_retries + 1):
            try:
                response = requests.post(
                    url, headers=headers, json=payload,
                    timeout=self.CHAT_TIMEOUT_SECONDS, proxies=proxies,
                )

                if response.status_code == 200:
                    return self._parse_response(response.json())
                elif response.status_code in self.TRANSIENT_CODES and attempt < max_retries:
                    jitter = random.uniform(0, 0.5 * backoff)
                    time.sleep(backoff + jitter)
                    backoff = min(backoff * 2, self.MAX_BACKOFF_SECONDS)
                    continue
                else:
                    logger.error(
                        "API returned %d: %s",
                        response.status_code, response.text[:200],
                    )
                    if mock_data is not None:
                        return mock_data() if callable(mock_data) else json.dumps(mock_data)
                    warnings.warn(
                        f"API error {response.status_code} and no mock_data — returning None"
                    )
                    return None

            except Exception as e:
                if attempt < max_retries:
                    time.sleep(backoff + random.uniform(0, 0.5 * backoff))
                    backoff = min(backoff * 2, self.MAX_BACKOFF_SECONDS)
                    continue
                logger.error("Error calling LLM: %s", e)
                if mock_data is not None:
                    return mock_data() if callable(mock_data) else json.dumps(mock_data)
                warnings.warn(
                    f"LLM call failed after {max_retries} retries and no mock_data — returning None"
                )
                return None

        if mock_data is not None:
            return mock_data() if callable(mock_data) else json.dumps(mock_data)
        warnings.warn(
            f"LLM call exhausted {max_retries} retries and no mock_data — returning None"
        )
        return None

    # ========== JSON Output ==========

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

    # ========== Embeddings ==========

    def embed(self, text: str) -> Optional[List[float]]:
        """Compute embedding vector for text using the embeddings API.

        Args:
            text: Text to embed

        Returns:
            List of floats (embedding vector), or None on failure
        """
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
                timeout=self.EMBED_TIMEOUT_SECONDS,
                proxies={'http': None, 'https': None} if is_local else None,
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
                    logger.error(
                        "Embedding error: unexpected response format: %s",
                        response.text[:200],
                    )
                    return None
            else:
                logger.error(
                    "Embedding error: API returned %d: %s",
                    response.status_code, response.text[:200],
                )
                return None

        except Exception as e:
            logger.error("Error computing embedding: %s", e)
            return None

    def embed_batch(
        self,
        texts: List[str],
        max_workers: int = 8,
    ) -> List[Optional[List[float]]]:
        """Compute embedding vectors for multiple texts in parallel.

        Uses ThreadPoolExecutor to parallelize I/O-bound embed calls.
        Falls back to sequential if max_workers == 1.

        Args:
            texts: List of texts to embed
            max_workers: Max concurrent requests (default 8)

        Returns:
            List of embedding vectors (parallel to input texts),
            None for any failed embedding
        """
        if not texts:
            return []

        if len(texts) == 1:
            return [self.embed(texts[0])]

        results: List[Optional[List[float]]] = [None] * len(texts)

        if max_workers <= 1:
            # Sequential fallback
            for i, text in enumerate(texts):
                results[i] = self.embed(text)
            return results

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(self.embed, text): i
                for i, text in enumerate(texts)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error("embed_batch[%d] failed: %s", idx, e)
                    results[idx] = None

        return results

    # ========== Mock ==========

    def mock_response(self, mock_data: Dict) -> str:
        """Generate a mock response for testing.

        Args:
            mock_data: Dict to JSON-serialize as the mock response

        Returns:
            JSON string of mock_data
        """
        return json.dumps(mock_data)
