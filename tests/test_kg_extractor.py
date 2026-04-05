#!/usr/bin/env python3
"""
KG Extractor Tests
"""

import json
import sys
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch

# 添加 scripts 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import pytest
from kg_extractor import (
    JSONLParser,
    MessageFilter,
    LLMClient,
    EntityExtractor,
    BatchProcessor,
    ReportGenerator,
    Message,
    Conversation,
    ExtractedEntity
)


class TestJSONLParser:
    """测试 JSONL 解析器"""

    def test_parse_file_not_exists(self):
        """测试解析不存在的文件"""
        result = JSONLParser.parse_file(Path('/nonexistent/file.jsonl'))
        assert result is None

    def test_scan_directory(self):
        """测试扫描目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建正确的目录结构：agents/*/sessions/*.jsonl
            agents_dir = Path(tmpdir)
            sessions_dir = agents_dir / 'main' / 'sessions'
            sessions_dir.mkdir(parents=True)

            # 创建测试文件
            (sessions_dir / 'session1.jsonl').write_text('{"messages": []}\n')
            (sessions_dir / 'session2.jsonl').write_text('{"messages": []}\n')
            # 创建非 jsonl 文件（应被忽略）
            (sessions_dir / 'readme.txt').write_text('not a jsonl')

            files = JSONLParser.scan_directory(agents_dir)
            assert len(files) == 2
            assert all(f.suffix == '.jsonl' for f in files)


class TestMessageFilter:
    """测试消息过滤器"""

    def test_is_system_message(self):
        """测试系统消息识别"""
        assert MessageFilter.is_system_message("system: hello")
        assert MessageFilter.is_system_message("Conversation info")
        assert not MessageFilter.is_system_message("Hello, how are you?")

    def test_is_error_message(self):
        """测试错误消息识别"""
        assert MessageFilter.is_error_message("429 error rate limit")  # 需要2个markers
        assert MessageFilter.is_error_message("500 server error exception")
        assert MessageFilter.is_error_message("")  # 空消息

    def test_filter_messages(self):
        """测试消息过滤"""
        messages = [
            Message(role='user', content='hello', timestamp='2026-01-01T00:00:00Z'),
            Message(role='assistant', content='error: something failed', timestamp='2026-01-01T00:01:00Z'),
            Message(role='user', content='system: config', timestamp='2026-01-01T00:02:00Z'),
            Message(role='assistant', content='Here is the result', timestamp='2026-01-01T00:03:00Z'),
        ]

        filtered = MessageFilter.filter_messages(messages)
        assert len(filtered) == 2  # 只保留最后两条
        assert filtered[0].content == 'hello'
        assert filtered[1].content == 'Here is the result'

    def test_merge_consecutive(self):
        """测试合并相邻消息"""
        messages = [
            Message(role='user', content='first', timestamp='2026-01-01T00:00:00Z', session_id='s1'),
            Message(role='user', content='second', timestamp='2026-01-01T00:00:01Z', session_id='s1'),
            Message(role='assistant', content='response', timestamp='2026-01-01T00:00:02Z', session_id='s1'),
        ]

        merged = MessageFilter.merge_consecutive(messages)
        assert len(merged) == 2
        assert 'first\nsecond' in merged[0].content


class TestLLMClient:
    """测试 LLM 客户端"""

    def test_mock_response(self):
        """测试模拟响应"""
        client = LLMClient(api_key='')  # 无 API key
        response = client.mock_response({"entities": [{"type": "Decision", "title": "Test"}]})

        assert response is not None
        data = json.loads(response)
        assert "entities" in data

    def test_call_with_api_key(self):
        """测试配置 API key 时的实际调用"""
        client = LLMClient(api_key='test-api-key', base_url='https://api.test.com')

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"entities": [{"type": "Decision", "title": "API Test", "rationale": "From API", "made_at": "2026-01-01T00:00:00Z", "confidence": 0.8, "tags": ["#api"]}]}'}}]
        }

        with patch('requests.post', return_value=mock_response) as mock_post:
            response = client.call([{"role": "user", "content": "test"}])

            assert response is not None
            data = json.loads(response)
            assert data["entities"][0]["title"] == "API Test"
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "Bearer test-api-key" in call_args.kwargs['headers']['Authorization']


class TestEntityExtractor:
    """测试实体提取器"""

    def test_parse_response_valid_json(self):
        """测试解析有效 JSON 响应"""
        client = Mock()
        client.call.return_value = json.dumps({
            "entities": [
                {
                    "type": "Decision",
                    "title": "Test Decision",
                    "rationale": "Test rationale",
                    "made_at": "2026-01-01T00:00:00Z",
                    "confidence": 0.9,
                    "tags": ["#test"]
                }
            ]
        })

        mock_validate = Mock(return_value=[])
        mock_create = Mock()
        extractor = EntityExtractor(client, mock_create, mock_validate)

        conversation = Conversation(
            session_id="test-session",
            messages=[
                Message(role='user', content='test', timestamp='2026-01-01T00:00:00Z')
            ]
        )

        entities = extractor._parse_response(client.call.return_value, "test-session", dry_run=True)

        assert len(entities) == 1
        assert entities[0].type == "Decision"
        assert entities[0].title == "Test Decision"

    def test_parse_response_invalid_json(self):
        """测试解析无效 JSON"""
        client = Mock()
        mock_validate = Mock(return_value=[])
        mock_create = Mock()
        extractor = EntityExtractor(client, mock_create, mock_validate)

        entities = extractor._parse_response("not valid json", "test-session", dry_run=True)
        assert len(entities) == 0


class TestBatchProcessor:
    """测试批量处理器"""

    def test_init(self):
        """测试初始化"""
        client = Mock()
        extractor = EntityExtractor(client)
        processor = BatchProcessor(extractor)

        assert processor.stats['files_processed'] == 0
        assert processor.stats['total_entities'] == 0

    def test_process_directory_dry_run(self):
        """测试 dry-run 模式处理目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建测试会话文件
            agents_dir = Path(tmpdir)
            sessions_dir = agents_dir / 'main' / 'sessions'
            sessions_dir.mkdir(parents=True)

            # 创建有效的 JSONL 文件
            session_content = json.dumps({
                'type': 'message',
                'id': 'msg1',
                'timestamp': '2026-01-01T00:00:00Z',
                'message': {
                    'role': 'user',
                    'content': [{'type': 'text', 'text': '我做了一个重要决定'}]
                }
            }) + '\n' + json.dumps({
                'type': 'message',
                'id': 'msg2',
                'timestamp': '2026-01-01T00:01:00Z',
                'message': {
                    'role': 'assistant',
                    'content': [{'type': 'text', 'text': '好的，我帮你记录'}]
                }
            })
            (sessions_dir / 'session1.jsonl').write_text(session_content)

            client = Mock()
            client.call.return_value = json.dumps({
                'entities': [{
                    'type': 'Decision',
                    'title': '测试决策',
                    'rationale': '测试理由',
                    'made_at': '2026-01-01T00:00:00Z',
                    'confidence': 0.8,
                    'tags': ['#test']
                }]
            })

            mock_create = Mock()
            mock_validate = Mock(return_value=[])
            extractor = EntityExtractor(client, mock_create, mock_validate)
            processor = BatchProcessor(extractor)

            stats = processor.process_directory(agents_dir, dry_run=True)

            assert stats['files_processed'] == 1
            assert stats['files_with_entities'] == 1
            assert stats['total_entities'] == 1
            assert 'Decision' in stats['by_type']
            mock_create.assert_not_called()  # dry-run 不会创建

    def test_process_directory_no_messages(self):
        """测试处理没有有效消息的文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = Path(tmpdir)
            sessions_dir = agents_dir / 'main' / 'sessions'
            sessions_dir.mkdir(parents=True)

            # 创建空消息文件
            (sessions_dir / 'empty.jsonl').write_text('')

            client = Mock()
            extractor = EntityExtractor(client)
            processor = BatchProcessor(extractor)

            stats = processor.process_directory(agents_dir)

            assert stats['files_processed'] == 0  # 无有效消息不计数

    def test_process_directory_limit(self):
        """测试处理文件数量限制"""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = Path(tmpdir)
            sessions_dir = agents_dir / 'main' / 'sessions'
            sessions_dir.mkdir(parents=True)

            # 创建多个会话文件
            for i in range(5):
                (sessions_dir / f'session{i}.jsonl').write_text(
                    json.dumps({
                        'type': 'message',
                        'id': f'msg{i}',
                        'timestamp': '2026-01-01T00:00:00Z',
                        'message': {'role': 'user', 'content': [{'type': 'text', 'text': 'hello'}]}
                    }) + '\n'
                )

            client = Mock()
            client.call.return_value = json.dumps({'entities': []})
            extractor = EntityExtractor(client)
            processor = BatchProcessor(extractor)

            stats = processor.process_directory(agents_dir, limit=3)

            assert stats['files_processed'] == 3


class TestReportGenerator:
    """测试报告生成器"""

    def test_print_stats(self):
        """测试统计信息打印"""
        stats = {
            'files_processed': 10,
            'files_with_entities': 7,
            'total_entities': 25,
            'by_type': {
                'Decision': 10,
                'Finding': 8,
                'LessonLearned': 7
            },
            'processed_files': [
                {'file': '/path/to/file1.jsonl', 'session_id': 's1', 'entities_count': 3},
                {'file': '/path/to/file2.jsonl', 'session_id': 's2', 'entities_count': 5},
            ]
        }

        # 不应该抛出异常
        ReportGenerator.print_stats(stats)

    def test_print_stats_empty(self):
        """测试空统计信息打印"""
        stats = {
            'files_processed': 0,
            'files_with_entities': 0,
            'total_entities': 0,
            'by_type': {},
            'processed_files': []
        }

        ReportGenerator.print_stats(stats)


class TestEntityExtractorEdgeCases:
    """测试 EntityExtractor 边缘情况"""

    def test_extract_no_messages(self):
        """测试提取空消息会话"""
        client = Mock()
        extractor = EntityExtractor(client)

        conversation = Conversation(
            session_id="test-session",
            messages=[]
        )

        entities = extractor.extract(conversation, dry_run=True)
        assert len(entities) == 0
        client.call.assert_not_called()  # 不应调用 LLM

    def test_extract_all_filtered(self):
        """测试所有消息都被过滤的情况"""
        client = Mock()
        extractor = EntityExtractor(client)

        conversation = Conversation(
            session_id="test-session",
            messages=[
                Message(role='user', content='system: hello', timestamp='2026-01-01T00:00:00Z')
            ]
        )

        entities = extractor.extract(conversation, dry_run=True)
        assert len(entities) == 0

    def test_parse_response_empty_entities(self):
        """测试解析空 entities 数组"""
        client = Mock()
        client.call.return_value = json.dumps({'entities': []})

        mock_validate = Mock(return_value=[])
        mock_create = Mock()
        extractor = EntityExtractor(client, mock_create, mock_validate)

        conversation = Conversation(
            session_id="test",
            messages=[Message(role='user', content='test', timestamp='2026-01-01T00:00:00Z')]
        )

        entities = extractor.extract(conversation, dry_run=True)
        assert len(entities) == 0

    def test_parse_response_with_concept_mapping(self):
        """测试 Concept 类型映射为 Finding"""
        client = Mock()
        client.call.return_value = json.dumps({
            'entities': [{
                'type': 'Concept',
                'title': '测试概念',
                'content': '概念内容',
                'confidence': 0.7,
                'tags': ['#concept']
            }]
        })

        mock_validate = Mock(return_value=[])
        mock_create = Mock()
        extractor = EntityExtractor(client, mock_create, mock_validate)

        conversation = Conversation(
            session_id="test",
            messages=[Message(role='user', content='这是一个测试会话消息', timestamp='2026-01-01T00:00:00Z')]
        )

        entities = extractor.extract(conversation, dry_run=True)
        assert len(entities) == 1
        assert entities[0].type == 'Finding'

    def test_parse_response_with_commitment(self):
        """测试 Commitment 类型解析"""
        client = Mock()
        client.call.return_value = json.dumps({
            'entities': [{
                'type': 'Commitment',
                'title': '测试承诺',
                'description': '承诺内容',
                'confidence': 0.9,
                'tags': ['#commitment']
            }]
        })

        mock_validate = Mock(return_value=[])
        mock_create = Mock()
        extractor = EntityExtractor(client, mock_create, mock_validate)

        conversation = Conversation(
            session_id="test",
            messages=[Message(role='user', content='这是一个测试会话消息内容', timestamp='2026-01-01T00:00:00Z')]
        )

        entities = extractor.extract(conversation, dry_run=True)
        assert len(entities) == 1
        assert entities[0].type == 'Commitment'


# 运行测试
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
