#!/usr/bin/env python3
"""
Tests for memory_ontology/storage.py
"""

import json
import os
import sys
import tempfile
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock, call

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))


class TestAcquireLockWithTimeout:
    """Tests for _acquire_lock_with_timeout function"""

    def test_acquires_shared_lock_successfully(self):
        """Should acquire shared lock without blocking"""
        from memory_ontology.storage import _acquire_lock_with_timeout
        import fcntl

        with patch('fcntl.flock') as mock_flock:
            lock_f = _acquire_lock_with_timeout(Path('/tmp/test.lock'), fcntl.LOCK_SH)
            mock_flock.assert_called()
            lock_f.close()

    def test_acquires_exclusive_lock_successfully(self):
        """Should acquire exclusive lock without blocking"""
        from memory_ontology.storage import _acquire_lock_with_timeout
        import fcntl

        with patch('fcntl.flock') as mock_flock:
            lock_f = _acquire_lock_with_timeout(Path('/tmp/test.lock'), fcntl.LOCK_EX)
            mock_flock.assert_called()
            lock_f.close()

    def test_retries_on_blocking_io_error(self):
        """Should retry when lock is held by another process"""
        from memory_ontology.storage import _acquire_lock_with_timeout
        import fcntl

        call_count = [0]

        def mock_flock_side_effect(fd, op):
            call_count[0] += 1
            if call_count[0] < 3:
                raise BlockingIOError("Resource temporarily unavailable")
            # Success on 3rd attempt

        with patch('fcntl.flock', side_effect=mock_flock_side_effect):
            with patch('time.sleep'):  # Skip actual sleep
                lock_f = _acquire_lock_with_timeout(
                    Path('/tmp/test.lock'),
                    fcntl.LOCK_SH,
                    timeout=5.0
                )
                assert call_count[0] == 3
                lock_f.close()

    def test_raises_timeout_after_expiration(self):
        """Should raise TimeoutError after timeout expires"""
        from memory_ontology.storage import _acquire_lock_with_timeout
        import fcntl

        with patch('fcntl.flock', side_effect=BlockingIOError("Resource busy")):
            with patch('time.sleep'):  # Skip actual sleep
                with pytest.raises(TimeoutError) as exc_info:
                    _acquire_lock_with_timeout(
                        Path('/tmp/test.lock'),
                        fcntl.LOCK_EX,
                        timeout=0.5
                    )
                assert "KG lock timeout" in str(exc_info.value)
                assert "0.5s" in str(exc_info.value)


class TestWriteToGraph:
    """Tests for _write_to_graph function"""

    def test_writes_data_to_graph_file(self):
        """Should write data to graph.jsonl with lock"""
        from memory_ontology.storage import _write_to_graph

        with tempfile.TemporaryDirectory() as tmpdir:
            graph_file = Path(tmpdir) / 'graph.jsonl'
            lock_file = graph_file.with_suffix('.lock')

            with patch('memory_ontology.storage.GRAPH_FILE', graph_file), \
                 patch('memory_ontology.storage._acquire_lock_with_timeout') as mock_acquire, \
                 patch('fcntl.flock'):

                mock_lock = MagicMock()
                mock_acquire.return_value = mock_lock

                _write_to_graph('{"op":"create","entity":{"id":"test_1"}}\n')

                mock_acquire.assert_called_once()
                # Verify lock was released
                mock_lock.close.assert_called_once()

    def test_uses_append_mode(self):
        """Should open file in append mode to prevent truncation"""
        from memory_ontology.storage import _write_to_graph

        with tempfile.TemporaryDirectory() as tmpdir:
            graph_file = Path(tmpdir) / 'graph.jsonl'
            graph_file.write_text('{"op":"create","entity":{"id":"existing"}}\n')

            with patch('memory_ontology.storage.GRAPH_FILE', graph_file), \
                 patch('memory_ontology.storage._acquire_lock_with_timeout') as mock_acquire, \
                 patch('fcntl.flock'):

                mock_lock = MagicMock()
                mock_acquire.return_value = mock_lock

                _write_to_graph('{"op":"create","entity":{"id":"test_1"}}\n')

                # Verify existing content preserved
                content = graph_file.read_text()
                assert "existing" in content
                assert "test_1" in content


class TestLoadAllEntities:
    """Tests for load_all_entities function"""

    def test_returns_empty_dict_when_file_not_exists(self):
        """Should return empty dict if graph file doesn't exist"""
        from memory_ontology.storage import load_all_entities

        with tempfile.TemporaryDirectory() as tmpdir:
            graph_file = Path(tmpdir) / 'graph.jsonl'

            with patch('memory_ontology.storage.GRAPH_FILE', graph_file), \
                 patch('memory_ontology.storage._acquire_lock_with_timeout'):
                result = load_all_entities()
                assert result == {}

    def test_loads_entities_in_correct_order(self):
        """Should process create before update for same entity"""
        from memory_ontology.storage import load_all_entities

        with tempfile.TemporaryDirectory() as tmpdir:
            graph_file = Path(tmpdir) / 'graph.jsonl'
            # Update comes before create in file, but should be processed after
            lines = [
                '{"op":"update","entity":{"id":"dec_001","properties":{"note":"updated"}},"timestamp":"2026-01-02T00:00:00+08:00"}',
                '{"op":"create","entity":{"id":"dec_001","type":"Decision","properties":{"note":"original","strength":0.8}},"timestamp":"2026-01-01T00:00:00+08:00"}'
            ]
            graph_file.write_text('\n'.join(lines) + '\n')

            with patch('memory_ontology.storage.GRAPH_FILE', graph_file), \
                 patch('memory_ontology.storage._acquire_lock_with_timeout'), \
                 patch('fcntl.flock'):
                result = load_all_entities()

                # Create is processed first, then update
                assert result['dec_001']['properties']['note'] == 'updated'
                assert result['dec_001']['properties']['strength'] == 0.8

    def test_skips_relation_records(self):
        """Should skip records that are not create or update"""
        from memory_ontology.storage import load_all_entities

        with tempfile.TemporaryDirectory() as tmpdir:
            graph_file = Path(tmpdir) / 'graph.jsonl'
            lines = [
                '{"op":"create","entity":{"id":"dec_001","type":"Decision","properties":{}},"timestamp":"2026-01-01T00:00:00+08:00"}',
                '{"op":"relate","relation":{"from":"dec_001","to":"dec_002","type":"led_to"}}',
                '{"op":"create","entity":{"id":"find_001","type":"Finding","properties":{}},"timestamp":"2026-01-01T00:00:00+08:00"}'
            ]
            graph_file.write_text('\n'.join(lines) + '\n')

            with patch('memory_ontology.storage.GRAPH_FILE', graph_file), \
                 patch('memory_ontology.storage._acquire_lock_with_timeout'), \
                 patch('fcntl.flock'):
                result = load_all_entities()

                assert 'dec_001' in result
                assert 'find_001' in result
                # Relations are skipped
                assert len(result) == 2

    def test_handles_json_decode_error_gracefully(self):
        """Should skip lines with invalid JSON"""
        from memory_ontology.storage import load_all_entities

        with tempfile.TemporaryDirectory() as tmpdir:
            graph_file = Path(tmpdir) / 'graph.jsonl'
            lines = [
                '{"op":"create","entity":{"id":"dec_001","type":"Decision","properties":{}},"timestamp":"2026-01-01T00:00:00+08:00"}',
                'invalid json line',
                '{"op":"create","entity":{"id":"dec_002","type":"Decision","properties":{}},"timestamp":"2026-01-01T00:00:00+08:00"}'
            ]
            graph_file.write_text('\n'.join(lines) + '\n')

            with patch('memory_ontology.storage.GRAPH_FILE', graph_file), \
                 patch('memory_ontology.storage._acquire_lock_with_timeout'), \
                 patch('fcntl.flock'):
                result = load_all_entities()

                assert 'dec_001' in result
                assert 'dec_002' in result


class TestLoadAllRelations:
    """Tests for load_all_relations function"""

    def test_returns_empty_list_when_file_not_exists(self):
        """Should return empty list if graph file doesn't exist"""
        from memory_ontology.storage import load_all_relations

        with tempfile.TemporaryDirectory() as tmpdir:
            graph_file = Path(tmpdir) / 'graph.jsonl'

            with patch('memory_ontology.storage.GRAPH_FILE', graph_file), \
                 patch('memory_ontology.storage._acquire_lock_with_timeout'):
                result = load_all_relations()
                assert result == []

    def test_loads_only_relate_operations(self):
        """Should load only 'relate' operations"""
        from memory_ontology.storage import load_all_relations

        with tempfile.TemporaryDirectory() as tmpdir:
            graph_file = Path(tmpdir) / 'graph.jsonl'
            lines = [
                '{"op":"create","entity":{"id":"dec_001","type":"Decision","properties":{}},"timestamp":"2026-01-01T00:00:00+08:00"}',
                '{"op":"relate","relation":{"from":"dec_001","to":"dec_002","type":"led_to"},"timestamp":"2026-01-01T00:00:00+08:00"}',
                '{"op":"update","entity":{"id":"dec_001","properties":{}},"timestamp":"2026-01-01T00:00:00+08:00"}'
            ]
            graph_file.write_text('\n'.join(lines) + '\n')

            with patch('memory_ontology.storage.GRAPH_FILE', graph_file), \
                 patch('memory_ontology.storage._acquire_lock_with_timeout'), \
                 patch('fcntl.flock'):
                result = load_all_relations()

                assert len(result) == 1
                assert result[0]['relation']['from'] == 'dec_001'


class TestCompactGraph:
    """Tests for compact_graph function"""

    def test_returns_zeros_when_file_not_exists(self):
        """Should return zeros if graph file doesn't exist"""
        from memory_ontology.storage import compact_graph

        with tempfile.TemporaryDirectory() as tmpdir:
            graph_file = Path(tmpdir) / 'graph.jsonl'

            with patch('memory_ontology.storage.GRAPH_FILE', graph_file), \
                 patch('memory_ontology.storage._acquire_lock_with_timeout'):
                result = compact_graph()
                assert result['kept'] == 0
                assert result['total_ops'] == 0

    def test_no_compaction_needed_when_already_compact(self):
        """Should return early if no compaction needed"""
        from memory_ontology.storage import compact_graph

        with tempfile.TemporaryDirectory() as tmpdir:
            graph_file = Path(tmpdir) / 'graph.jsonl'
            lines = [
                '{"op":"create","entity":{"id":"dec_001","type":"Decision","properties":{}},"timestamp":"2026-01-01T00:00:00+08:00"}',
            ]
            graph_file.write_text('\n'.join(lines) + '\n')

            with patch('memory_ontology.storage.GRAPH_FILE', graph_file), \
                 patch('memory_ontology.storage._acquire_lock_with_timeout'), \
                 patch('fcntl.flock'):
                result = compact_graph()

                assert result['kept'] == 1
                assert result['total_ops'] == 1
                assert 'compacted_to' not in result

    def test_compacts_multiple_updates_to_single_entity(self):
        """Should keep only latest version of entity"""
        from memory_ontology.storage import compact_graph

        with tempfile.TemporaryDirectory() as tmpdir:
            graph_file = Path(tmpdir) / 'graph.jsonl'
            lines = [
                '{"op":"create","entity":{"id":"dec_001","type":"Decision","properties":{"v":1}},"timestamp":"2026-01-01T00:00:00+08:00"}',
                '{"op":"update","entity":{"id":"dec_001","properties":{"v":2}},"timestamp":"2026-01-02T00:00:00+08:00"}',
                '{"op":"update","entity":{"id":"dec_001","properties":{"v":3}},"timestamp":"2026-01-03T00:00:00+08:00"}',
            ]
            graph_file.write_text('\n'.join(lines) + '\n')

            with patch('memory_ontology.storage.GRAPH_FILE', graph_file), \
                 patch('memory_ontology.storage._acquire_lock_with_timeout'), \
                 patch('fcntl.flock'):
                result = compact_graph()

                assert result['kept'] == 1
                assert result['total_ops'] == 3
                assert result['compacted_to'] == 1

                # Verify compacted content
                content = graph_file.read_text()
                assert 'dec_001' in content
                # Should only have one create line
                assert content.count('dec_001') == 1

    def test_preserves_relations_during_compaction(self):
        """Should preserve relation records during compaction"""
        from memory_ontology.storage import compact_graph

        with tempfile.TemporaryDirectory() as tmpdir:
            graph_file = Path(tmpdir) / 'graph.jsonl'
            lines = [
                '{"op":"create","entity":{"id":"dec_001","type":"Decision","properties":{"v":1}},"timestamp":"2026-01-01T00:00:00+08:00"}',
                '{"op":"update","entity":{"id":"dec_001","properties":{"v":2}},"timestamp":"2026-01-02T00:00:00+08:00"}',
                '{"op":"relate","relation":{"from":"dec_001","to":"dec_002"},"timestamp":"2026-01-01T00:00:00+08:00"}',
            ]
            graph_file.write_text('\n'.join(lines) + '\n')

            with patch('memory_ontology.storage.GRAPH_FILE', graph_file), \
                 patch('memory_ontology.storage._acquire_lock_with_timeout'), \
                 patch('fcntl.flock'):
                result = compact_graph()

                assert result['kept'] == 1
                assert result['compacted_to'] == 2  # 1 entity + 1 relation

                content = graph_file.read_text()
                assert 'dec_001' in content
                assert 'relate' in content


class TestEnsureOntologyDir:
    """Tests for ensure_ontology_dir function"""

    def test_creates_directory_if_not_exists(self):
        """Should create ontology directory if it doesn't exist"""
        from memory_ontology.storage import ensure_ontology_dir

        with tempfile.TemporaryDirectory() as tmpdir:
            ontology_dir = Path(tmpdir) / 'ontology'
            graph_file = ontology_dir / 'graph.jsonl'

            with patch('memory_ontology.storage.ONTOLOGY_DIR', ontology_dir), \
                 patch('memory_ontology.storage.GRAPH_FILE', graph_file):
                ensure_ontology_dir()

                assert ontology_dir.exists()
                assert graph_file.exists()

    def test_does_not_overwrite_existing_graph_file(self):
        """Should not overwrite existing graph file"""
        from memory_ontology.storage import ensure_ontology_dir

        with tempfile.TemporaryDirectory() as tmpdir:
            ontology_dir = Path(tmpdir) / 'ontology'
            ontology_dir.mkdir()
            graph_file = ontology_dir / 'graph.jsonl'
            graph_file.write_text('{"op":"create","entity":{"id":"existing"}}\n')

            with patch('memory_ontology.storage.ONTOLOGY_DIR', ontology_dir), \
                 patch('memory_ontology.storage.GRAPH_FILE', graph_file):
                ensure_ontology_dir()

                content = graph_file.read_text()
                assert "existing" in content
