#!/usr/bin/env python3
"""
Tests for LLMClient (scripts/utils/llm_client.py)
"""

import json
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))


class TestLLMClientCall:
    """Tests for LLMClient.call() method"""

    def test_call_with_api_key_success(self):
        """Test successful API call with API key"""
        from utils.llm_client import LLMClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{'message': {'content': '{"result": "success"}'}}]
        }

        client = LLMClient(api_key='test-key', base_url='https://api.test.com')

        with patch('requests.post', return_value=mock_response) as mock_post:
            result = client.call([{'role': 'user', 'content': 'hello'}])

            assert result == '{"result": "success"}'
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert 'Bearer test-key' in call_args.kwargs['headers']['Authorization']

    def test_call_without_api_key_returns_none(self):
        """Test call returns None when no API key and no mock_data"""
        from utils.llm_client import LLMClient

        with patch.dict('os.environ', {'OPENAI_API_KEY': ''}, clear=False):
            client = LLMClient(api_key='')
            result = client.call([{'role': 'user', 'content': 'hello'}])

        assert result is None

    def test_call_with_mock_data_dict(self):
        """Test call returns mock_data dict when API unavailable"""
        from utils.llm_client import LLMClient

        with patch.dict('os.environ', {'OPENAI_API_KEY': ''}, clear=False):
            client = LLMClient(api_key='')
            mock_data = {'result': 'mocked'}
            result = client.call([{'role': 'user', 'content': 'hello'}], mock_data=mock_data)

        assert result == json.dumps(mock_data)

    def test_call_with_mock_data_callable(self):
        """Test call invokes callable mock_data"""
        from utils.llm_client import LLMClient

        with patch.dict('os.environ', {'OPENAI_API_KEY': ''}, clear=False):
            client = LLMClient(api_key='')
            result = client.call([{'role': 'user', 'content': 'hello'}], mock_data=lambda: '{"called": true}')

        assert result == '{"called": true}'

    def test_call_with_transient_error_retries(self):
        """Test retry on transient errors (429, 500, 502, 503, 504)"""
        from utils.llm_client import LLMClient

        # First two calls fail with 503, third succeeds
        mock_503 = MagicMock()
        mock_503.status_code = 503
        mock_503.text = 'Service Unavailable'

        mock_success = MagicMock()
        mock_success.status_code = 200
        mock_success.json.return_value = {
            'choices': [{'message': {'content': '{"success": true}'}}]
        }

        client = LLMClient(api_key='test-key', base_url='https://api.test.com')

        with patch('requests.post', side_effect=[mock_503, mock_503, mock_success]) as mock_post:
            result = client.call([{'role': 'user', 'content': 'hello'}])

            assert result == '{"success": true}'
            assert mock_post.call_count == 3

    def test_call_with_non_transient_error_returns_none(self):
        """Test non-transient error returns None"""
        from utils.llm_client import LLMClient

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = 'Bad Request'

        client = LLMClient(api_key='test-key', base_url='https://api.test.com')

        with patch('requests.post', return_value=mock_response):
            result = client.call([{'role': 'user', 'content': 'hello'}])

        assert result is None

    def test_call_with_request_exception_retries(self):
        """Test request exception triggers retry"""
        from utils.llm_client import LLMClient

        mock_success = MagicMock()
        mock_success.status_code = 200
        mock_success.json.return_value = {
            'choices': [{'message': {'content': '{"success": true}'}}]
        }

        client = LLMClient(api_key='test-key', base_url='https://api.test.com')

        with patch('requests.post', side_effect=[Exception('Network error'), Exception('Timeout'), mock_success]) as mock_post:
            result = client.call([{'role': 'user', 'content': 'hello'}])

            assert result == '{"success": true}'
            assert mock_post.call_count == 3

    def test_call_with_max_retries_exhausted(self):
        """Test max retries exhausted returns None"""
        from utils.llm_client import LLMClient

        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.text = 'Service Unavailable'

        client = LLMClient(api_key='test-key', base_url='https://api.test.com')

        with patch('requests.post', return_value=mock_response):
            result = client.call([{'role': 'user', 'content': 'hello'}])

        assert result is None

    def test_call_with_temperature_parameter(self):
        """Test temperature parameter is passed correctly"""
        from utils.llm_client import LLMClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{'message': {'content': 'result'}}]
        }

        client = LLMClient(api_key='test-key', base_url='https://api.test.com')

        with patch('requests.post', return_value=mock_response) as mock_post:
            client.call([{'role': 'user', 'content': 'hello'}], temperature=0.9)

            call_args = mock_post.call_args
            assert call_args.kwargs['json']['temperature'] == 0.9


class TestLLMClientCallJson:
    """Tests for LLMClient.call_json() method"""

    def test_call_json_success(self):
        """Test call_json returns parsed JSON dict"""
        from utils.llm_client import LLMClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{'message': {'content': '{"key": "value"}'}}]
        }

        client = LLMClient(api_key='test-key', base_url='https://api.test.com')

        with patch('requests.post', return_value=mock_response):
            result = client.call_json([{'role': 'user', 'content': 'hello'}])

        assert result == {'key': 'value'}

    def test_call_json_returns_none_on_llm_failure(self):
        """Test call_json returns None when LLM call fails"""
        from utils.llm_client import LLMClient

        client = LLMClient(api_key='', base_url='https://api.test.com')
        result = client.call_json([{'role': 'user', 'content': 'hello'}])

        assert result is None

    def test_call_json_returns_none_on_invalid_json(self):
        """Test call_json returns None when response is not valid JSON"""
        from utils.llm_client import LLMClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{'message': {'content': 'not valid json {'}}]
        }

        client = LLMClient(api_key='test-key', base_url='https://api.test.com')

        with patch('requests.post', return_value=mock_response):
            result = client.call_json([{'role': 'user', 'content': 'hello'}])

        assert result is None


class TestLLMClientEmbed:
    """Tests for LLMClient.embed() method"""

    def test_embed_with_local_ollama(self):
        """Test embed with local Ollama (no API key needed)"""
        from utils.llm_client import LLMClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'embedding': [0.1, 0.2, 0.3]}

        client = LLMClient(api_key='', base_url='http://localhost:11434/api')

        with patch('requests.post', return_value=mock_response) as mock_post:
            result = client.embed('test text')

            assert result == [0.1, 0.2, 0.3]
            mock_post.assert_called_once()

    def test_embed_with_openai_format(self):
        """Test embed with OpenAI-compatible API format"""
        from utils.llm_client import LLMClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'data': [{'embedding': [0.1, 0.2, 0.3]}]
        }

        env = {
            'OPENAI_API_KEY': 'test-key',
            'OPENAI_EMBED_BASE_URL': 'https://api.openai.com/v1',
            'OPENAI_EMBED_MODEL': 'text-embedding-3-small'
        }

        with patch.dict('os.environ', env, clear=True):
            client = LLMClient()

        with patch('requests.post', return_value=mock_response) as mock_post:
            result = client.embed('test text')

            assert result == [0.1, 0.2, 0.3]

    def test_embed_without_api_key_local(self):
        """Test embed with local Ollama works without API key"""
        from utils.llm_client import LLMClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'embedding': [0.1, 0.2, 0.3]}

        env = {
            'OPENAI_EMBED_BASE_URL': 'http://localhost:11434/api',
            'OPENAI_EMBED_MODEL': 'qwen3-embedding'
        }

        with patch.dict('os.environ', env, clear=True):
            client = LLMClient(api_key='')

        with patch('requests.post', return_value=mock_response) as mock_post:
            result = client.embed('test text')

            assert result == [0.1, 0.2, 0.3]

    def test_embed_without_api_key_remote(self):
        """Test embed returns None for remote API without API key"""
        from utils.llm_client import LLMClient

        env = {
            'OPENAI_API_KEY': '',
            'OPENAI_EMBED_BASE_URL': 'https://api.openai.com/v1',
            'OPENAI_EMBED_MODEL': 'text-embedding-3-small'
        }

        with patch.dict('os.environ', env, clear=True):
            client = LLMClient()

        result = client.embed('test text')
        assert result is None

    def test_embed_with_error_response(self):
        """Test embed returns None on error response"""
        from utils.llm_client import LLMClient

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = 'Internal Server Error'

        env = {
            'OPENAI_API_KEY': 'test-key',
            'OPENAI_EMBED_BASE_URL': 'http://localhost:11434/api'
        }

        with patch.dict('os.environ', env, clear=True):
            client = LLMClient()

        with patch('requests.post', return_value=mock_response):
            result = client.embed('test text')

        assert result is None

    def test_embed_with_exception(self):
        """Test embed returns None on exception"""
        from utils.llm_client import LLMClient

        env = {
            'OPENAI_API_KEY': 'test-key',
            'OPENAI_EMBED_BASE_URL': 'http://localhost:11434/api'
        }

        with patch.dict('os.environ', env, clear=True):
            client = LLMClient()

        with patch('requests.post', side_effect=Exception('Connection error')):
            result = client.embed('test text')

        assert result is None

    def test_embed_with_unexpected_response_format(self):
        """Test embed returns None for unexpected response format"""
        from utils.llm_client import LLMClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'unexpected': 'format'}
        mock_response.text = '{"unexpected": "format"}'

        env = {
            'OPENAI_API_KEY': 'test-key',
            'OPENAI_EMBED_BASE_URL': 'http://localhost:11434/api'
        }

        with patch.dict('os.environ', env, clear=True):
            client = LLMClient()

        with patch('requests.post', return_value=mock_response):
            result = client.embed('test text')

        assert result is None


class TestLLMClientMockResponse:
    """Tests for LLMClient.mock_response() method"""

    def test_mock_response_returns_json_string(self):
        """Test mock_response returns JSON string"""
        from utils.llm_client import LLMClient

        client = LLMClient()
        result = client.mock_response({'key': 'value'})

        data = json.loads(result)
        assert data == {'key': 'value'}


class TestLLMClientInitialization:
    """Tests for LLMClient initialization"""

    def test_default_values(self):
        """Test default values are set correctly"""
        from utils.llm_client import LLMClient

        with patch.dict('os.environ', {}, clear=True):
            client = LLMClient()

        assert client.model == 'glm-5'
        assert client.base_url == 'https://open.bigmodel.cn/api/paas/v4'
        assert client.embed_model == 'qwen3-embedding'
        assert client.embed_base_url == 'http://localhost:11434/api'

    def test_env_var_overrides(self):
        """Test environment variables override defaults"""
        from utils.llm_client import LLMClient

        env = {
            'OPENAI_API_KEY': 'env-key',
            'OPENAI_BASE_URL': 'https://env.url.com',
            'OPENAI_MODEL': 'env-model',
            'OPENAI_EMBED_BASE_URL': 'https://embed.env.url.com',
            'OPENAI_EMBED_MODEL': 'env-embed-model'
        }

        with patch.dict('os.environ', env, clear=True):
            client = LLMClient()

        assert client.api_key == 'env-key'
        assert client.base_url == 'https://env.url.com'
        assert client.model == 'env-model'
        assert client.embed_base_url == 'https://embed.env.url.com'
        assert client.embed_model == 'env-embed-model'

    def test_constructor_args_override_env(self):
        """Test constructor arguments override environment variables"""
        from utils.llm_client import LLMClient

        env = {
            'OPENAI_API_KEY': 'env-key',
            'OPENAI_BASE_URL': 'https://env.url.com',
            'OPENAI_MODEL': 'env-model'
        }

        with patch.dict('os.environ', env, clear=True):
            client = LLMClient(api_key='arg-key', base_url='https://arg.url.com', model='arg-model')

        assert client.api_key == 'arg-key'
        assert client.base_url == 'https://arg.url.com'
        assert client.model == 'arg-model'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])