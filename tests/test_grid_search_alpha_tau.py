#!/usr/bin/env python3
"""Tests for grid_search_alpha_tau.py"""

import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from grid_search_alpha_tau import string_match_score, score_results, GridResult


class TestStringMatchScore:
    """Tests for string_match_score function."""

    def test_exact_match(self):
        """Should return True for exact match."""
        assert string_match_score('blue', 'blue') is True
        assert string_match_score('Hello World', 'hello world') is True

    def test_substring_match(self):
        """Should return True when answer is substring of hypothesis."""
        assert string_match_score('The answer is blue', 'blue') is True
        assert string_match_score('blue is the color', 'blue') is True

    def test_hypothesis_substring_of_answer(self):
        """Should return True when hypothesis is substring of answer."""
        assert string_match_score('blue', 'the color is blue') is True

    def test_case_insensitive(self):
        """Should match case-insensitively."""
        assert string_match_score('BLUE', 'blue') is True
        assert string_match_score('Blue', 'BLUE') is True

    def test_strips_punctuation(self):
        """Should strip common punctuation before matching."""
        assert string_match_score('blue.', 'blue') is True
        assert string_match_score('blue!', 'blue') is True
        assert string_match_score('blue,', 'blue') is True
        assert string_match_score('"blue"', 'blue') is True

    def test_empty_hypothesis(self):
        """Should return False for empty hypothesis."""
        assert string_match_score('', 'blue') is False
        assert string_match_score(None, 'blue') is False

    def test_empty_answer(self):
        """Should return False for empty answer."""
        assert string_match_score('blue', '') is False
        assert string_match_score('blue', None) is False

    def test_both_empty(self):
        """Should return False when both are empty."""
        assert string_match_score('', '') is False

    def test_integer_answer(self):
        """Should handle integer answers (grid search edge case)."""
        assert string_match_score('The answer is 42', 42) is True
        assert string_match_score('42', 42) is True
        assert string_match_score('forty-two', 42) is False

    def test_no_match(self):
        """Should return False when no match."""
        assert string_match_score('red', 'blue') is False
        assert string_match_score('completely wrong', 'blue') is False


class TestScoreResults:
    """Tests for score_results function."""

    def test_correct_increments(self, tmp_path):
        """Should increment correct when string_match_score is True."""
        jsonl = tmp_path / 'results.jsonl'
        jsonl.write_text(
            json.dumps({'question_id': 'q1', 'hypothesis': 'blue'}) + '\n'
        )
        gt = {'q1': 'blue'}

        correct, total, abstained = score_results(str(jsonl), gt)

        assert correct == 1
        assert total == 1
        assert abstained == 0

    def test_abstain_counts(self, tmp_path):
        """Should count abstention separately."""
        jsonl = tmp_path / 'results.jsonl'
        jsonl.write_text('\n'.join([
            json.dumps({'question_id': 'q1', 'hypothesis': "I don't know"}),
            json.dumps({'question_id': 'q2', 'hypothesis': "I do not know"}),
            json.dumps({'question_id': 'q3', 'hypothesis': 'unknown'}),
            json.dumps({'question_id': 'q4', 'hypothesis': ''}),
        ]))
        gt = {f'q{i}': f'answer{i}' for i in range(1, 5)}

        correct, total, abstained = score_results(str(jsonl), gt)

        assert abstained == 4
        assert correct == 0
        assert total == 4

    def test_skips_unknown_qids(self, tmp_path):
        """Should skip question IDs not in ground truth."""
        jsonl = tmp_path / 'results.jsonl'
        jsonl.write_text(
            json.dumps({'question_id': 'unknown', 'hypothesis': 'blue'}) + '\n'
        )
        gt = {}

        correct, total, abstained = score_results(str(jsonl), gt)

        assert total == 0

    def test_ignores_empty_lines(self, tmp_path):
        """Should skip empty lines in JSONL."""
        jsonl = tmp_path / 'results.jsonl'
        jsonl.write_text(
            json.dumps({'question_id': 'q1', 'hypothesis': 'blue'}) + '\n\n  \n'
        )
        gt = {'q1': 'blue'}

        correct, total, abstained = score_results(str(jsonl), gt)

        assert total == 1

    def test_mixed_correct_and_incorrect(self, tmp_path):
        """Should correctly count both correct and incorrect."""
        jsonl = tmp_path / 'results.jsonl'
        jsonl.write_text('\n'.join([
            json.dumps({'question_id': 'q1', 'hypothesis': 'blue'}),
            json.dumps({'question_id': 'q2', 'hypothesis': 'red'}),
            json.dumps({'question_id': 'q3', 'hypothesis': 'the color is green'}),
        ]))
        gt = {'q1': 'blue', 'q2': 'blue', 'q3': 'green'}

        correct, total, abstained = score_results(str(jsonl), gt)

        assert correct == 2  # q1 and q3
        assert total == 3
        assert abstained == 0


class TestGridResult:
    """Tests for GridResult dataclass."""

    def test_grid_result_fields(self):
        """Should have all expected fields."""
        r = GridResult(alpha=0.6, tau=30, accuracy=0.5, correct=50,
                       total=100, abstained=7, avg_confidence=0.6, timing_ms=1000.0)
        assert r.alpha == 0.6
        assert r.tau == 30
        assert r.accuracy == 0.5
        assert r.correct == 50
        assert r.total == 100
        assert r.abstained == 7
        assert r.avg_confidence == 0.6
        assert r.timing_ms == 1000.0
