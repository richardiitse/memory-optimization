#!/usr/bin/env python3
"""
QA Reader — Two-stage retrieval + reading for LongMemEval.

Stage 1 (Retriever): Embedding-based semantic search over entities.
Stage 2 (Reader): LLM generates answer from retrieved context.

Supports 6 question types with type-specific retrieval strategies.

Usage:
    python3 qa_reader.py --help
"""

import json
import logging
import math
import sys
import time
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from utils.llm_client import LLMClient
from utils import cosine_similarity
from longmemeval_adapter import (
    LongMemEvalAdapter, QuestionInstance, TurnEntity, EmbeddingIndex,
)

logger = logging.getLogger(__name__)

SECONDS_PER_DAY = 86400.0
DEFAULT_READER_TEMPERATURE = 0.5


# ========== Retriever ==========

@dataclass
class RetrievalResult:
    """Result from retrieval stage."""
    entity: TurnEntity
    score: float
    rank: int


class Retriever:
    """Embedding-based retriever with question-type-aware strategies."""

    def __init__(
        self,
        client: LLMClient,
        top_k: int = 20,
        alpha: float = 1.0,
        tau: float = 30.0,
    ):
        self.client = client
        self.top_k = top_k
        self.alpha = alpha  # semantic weight (1-alpha = temporal weight)
        self.tau = tau      # temporal decay constant in days

    def retrieve(
        self,
        question: str,
        qi: QuestionInstance,
        index: EmbeddingIndex,
    ) -> List[RetrievalResult]:
        """Retrieve top-k entities for a question.

        When alpha < 1.0, uses hybrid scoring:
          combined = alpha * semantic_sim + (1-alpha) * temporal_proximity
        When alpha = 1.0, pure semantic similarity (original behavior).

        Applies question-type-specific post-processing:
        - temporal-reasoning: Sort results by session_date after retrieval
        - knowledge-update: Sort by session_date, prefer latest
        - Others: Pure embedding similarity ranking
        """
        # Get query embedding
        query_emb = self.client.embed(question)
        if query_emb is None:
            return []

        # Score all entities
        scored: List[Tuple[str, float]] = []
        for i, eid in enumerate(index.entity_ids):
            if i >= len(index.embeddings):
                continue
            emb = index.embeddings[i]
            if not emb or all(v == 0.0 for v in emb):
                continue
            sim = cosine_similarity(query_emb, emb)

            # Hybrid scoring: add temporal proximity if alpha < 1.0
            if self.alpha < 1.0 and qi.question_date_iso:
                entity = index.entity_map.get(eid)
                entity_date = entity.session_date if entity else ""
                t_prox = self._temporal_proximity(
                    entity_date, qi.question_date_iso, self.tau,
                )
                combined = self.alpha * sim + (1.0 - self.alpha) * t_prox
            else:
                combined = sim

            scored.append((eid, combined))

        # Sort by score, take top_k
        scored.sort(key=lambda x: -x[1])
        top = scored[:self.top_k]

        # Apply question-type-specific re-ranking
        if qi.question_type == 'temporal-reasoning':
            top = self._rerank_temporal(top, index)
        elif qi.question_type == 'knowledge-update':
            top = self._rerank_knowledge_update(top, index)

        results = []
        for rank, (eid, score) in enumerate(top, 1):
            entity = index.entity_map.get(eid)
            if entity:
                results.append(RetrievalResult(
                    entity=entity,
                    score=score,
                    rank=rank,
                ))

        return results

    @staticmethod
    def _temporal_proximity(
        entity_date: str,
        question_date: str,
        tau: float,
    ) -> float:
        """Compute temporal proximity score between entity and question dates.

        Uses exponential decay: exp(-|days_diff| / tau).
        Returns 0.0 on any parse failure.
        """
        if not entity_date or not question_date:
            return 0.0
        try:
            # Parse ISO format dates (handle various formats)
            ed = datetime.fromisoformat(entity_date)
            qd = datetime.fromisoformat(question_date)
            days_diff = abs((ed - qd).total_seconds()) / SECONDS_PER_DAY
            return math.exp(-days_diff / tau)
        except (ValueError, TypeError):
            return 0.0

    def _rerank_temporal(
        self,
        top: List[Tuple[str, float]],
        index: EmbeddingIndex,
    ) -> List[Tuple[str, float]]:
        """For temporal-reasoning: keep top results but sort by date within top-k.

        The top-k by similarity are kept, then re-sorted chronologically
        so the Reader sees events in temporal order.
        """
        dated = []
        for eid, score in top:
            entity = index.entity_map.get(eid)
            if entity and entity.session_date:
                dated.append((eid, score, entity.session_date))
            else:
                dated.append((eid, score, '1970-01-01T00:00'))

        # Sort by date ascending (chronological order)
        dated.sort(key=lambda x: x[2])

        return [(eid, score) for eid, score, _ in dated]

    def _rerank_knowledge_update(
        self,
        top: List[Tuple[str, float]],
        index: EmbeddingIndex,
    ) -> List[Tuple[str, float]]:
        """For knowledge-update: prefer most recent entity version.

        Re-rank so the latest version of a fact appears first.
        """
        dated = []
        for eid, score in top:
            entity = index.entity_map.get(eid)
            if entity and entity.session_date:
                dated.append((eid, score, entity.session_date))
            else:
                dated.append((eid, score, '1970-01-01T00:00'))

        # Sort by date descending (most recent first)
        dated.sort(key=lambda x: x[2], reverse=True)

        return [(eid, score) for eid, score, _ in dated]


# ========== Reader ==========

# Reader prompts per question type
READER_PROMPTS = {
    'single-session-user': """Based on the following chat history between a user and an assistant, answer the question. The user mentioned relevant information in their messages.

Chat History:
{context}

Question: {question}

Provide a concise, direct answer based only on the chat history. If the information is not present, say "I don't know".""",

    'single-session-assistant': """Based on the following chat history between a user and an assistant, answer the question. The assistant provided relevant information in their responses.

Chat History:
{context}

Question: {question}

Provide a concise, direct answer based only on the chat history. If the information is not present, say "I don't know".""",

    'single-session-preference': """Based on the following chat history, the user has expressed personal preferences. Answer the question by recalling and utilizing the user's preferences.

Chat History:
{context}

Question: {question}

Provide a personalized response based on the user's stated preferences. If the preferences are not clearly stated, say "I don't know".""",

    'temporal-reasoning': """Based on the following chronologically ordered chat history, answer the temporal reasoning question. Pay close attention to the dates and the order of events.

Chat History (chronological order):
{context}

Question: {question}

Provide a concise answer. For questions about durations (days/weeks/months), calculate carefully. If the information is not present, say "I don't know".""",

    'knowledge-update': """Based on the following chat history, answer the question. Note that the user's information may have changed over time. Use the MOST RECENT information to answer.

Chat History (most recent first):
{context}

Question: {question}

Provide the answer based on the most up-to-date information. If the information is not present, say "I don't know".""",

    'multi-session': """Based on the following chat history from multiple sessions, answer the question. You may need to combine information from different sessions.

Chat History:
{context}

Question: {question}

Provide a concise answer that combines relevant information from all sessions. If the information is not present, say "I don't know".""",
}

ABSTENTION_PROMPT = """Based on the following chat history, determine if the question can be answered with the available information.

Chat History:
{context}

Question: {question}

If the information needed to answer this question is NOT present in the chat history, respond with: "The information provided is not enough." followed by a brief explanation of what is missing.
If the information IS present, provide the answer."""


@dataclass
class ReaderResult:
    """Result from reader stage."""
    question_id: str
    hypothesis: str
    confidence: float  # based on top retrieval score
    abstained: bool
    n_retrieved: int
    top_score: float
    timing_ms: float = 0.0


class Reader:
    """LLM-based reader that generates answers from retrieved context."""

    def __init__(
        self,
        client: LLMClient,
        abstention_threshold: float = 0.3,
        max_context_chars: int = 8000,
    ):
        self.client = client
        self.abstention_threshold = abstention_threshold
        self.max_context_chars = max_context_chars

    def read(
        self,
        qi: QuestionInstance,
        results: List[RetrievalResult],
    ) -> ReaderResult:
        """Generate an answer for a question given retrieval results."""
        start = time.time()

        if not results:
            return ReaderResult(
                question_id=qi.question_id,
                hypothesis="I don't know",
                confidence=0.0,
                abstained=True,
                n_retrieved=0,
                top_score=0.0,
            )

        top_score = results[0].score

        # Abstention: if top retrieval score is below threshold, skip LLM call
        if top_score < self.abstention_threshold:
            elapsed_ms = (time.time() - start) * 1000
            return ReaderResult(
                question_id=qi.question_id,
                hypothesis="I don't know",
                confidence=top_score,
                abstained=True,
                n_retrieved=len(results),
                top_score=top_score,
                timing_ms=elapsed_ms,
            )

        # Build context from retrieved entities
        context = self._build_context(results)

        # Choose prompt based on question type
        if qi.is_abstention:
            prompt_template = ABSTENTION_PROMPT
        else:
            prompt_template = READER_PROMPTS.get(
                qi.question_type,
                READER_PROMPTS['single-session-user']
            )

        prompt = prompt_template.format(
            context=context,
            question=qi.question,
        )

        # Call LLM
        messages = [
            {"role": "system", "content": "You are a helpful assistant that answers questions based on chat history. Be concise and direct."},
            {"role": "user", "content": prompt},
        ]

        response = self.client.call(messages, temperature=DEFAULT_READER_TEMPERATURE)

        elapsed_ms = (time.time() - start) * 1000

        if not response:
            hypothesis = "I don't know"
            abstained = True
        else:
            hypothesis = response.strip()
            abstained = False

        return ReaderResult(
            question_id=qi.question_id,
            hypothesis=hypothesis,
            confidence=top_score,
            abstained=abstained,
            n_retrieved=len(results),
            top_score=top_score,
            timing_ms=elapsed_ms,
        )

    def _build_context(self, results: List[RetrievalResult]) -> str:
        """Build context string from retrieval results.

        Truncates to max_context_chars to avoid exceeding LLM limits.
        """
        lines = []
        total_chars = 0

        for r in results:
            entity = r.entity
            role_label = "User" if entity.role == "user" else "Assistant"
            date_label = f" [{entity.session_date}]" if entity.session_date else ""
            line = f"{role_label}{date_label}: {entity.content}"
            if total_chars + len(line) > self.max_context_chars:
                break
            lines.append(line)
            total_chars += len(line)

        return "\n\n".join(lines)


# ========== CLI ==========

def main():
    parser = argparse.ArgumentParser(
        description='QA Reader — Two-stage retrieval + reading for LongMemEval'
    )
    parser.add_argument(
        'data_file',
        help='Path to longmemeval_oracle.json'
    )
    parser.add_argument(
        '--limit', '-l', type=int, default=None,
        help='Limit number of questions'
    )
    parser.add_argument(
        '--top-k', '-k', type=int, default=20,
        help='Number of entities to retrieve (default: 20)'
    )
    parser.add_argument(
        '--abstention-threshold', '-t', type=float, default=0.3,
        help='Confidence threshold for abstention (default: 0.3)'
    )
    parser.add_argument(
        '--output', '-o', type=Path, default=None,
        help='Output JSONL file path'
    )
    parser.add_argument(
        '--model', '-m', default=None,
        help='LLM model name'
    )
    parser.add_argument(
        '--api-key', default=None,
        help='API key'
    )
    parser.add_argument(
        '--base-url', '-b', default=None,
        help='API base URL'
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(message)s')

    print("QA Reader")
    print(f"  Data: {args.data_file}")
    print(f"  Top-K: {args.top_k}")
    print(f"  Abstention threshold: {args.abstention_threshold}")

    client = LLMClient(
        model=args.model,
        api_key=args.api_key,
        base_url=args.base_url,
    )

    # Parse data
    adapter = LongMemEvalAdapter(llm_client=client)
    questions = adapter.parse_file(args.data_file)

    if args.limit:
        questions = questions[:args.limit]

    print(f"\nProcessing {len(questions)} questions...")

    retriever = Retriever(client=client, top_k=args.top_k)
    reader = Reader(
        client=client,
        abstention_threshold=args.abstention_threshold,
    )

    results = []
    for i, qi in enumerate(questions):
        print(f"\n[{i+1}/{len(questions)}] {qi.question_id} ({qi.question_type})")

        # Build embedding index for this question
        index = adapter.build_embedding_index(qi)

        # Retrieve
        retrieved = retriever.retrieve(qi.question, qi, index)
        print(f"  Retrieved {len(retrieved)} entities, top score: {retrieved[0].score:.3f}" if retrieved else "  No results retrieved")

        # Read
        result = reader.read(qi, retrieved)
        print(f"  Answer: {result.hypothesis[:100]}...")
        print(f"  Confidence: {result.confidence:.3f}, Time: {result.timing_ms:.0f}ms")

        results.append(result)

    # Output JSONL
    output_path = args.output or Path('results/qa_output.jsonl')
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        for r in results:
            f.write(json.dumps({
                'question_id': r.question_id,
                'hypothesis': r.hypothesis,
            }, ensure_ascii=False) + '\n')

    print(f"\nResults saved to {output_path}")


if __name__ == '__main__':
    main()
