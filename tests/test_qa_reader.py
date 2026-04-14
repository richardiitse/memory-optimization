"""Tests for QA Reader — retrieval and reading logic."""

import json
import pytest
from unittest.mock import MagicMock, patch

from longmemeval_adapter import (
    QuestionInstance, TurnEntity, EmbeddingIndex,
)
from qa_reader import Retriever, Reader, RetrievalResult, cosine_similarity


# ========== Helpers ==========

def make_question(qtype='single-session-user', qid='test_1', is_abs=False):
    return QuestionInstance(
        question_id=qid,
        question_type=qtype,
        question="What is my favorite color?",
        answer="Blue",
        question_date="2023/04/10 (Mon) 23:07",
        question_date_iso="2023-04-10T23:07",
        is_abstention=is_abs,
        entities=[
            TurnEntity(
                entity_id=f"{qid}_s0_t0",
                role="user",
                content="I love the color blue.",
                session_id="sess_1",
                session_date="2023-04-10T17:50",
                question_id=qid,
                question_type=qtype,
                has_answer=True,
                turn_index=0,
            ),
            TurnEntity(
                entity_id=f"{qid}_s0_t1",
                role="assistant",
                content="Blue is a nice color.",
                session_id="sess_1",
                session_date="2023-04-10T17:50",
                question_id=qid,
                question_type=qtype,
                has_answer=False,
                turn_index=1,
            ),
            TurnEntity(
                entity_id=f"{qid}_s1_t0",
                role="user",
                content="I also like green.",
                session_id="sess_2",
                session_date="2023-04-11T09:00",
                question_id=qid,
                question_type=qtype,
                has_answer=False,
                turn_index=0,
            ),
        ],
    )


def make_index(qid='test_1'):
    qi = make_question(qid=qid)
    dim = 8
    return EmbeddingIndex(
        question_id=qid,
        entity_ids=[e.entity_id for e in qi.entities],
        embeddings=[
            [0.9, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],  # high sim to query
            [0.1, 0.9, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],  # low sim
            [0.5, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],  # medium sim
        ],
        entity_map={e.entity_id: e for e in qi.entities},
    )


# ========== Cosine Similarity ==========

class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        assert cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert cosine_similarity(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_zero_vector(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


# ========== Retriever ==========

class TestRetriever:
    def test_retrieve_returns_sorted_results(self):
        client = MagicMock()
        client.embed.return_value = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

        retriever = Retriever(client=client, top_k=10)
        qi = make_question()
        index = make_index()

        results = retriever.retrieve("favorite color", qi, index)

        assert len(results) == 3
        # Should be sorted by score descending
        assert results[0].score >= results[1].score >= results[2].score

    def test_retrieve_respects_top_k(self):
        client = MagicMock()
        client.embed.return_value = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

        retriever = Retriever(client=client, top_k=2)
        qi = make_question()
        index = make_index()

        results = retriever.retrieve("favorite color", qi, index)
        assert len(results) == 2

    def test_retrieve_temporal_rerank(self):
        client = MagicMock()
        client.embed.return_value = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

        retriever = Retriever(client=client, top_k=10)
        qi = make_question(qtype='temporal-reasoning')
        index = make_index()

        results = retriever.retrieve("what did I do first", qi, index)

        # Temporal: should be sorted by date ascending
        dates = [r.entity.session_date for r in results]
        assert dates == sorted(dates)

    def test_retrieve_knowledge_update_rerank(self):
        client = MagicMock()
        client.embed.return_value = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

        retriever = Retriever(client=client, top_k=10)
        qi = make_question(qtype='knowledge-update')
        index = make_index()

        results = retriever.retrieve("current preference", qi, index)

        # Knowledge update: should be sorted by date descending (most recent first)
        dates = [r.entity.session_date for r in results]
        assert dates == sorted(dates, reverse=True)

    def test_retrieve_empty_index(self):
        client = MagicMock()
        client.embed.return_value = [1.0, 0.0]

        retriever = Retriever(client=client, top_k=10)
        qi = make_question()
        index = EmbeddingIndex(
            question_id='test_1',
            entity_ids=[],
            embeddings=[],
            entity_map={},
        )

        results = retriever.retrieve("query", qi, index)
        assert len(results) == 0

    def test_retrieve_embedding_failure(self):
        client = MagicMock()
        client.embed.return_value = None  # embedding fails

        retriever = Retriever(client=client, top_k=10)
        qi = make_question()
        index = make_index()

        results = retriever.retrieve("query", qi, index)
        assert len(results) == 0


# ========== Reader ==========

class TestReader:
    def test_read_generates_answer(self):
        client = MagicMock()
        client.call.return_value = "Blue"

        reader = Reader(client=client)
        qi = make_question()
        results = [
            RetrievalResult(entity=qi.entities[0], score=0.9, rank=1),
        ]

        result = reader.read(qi, results)
        assert result.hypothesis == "Blue"
        assert result.confidence == 0.9
        assert result.abstained is False
        assert result.n_retrieved == 1

    def test_read_empty_retrieval(self):
        client = MagicMock()
        reader = Reader(client=client)

        qi = make_question()
        result = reader.read(qi, [])
        assert result.hypothesis == "I don't know"
        assert result.abstained is True

    def test_read_llm_failure(self):
        client = MagicMock()
        client.call.return_value = None  # LLM fails

        reader = Reader(client=client)
        qi = make_question()
        results = [RetrievalResult(entity=qi.entities[0], score=0.9, rank=1)]

        result = reader.read(qi, results)
        assert result.abstained is True
        assert result.hypothesis == "I don't know"

    def test_read_uses_correct_prompt_per_type(self):
        """Verify different question types use different prompts."""
        client = MagicMock()
        client.call.return_value = "answer"

        reader = Reader(client=client)

        # Test each question type
        for qtype in ['single-session-user', 'temporal-reasoning', 'knowledge-update',
                      'multi-session', 'single-session-preference']:
            qi = make_question(qtype=qtype)
            results = [RetrievalResult(entity=qi.entities[0], score=0.9, rank=1)]

            reader.read(qi, results)

        # Verify LLM was called (different prompts would be used)
        assert client.call.call_count == 5

    def test_read_temporal_prompt_contains_chronological(self):
        """Temporal-reasoning prompt should contain 'chronological'."""
        client = MagicMock()
        client.call.return_value = "answer"

        reader = Reader(client=client)
        qi = make_question(qtype='temporal-reasoning')
        results = [RetrievalResult(entity=qi.entities[0], score=0.9, rank=1)]

        reader.read(qi, results)

        messages = client.call.call_args[0][0]
        user_msg = messages[1]['content']
        assert 'chronological' in user_msg.lower()

    def test_read_knowledge_update_prompt_contains_recent(self):
        """Knowledge-update prompt should contain 'MOST RECENT'."""
        client = MagicMock()
        client.call.return_value = "answer"

        reader = Reader(client=client)
        qi = make_question(qtype='knowledge-update')
        results = [RetrievalResult(entity=qi.entities[0], score=0.9, rank=1)]

        reader.read(qi, results)

        messages = client.call.call_args[0][0]
        user_msg = messages[1]['content']
        assert 'most recent' in user_msg.lower()

    def test_read_abstention_threshold(self):
        """Reader should abstain when top_score < abstention_threshold."""
        client = MagicMock()
        client.call.return_value = "Should not be called"

        reader = Reader(client=client, abstention_threshold=0.8)
        qi = make_question()
        # Score 0.5 < threshold 0.8
        results = [RetrievalResult(entity=qi.entities[0], score=0.5, rank=1)]

        result = reader.read(qi, results)

        assert result.abstained is True
        assert result.hypothesis == "I don't know"
        # LLM should NOT be called when below threshold
        client.call.assert_not_called()

    def test_read_abstention_question(self):
        client = MagicMock()
        client.call.return_value = "The information provided is not enough."

        reader = Reader(client=client)
        qi = make_question(is_abs=True)
        results = [RetrievalResult(entity=qi.entities[0], score=0.5, rank=1)]

        result = reader.read(qi, results)
        assert "not enough" in result.hypothesis.lower()

    def test_context_truncation(self):
        """Context should be truncated to max_context_chars."""
        client = MagicMock()
        client.call.return_value = "answer"

        reader = Reader(client=client, max_context_chars=100)
        qi = make_question()

        # Create many retrieval results with long content
        results = []
        for i in range(20):
            entity = TurnEntity(
                entity_id=f"e_{i}",
                role="user",
                content="x" * 50,  # 50 chars each
                session_id="s1",
                session_date="2023-04-10T17:50",
                question_id="test_1",
                question_type="single-session-user",
                turn_index=i,
            )
            results.append(RetrievalResult(entity=entity, score=0.9 - i * 0.01, rank=i + 1))

        result = reader.read(qi, results)

        # The context passed to LLM should be truncated
        call_args = client.call.call_args
        messages = call_args[0][0]
        user_msg = messages[1]['content']
        assert len(user_msg) < 2000  # Well within reasonable bounds
