#!/usr/bin/env python3
"""Tests for evaluate_with_llm.py"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import re

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from evaluate_with_llm import (
    get_anscheck_prompt,
    judge_with_llm,
    _evaluate_one,
)


class TestGetAnscheckPrompt:
    """Tests for prompt template generation."""

    def test_single_session_user_prompt(self):
        """Should generate correct prompt for single-session-user."""
        prompt = get_anscheck_prompt(
            task='single-session-user',
            question='What did the user say?',
            answer='hello',
            response='The user said hello',
            abstention=False,
        )
        assert 'Question: What did the user say?' in prompt
        assert 'Correct Answer: hello' in prompt
        assert 'Model Response: The user said hello' in prompt
        assert 'yes or no only' in prompt

    def test_temporal_reasoning_prompt_includes_off_by_one(self):
        """temporal-reasoning should include off-by-one suffix."""
        temporal_prompt = get_anscheck_prompt(
            task='temporal-reasoning',
            question='How many days?',
            answer='18',
            response='19 days',
            abstention=False,
        )
        non_temporal_prompt = get_anscheck_prompt(
            task='single-session-user',
            question='How many days?',
            answer='18',
            response='19 days',
            abstention=False,
        )
        # temporal-reasoning has off-by-one relaxation
        assert 'off-by-one' in temporal_prompt
        assert 'off-by-one' not in non_temporal_prompt

    def test_knowledge_update_prompt_includes_suffix(self):
        """knowledge-update should include knowledge-update suffix."""
        ku_prompt = get_anscheck_prompt(
            task='knowledge-update',
            question='What is the updated email?',
            answer='new@example.com',
            response='new@example.com',
            abstention=False,
        )
        ss_prompt = get_anscheck_prompt(
            task='single-session-user',
            question='What is the updated email?',
            answer='new@example.com',
            response='new@example.com',
            abstention=False,
        )
        assert 'updated answer' in ku_prompt
        assert ku_prompt != ss_prompt

    def test_preference_uses_rubric_template(self):
        """single-session-preference should use rubric template."""
        prompt = get_anscheck_prompt(
            task='single-session-preference',
            question='What is the user preference?',
            answer='likes dark mode',
            response='prefers dark theme',
            abstention=False,
        )
        assert 'Rubric:' in prompt
        assert 'Correct Answer:' not in prompt

    def test_abstention_prompt_format(self):
        """Abstention questions should use abstention template."""
        prompt = get_anscheck_prompt(
            task='single-session-user',
            question='What was discussed?',
            answer='Cannot be determined from context',
            response='I cannot answer',
            abstention=True,
        )
        assert 'unanswerable' in prompt.lower() or 'incomplete' in prompt.lower()
        assert 'Model Response: I cannot answer' in prompt

    def test_unknown_task_raises(self):
        """Unknown task type should raise NotImplementedError."""
        with pytest.raises(NotImplementedError, match='Unknown task type'):
            get_anscheck_prompt(
                task='unknown-task',
                question='Test?',
                answer='answer',
                response='response',
                abstention=False,
            )

    def test_answer_can_be_integer(self):
        """Answer can be an integer (grid search issue)."""
        prompt = get_anscheck_prompt(
            task='single-session-user',
            question='How many?',
            answer=42,
            response='42',
            abstention=False,
        )
        assert 'Correct Answer: 42' in prompt


class TestJudgeWithLlm:
    """Tests for LLM judgment."""

    def test_judge_yes_response(self):
        """Should return is_correct=True for 'yes' response."""
        client = MagicMock()
        client.call.return_value = '  YES  '

        is_correct, content = judge_with_llm(
            client=client,
            question='Test question?',
            answer='answer',
            response='model response',
            task='single-session-user',
            is_abstention=False,
        )

        assert is_correct is True
        assert content == 'YES'
        client.call.assert_called_once()

    def test_judge_no_response(self):
        """Should return is_correct=False for 'no' response."""
        client = MagicMock()
        client.call.return_value = 'No, that is incorrect.'

        is_correct, content = judge_with_llm(
            client=client,
            question='Test question?',
            answer='answer',
            response='model response',
            task='single-session-user',
            is_abstention=False,
        )

        assert is_correct is False

    def test_judge_llm_failure_returns_error(self):
        """Should return False when LLM call returns None."""
        client = MagicMock()
        client.call.return_value = None

        is_correct, err_msg = judge_with_llm(
            client=client,
            question='Test question?',
            answer='answer',
            response='model response',
            task='single-session-user',
            is_abstention=False,
        )

        assert is_correct is False
        assert 'error' in err_msg.lower()

    def test_judge_yes_in_sentence(self):
        """Should find 'yes' within a sentence."""
        client = MagicMock()
        client.call.return_value = 'The answer is yes, it matches.'

        is_correct, _ = judge_with_llm(
            client=client,
            question='Test?',
            answer='answer',
            response='response',
            task='single-session-user',
            is_abstention=False,
        )

        assert is_correct is True

    def test_judge_no_in_sentence(self):
        """Should not match 'yes' when only 'no' is the answer."""
        client = MagicMock()
        client.call.return_value = 'No, that is not correct.'

        is_correct, content = judge_with_llm(
            client=client,
            question='Test?',
            answer='answer',
            response='response',
            task='single-session-user',
            is_abstention=False,
        )

        assert is_correct is False


class TestEvaluateOne:
    """Tests for _evaluate_one."""

    def test_evaluate_one_returns_correct_structure(self):
        """Should return correct result dict."""
        client = MagicMock()
        client.call.return_value = 'YES'

        hyp = {'question_id': 'q1', 'hypothesis': 'answer'}
        qid2ref = {
            'q1': {
                'question': 'What is 2+2?',
                'answer': '4',
                'question_type': 'single-session-user',
            }
        }

        result = _evaluate_one(0, hyp, qid2ref, client)

        assert result['question_id'] == 'q1'
        assert result['is_correct'] is True
        assert result['question_type'] == 'single-session-user'
        assert 'hypothesis' in result
        assert 'reference_answer' in result
        assert 'llm_judgment' in result

    def test_evaluate_one_skips_unknown_qid(self):
        """Should return None for unknown question ID."""
        client = MagicMock()
        hyp = {'question_id': 'unknown_q', 'hypothesis': 'answer'}
        qid2ref = {}

        result = _evaluate_one(0, hyp, qid2ref, client)

        assert result is None
        client.call.assert_not_called()

    def test_evaluate_one_detects_abstention_from_qid(self):
        """Should detect abstention from _abs suffix."""
        client = MagicMock()
        client.call.return_value = 'yes'

        hyp = {'question_id': 'q1_abs', 'hypothesis': 'I dont know'}
        qid2ref = {
            'q1_abs': {
                'question': 'What was discussed?',
                'answer': 'Cannot be determined',
                'question_type': 'single-session-user',
            }
        }

        result = _evaluate_one(0, hyp, qid2ref, client)

        assert result['is_abstention'] is True
