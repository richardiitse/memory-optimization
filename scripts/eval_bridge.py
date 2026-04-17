#!/usr/bin/env python3
"""
Eval Bridge — Orchestrate LongMemEval evaluation pipeline.

End-to-end: adapter → retriever → reader → JSONL output compatible with evaluate_qa.py.

Usage:
    python3 eval_bridge.py data/longmemeval/longmemeval_oracle.json --limit 5 --output results/oracle.jsonl
    python3 eval_bridge.py data/longmemeval/longmemeval_oracle.json --dry-run
"""

import json
import logging
import os
import sys
import time
import argparse
from dataclasses import asdict
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from utils.llm_client import LLMClient
from longmemeval_adapter import LongMemEvalAdapter, QuestionInstance, EmbeddingIndex
from qa_reader import Retriever, Reader, RetrievalResult, ReaderResult

logger = logging.getLogger(__name__)


# ========== Flight Record ==========

@dataclass
class FlightRecord:
    """Audit trail for a single question evaluation."""
    question_id: str
    question_type: str
    timestamp: str
    retrieval: Dict
    reader: Dict
    timing_ms: float


def build_flight_record(
    qi: QuestionInstance,
    retrieved: List[RetrievalResult],
    result: ReaderResult,
    index: EmbeddingIndex,
    elapsed_ms: float,
) -> FlightRecord:
    """Build a FlightRecord from evaluation results."""
    candidates = []
    for r in retrieved[:10]:  # Top 10 in audit
        candidates.append({
            'entity_id': r.entity.entity_id,
            'role': r.entity.role,
            'score': round(r.score, 4),
            'session_date': r.entity.session_date,
            'has_answer': r.entity.has_answer,
        })

    return FlightRecord(
        question_id=qi.question_id,
        question_type=qi.question_type,
        timestamp=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        retrieval={
            'n_candidates': len(retrieved),
            'top_k': len(retrieved),
            'candidates': candidates,
            'kg_snapshot': {
                'total_entities': len(index.entity_ids),
                'embedding_dim': len(index.embeddings[0]) if index.embeddings else 0,
            },
        },
        reader={
            'hypothesis': result.hypothesis[:200],
            'confidence': round(result.confidence, 4),
            'abstained': result.abstained,
            'n_retrieved': result.n_retrieved,
        },
        timing_ms=round(elapsed_ms, 1),
    )


# ========== Pipeline ==========

class EvalPipeline:
    """End-to-end evaluation pipeline."""

    def __init__(
        self,
        embed_client: LLMClient,
        reader_client: LLMClient,
        top_k: int = 20,
        abstention_threshold: float = 0.3,
        max_context_chars: int = 8000,
        cache_dir: Optional[str] = None,
        alpha: float = 1.0,
        tau: float = 30.0,
    ):
        self.adapter = LongMemEvalAdapter(llm_client=embed_client, cache_dir=cache_dir)
        self.retriever = Retriever(client=embed_client, top_k=top_k, alpha=alpha, tau=tau)
        self.reader = Reader(
            client=reader_client,
            abstention_threshold=abstention_threshold,
            max_context_chars=max_context_chars,
        )

    def run_single(
        self, qi: QuestionInstance,
    ) -> tuple:
        """Evaluate a single question. Returns (ReaderResult, FlightRecord)."""
        start = time.time()

        # Build embedding index
        index = self.adapter.build_embedding_index(qi)

        # Retrieve
        retrieved = self.retriever.retrieve(qi.question, qi, index)

        # Read
        result = self.reader.read(qi, retrieved)

        elapsed_ms = (time.time() - start) * 1000

        # Build flight record
        flight = build_flight_record(qi, retrieved, result, index, elapsed_ms)

        return result, flight

    def run(
        self,
        questions: List[QuestionInstance],
        progress: bool = True,
    ) -> tuple:
        """Run pipeline on all questions.

        Returns:
            (results: List[ReaderResult], flights: List[FlightRecord])
        """
        results = []
        flights = []
        total = len(questions)

        for i, qi in enumerate(questions):
            if progress:
                abst_label = 'ABST' if qi.is_abstention else 'REGULAR'
                logger.info("[%d/%d] %s (%s, %s)", i+1, total, qi.question_id,
                            qi.question_type, abst_label)

            result, flight = self.run_single(qi)

            if progress:
                conf_str = f"{result.confidence:.3f}"
                abst_str = " [ABSTAINED]" if result.abstained else ""
                logger.info("  → %s...%s", result.hypothesis[:80], abst_str)
                logger.info("  conf=%s time=%.0fms", conf_str, result.timing_ms)

            results.append(result)
            flights.append(flight)

        return results, flights


# ========== Report ==========

def print_report(results: List[ReaderResult], questions: List[QuestionInstance]):
    """Print evaluation report with per-type statistics."""
    from collections import defaultdict

    print("\n" + "=" * 60)
    print("Eval Bridge Report")
    print("=" * 60)

    print(f"\nTotal questions: {len(results)}")

    # Per-type stats
    type_results: Dict[str, List[ReaderResult]] = defaultdict(list)
    for r, qi in zip(results, questions):
        type_results[qi.question_type].append(r)
        if qi.is_abstention:
            type_results['abstention'].append(r)

    print("\nPer question type:")
    for qtype in sorted(type_results):
        rs = type_results[qtype]
        avg_conf = sum(r.confidence for r in rs) / len(rs) if rs else 0
        abst_count = sum(1 for r in rs if r.abstained)
        avg_time = sum(r.timing_ms for r in rs) / len(rs) if rs else 0
        print(f"  {qtype}: {len(rs)} questions, "
              f"avg_conf={avg_conf:.3f}, "
              f"abstained={abst_count}, "
              f"avg_time={avg_time:.0f}ms")

    # Overall
    total_time = sum(r.timing_ms for r in results)
    print(f"\nTotal time: {total_time / 1000:.1f}s")


# ========== CLI ==========

def main():
    parser = argparse.ArgumentParser(
        description='Eval Bridge — LongMemEval evaluation pipeline'
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
        help='Output JSONL file (for evaluate_qa.py)'
    )
    parser.add_argument(
        '--flight-log', type=Path, default=None,
        help='Save flight records to JSONL'
    )
    parser.add_argument(
        '--dry-run', '-n', action='store_true',
        help='Parse and validate only, skip LLM calls'
    )
    parser.add_argument(
        '--embed-model', default=None,
        help='Embedding model name (default: qwen3-embedding via Ollama)'
    )
    parser.add_argument(
        '--reader-model', '-m', default=None,
        help='Reader model name (default: gemma4:26b via Ollama)'
    )
    parser.add_argument(
        '--api-key', default=None,
        help='API key (not needed for local Ollama)'
    )
    parser.add_argument(
        '--base-url', '-b', default=None,
        help='API base URL for reader (default: Ollama localhost)'
    )
    parser.add_argument(
        '--cache-dir', default=None,
        help='Directory for embedding cache files (default: no cache)'
    )
    parser.add_argument(
        '--alpha', type=float, default=1.0,
        help='Semantic weight for hybrid retrieval (0-1, default: 1.0 = pure semantic)'
    )
    parser.add_argument(
        '--tau', type=float, default=30.0,
        help='Temporal decay constant in days (default: 30)'
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(message)s')

    print("Eval Bridge — LongMemEval Pipeline")
    print(f"  Data: {args.data_file}")
    print(f"  Top-K: {args.top_k}")
    print(f"  Abstention threshold: {args.abstention_threshold}")
    print(f"  Dry-run: {args.dry_run}")

    # Parse data (no LLM needed)
    adapter = LongMemEvalAdapter()
    questions = adapter.parse_file(args.data_file)

    if args.limit:
        questions = questions[:args.limit]

    print(f"\nLoaded {len(questions)} questions")

    if args.dry_run:
        from collections import Counter
        types = Counter(q.question_type for q in questions)
        for t, c in sorted(types.items(), key=lambda x: -x[1]):
            print(f"  {t}: {c}")
        total_entities = sum(len(q.entities) for q in questions)
        print(f"  Total entities: {total_entities}")
        print("\nDry-run complete. No LLM calls made.")
        return

    # Run pipeline — two separate clients for embedding and reading
    # Embedding client: uses Ollama qwen3-embedding (local, no auth)
    embed_client = LLMClient()

    # Reader client: uses OPENAI_BASE_URL if set, otherwise MiniMax API
    reader_base_url = args.base_url or os.environ.get('OPENAI_BASE_URL') or os.environ.get('READER_BASE_URL', 'https://api.minimaxi.com/anthropic/v1')
    reader_model = args.reader_model or os.environ.get('OPENAI_MODEL') or os.environ.get('READER_MODEL', 'MiniMax-M2.7-highspeed')
    reader_api_key = args.api_key or os.environ.get('MINIMAX_API_KEY') or os.environ.get('OPENAI_API_KEY', '')

    reader_client = LLMClient(
        model=reader_model,
        api_key=reader_api_key,
        base_url=reader_base_url,
    )
    print(f"  Embed model: {embed_client.embed_model} @ {embed_client.embed_base_url}")
    print(f"  Reader model: {reader_client.model} @ {reader_client.base_url}")

    pipeline = EvalPipeline(
        embed_client=embed_client,
        reader_client=reader_client,
        top_k=args.top_k,
        abstention_threshold=args.abstention_threshold,
        cache_dir=args.cache_dir,
        alpha=args.alpha,
        tau=args.tau,
    )

    start = time.time()
    results, flights = pipeline.run(questions)
    elapsed = time.time() - start

    # Output hypothesis JSONL
    output_path = args.output or Path('results/oracle_baseline.jsonl')
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        for r in results:
            f.write(json.dumps({
                'question_id': r.question_id,
                'hypothesis': r.hypothesis,
            }, ensure_ascii=False) + '\n')

    print(f"\nHypothesis output: {output_path}")

    # Save flight records
    if args.flight_log:
        with open(args.flight_log, 'w', encoding='utf-8') as f:
            for fl in flights:
                f.write(json.dumps(asdict(fl), ensure_ascii=False) + '\n')
        print(f"Flight records: {args.flight_log}")

    # Report
    print_report(results, questions)
    print(f"\nTotal pipeline time: {elapsed:.1f}s")


if __name__ == '__main__':
    main()
