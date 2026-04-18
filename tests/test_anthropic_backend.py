#!/usr/bin/env python3
"""
Tests for Anthropic backend support in LLMClient and load_dotenv in utils/__init__.
Covers: _detect_backend, _build_request, _parse_response for minimax_anthropic
and dashscope_anthropic, plus load_dotenv edge cases.
"""

import os
import pytest
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))


class TestDetectBackend:
    """Tests for LLMClient._detect_backend()"""

    def test_minimax_anthropic_detected(self):
        from utils.llm_client import LLMClient

        with patch.dict('os.environ', {}, clear=True):
            client = LLMClient(
                base_url='https://api.minimaxi.com/anthropic/v1',
                api_key='test',
            )
        assert client._backend == 'minimax_anthropic'

    def test_minimax_anthropic_case_insensitive(self):
        from utils.llm_client import LLMClient

        with patch.dict('os.environ', {}, clear=True):
            client = LLMClient(
                base_url='https://API.MINIMAXI.COM/Anthropic/V1',
                api_key='test',
            )
        assert client._backend == 'minimax_anthropic'

    def test_dashscope_anthropic_detected(self):
        from utils.llm_client import LLMClient

        with patch.dict('os.environ', {}, clear=True):
            client = LLMClient(
                base_url='https://dashscope.aliyuncs.com/anthropic/v1',
                api_key='test',
            )
        assert client._backend == 'dashscope_anthropic'

    def test_minimax_without_anthropic_is_openai(self):
        from utils.llm_client import LLMClient

        with patch.dict('os.environ', {}, clear=True):
            client = LLMClient(
                base_url='https://api.minimaxi.com/v1',
                api_key='test',
            )
        assert client._backend == 'openai'

    def test_ollama_detected(self):
        from utils.llm_client import LLMClient

        with patch.dict('os.environ', {}, clear=True):
            client = LLMClient(
                base_url='http://localhost:11434/api',
                api_key='',
            )
        assert client._backend == 'ollama'

    def test_minimax_api_key_does_not_override_non_minimax_url(self):
        """MINIMAX_API_KEY does NOT override a non-minimaxi URL to minimax_anthropic."""
        from utils.llm_client import LLMClient

        env = {'MINIMAX_API_KEY': 'some-key'}
        with patch.dict('os.environ', env, clear=True):
            client = LLMClient(
                base_url='https://some-proxy.com/anthropic/v1',
                api_key='test',
            )
        # MINIMAX_API_KEY no longer acts as a side channel;
        # URL must contain 'minimaxi' to be detected as minimax_anthropic
        assert client._backend == 'openai'

    def test_generic_url_is_openai(self):
        from utils.llm_client import LLMClient

        with patch.dict('os.environ', {}, clear=True):
            client = LLMClient(
                base_url='https://api.openai.com/v1',
                api_key='test',
            )
        assert client._backend == 'openai'


class TestBuildRequestAnthropic:
    """Tests for _build_request() with Anthropic backends"""

    def test_minimax_anthropic_uses_bearer_auth(self):
        from utils.llm_client import LLMClient

        with patch.dict('os.environ', {}, clear=True):
            client = LLMClient(
                base_url='https://api.minimaxi.com/anthropic/v1',
                api_key='mm-key-123',
                model='MiniMax-M2.7-highspeed',
            )

        headers, payload, url = client._build_request(
            [{'role': 'user', 'content': 'hi'}], temperature=0.5
        )

        assert headers['Authorization'] == 'Bearer mm-key-123'
        assert headers['anthropic-version'] == '2023-06-01'

    def test_anthropic_extracts_system_message(self):
        from utils.llm_client import LLMClient

        with patch.dict('os.environ', {}, clear=True):
            client = LLMClient(
                base_url='https://api.minimaxi.com/anthropic/v1',
                api_key='test',
                model='test-model',
            )

        messages = [
            {'role': 'system', 'content': 'You are helpful.'},
            {'role': 'user', 'content': 'hi'},
        ]
        headers, payload, url = client._build_request(messages, temperature=0.7)

        assert payload['system'] == 'You are helpful.'
        assert len(payload['messages']) == 1
        assert payload['messages'][0]['role'] == 'user'
        # Anthropic format now includes temperature
        assert payload['temperature'] == 0.7

    def test_anthropic_url_appends_messages(self):
        from utils.llm_client import LLMClient

        with patch.dict('os.environ', {}, clear=True):
            client = LLMClient(
                base_url='https://api.minimaxi.com/anthropic/v1',
                api_key='test',
                model='test-model',
            )

        _, _, url = client._build_request(
            [{'role': 'user', 'content': 'hi'}], temperature=0.5
        )

        assert url == 'https://api.minimaxi.com/anthropic/v1/messages'

    def test_dashscope_anthropic_uses_bearer_auth(self):
        from utils.llm_client import LLMClient

        with patch.dict('os.environ', {}, clear=True):
            client = LLMClient(
                base_url='https://dashscope.aliyuncs.com/anthropic/v1',
                api_key='ds-key-456',
                model='claude-3',
            )

        headers, payload, url = client._build_request(
            [{'role': 'user', 'content': 'hi'}], temperature=0.3
        )

        assert headers['Authorization'] == 'Bearer ds-key-456'
        assert headers['anthropic-version'] == '2023-06-01'

    def test_no_system_message_no_system_field(self):
        from utils.llm_client import LLMClient

        with patch.dict('os.environ', {}, clear=True):
            client = LLMClient(
                base_url='https://api.minimaxi.com/anthropic/v1',
                api_key='test',
                model='test-model',
            )

        _, payload, _ = client._build_request(
            [{'role': 'user', 'content': 'hi'}], temperature=0.5
        )

        assert 'system' not in payload


class TestParseResponseAnthropic:
    """Tests for _parse_response() with Anthropic format"""

    def test_parse_anthropic_text_block(self):
        from utils.llm_client import LLMClient

        with patch.dict('os.environ', {}, clear=True):
            client = LLMClient(
                base_url='https://api.minimaxi.com/anthropic/v1',
                api_key='test',
            )

        response_json = {
            'content': [{'type': 'text', 'text': 'Hello from Anthropic'}]
        }
        result = client._parse_response(response_json)
        assert result == 'Hello from Anthropic'

    def test_parse_anthropic_empty_content(self):
        from utils.llm_client import LLMClient

        with patch.dict('os.environ', {}, clear=True):
            client = LLMClient(
                base_url='https://api.minimaxi.com/anthropic/v1',
                api_key='test',
            )

        response_json = {'content': []}
        result = client._parse_response(response_json)
        assert result == ''

    def test_parse_anthropic_multiple_blocks(self):
        from utils.llm_client import LLMClient

        with patch.dict('os.environ', {}, clear=True):
            client = LLMClient(
                base_url='https://api.minimaxi.com/anthropic/v1',
                api_key='test',
            )

        response_json = {
            'content': [
                {'type': 'thinking', 'thinking': '...'},
                {'type': 'text', 'text': 'The answer is 42'},
            ]
        }
        result = client._parse_response(response_json)
        assert result == 'The answer is 42'


class TestCallAnthropicIntegration:
    """Integration tests for call() with Anthropic backend"""

    def test_call_minimax_anthropic_success(self):
        from utils.llm_client import LLMClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'content': [{'type': 'text', 'text': '{"answer": "yes"}'}]
        }

        with patch.dict('os.environ', {}, clear=True):
            client = LLMClient(
                base_url='https://api.minimaxi.com/anthropic/v1',
                api_key='mm-key',
                model='MiniMax-M2.7-highspeed',
            )

        with patch('requests.post', return_value=mock_response) as mock_post:
            result = client.call([{'role': 'user', 'content': 'hello'}])

            assert result == '{"answer": "yes"}'
            # Verify Anthropic-format URL was used
            call_url = mock_post.call_args.args[0]
            assert call_url.endswith('/messages')

    def test_call_dashscope_anthropic_success(self):
        from utils.llm_client import LLMClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'content': [{'type': 'text', 'text': 'dashscope reply'}]
        }

        with patch.dict('os.environ', {}, clear=True):
            client = LLMClient(
                base_url='https://dashscope.aliyuncs.com/anthropic/v1',
                api_key='ds-key',
                model='claude-3',
            )

        with patch('requests.post', return_value=mock_response) as mock_post:
            result = client.call([{'role': 'user', 'content': 'hello'}])

            assert result == 'dashscope reply'
            call_headers = mock_post.call_args.kwargs['headers']
            assert call_headers['Authorization'] == 'Bearer ds-key'


class TestLoadDotenv:
    """Tests for load_dotenv() in utils/__init__.py"""

    def test_load_dotenv_finds_file(self):
        from utils import load_dotenv

        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / '.env'
            env_file.write_text('TEST_LOAD_DOTENV_VAR=hello\n')

            # Clear env var before test
            os.environ.pop('TEST_LOAD_DOTENV_VAR', None)
            load_dotenv(str(env_file))

            assert os.environ.get('TEST_LOAD_DOTENV_VAR') == 'hello'
            del os.environ['TEST_LOAD_DOTENV_VAR']

    def test_load_dotenv_no_file_returns_silently(self):
        from utils import load_dotenv

        # Should not raise
        load_dotenv('/nonexistent/path/.env')

    def test_load_dotenv_does_not_overwrite_existing(self):
        from utils import load_dotenv

        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / '.env'
            env_file.write_text('TEST_EXISTING_VAR=new_value\n')

            os.environ['TEST_EXISTING_VAR'] = 'original'
            load_dotenv(str(env_file))

            assert os.environ['TEST_EXISTING_VAR'] == 'original'
            del os.environ['TEST_EXISTING_VAR']

    def test_load_dotenv_strips_quoted_values(self):
        from utils import load_dotenv

        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / '.env'
            env_file.write_text(
                'TEST_QUOTED_VAR="double_quoted"\n'
                "TEST_SINGLE_QUOTED='single_quoted'\n"
            )

            os.environ.pop('TEST_QUOTED_VAR', None)
            os.environ.pop('TEST_SINGLE_QUOTED', None)
            load_dotenv(str(env_file))

            assert os.environ.get('TEST_QUOTED_VAR') == 'double_quoted'
            assert os.environ.get('TEST_SINGLE_QUOTED') == 'single_quoted'
            del os.environ['TEST_QUOTED_VAR']
            del os.environ['TEST_SINGLE_QUOTED']

    def test_load_dotenv_skips_comments_and_empty(self):
        from utils import load_dotenv

        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / '.env'
            env_file.write_text('# comment\n\nKEY_ONLY_NO_EQUALS\nVALID_VAR=works\n')

            os.environ.pop('VALID_VAR', None)
            load_dotenv(str(env_file))

            assert os.environ.get('VALID_VAR') == 'works'
            assert 'KEY_ONLY_NO_EQUALS' not in os.environ
            del os.environ['VALID_VAR']

    def test_load_dotenv_auto_walk_finds_env(self):
        """Test that load_dotenv() without path walks up to find .env."""
        from utils import load_dotenv

        # The actual .env file should exist at project root
        project_root = Path(__file__).parent.parent
        env_file = project_root / '.env'

        if not env_file.exists():
            pytest.skip("No .env file at project root")

        # Just verify it doesn't crash and returns None
        # We can't assert specific vars without knowing the file contents
        load_dotenv()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
