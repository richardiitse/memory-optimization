"""Tests for SemanticRetriever — hybrid scoring, MMR, entity loading."""

import json
import os
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from semantic_retriever import Entity, SemanticRetriever, _cache_key


# ── Fixtures ────────────────────────────────────────────────────────

def _make_kg_jsonl(entities, relations=None):
    """Create a temp JSONL file with given entities."""
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False, encoding='utf-8')
    for e in entities:
        f.write(json.dumps({"op": "create", "entity": e}, ensure_ascii=False) + '\n')
    if relations:
        for r in relations:
            f.write(json.dumps({"op": "relate", **r}, ensure_ascii=False) + '\n')
    f.close()
    return f.name


def _entity(id, type, name, desc, created=None, tags=None):
    return {
        "id": id, "type": type,
        "properties": {
            "name": name, "description": desc,
            "tags": tags or [],
        },
        "created": created or "2026-04-15T00:00:00+08:00",
    }


def _mock_llm(embedding=None):
    m = MagicMock()
    m.embed_model = "test-model"
    m.embed_base_url = "http://localhost:11434/api"
    m.embed.return_value = embedding or [0.1] * 8
    m.embed_batch.return_value = [embedding or [0.1] * 8] * 100
    return m


# ── Entity Loading ──────────────────────────────────────────────────

class TestEntityLoading:
    def test_load_create_entities(self):
        path = _make_kg_jsonl([
            _entity("c1", "Concept", "Test", "A test concept"),
            _entity("c2", "Decision", "Decide", "A decision"),
        ])
        try:
            r = SemanticRetriever(path, _mock_llm())
            assert len(r.entities) == 2
            assert r.entities[0].name == "Test"
            assert r.entities[1].type == "Decision"
        finally:
            os.unlink(path)

    def test_skip_merge_into_ops(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False, encoding='utf-8')
        f.write(json.dumps({"op": "create", "entity": _entity("c1", "Concept", "A", "desc")}) + '\n')
        f.write(json.dumps({"op": "merge_into", "source": "c1", "target": "c2"}) + '\n')
        f.write(json.dumps({"op": "create", "entity": _entity("c2", "Concept", "B", "desc2")}) + '\n')
        f.close()
        try:
            r = SemanticRetriever(f.name, _mock_llm())
            ids = [e.id for e in r.entities]
            assert "c1" not in ids  # merged away
            assert "c2" in ids
        finally:
            os.unlink(f.name)

    def test_corrupt_jsonl_lines_skipped(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False, encoding='utf-8')
        f.write('not valid json\n')
        f.write(json.dumps({"op": "create", "entity": _entity("c1", "Concept", "A", "desc")}) + '\n')
        f.write('also broken\n')
        f.close()
        try:
            r = SemanticRetriever(f.name, _mock_llm())
            assert len(r.entities) == 1
        finally:
            os.unlink(f.name)

    def test_missing_kg_file_returns_empty(self):
        r = SemanticRetriever("/nonexistent/path.jsonl", _mock_llm())
        assert r.entities == []
        assert r.get_related("any") == []  # no AttributeError

    def test_entities_from_real_kg(self):
        kg_path = Path(__file__).resolve().parent.parent / "ontology" / "graph.jsonl"
        if not kg_path.exists():
            pytest.skip("graph.jsonl not found")
        r = SemanticRetriever(str(kg_path), _mock_llm())
        assert len(r.entities) >= 297  # grows over time
        assert r.entities[0].id  # has valid ID


# ── Hybrid Scoring ─────────────────────────────────────────────────

class TestHybridScoring:
    def test_alpha_weights_affect_ranking(self):
        path = _make_kg_jsonl([
            _entity("c1", "Concept", "X", "x"),
            _entity("c2", "Concept", "Y", "y"),
        ])
        try:
            llm = _mock_llm([1.0, 0.0])

            # High alpha (0.9): semantic dominates, c1 wins
            r_high = SemanticRetriever(path, llm, alpha=0.9, tau_days=30)
            r_high.entities[0].embedding = [1.0, 0.0]
            r_high.entities[1].embedding = [0.0, 1.0]
            results_high = r_high.search("test", top_k=2, mmr_lambda=1.0)

            assert len(results_high) >= 1
            # The entity closest to query vector [1.0, 0.0] should rank first
            assert results_high[0].entity.id == "c1"
        finally:
            os.unlink(path)

    def test_temporal_decay(self):
        now = datetime.now(timezone.utc).isoformat()
        old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        path = _make_kg_jsonl([
            _entity("c1", "Concept", "New", "new", created=now),
            _entity("c2", "Concept", "Old", "old", created=old),
        ])
        try:
            llm = _mock_llm()
            r = SemanticRetriever(path, llm, alpha=0.5, tau_days=30)
            r.entities[0].embedding = [1.0, 0.0]
            r.entities[1].embedding = [1.0, 0.0]

            # Same semantic similarity, but temporal should favor newer
            new_score = r._temporal_score(r.entities[0])
            old_score = r._temporal_score(r.entities[1])
            assert new_score > old_score
        finally:
            os.unlink(path)

    def test_temporal_no_date_returns_neutral(self):
        e = Entity(id="x", type="Concept", name="X", description="x", created_at=None)
        r = SemanticRetriever.__new__(SemanticRetriever)
        r.tau_days = 30
        assert r._temporal_score(e) == 0.5


# ── MMR Diversification ────────────────────────────────────────────

class TestMMR:
    def test_mmr_returns_diverse_results(self):
        path = _make_kg_jsonl([
            _entity("c1", "Concept", "A", "aaa"),
            _entity("c2", "Concept", "B", "bbb"),
            _entity("c3", "Concept", "C", "ccc"),
            _entity("c4", "Concept", "D", "ddd"),
        ])
        try:
            llm = _mock_llm()
            r = SemanticRetriever(path, llm)
            # Give diverse embeddings
            r.entities[0].embedding = [1.0, 0.0]
            r.entities[1].embedding = [0.0, 1.0]
            r.entities[2].embedding = [1.0, 0.0]  # same as c1
            r.entities[3].embedding = [0.5, 0.5]

            llm.embed.return_value = [1.0, 0.0]  # query similar to c1/c3

            results = r.search("test", top_k=3, mmr_lambda=0.7)
            ids = [se.entity.id for se in results]
            assert len(results) <= 3
            # With lambda=0.7, c1 and c3 have identical embeddings.
            # MMR should prefer at least one diverse entity (c2 or c4).
            diverse_ids = {"c2", "c4"}
            assert bool(set(ids) & diverse_ids), \
                f"Expected at least one diverse entity, got {ids}"
        finally:
            os.unlink(path)

    def test_mmr_empty_results_when_no_embeddings(self):
        path = _make_kg_jsonl([_entity("c1", "Concept", "A", "a")])
        try:
            llm = _mock_llm()
            r = SemanticRetriever(path, llm)
            # No embeddings set, embed returns None
            llm.embed.return_value = None
            results = r.search("test", top_k=5)
            assert results == []
        finally:
            os.unlink(path)


# ── Related Entities ───────────────────────────────────────────────

class TestRelatedEntities:
    def test_get_related_with_relations(self):
        path = _make_kg_jsonl(
            entities=[
                _entity("c1", "Concept", "A", "aaa"),
                _entity("c2", "Concept", "B", "bbb"),
                _entity("c3", "Concept", "C", "ccc"),
            ],
            relations=[
                {"from": "c1", "to": "c2", "type": "related_to"},
                {"from": "c1", "to": "c3", "type": "depends_on"},
            ],
        )
        try:
            r = SemanticRetriever(path, _mock_llm())
            related = r.get_related("c1")
            related_ids = {e.id for e in related}
            assert related_ids == {"c2", "c3"}
        finally:
            os.unlink(path)

    def test_get_related_no_relations_returns_empty(self):
        path = _make_kg_jsonl([_entity("c1", "Concept", "A", "a")])
        try:
            r = SemanticRetriever(path, _mock_llm())
            assert r.get_related("c1") == []
        finally:
            os.unlink(path)


# ── Embedding Cache ────────────────────────────────────────────────

class TestEmbeddingCache:
    def test_cache_key_includes_model(self):
        k1 = _cache_key("model-a", "http://x", "hello")
        k2 = _cache_key("model-b", "http://x", "hello")
        assert k1 != k2

    def test_cache_key_includes_base_url(self):
        k1 = _cache_key("m", "http://a", "hello")
        k2 = _cache_key("m", "http://b", "hello")
        assert k1 != k2

    def test_cache_hit_avoids_api_call(self):
        path = _make_kg_jsonl([_entity("c1", "Concept", "A", "a")])
        try:
            cache = {}
            llm = _mock_llm([1.0, 0.0])
            r = SemanticRetriever(path, llm, embedding_cache=cache)

            # First call — cache miss
            v1 = r.get_embedding("hello")
            assert llm.embed.call_count == 1

            # Second call — cache hit
            v2 = r.get_embedding("hello")
            assert llm.embed.call_count == 1  # no additional call
            assert v1 == v2
        finally:
            os.unlink(path)


# ── Embed Entities Batch ──────────────────────────────────────────

class TestEmbedEntities:
    def test_embed_entities_populates_vectors(self):
        path = _make_kg_jsonl([
            _entity("c1", "Concept", "A", "aaa"),
            _entity("c2", "Concept", "B", "bbb"),
        ])
        try:
            vec1, vec2 = [0.8, 0.2], [0.3, 0.7]
            llm = _mock_llm()
            llm.embed_batch.return_value = [vec1, vec2]
            r = SemanticRetriever(path, llm)
            count = r.embed_entities()
            assert count == 2
            assert r.entities[0].embedding == vec1
            assert r.entities[1].embedding == vec2
        finally:
            os.unlink(path)

    def test_embed_entities_skips_cached(self):
        path = _make_kg_jsonl([_entity("c1", "Concept", "A", "aaa")])
        try:
            llm = _mock_llm()
            r = SemanticRetriever(path, llm, embedding_cache={})
            # Pre-populate cache
            text = "A aaa"
            key = _cache_key(llm.embed_model, llm.embed_base_url, text)
            cached_vec = [0.5, 0.5]
            r._cache[key] = cached_vec

            count = r.embed_entities()
            assert count == 0  # was cached, not newly embedded
            assert r.entities[0].embedding == cached_vec
            llm.embed_batch.assert_not_called()
        finally:
            os.unlink(path)


# ── Stats ──────────────────────────────────────────────────────────

class TestStats:
    def test_stats_returns_correct_counts(self):
        path = _make_kg_jsonl([
            _entity("c1", "Concept", "A", "a"),
            _entity("c2", "Decision", "B", "b"),
        ])
        try:
            r = SemanticRetriever(path, _mock_llm())
            r.entities[0].embedding = [1.0]
            stats = r.stats()
            assert stats["total"] == 2
            assert stats["by_type"] == {"Concept": 1, "Decision": 1}
            assert stats["with_embedding"] == 1
        finally:
            os.unlink(path)
