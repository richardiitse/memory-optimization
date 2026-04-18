#!/usr/bin/env python3
"""Tests for filter_temporal_questions.py"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from filter_temporal_questions import filter_questions


@pytest.fixture
def sample_oracle_data():
    """Sample oracle data with multiple question types."""
    return [
        {
            'question_id': 'q1',
            'question_type': 'temporal-reasoning',
            'question': 'How long did the project take?',
            'answer': '3 months',
            'question_date': '2023/04/10 (Mon) 23:07',
            'haystack_dates': ['2023/01/01 (Sun) 12:00', '2023/01/02 (Mon) 12:00'],
            'haystack_sessions': [[{'role': 'user', 'content': 'hello'}]],
            'haystack_session_ids': ['s1'],
        },
        {
            'question_id': 'q2',
            'question_type': 'single-session-user',
            'question': 'What did the user say?',
            'answer': 'hello',
            'question_date': '2023/04/10 (Mon) 23:07',
            'haystack_dates': ['2023/01/01 (Sun) 12:00'],
            'haystack_sessions': [[{'role': 'user', 'content': 'hello'}]],
            'haystack_session_ids': ['s1'],
        },
        {
            'question_id': 'q3',
            'question_type': 'temporal-reasoning',
            'question': 'When was the last meeting?',
            'answer': '2023-01-02',
            'question_date': '2023/04/10 (Mon) 23:07',
            'haystack_dates': ['2023/01/01 (Sun) 12:00'],
            'haystack_sessions': [[{'role': 'user', 'content': 'meeting'}]],
            'haystack_session_ids': ['s1'],
        },
    ]


class TestFilterQuestions:
    """Tests for filter_questions function."""

    def test_filter_temporal_reasoning(self, sample_oracle_data, tmp_path):
        """Should filter only temporal-reasoning questions."""
        input_file = tmp_path / 'oracle.json'
        output_file = tmp_path / 'output.json'
        input_file.write_text(json.dumps(sample_oracle_data))

        with patch('filter_temporal_questions.print') as mock_print:
            filter_questions(str(input_file), str(output_file), 'temporal-reasoning')

        result = json.loads(output_file.read_text())
        assert len(result) == 2
        assert all(item['question_type'] == 'temporal-reasoning' for item in result)

    def test_filter_single_session_user(self, sample_oracle_data, tmp_path):
        """Should filter single-session-user questions."""
        input_file = tmp_path / 'oracle.json'
        output_file = tmp_path / 'output.json'
        input_file.write_text(json.dumps(sample_oracle_data))

        with patch('filter_temporal_questions.print'):
            filter_questions(str(input_file), str(output_file), 'single-session-user')

        result = json.loads(output_file.read_text())
        assert len(result) == 1
        assert result[0]['question_id'] == 'q2'

    def test_filter_no_matches(self, sample_oracle_data, tmp_path):
        """Should return empty list when no questions match type."""
        input_file = tmp_path / 'oracle.json'
        output_file = tmp_path / 'output.json'
        input_file.write_text(json.dumps(sample_oracle_data))

        with patch('filter_temporal_questions.print'):
            filter_questions(str(input_file), str(output_file), 'non-existent-type')

        result = json.loads(output_file.read_text())
        assert result == []

    def test_time_span_single_day(self, sample_oracle_data, tmp_path, capsys):
        """Should correctly count single-day time spans."""
        # q1 has 2 different dates (2023/01/01, 2023/01/02), q3 has 1 date
        input_file = tmp_path / 'oracle.json'
        output_file = tmp_path / 'output.json'
        input_file.write_text(json.dumps(sample_oracle_data))

        filter_questions(str(input_file), str(output_file), 'temporal-reasoning')

        captured = capsys.readouterr()
        # q1 has 2 dates (multi-day), q3 has 1 date (single-day)
        assert '单日: 1' in captured.out
        assert '多日: 1' in captured.out

    def test_creates_output_directory(self, sample_oracle_data, tmp_path):
        """Should create output parent directories if they don't exist."""
        input_file = tmp_path / 'oracle.json'
        output_file = tmp_path / 'deeply' / 'nested' / 'output.json'
        input_file.write_text(json.dumps(sample_oracle_data))

        with patch('filter_temporal_questions.print'):
            filter_questions(str(input_file), str(output_file), 'temporal-reasoning')

        assert output_file.exists()
        result = json.loads(output_file.read_text())
        assert len(result) == 2

    def test_preserves_full_question_data(self, sample_oracle_data, tmp_path):
        """Should preserve all fields in filtered questions."""
        input_file = tmp_path / 'oracle.json'
        output_file = tmp_path / 'output.json'
        input_file.write_text(json.dumps(sample_oracle_data))

        with patch('filter_temporal_questions.print'):
            filter_questions(str(input_file), str(output_file), 'temporal-reasoning')

        result = json.loads(output_file.read_text())
        q1 = next(item for item in result if item['question_id'] == 'q1')
        assert q1['question'] == 'How long did the project take?'
        assert q1['answer'] == '3 months'
        assert q1['haystack_session_ids'] == ['s1']
