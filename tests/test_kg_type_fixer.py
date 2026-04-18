#!/usr/bin/env python3
"""
Smoke tests for KG Type Fixer
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from kg_type_fixer import (
    infer_type,
    parse_jsonl_file,
    fix_kg_file,
    PREFIX_TYPE_MAP,
)


class TestInferType:
    """Tests for infer_type() — infer entity type from ID prefix."""

    @pytest.mark.parametrize("prefix,expected", [
        ("find_abc123", "Finding"),
        ("commit_xyz789", "Commitment"),
        ("dec_hello", "Decision"),
        ("lesson_001", "LessonLearned"),
        ("skil_card", "Skill"),
        ("skill_card2", "Skill"),
        ("skc_abc", "SkillCard"),
        ("ent_xyz", "Entity"),
    ])
    def test_prefix_mapping(self, prefix, expected):
        result, inferred = infer_type(prefix)
        assert result == expected
        assert inferred is True

    @pytest.mark.parametrize("unknown_id", [
        "unknown_123",
        "xyz_abc",
        "orphan_001",
        "",
    ])
    def test_unknown_prefix_returns_empty(self, unknown_id):
        result, inferred = infer_type(unknown_id)
        assert result == ""
        assert inferred is False


class TestParseJsonlFile:
    """Tests for parse_jsonl_file() — JSONL parser with multi-object merge handling."""

    def test_simple_jsonl(self, tmp_path):
        """Single JSON objects per line — standard case."""
        f = tmp_path / "simple.jsonl"
        f.write_text('{"id":"1"}\n{"id":"2"}\n', encoding="utf-8")
        lines = parse_jsonl_file(f)
        assert len(lines) == 2

    def test_multi_object_merged_line(self, tmp_path):
        """Multiple JSON objects merged into one line — common JSONL corruption."""
        f = tmp_path / "merged.jsonl"
        # Two objects merged on one line: }\n{
        f.write_text('{"id":"1"}{"id":"2"}\n', encoding="utf-8")
        lines = parse_jsonl_file(f)
        assert len(lines) == 2
        assert json.loads(lines[0])["id"] == "1"
        assert json.loads(lines[1])["id"] == "2"

    def test_nested_json_with_newlines(self, tmp_path):
        """JSON with embedded newlines inside string values."""
        f = tmp_path / "nested.jsonl"
        f.write_text('{"msg":"line1\\nline2"}\n', encoding="utf-8")
        lines = parse_jsonl_file(f)
        assert len(lines) == 1
        assert json.loads(lines[0])["msg"] == "line1\nline2"


class TestFixKgFile:
    """Tests for fix_kg_file() — fixes entities missing type field."""

    def test_dry_run_does_not_modify_file(self, tmp_path):
        """Dry run should not write any changes."""
        f = tmp_path / "graph.jsonl"
        f.write_text('{"id":"1"}\n', encoding="utf-8")

        stats = fix_kg_file(f, dry_run=True)
        # File content unchanged
        assert f.read_text(encoding="utf-8") == '{"id":"1"}\n'

    def test_fixes_missing_type_from_prefix(self, tmp_path):
        """Entity missing type with known prefix should be fixed."""
        f = tmp_path / "graph.jsonl"
        f.write_text(
            '{"op":"create","entity":{"id":"find_test123","type":null}}\n',
            encoding="utf-8",
        )

        stats = fix_kg_file(f, dry_run=False)
        # Type should be inferred and file updated
        content = f.read_text(encoding="utf-8")
        fixed = json.loads(content.strip())
        assert fixed["entity"]["type"] == "Finding"

    def test_preserves_existing_type(self, tmp_path):
        """Entity already having type should be unchanged."""
        f = tmp_path / "graph.jsonl"
        original = '{"op":"create","entity":{"id":"find_123","type":"Decision"}}\n'
        f.write_text(original, encoding="utf-8")

        stats = fix_kg_file(f, dry_run=False)
        assert f.read_text(encoding="utf-8") == original

    def test_unknown_prefix_no_inference(self, tmp_path):
        """Entity with unknown prefix and no type stays unchanged."""
        f = tmp_path / "graph.jsonl"
        f.write_text(
            '{"op":"create","entity":{"id":"unknown_123","type":null}}\n',
            encoding="utf-8",
        )

        stats = fix_kg_file(f, dry_run=False)
        assert stats["no_inference"] == 1
        content = f.read_text(encoding="utf-8")
        assert json.loads(content.strip())["entity"].get("type") is None

    def test_relation_objects_skipped(self, tmp_path):
        """Relation objects should be passed through unchanged."""
        f = tmp_path / "graph.jsonl"
        f.write_text(
            '{"op":"create","relation":{"id":"rel_1","type":"RELATES"}}\n',
            encoding="utf-8",
        )

        stats = fix_kg_file(f, dry_run=False)
        assert stats["relations"] == 1
        assert "RELATES" in f.read_text(encoding="utf-8")

    def test_handles_jsonl_merging(self, tmp_path):
        """Multi-object merged line is split and processed correctly."""
        f = tmp_path / "graph.jsonl"
        # find_ with null type + entity with existing type — merged on one line
        f.write_text(
            '{"op":"create","entity":{"id":"find_test","type":null}}{"op":"create","entity":{"id":"dec_abc","type":"Decision"}}\n',
            encoding="utf-8",
        )

        stats = fix_kg_file(f, dry_run=False)
        content = f.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        # First should be fixed to Finding, second should be unchanged Decision
        entities = [json.loads(l)["entity"] for l in lines]
        assert entities[0]["type"] == "Finding"
        assert entities[1]["type"] == "Decision"
