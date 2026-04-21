"""End-to-end tests for metacognition enhancement pipeline."""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from metacog_enhancer import MetacogEnhancer
from semantic_retriever import SemanticRetriever


def _make_kg_jsonl(entities):
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False, encoding='utf-8')
    for e in entities:
        f.write(json.dumps({"op": "create", "entity": e}, ensure_ascii=False) + '\n')
    f.close()
    return f.name


def _entity(id, name, desc, created=None):
    return {
        "id": id, "type": "Concept",
        "properties": {"name": name, "description": desc, "tags": ["#test"]},
        "created": created or "2026-04-15T00:00:00+08:00",
    }


def _mock_llm(embedding):
    m = MagicMock()
    m.embed_model = "test"
    m.embed_base_url = "http://localhost"
    m.embed.return_value = embedding
    m.embed_batch.return_value = [embedding]
    return m


class TestE2EMetacognition:
    def test_bias_detection_enhances_semantic_search(self):
        """Real bias query → enhanced → semantic search returns results."""
        path = _make_kg_jsonl([
            _entity("c1", "架构简化", "过度简化架构决策的危险"),
            _entity("c2", "技术选型", "技术选型应考虑多维度因素"),
        ])
        try:
            llm = _mock_llm([0.8, 0.6])
            r = SemanticRetriever(path, llm, alpha=0.6, tau_days=30)
            r.entities[0].embedding = [0.9, 0.5]
            r.entities[1].embedding = [0.7, 0.8]

            enhancer = MetacogEnhancer()
            enhancement = enhancer.enhance("这个架构最佳方案是什么？")

            assert len(enhancement.matched_biases) >= 1
            assert len(enhancement.challenge_questions) >= 2

            results = r.search(enhancement.enhanced_query, top_k=5, mmr_lambda=0.7)
            assert len(results) >= 1
        finally:
            os.unlink(path)

    def test_fallback_no_ai_wiki_no_crash(self):
        """When AI-wiki missing, system works with raw query."""
        path = _make_kg_jsonl([_entity("c1", "Test", "test entity")])
        try:
            llm = _mock_llm([0.5, 0.5])
            r = SemanticRetriever(path, llm)
            r.entities[0].embedding = [1.0, 0.0]

            enhancer = MetacogEnhancer("/nonexistent/path")
            assert len(enhancer.context) == 0

            enhancement = enhancer.enhance("test query")
            assert enhancement.enhanced_query == "test query"

            results = r.search(enhancement.enhanced_query, top_k=5)
            # Should still return results (no crash)
            assert isinstance(results, list)
        finally:
            os.unlink(path)

    def test_mmr_diversifies_similar_entities(self):
        """MMR returns diverse results even with similar embeddings."""
        path = _make_kg_jsonl([
            _entity("c1", "A", "first", created=datetime.now(timezone.utc).isoformat()),
            _entity("c2", "B", "second", created=datetime.now(timezone.utc).isoformat()),
            _entity("c3", "C", "third", created=datetime.now(timezone.utc).isoformat()),
        ])
        try:
            llm = _mock_llm([1.0, 0.0])
            r = SemanticRetriever(path, llm, alpha=0.7, tau_days=30)
            # c1 and c3 have similar embeddings, c2 is different
            r.entities[0].embedding = [1.0, 0.0]
            r.entities[1].embedding = [0.0, 1.0]
            r.entities[2].embedding = [0.95, 0.05]

            results = r.search("test", top_k=2, mmr_lambda=0.5)
            # With low lambda, should prefer diverse: one of c1/c3 + c2
            assert len(results) == 2
            ids = {se.entity.id for se in results}
            # c2 (diverse) should be included
            assert "c2" in ids
        finally:
            os.unlink(path)

    def test_temporal_boosts_recent_entities(self):
        """Newer entities get higher temporal scores."""
        now = datetime.now(timezone.utc).isoformat()
        old = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()

        path = _make_kg_jsonl([
            _entity("c1", "New", "recent", created=now),
            _entity("c2", "Old", "ancient", created=old),
        ])
        try:
            llm = _mock_llm([1.0, 0.0])
            r = SemanticRetriever(path, llm, alpha=0.3, tau_days=30)  # heavy temporal weight
            r.entities[0].embedding = [1.0, 0.0]
            r.entities[1].embedding = [1.0, 0.0]  # same semantic

            results = r.search("test", top_k=2, mmr_lambda=1.0)
            assert len(results) == 2
            # Same embedding, lambda=1.0 ignores diversity, temporal wins
            assert results[0].entity.name == "New"
        finally:
            os.unlink(path)
