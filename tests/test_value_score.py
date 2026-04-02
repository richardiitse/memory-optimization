#!/usr/bin/env python3
"""
Tests for Phase 6: Value-Aware Retrieval
"""

import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from memory_ontology.value_score import (
    ValueScoreCalculator,
    value_aware_sort,
    DEFAULT_WEIGHTS,
)


class TestValueScoreCalculator:
    """Test ValueScoreCalculator"""

    def test_default_weights(self):
        """Test default weights are defined"""
        assert DEFAULT_WEIGHTS['source_reliability'] == 0.20
        assert DEFAULT_WEIGHTS['strength'] == 0.20
        assert DEFAULT_WEIGHTS['significance'] == 0.25
        assert DEFAULT_WEIGHTS['preference_match'] == 0.20
        assert DEFAULT_WEIGHTS['recency_boost'] == 0.15

    def test_calculate_with_no_entity_data(self):
        """Test calculation with minimal entity data"""
        calc = ValueScoreCalculator()
        entity = {
            'id': 'test_123',
            'type': 'Decision',
            'properties': {
                'title': 'Test',
                'strength': 1.0
            }
        }

        score = calc.calculate(entity)
        assert 0.0 <= score <= 1.0

    def test_calculate_with_custom_weights(self):
        """Test calculation with custom weights"""
        weights = {
            'source_reliability': 0.0,
            'strength': 0.5,
            'significance': 0.0,
            'preference_match': 0.0,
            'recency_boost': 0.5
        }
        calc = ValueScoreCalculator(weights=weights)
        entity = {
            'id': 'test_123',
            'type': 'Decision',
            'properties': {
                'title': 'Test',
                'strength': 0.8
            }
        }

        score = calc.calculate(entity)
        assert 0.0 <= score <= 1.0

    def test_calculate_batch(self):
        """Test batch calculation"""
        calc = ValueScoreCalculator()
        entities = [
            {
                'id': 'test_1',
                'type': 'Decision',
                'properties': {'title': 'Test 1', 'strength': 1.0}
            },
            {
                'id': 'test_2',
                'type': 'Decision',
                'properties': {'title': 'Test 2', 'strength': 0.5}
            },
        ]

        results = calc.calculate_batch(entities)
        assert len(results) == 2
        assert results[0][1] >= results[1][1]
        assert results[0][0]['id'] == 'test_1'

    def test_calculate_source_reliability_default(self):
        """Test source reliability defaults to 0.5 when no source"""
        calc = ValueScoreCalculator()
        entity = {
            'id': 'test_123',
            'type': 'Decision',
            'properties': {'title': 'Test'}
        }

        score = calc._calculate_source_reliability(entity)
        assert score == 0.5

    def test_calculate_strength(self):
        """Test strength calculation"""
        calc = ValueScoreCalculator()
        entity = {
            'id': 'test_123',
            'type': 'Decision',
            'properties': {'title': 'Test', 'strength': 0.75}
        }

        score = calc._calculate_strength(entity)
        assert score == 0.75

    def test_calculate_strength_default(self):
        """Test strength defaults to 1.0"""
        calc = ValueScoreCalculator()
        entity = {
            'id': 'test_123',
            'type': 'Decision',
            'properties': {'title': 'Test'}
        }

        score = calc._calculate_strength(entity)
        assert score == 1.0

    def test_calculate_recency_boost_recent(self):
        """Test recency boost for recent entities"""
        calc = ValueScoreCalculator()
        now = datetime.now()
        entity = {
            'id': 'test_123',
            'type': 'Decision',
            'properties': {
                'title': 'Test',
                'last_accessed': (now - timedelta(hours=12)).isoformat()
            }
        }

        score = calc._calculate_recency_boost(entity)
        assert score == 1.0

    def test_calculate_recency_boost_week_old(self):
        """Test recency boost for week-old entities"""
        calc = ValueScoreCalculator()
        now = datetime.now()
        entity = {
            'id': 'test_123',
            'type': 'Decision',
            'properties': {
                'title': 'Test',
                'last_accessed': (now - timedelta(days=5)).isoformat()
            }
        }

        score = calc._calculate_recency_boost(entity)
        assert score == 0.8

    def test_calculate_recency_boost_old(self):
        """Test recency boost for old entities"""
        calc = ValueScoreCalculator()
        now = datetime.now()
        entity = {
            'id': 'test_123',
            'type': 'Decision',
            'properties': {
                'title': 'Test',
                'last_accessed': (now - timedelta(days=60)).isoformat()
            }
        }

        score = calc._calculate_recency_boost(entity)
        assert score == 0.4

    def test_calculate_preference_match_no_prefs(self):
        """Test preference match defaults to 0.5 with no preferences"""
        calc = ValueScoreCalculator()
        entity = {
            'id': 'test_123',
            'type': 'Decision',
            'properties': {'title': 'Test'}
        }

        score = calc._calculate_preference_match(entity)
        assert score == 0.5

    def test_calculate_preference_match_with_prefs(self):
        """Test preference match with matching preferences"""
        calc = ValueScoreCalculator()
        entity = {
            'id': 'test_123',
            'type': 'Decision',
            'properties': {
                'title': 'Test Decision',
                'tags': ['#architecture']
            }
        }

        preferences = [
            {
                'id': 'pref_123',
                'type': 'Preference',
                'properties': {
                    'preference_type': 'entity_type',
                    'pattern': 'Decision',
                    'confidence': 0.9
                }
            },
            {
                'id': 'pref_456',
                'type': 'Preference',
                'properties': {
                    'preference_type': 'tag',
                    'pattern': '#architecture',
                    'confidence': 0.8
                }
            }
        ]
        calc.preferences = preferences

        score = calc._calculate_preference_match(entity)
        assert score > 0.5

    def test_get_components(self):
        """Test getting all score components"""
        calc = ValueScoreCalculator()
        entity = {
            'id': 'test_123',
            'type': 'Decision',
            'properties': {
                'title': 'Test',
                'strength': 0.8
            }
        }

        components = calc.get_components(entity)
        assert 'source_reliability' in components
        assert 'strength' in components
        assert 'significance' in components
        assert 'preference_match' in components
        assert 'recency_boost' in components

        assert 'score' in components['strength']
        assert 'weight' in components['strength']


class TestValueAwareSort:
    """Test value_aware_sort function"""

    def test_sort_returns_tuples(self):
        """Test sort returns list of tuples"""
        entities = [
            {
                'id': 'test_1',
                'type': 'Decision',
                'properties': {'title': 'Test 1', 'strength': 0.5}
            },
            {
                'id': 'test_2',
                'type': 'Decision',
                'properties': {'title': 'Test 2', 'strength': 1.0}
            },
        ]

        results = value_aware_sort(entities)
        assert all(isinstance(r, tuple) for r in results)
        assert all(len(r) == 2 for r in results)

    def test_sort_descending(self):
        """Test sort is descending by score"""
        entities = [
            {
                'id': 'test_1',
                'type': 'Decision',
                'properties': {'title': 'Test 1', 'strength': 0.3}
            },
            {
                'id': 'test_2',
                'type': 'Decision',
                'properties': {'title': 'Test 2', 'strength': 0.9}
            },
            {
                'id': 'test_3',
                'type': 'Decision',
                'properties': {'title': 'Test 3', 'strength': 0.6}
            },
        ]

        results = value_aware_sort(entities)
        scores = [r[1] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_sort_with_empty_list(self):
        """Test sort with empty list"""
        results = value_aware_sort([])
        assert results == []


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
