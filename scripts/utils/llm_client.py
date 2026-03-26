"""
Shared LLM Client — unified interface for all memory optimization scripts.

Provides a single LLMClient implementation used by:
- kg_extractor.py
- preference_engine.py
- consolidation_engine.py
- working_memory.py
"""

import json
import os
import requests
from typing import Dict, List, Optional


class LLMClient:
    """Shared LLM client — supports OpenAI compatible API.

    Priority: constructor arg > environment variable > default
    """

    DEFAULT_MODEL = 'glm-5'
    DEFAULT_BASE_URL = 'https://open.bigmodel.cn/api/paas/v4'

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model: str = None,
    ):
        self.api_key = api_key or os.environ.get('OPENAI_API_KEY', '')
        self.base_url = base_url or os.environ.get(
            'OPENAI_BASE_URL', self.DEFAULT_BASE_URL
        )
        self.model = model or os.environ.get('OPENAI_MODEL', self.DEFAULT_MODEL)

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
        if not self.api_key:
            print("Warning: No API key configured, using mock response")
            if mock_data is not None:
                return mock_data() if callable(mock_data) else json.dumps(mock_data)
            return None

        # Transient error codes that warrant retry
        TRANSIENT_CODES = {429, 500, 502, 503, 504}
        max_retries = 3
        backoff = 1.0  # seconds

        for attempt in range(max_retries + 1):
            try:
                headers = {
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json'
                }

                payload = {
                    'model': self.model,
                    'messages': messages,
                    'temperature': temperature
                }

                response = requests.post(
                    f'{self.base_url}/chat/completions',
                    headers=headers,
                    json=payload,
                    timeout=60
                )

                if response.status_code == 200:
                    result = response.json()
                    return result['choices'][0]['message']['content']
                elif response.status_code in TRANSIENT_CODES and attempt < max_retries:
                    import time
                    import random
                    jitter = random.uniform(0, 0.5 * backoff)
                    time.sleep(backoff + jitter)
                    backoff = min(backoff * 2, 30)  # cap at 30s
                    continue
                else:
                    print(f"Error: API returned {response.status_code}: {response.text[:200]}")
                    if mock_data is not None:
                        return mock_data() if callable(mock_data) else json.dumps(mock_data)
                    return None

            except Exception as e:
                if attempt < max_retries:
                    import time
                    import random
                    time.sleep(backoff + random.uniform(0, 0.5 * backoff))
                    backoff = min(backoff * 2, 30)
                    continue
                print(f"Error calling LLM: {e}")
                if mock_data is not None:
                    return mock_data() if callable(mock_data) else json.dumps(mock_data)
                return None

        if mock_data is not None:
            return mock_data() if callable(mock_data) else json.dumps(mock_data)
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

    def mock_response(self, mock_data: Dict) -> str:
        """Generate a mock response for testing.

        Args:
            mock_data: Dict to JSON-serialize as the mock response

        Returns:
            JSON string of mock_data
        """
        return json.dumps(mock_data)
