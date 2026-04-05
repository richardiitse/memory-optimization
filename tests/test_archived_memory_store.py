#!/usr/bin/env python3
"""
Tests for archived_memory_store.py
"""

import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))


class TestArchivedMemoryStore:
    """Tests for ArchivedMemoryStore class"""

    def test_init_creates_cold_storage_dir(self):
        """Should create cold storage directory on init"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from archived_memory_store import ArchivedMemoryStore
            store = ArchivedMemoryStore(cold_storage_dir=Path(tmpdir) / 'cold')
            assert (Path(tmpdir) / 'cold').exists()

    def test_list_archived_returns_list(self):
        """Should return list of archived entities"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from archived_memory_store import ArchivedMemoryStore
            with patch('archived_memory_store.get_all_archived_entities', return_value=[]):
                store = ArchivedMemoryStore(cold_storage_dir=Path(tmpdir) / 'cold')
                result = store.list_archived()
                assert isinstance(result, list)

    def test_list_archived_filters_by_reason(self):
        """Should filter archived entities by reason"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from archived_memory_store import ArchivedMemoryStore
            mock_entities = [
                {'id': 'arch_1', 'properties': {'archived_reason': 'weak'}},
                {'id': 'arch_2', 'properties': {'archived_reason': 'decay'}},
            ]
            with patch('archived_memory_store.get_all_archived_entities', return_value=mock_entities):
                store = ArchivedMemoryStore(cold_storage_dir=Path(tmpdir) / 'cold')
                result = store.list_archived(reason='weak')
                assert len(result) == 1
                assert result[0]['id'] == 'arch_1'

    def test_list_archived_respects_limit(self):
        """Should limit the number of returned entities"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from archived_memory_store import ArchivedMemoryStore
            mock_entities = [
                {'id': f'arch_{i}', 'properties': {'archived_reason': 'weak', 'archived_at': f'2026-01-{i:02d}T00:00:00+08:00'}}
                for i in range(1, 6)
            ]
            with patch('archived_memory_store.get_all_archived_entities', return_value=mock_entities):
                store = ArchivedMemoryStore(cold_storage_dir=Path(tmpdir) / 'cold')
                result = store.list_archived(limit=3)
                assert len(result) == 3

    def test_recover_entity_returns_none_for_nonexistent(self):
        """Should return None for non-existent entity"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from archived_memory_store import ArchivedMemoryStore
            with patch('archived_memory_store.get_all_archived_entities', return_value=[]):
                store = ArchivedMemoryStore(cold_storage_dir=Path(tmpdir) / 'cold')
                result = store.recover_entity('nonexistent')
                assert result is None

    def test_recover_entity_returns_archived_entity(self):
        """Should return the archived entity for recovery"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from archived_memory_store import ArchivedMemoryStore
            mock_entity = {
                'id': 'arch_1',
                'type': 'ArchivedMemory',
                'properties': {
                    'original_id': 'dec_001',
                    'archived_reason': 'weak',
                    'original_type': 'Decision',
                }
            }
            with patch('archived_memory_store.get_all_archived_entities', return_value=[mock_entity]), \
                 patch('archived_memory_store.recover_entity_from_cold_storage', return_value=mock_entity):
                store = ArchivedMemoryStore(cold_storage_dir=Path(tmpdir) / 'cold')
                result = store.recover_entity('arch_1')
                assert result is not None
                assert result['id'] == 'arch_1'

    def test_search_archived_returns_matches(self):
        """Should return matching archived entities"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from archived_memory_store import ArchivedMemoryStore
            mock_entities = [
                {'id': 'arch_1', 'properties': {
                    'original_entity': {'properties': {'title': 'Python optimization'}},
                    'archived_reason': 'weak'
                }},
                {'id': 'arch_2', 'properties': {
                    'original_entity': {'properties': {'title': 'Database migration'}},
                    'archived_reason': 'decay'
                }},
            ]
            with patch('archived_memory_store.get_all_archived_entities', return_value=mock_entities):
                store = ArchivedMemoryStore(cold_storage_dir=Path(tmpdir) / 'cold')
                result = store.search_archived('Python')
                assert len(result) == 1
                assert result[0]['id'] == 'arch_1'

    def test_search_archived_respects_limit(self):
        """Should limit search results"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from archived_memory_store import ArchivedMemoryStore
            mock_entities = [
                {'id': f'arch_{i}', 'properties': {
                    'original_entity': {'properties': {'title': f'Item {i}'}},
                    'archived_reason': 'weak'
                }}
                for i in range(20)
            ]
            with patch('archived_memory_store.get_all_archived_entities', return_value=mock_entities):
                store = ArchivedMemoryStore(cold_storage_dir=Path(tmpdir) / 'cold')
                result = store.search_archived('Item', limit=5)
                assert len(result) == 5

    def test_permanently_delete_returns_false_for_nonexistent(self):
        """Should return False for non-existent entity"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from archived_memory_store import ArchivedMemoryStore
            with patch('archived_memory_store.get_all_archived_entities', return_value=[]):
                store = ArchivedMemoryStore(cold_storage_dir=Path(tmpdir) / 'cold')
                result = store.permanently_delete('nonexistent')
                assert result is False

    def test_get_stats_returns_dict(self):
        """Should return storage statistics"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from archived_memory_store import ArchivedMemoryStore
            with patch('archived_memory_store.get_all_archived_entities', return_value=[]):
                store = ArchivedMemoryStore(cold_storage_dir=Path(tmpdir) / 'cold')
                result = store.get_stats()
                assert isinstance(result, dict)

    def test_get_stats_counts_by_reason(self):
        """Should count archived entities by reason"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from archived_memory_store import ArchivedMemoryStore
            mock_entities = [
                {'id': 'arch_1', 'properties': {'archived_reason': 'weak'}},
                {'id': 'arch_2', 'properties': {'archived_reason': 'weak'}},
                {'id': 'arch_3', 'properties': {'archived_reason': 'decay'}},
            ]
            with patch('archived_memory_store.get_all_archived_entities', return_value=mock_entities):
                store = ArchivedMemoryStore(cold_storage_dir=Path(tmpdir) / 'cold')
                result = store.get_stats()
                assert result['by_reason']['weak'] == 2
                assert result['by_reason']['decay'] == 1

    def test_purge_old_returns_dry_run_info(self):
        """Should return info about entities that would be purged in dry run"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from archived_memory_store import ArchivedMemoryStore
            old_date = (datetime.now() - timedelta(days=100)).isoformat()
            mock_entities = [
                {'id': 'arch_1', 'properties': {'archived_reason': 'weak', 'archived_at': old_date}},
            ]
            with patch('archived_memory_store.get_all_archived_entities', return_value=mock_entities):
                store = ArchivedMemoryStore(cold_storage_dir=Path(tmpdir) / 'cold')
                result = store.purge_old(days=90, dry_run=True)
                assert result['candidates'] == 1
                assert result['dry_run'] is True

    def test_purge_old_deletes_when_not_dry_run(self):
        """Should actually delete entities when dry_run is False"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from archived_memory_store import ArchivedMemoryStore
            old_date = (datetime.now() - timedelta(days=100)).isoformat()
            mock_entities = [
                {'id': 'arch_1', 'properties': {'archived_reason': 'weak', 'archived_at': old_date}},
            ]
            with patch('archived_memory_store.get_all_archived_entities', return_value=mock_entities):
                store = ArchivedMemoryStore(cold_storage_dir=Path(tmpdir) / 'cold')
                # Mock permanently_delete to return True
                with patch.object(store, 'permanently_delete', return_value=True):
                    result = store.purge_old(days=90, dry_run=False)
                    assert result['deleted'] == 1
                    assert result['dry_run'] is False
