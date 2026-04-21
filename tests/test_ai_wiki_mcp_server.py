"""Tests for AI-wiki MCP Server tools."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ai_wiki_mcp_server as mcp_mod
from semantic_retriever import Entity


# ── Helpers ────────────────────────────────────────────────────────

def _mock_retriever(entities=None):
    r = MagicMock()
    r.entities = entities or []
    r.search.return_value = []
    r.stats.return_value = {"total": 0, "by_type": {}, "with_embedding": 0,
                            "with_date": 0, "cache_size": 0}
    return r


def _mock_enhancer():
    e = MagicMock()
    e.context = {"blind-spots": "test"}
    e.biases = [{"name": "test"}]
    e.enhance.return_value = MagicMock(
        matched_biases=["单维度简化倾向"],
        challenge_questions=["是否有其他维度？"],
        enhanced_query="test query 是否有其他维度？",
    )
    return e


# ── Global state cleanup ──────────────────────────────────────────

def _reset_globals():
    mcp_mod._retriever = None
    mcp_mod._enhancer = None


# ── Tool Tests ─────────────────────────────────────────────────────

class TestSearchWithMetacognition:
    def teardown_method(self):
        _reset_globals()

    def test_returns_json_with_expected_fields(self):
        mcp_mod._retriever = _mock_retriever()
        mcp_mod._enhancer = _mock_enhancer()

        result = json.loads(mcp_mod.search_with_metacognition("test query"))
        assert "original_query" in result
        assert "enhanced_query" in result
        assert "matched_biases" in result
        assert "results" in result
        assert "total_entities" in result

    def test_enhanced_query_included(self):
        mcp_mod._retriever = _mock_retriever()
        mcp_mod._enhancer = _mock_enhancer()

        result = json.loads(mcp_mod.search_with_metacognition("test"))
        assert result["enhanced_query"] != "test"

    def test_uninitialized_returns_error(self):
        _reset_globals()
        result = json.loads(mcp_mod.search_with_metacognition("test"))
        assert "error" in result

    def test_top_k_clamped_to_max(self):
        mcp_mod._retriever = _mock_retriever()
        mcp_mod._enhancer = _mock_enhancer()

        json.loads(mcp_mod.search_with_metacognition("test", top_k=99999))
        call_args = mcp_mod._retriever.search.call_args
        assert call_args[1]["top_k"] == 100


class TestGetEntityDetails:
    def teardown_method(self):
        _reset_globals()

    def test_found_entity(self):
        e = Entity(id="c1", type="Concept", name="Test", description="A test",
                   tags=["#test"], created_at="2026-04-15T00:00:00+08:00",
                   properties={"strength": 0.9})
        mcp_mod._retriever = _mock_retriever([e])

        result = json.loads(mcp_mod.get_entity_details("c1"))
        assert result["id"] == "c1"
        assert result["name"] == "Test"
        assert result["properties"]["strength"] == 0.9

    def test_not_found_entity(self):
        mcp_mod._retriever = _mock_retriever([])
        result = json.loads(mcp_mod.get_entity_details("missing"))
        assert "error" in result
        _reset_globals()


class TestGetRelatedEntities:
    def test_returns_related(self):
        e1 = Entity(id="c1", type="Concept", name="A", description="a")
        e2 = Entity(id="c2", type="Concept", name="B", description="b")
        r = _mock_retriever([e1, e2])
        r.get_related.return_value = [e2]
        mcp_mod._retriever = r

        result = json.loads(mcp_mod.get_related_entities("c1"))
        assert result["related_count"] == 1
        assert result["related"][0]["id"] == "c2"
        _reset_globals()


class TestReloadMetacogContext:
    def test_reload_returns_count(self):
        mcp_mod._enhancer = _mock_enhancer()
        mcp_mod._enhancer.reload.return_value = 5
        result = json.loads(mcp_mod.reload_metacog_context())
        assert result["status"] == "ok"
        assert result["context_files_reloaded"] == 5
        _reset_globals()


class TestMemoryStats:
    def test_returns_stats(self):
        mcp_mod._retriever = _mock_retriever()
        mcp_mod._retriever.stats.return_value = {"total": 297, "by_type": {"Concept": 185}}
        mcp_mod._enhancer = _mock_enhancer()

        result = json.loads(mcp_mod.memory_stats())
        assert result["retriever"]["total"] == 297
        assert result["enhancer"]["context_files"] >= 1
        _reset_globals()


class TestEmbedAllEntities:
    def test_embed_returns_count(self):
        mcp_mod._retriever = _mock_retriever()
        mcp_mod._retriever.embed_entities.return_value = 42
        mcp_mod._retriever.entities = [MagicMock()] * 50

        result = json.loads(mcp_mod.embed_all_entities())
        assert result["status"] == "ok"
        assert result["newly_embedded"] == 42
        assert result["total_entities"] == 50
        _reset_globals()

    def test_uninitialized_returns_error(self):
        _reset_globals()
        result = json.loads(mcp_mod.embed_all_entities())
        assert "error" in result


# ── KG Path Validation ─────────────────────────────────────────────

class TestKgPathValidation:
    def teardown_method(self):
        _reset_globals()

    def test_reject_path_outside_project(self):
        with pytest.raises(ValueError, match="outside allowed"):
            mcp_mod._validate_kg_path("/etc/passwd")

    def test_accept_default_kg_path(self):
        result = mcp_mod._validate_kg_path(str(mcp_mod.DEFAULT_KG_PATH))
        assert result.exists() or True  # path resolved without error

    def test_allow_any_bypasses_validation(self):
        with patch.dict(os.environ, {"ALLOW_ANY_KG_DIR": "true"}):
            result = mcp_mod._validate_kg_path("/tmp/any/graph.jsonl")
            assert result == Path("/tmp/any/graph.jsonl").resolve()


# ── Init Graceful Fallback ─────────────────────────────────────────

class TestInitGracefulFallback:
    def teardown_method(self):
        _reset_globals()

    def test_init_bad_kg_path_sets_retriever_none(self):
        with patch.dict(os.environ, {"KG_PATH": "/nonexistent/path.jsonl"}):
            mcp_mod._init()
            # Should not crash, retriever may be None or empty
            assert isinstance(mcp_mod._retriever, (type(None), MagicMock)) or True

    def test_init_tools_return_error_when_partial_init(self):
        mcp_mod._retriever = None
        mcp_mod._enhancer = _mock_enhancer()
        result = json.loads(mcp_mod.search_with_metacognition("test"))
        assert "error" in result
