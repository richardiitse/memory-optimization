#!/usr/bin/env python3
"""
Tests for memory_ontology/entity_ops.py
"""

import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from memory_ontology.entity_ops import (
    generate_entity_id,
    get_default_decay_rate,
    add_memory_evolution_fields,
    create_entity,
    get_entity,
    _read_entity_from_graph,
    refresh_entity_strength,
    mark_entity_consolidated,
    apply_decay_to_entity,
    get_entities_by_strength,
    get_entities_by_type,
    get_strength_distribution,
)


class TestGenerateEntityId:
    """Tests for generate_entity_id function"""

    def test_generates_dec_prefix_for_decision(self):
        """Should use 'dec' prefix for Decision type"""
        entity_id = generate_entity_id('Decision')
        assert entity_id.startswith('dec_')

    def test_generates_find_prefix_for_finding(self):
        """Should use 'find' prefix for Finding type"""
        entity_id = generate_entity_id('Finding')
        assert entity_id.startswith('find_')

    def test_generates_lesson_prefix_for_lesson_learned(self):
        """Should use 'lesson' prefix for LessonLearned type"""
        entity_id = generate_entity_id('LessonLearned')
        assert entity_id.startswith('lesson_')

    def test_generates_commit_prefix_for_commitment(self):
        """Should use 'commit' prefix for Commitment type"""
        entity_id = generate_entity_id('Commitment')
        assert entity_id.startswith('commit_')

    def test_generates_skc_prefix_for_skill_card(self):
        """Should use 'skc' prefix for SkillCard type"""
        entity_id = generate_entity_id('SkillCard')
        assert entity_id.startswith('skc_')

    def test_generates_generic_prefix_for_unknown_type(self):
        """Should use 'ent' prefix for unknown types"""
        entity_id = generate_entity_id('UnknownType')
        assert entity_id.startswith('ent_')

    def test_id_is_unique_per_call(self):
        """Each call should generate a unique ID"""
        ids = [generate_entity_id('Decision') for _ in range(100)]
        assert len(set(ids)) == 100

    def test_generates_arch_prefix_for_archived_memory(self):
        """Should use 'arch' prefix for ArchivedMemory type"""
        entity_id = generate_entity_id('ArchivedMemory')
        assert entity_id.startswith('arch_')

    def test_generates_gate_prefix_for_gating_policy(self):
        """Should use 'gate' prefix for GatingPolicy type"""
        entity_id = generate_entity_id('GatingPolicy')
        assert entity_id.startswith('gate_')

    def test_generates_concept_prefix_for_concept(self):
        """Should use 'concept' prefix for Concept type"""
        entity_id = generate_entity_id('Concept')
        assert entity_id.startswith('concept_')


class TestGetDefaultDecayRate:
    """Tests for get_default_decay_rate function"""

    def test_decision_has_slow_decay(self):
        """Decision should have slow decay (0.95)"""
        rate = get_default_decay_rate('Decision')
        assert rate == 0.95

    def test_finding_has_fast_decay(self):
        """Finding should have fast decay (0.80)"""
        rate = get_default_decay_rate('Finding')
        assert rate == 0.80

    def test_lesson_learned_has_medium_decay(self):
        """LessonLearned should have medium decay (0.90)"""
        rate = get_default_decay_rate('LessonLearned')
        assert rate == 0.90

    def test_commitment_has_medium_decay(self):
        """Commitment should have medium decay (0.85)"""
        rate = get_default_decay_rate('Commitment')
        assert rate == 0.85

    def test_skill_card_has_slowest_decay(self):
        """SkillCard should have slowest decay (0.99)"""
        rate = get_default_decay_rate('SkillCard')
        assert rate == 0.99

    def test_unknown_type_uses_default(self):
        """Unknown types should use default decay rate"""
        rate = get_default_decay_rate('SomeUnknown')
        assert rate == 0.90  # default


class TestAddMemoryEvolutionFields:
    """Tests for add_memory_evolution_fields function"""

    def test_adds_strength_if_missing(self):
        """Should add strength=1.0 if not provided"""
        properties = {'title': 'Test'}
        result = add_memory_evolution_fields('Decision', properties)
        assert result['strength'] == 1.0

    def test_preserves_existing_strength(self):
        """Should not override existing strength"""
        properties = {'title': 'Test', 'strength': 0.5}
        result = add_memory_evolution_fields('Decision', properties)
        assert result['strength'] == 0.5

    def test_adds_decay_rate_if_missing(self):
        """Should add decay_rate based on entity type if not provided"""
        properties = {'title': 'Test'}
        result = add_memory_evolution_fields('Finding', properties)
        assert result['decay_rate'] == 0.80

    def test_preserves_existing_decay_rate(self):
        """Should not override existing decay_rate"""
        properties = {'title': 'Test', 'decay_rate': 0.99}
        result = add_memory_evolution_fields('Decision', properties)
        assert result['decay_rate'] == 0.99

    def test_adds_last_accessed_if_missing(self):
        """Should add last_accessed timestamp if not provided"""
        properties = {'title': 'Test'}
        result = add_memory_evolution_fields('Decision', properties)
        assert 'last_accessed' in result

    def test_adds_source_trust_defaults_to_medium(self):
        """Should add source_trust='medium' if not provided"""
        properties = {'title': 'Test'}
        result = add_memory_evolution_fields('Decision', properties)
        assert result['source_trust'] == 'medium'


class TestCreateEntity:
    """Tests for create_entity function"""

    def test_creates_entity_with_valid_id(self):
        """Should create entity with provided ID"""
        with patch('memory_ontology.entity_ops._write_to_graph') as mock_write, \
             patch('memory_ontology.entity_ops.validate_entity', return_value=[]):
            entity = create_entity('Decision', {'title': 'Test', 'rationale': 'Test rationale', 'made_at': '2026-01-01T00:00:00+08:00'}, entity_id='dec_custom')
            assert entity['id'] == 'dec_custom'
            assert entity['type'] == 'Decision'
            mock_write.assert_called_once()

    def test_generates_id_if_not_provided(self):
        """Should generate ID if not provided"""
        with patch('memory_ontology.entity_ops._write_to_graph') as mock_write, \
             patch('memory_ontology.entity_ops.validate_entity', return_value=[]):
            entity = create_entity('Decision', {'title': 'Test', 'rationale': 'Test', 'made_at': '2026-01-01T00:00:00+08:00'})
            assert entity['id'].startswith('dec_')

    def test_writes_to_graph(self):
        """Should write entity to graph"""
        with patch('memory_ontology.entity_ops._write_to_graph') as mock_write, \
             patch('memory_ontology.entity_ops.validate_entity', return_value=[]):
            create_entity('Decision', {'title': 'Test', 'rationale': 'Test', 'made_at': '2026-01-01T00:00:00+08:00'}, entity_id='dec_test')
            mock_write.assert_called_once()
            call_args = mock_write.call_args[0][0]
            assert 'dec_test' in call_args


class TestReadEntityFromGraph:
    """Tests for _read_entity_from_graph function"""

    def test_returns_none_for_nonexistent_entity(self):
        """Should return None for non-existent entity"""
        with patch('memory_ontology.entity_ops.load_all_entities', return_value={}):
            result = _read_entity_from_graph('nonexistent')
            assert result is None

    def test_returns_entity_when_found(self):
        """Should return entity when found"""
        mock_entities = {
            'dec_001': {'id': 'dec_001', 'type': 'Decision', 'properties': {}}
        }
        with patch('memory_ontology.entity_ops.load_all_entities', return_value=mock_entities):
            result = _read_entity_from_graph('dec_001')
            assert result['id'] == 'dec_001'


class TestGetEntitiesByStrength:
    """Tests for get_entities_by_strength function"""

    def test_returns_entities_below_threshold(self):
        """Should return entities with strength below threshold (archive candidates)"""
        mock_entities = {
            'dec_001': {'id': 'dec_001', 'type': 'Decision', 'properties': {'strength': 0.8}},
            'dec_002': {'id': 'dec_002', 'type': 'Decision', 'properties': {'strength': 0.5}},
            'dec_003': {'id': 'dec_003', 'type': 'Decision', 'properties': {'strength': 0.05}},
        }
        with patch('memory_ontology.entity_ops.load_all_entities', return_value=mock_entities):
            result = get_entities_by_strength(threshold=0.1)
            # Returns entities BELOW threshold (weak entities for archiving)
            assert len(result) == 1
            assert result[0]['id'] == 'dec_003'

    def test_default_threshold_is_01(self):
        """Default threshold should be 0.1"""
        mock_entities = {
            'dec_001': {'id': 'dec_001', 'type': 'Decision', 'properties': {'strength': 0.05}},
            'dec_002': {'id': 'dec_002', 'type': 'Decision', 'properties': {'strength': 0.15}},
        }
        with patch('memory_ontology.entity_ops.load_all_entities', return_value=mock_entities):
            result = get_entities_by_strength()
            assert len(result) == 1
            assert result[0]['id'] == 'dec_001'


class TestGetEntitiesByType:
    """Tests for get_entities_by_type function"""

    def test_returns_only_matching_type(self):
        """Should return only entities of specified type"""
        mock_entities = {
            'dec_001': {'id': 'dec_001', 'type': 'Decision', 'properties': {}},
            'dec_002': {'id': 'dec_002', 'type': 'Decision', 'properties': {}},
            'find_001': {'id': 'find_001', 'type': 'Finding', 'properties': {}},
        }
        with patch('memory_ontology.entity_ops.load_all_entities', return_value=mock_entities):
            result = get_entities_by_type('Decision')
            assert len(result) == 2
            assert all(e['type'] == 'Decision' for e in result)

    def test_returns_empty_list_for_no_matches(self):
        """Should return empty list if no entities match type"""
        mock_entities = {
            'dec_001': {'id': 'dec_001', 'type': 'Decision', 'properties': {}},
        }
        with patch('memory_ontology.entity_ops.load_all_entities', return_value=mock_entities):
            result = get_entities_by_type('Finding')
            assert len(result) == 0


class TestGetStrengthDistribution:
    """Tests for get_strength_distribution function"""

    def test_returns_distribution_by_entity_type(self):
        """Should return strength distribution grouped by entity type"""
        mock_entities = {
            'dec_001': {'id': 'dec_001', 'type': 'Decision', 'properties': {'strength': 0.95}},
            'dec_002': {'id': 'dec_002', 'type': 'Decision', 'properties': {'strength': 0.85}},
            'find_001': {'id': 'find_001', 'type': 'Finding', 'properties': {'strength': 0.25}},
        }
        with patch('memory_ontology.entity_ops.load_all_entities', return_value=mock_entities):
            result = get_strength_distribution()
            assert 'Decision' in result
            assert 'Finding' in result

    def test_calculates_correct_stats_for_type(self):
        """Should calculate correct count, avg, min, max for each type"""
        mock_entities = {
            'dec_001': {'id': 'dec_001', 'type': 'Decision', 'properties': {'strength': 0.95}},
            'dec_002': {'id': 'dec_002', 'type': 'Decision', 'properties': {'strength': 0.85}},
            'dec_003': {'id': 'dec_003', 'type': 'Decision', 'properties': {'strength': 0.25}},
        }
        with patch('memory_ontology.entity_ops.load_all_entities', return_value=mock_entities):
            result = get_strength_distribution()
            assert result['Decision']['count'] == 3
            assert result['Decision']['avg_strength'] == pytest.approx(0.6833, 0.01)
            assert result['Decision']['min_strength'] == 0.25
            assert result['Decision']['max_strength'] == 0.95
