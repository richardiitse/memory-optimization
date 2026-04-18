#!/usr/bin/env python3
"""
LongMemEval Adapter — Parse oracle data and build entity + embedding index.

Reads longmemeval_oracle.json, maps chat history to memory-optimization Entity
format, and pre-computes an embedding index for semantic retrieval.

Usage:
    python3 longmemeval_adapter.py path/to/longmemeval_oracle.json --limit 5
    python3 longmemeval_adapter.py path/to/longmemeval_oracle.json --dry-run
"""

import json
import logging
import re
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent
WORKSPACE_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from utils.llm_client import LLMClient


# ========== Date Parsing ==========

def parse_longmemeval_date(date_str: str) -> str:
    """Parse LongMemEval date format to ISO 8601.

    Input:  '2023/04/10 (Mon) 23:07'
    Output: '2023-04-10T23:07:00'
    """
    # Strip parenthetical day-of-week: '2023/04/10 (Mon) 23:07' → '2023/04/10 23:07'
    clean = re.sub(r'\s*\([^)]+\)', '', date_str)
    dt = datetime.strptime(clean.strip(), '%Y/%m/%d %H:%M')
    return dt.isoformat(timespec='minutes')


# ========== Data Models ==========

@dataclass
class TurnEntity:
    """A single chat turn mapped to an entity-like structure."""
    entity_id: str
    role: str  # 'user' or 'assistant'
    content: str
    session_id: str
    session_date: str  # ISO format
    question_id: str
    question_type: str
    has_answer: bool = False
    turn_index: int = 0
    embedding: Optional[List[float]] = None


@dataclass
class QuestionInstance:
    """One LongMemEval evaluation instance."""
    question_id: str
    question_type: str
    question: str
    answer: str
    question_date: str  # raw format
    question_date_iso: str  # ISO format
    is_abstention: bool
    entities: List[TurnEntity] = field(default_factory=list)
    answer_session_ids: List[str] = field(default_factory=list)


@dataclass
class EmbeddingIndex:
    """Pre-computed embedding index for semantic retrieval."""
    question_id: str
    entity_ids: List[str]
    embeddings: List[List[float]]  # parallel to entity_ids
    entity_map: Dict[str, TurnEntity]  # id -> entity


# ========== Question Types ==========

QUESTION_TYPES = [
    'single-session-user',
    'single-session-assistant',
    'single-session-preference',
    'temporal-reasoning',
    'knowledge-update',
    'multi-session',
]


# ========== Adapter ==========

class LongMemEvalAdapter:
    """Parse LongMemEval oracle data into entity structures."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        cache_dir: Optional[str] = None,
    ):
        self.client = llm_client
        self.cache_dir = cache_dir

    def parse_file(self, filepath: str) -> List[QuestionInstance]:
        """Parse a LongMemEval JSON file into QuestionInstance list."""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not isinstance(data, list):
            raise ValueError(f"Expected JSON array, got {type(data).__name__}")

        return [self._parse_instance(inst) for inst in data]

    def _parse_instance(self, inst: Dict) -> QuestionInstance:
        """Parse a single evaluation instance."""
        qid = inst['question_id']
        qtype = inst['question_type']

        # Validate question_type
        if qtype not in QUESTION_TYPES:
            raise ValueError(
                f"Unknown question_type '{qtype}' in {qid}. "
                f"Expected one of: {QUESTION_TYPES}"
            )

        is_abs = qid.endswith('_abs')
        question_date = inst.get('question_date', '')
        question_date_iso = parse_longmemeval_date(question_date) if question_date else ''

        qi = QuestionInstance(
            question_id=qid,
            question_type=qtype,
            question=inst['question'],
            answer=inst['answer'],
            question_date=question_date,
            question_date_iso=question_date_iso,
            is_abstention=is_abs,
            answer_session_ids=inst.get('answer_session_ids', []),
        )

        # Parse haystack sessions into entities
        sessions = inst.get('haystack_sessions', [])
        session_ids = inst.get('haystack_session_ids', [])
        session_dates = inst.get('haystack_dates', [])

        for sess_idx, session in enumerate(sessions):
            sid = session_ids[sess_idx] if sess_idx < len(session_ids) else f"session_{sess_idx}"
            sdate = session_dates[sess_idx] if sess_idx < len(session_dates) else ''
            sdate_iso = parse_longmemeval_date(sdate) if sdate else ''

            for turn_idx, turn in enumerate(session):
                role = turn.get('role', '')
                content = turn.get('content', '')
                has_answer = turn.get('has_answer', False)

                if role not in ('user', 'assistant'):
                    continue
                if not content.strip():
                    continue

                entity_id = f"{qid}_s{sess_idx}_t{turn_idx}"
                qi.entities.append(TurnEntity(
                    entity_id=entity_id,
                    role=role,
                    content=content,
                    session_id=sid,
                    session_date=sdate_iso,
                    question_id=qid,
                    question_type=qtype,
                    has_answer=has_answer,
                    turn_index=turn_idx,
                ))

        return qi

    def build_embedding_index(self, qi: QuestionInstance) -> EmbeddingIndex:
        """Pre-compute embeddings for all entities in a question instance.

        Uses LLMClient.embed() for per-entity embedding calls.
        Failed embeddings get a zero vector derived from the first
        successful embedding dimension.

        When cache_dir is set, checks for cached embeddings first.
        """
        # Check cache
        if self.cache_dir:
            cache_path = Path(self.cache_dir) / f"{qi.question_id}.json"
            if cache_path.exists():
                return self._load_cache(cache_path)

        if not self.client:
            raise RuntimeError("LLMClient required for embedding index build")

        entity_ids = []
        embeddings = []
        entity_map = {}
        embedding_dim = 0

        for entity in qi.entities:
            emb = self.client.embed(entity.content)
            entity.embedding = emb
            entity_ids.append(entity.entity_id)
            if emb is not None:
                if embedding_dim == 0:
                    embedding_dim = len(emb)
                embeddings.append(emb)
            else:
                # Zero vector fallback — derive dim from first successful embedding
                fallback_dim = embedding_dim if embedding_dim > 0 else 0
                embeddings.append([0.0] * fallback_dim)
            entity_map[entity.entity_id] = entity

        index = EmbeddingIndex(
            question_id=qi.question_id,
            entity_ids=entity_ids,
            embeddings=embeddings,
            entity_map=entity_map,
        )

        # Save cache
        if self.cache_dir:
            cache_path = Path(self.cache_dir) / f"{qi.question_id}.json"
            self._save_cache(cache_path, index)

        return index

    def _load_cache(self, cache_path: Path) -> EmbeddingIndex:
        """Load EmbeddingIndex from cached JSON file."""
        with open(cache_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        entity_map = {}
        for eid, edata in data['entity_map'].items():
            entity_map[eid] = TurnEntity(
                entity_id=edata['entity_id'],
                role=edata['role'],
                content=edata['content'],
                session_id=edata['session_id'],
                session_date=edata['session_date'],
                question_id=edata.get('question_id', ''),
                question_type=edata.get('question_type', ''),
                has_answer=edata.get('has_answer', False),
                turn_index=edata.get('turn_index', 0),
            )

        return EmbeddingIndex(
            question_id=data['question_id'],
            entity_ids=data['entity_ids'],
            embeddings=data['embeddings'],
            entity_map=entity_map,
        )

    def _save_cache(self, cache_path: Path, index: EmbeddingIndex) -> None:
        """Save EmbeddingIndex to JSON cache file."""
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        entity_map_data = {}
        for eid, entity in index.entity_map.items():
            entity_map_data[eid] = {
                'entity_id': entity.entity_id,
                'role': entity.role,
                'content': entity.content,
                'session_id': entity.session_id,
                'session_date': entity.session_date,
                'question_type': entity.question_type,
                'has_answer': entity.has_answer,
                'turn_index': entity.turn_index,
            }

        cache_data = {
            'question_id': index.question_id,
            'entity_ids': index.entity_ids,
            'embeddings': index.embeddings,
            'entity_map': entity_map_data,
        }

        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f)

    def build_all_indices(
        self,
        questions: List[QuestionInstance],
        limit: Optional[int] = None,
        progress: bool = True,
    ) -> List[Tuple[QuestionInstance, EmbeddingIndex]]:
        """Build embedding indices for all (or limited) questions.

        Returns list of (QuestionInstance, EmbeddingIndex) tuples.
        """
        if limit:
            questions = questions[:limit]

        results = []
        total = len(questions)

        for i, qi in enumerate(questions):
            if progress:
                logger.info("[%d/%d] Building index for %s "
                            "(%s, %d entities)", i+1, total, qi.question_id,
                            qi.question_type, len(qi.entities))

            idx = self.build_embedding_index(qi)
            results.append((qi, idx))

        if progress:
            total_entities = sum(len(qi.entities) for qi, _ in results)
            logger.info("Built %d indices, %d total entities", len(results), total_entities)

        return results


# ========== CLI ==========

def _print_parse_stats(questions: List[QuestionInstance]) -> None:
    """Print statistics about parsed questions."""
    from collections import Counter
    print(f"\nParsed {len(questions)} questions")
    types = Counter(q.question_type for q in questions)
    for t, c in sorted(types.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c}")
    abs_count = sum(1 for q in questions if q.is_abstention)
    print(f"  Abstention: {abs_count}")
    total_entities = sum(len(q.entities) for q in questions)
    print(f"  Total entities (turns): {total_entities}")


def _write_embedded_output(
    indices: List[tuple],
    output_path: Path,
) -> None:
    """Write parsed + embedded data to JSON."""
    output_data = []
    for qi, idx in indices:
        entry = {
            'question_id': qi.question_id,
            'question_type': qi.question_type,
            'question': qi.question,
            'answer': qi.answer,
            'is_abstention': qi.is_abstention,
            'n_entities': len(qi.entities),
            'embedding_dim': len(idx.embeddings[0]) if idx.embeddings else 0,
        }
        output_data.append(entry)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to {output_path}")


def _write_parsed_output(
    questions: List[QuestionInstance],
    output_path: Path,
) -> None:
    """Write parsed data (without embeddings) to JSON."""
    output_data = []
    for qi in questions:
        entry = {
            'question_id': qi.question_id,
            'question_type': qi.question_type,
            'question': qi.question,
            'answer': qi.answer,
            'is_abstention': qi.is_abstention,
            'n_entities': len(qi.entities),
            'entities': [
                {
                    'entity_id': e.entity_id,
                    'role': e.role,
                    'content': e.content[:100] + '...' if len(e.content) > 100 else e.content,
                    'session_date': e.session_date,
                    'has_answer': e.has_answer,
                }
                for e in qi.entities[:5]  # preview first 5
            ],
        }
        output_data.append(entry)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='LongMemEval Adapter — parse oracle data and build embedding index'
    )
    parser.add_argument(
        'data_file',
        help='Path to longmemeval_oracle.json'
    )
    parser.add_argument(
        '--limit', '-l', type=int, default=None,
        help='Limit number of questions to process'
    )
    parser.add_argument(
        '--dry-run', '-n', action='store_true',
        help='Parse only, skip embedding computation'
    )
    parser.add_argument(
        '--output', '-o', type=Path, default=None,
        help='Save parsed data to JSON file'
    )
    parser.add_argument(
        '--model', '-m', default=None,
        help='LLM embedding model name'
    )
    parser.add_argument(
        '--api-key', '-k', default=None,
        help='API key (default: OPENAI_API_KEY env var)'
    )
    parser.add_argument(
        '--base-url', '-b', default=None,
        help='API base URL'
    )

    args = parser.parse_args()

    print("LongMemEval Adapter")
    print(f"  Data: {args.data_file}")
    print(f"  Dry-run: {args.dry_run}")

    # Parse
    adapter = LongMemEvalAdapter()
    questions = adapter.parse_file(args.data_file)
    _print_parse_stats(questions)

    if args.limit:
        questions = questions[:args.limit]
        print(f"\n  Limited to {args.limit} questions")

    # Build embeddings
    if not args.dry_run:
        client = LLMClient(
            model=args.model,
            api_key=args.api_key,
            base_url=args.base_url,
        )
        adapter = LongMemEvalAdapter(llm_client=client)
        indices = adapter.build_all_indices(questions)
        if args.output:
            _write_embedded_output(indices, args.output)
    elif args.output:
        _write_parsed_output(questions, args.output)


if __name__ == '__main__':
    main()
