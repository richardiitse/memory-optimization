#!/usr/bin/env python3
"""
LLM-based Evaluation for LongMemEval.

Implements the official evaluation method from LongMemEval paper:
https://github.com/xiaowu0162/LongMemEval

Uses an LLM judge to determine whether the model's answer is correct.
Uses the shared LLMClient for all API calls.

Usage:
    python3 evaluate_with_llm.py --hypothesis /tmp/eval_results.jsonl \
        --reference data/longmemeval/longmemeval_oracle.json \
        --output /tmp/eval_results.evaluated.jsonl
"""

import logging
import re

import json
import os
import sys
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Optional
from threading import Lock

logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
from utils.llm_client import LLMClient  # noqa: E402


# ========== Official Evaluation Prompts from LongMemEval ==========

_COMMON_INTRO = (
    "I will give you a question, a correct answer, and a response from a model. "
    "Please answer yes if the response contains the correct answer. Otherwise, answer no. "
    "If the response is equivalent to the correct answer or contains all the intermediate steps "
    "to get the correct answer, you should also answer yes. "
    "If the response only contains a subset of the information required by the answer, answer no."
)

_TEMP_REASONING_SUFFIX = (
    "In addition, do not penalize off-by-one errors for the number of days. "
    "If the question asks for the number of days/weeks/months, etc., and the model makes "
    "off-by-one errors (e.g., predicting 19 days when the answer is 18), "
    "the model's response is still correct."
)

_KNOWLEDGE_UPDATE_SUFFIX = (
    "If the response contains some previous information along with an updated answer, "
    "the response should be considered as correct as long as the updated answer is the required answer."
)

_TASK_INSTRUCTIONS = {
    'single-session-user': _COMMON_INTRO,
    'single-session-assistant': _COMMON_INTRO,
    'multi-session': _COMMON_INTRO,
    'temporal-reasoning': _COMMON_INTRO + ' ' + _TEMP_REASONING_SUFFIX,
    'knowledge-update': _COMMON_INTRO + ' ' + _KNOWLEDGE_UPDATE_SUFFIX,
    'single-session-preference': (
        "I will give you a question, a rubric for desired personalized response, and a response from a model. "
        "Please answer yes if the response satisfies the desired response. Otherwise, answer no. "
        "The model does not need to reflect all the points in the rubric. "
        "The response is correct as long as it recalls and utilizes the user's personal information correctly."
    ),
}

_ANSWERABLE_TEMPLATE = "{intro}\n\nQuestion: {question}\n\nCorrect Answer: {answer}\n\nModel Response: {response}\n\nIs the model response correct? Answer yes or no only."

_PREFERENCE_TEMPLATE = "{intro}\n\nQuestion: {question}\n\nRubric: {answer}\n\nModel Response: {response}\n\nIs the model response correct? Answer yes or no only."

_ABSTENTION_TEMPLATE = (
    "I will give you an unanswerable question, an explanation, and a response from a model. "
    "Please answer yes if the model correctly identifies the question as unanswerable. "
    "The model could say that the information is incomplete, or some other information is given "
    "but the asked information is not.\n\n"
    "Question: {question}\n\nExplanation: {answer}\n\nModel Response: {response}\n\n"
    "Does the model correctly identify the question as unanswerable? Answer yes or no only."
)


def get_anscheck_prompt(task: str, question: str, answer: str, response: str, abstention: bool = False) -> str:
    """Official prompt templates from LongMemEval evaluate_qa.py."""
    if abstention:
        return _ABSTENTION_TEMPLATE.format(question=question, answer=answer, response=response)

    intro = _TASK_INSTRUCTIONS.get(task)
    if intro is None:
        raise NotImplementedError(f"Unknown task type: {task}")

    if task == 'single-session-preference':
        return _PREFERENCE_TEMPLATE.format(intro=intro, question=question, answer=answer, response=response)
    return _ANSWERABLE_TEMPLATE.format(intro=intro, question=question, answer=answer, response=response)


# ========== LLM Judging ==========

def judge_with_llm(
    client: LLMClient,
    question: str,
    answer: str,
    response: str,
    task: str,
    is_abstention: bool,
) -> tuple:
    """Use LLM to judge if the response is correct.

    Returns:
        (is_correct: bool, llm_response: str)
    """
    prompt = get_anscheck_prompt(task, question, answer, response, is_abstention)
    messages = [{"role": "user", "content": prompt}]

    content = client.call(messages, temperature=0)

    if content is None:
        return False, "error: LLM call failed"

    content_lower = content.strip().lower()
    is_correct = bool(re.search(r'\byes\b', content_lower))
    return is_correct, content.strip()


# ========== Main Evaluation ==========

def _evaluate_one(
    idx: int,
    hyp: dict,
    qid2ref: dict,
    client: LLMClient,
) -> Optional[dict]:
    """Evaluate a single hypothesis. Returns result dict or None if skipped."""
    qid = hyp['question_id']

    if qid not in qid2ref:
        return None

    ref = qid2ref[qid]
    question = ref['question']
    answer = ref['answer']
    task = ref['question_type']
    is_abstention = qid.endswith('_abs')

    is_correct, llm_response = judge_with_llm(
        client=client,
        question=question,
        answer=answer,
        response=hyp['hypothesis'],
        task=task,
        is_abstention=is_abstention,
    )

    return {
        'idx': idx,
        'question_id': qid,
        'question_type': task,
        'is_abstention': is_abstention,
        'hypothesis': hyp['hypothesis'],
        'reference_answer': answer,
        'llm_judgment': llm_response,
        'is_correct': is_correct,
    }


def evaluate(
    hypothesis_file: str,
    reference_file: str,
    output_file: str,
    client: LLMClient,
    limit: Optional[int] = None,
    workers: int = 5,
):
    """Run LLM-based evaluation on hypothesis file."""

    # Load references
    with open(reference_file, 'r', encoding='utf-8') as f:
        references = json.load(f)

    qid2ref = {ref['question_id']: ref for ref in references}

    # Load hypotheses
    with open(hypothesis_file, 'r', encoding='utf-8') as f:
        hypotheses = [json.loads(line) for line in f]

    if limit:
        hypotheses = hypotheses[:limit]

    total = len(hypotheses)
    print(f"Evaluating {total} questions with {workers} workers...")

    # Concurrent evaluation
    results: List[Optional[dict]] = [None] * total
    done_count = 0
    print_lock = Lock()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _evaluate_one,
                idx=i,
                hyp=hyp,
                qid2ref=qid2ref,
                client=client,
            ): i
            for i, hyp in enumerate(hypotheses)
        }

        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as e:
                logger.error("Evaluation failed: %s", e)
                continue
            if result is None:
                continue

            idx = result.pop('idx')
            results[idx] = result

            with print_lock:
                done_count += 1
                mark = '✓' if result['is_correct'] else '✗'
                judge = result['llm_judgment'][:50]
                print(f"[{done_count}/{total}] {mark} {result['question_id']} ({result['question_type']}) {judge}")

    # Filter out None results (skipped)
    results = [r for r in results if r is not None]

    # Save results
    with open(output_file, 'w', encoding='utf-8') as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    # Print summary
    print("\n" + "=" * 60)
    print("Evaluation Results (LLM-based)")
    print("=" * 60)

    correct_by_type: Dict[str, int] = {}
    total_by_type: Dict[str, int] = {}
    abstain_by_type: Dict[str, int] = {}

    for r in results:
        task = r['question_type']
        total_by_type[task] = total_by_type.get(task, 0) + 1
        correct_by_type[task] = correct_by_type.get(task, 0) + (1 if r['is_correct'] else 0)
        if r['is_abstention']:
            abstain_by_type[task] = abstain_by_type.get(task, 0) + 1

    total_correct = sum(correct_by_type.values())
    total_q = sum(total_by_type.values())
    overall_acc = total_correct / total_q * 100 if total_q > 0 else 0

    print(f"\nOverall Accuracy: {total_correct}/{total_q} = {overall_acc:.1f}%")

    print("\nPer question type:")
    for task in sorted(total_by_type.keys()):
        n = total_by_type[task]
        c = correct_by_type[task]
        acc = c / n * 100 if n > 0 else 0
        abst = abstain_by_type.get(task, 0)
        print(f"  {task}: {c}/{n} = {acc:.1f}% (abstained: {abst})")

    print(f"\nResults saved to: {output_file}")

    return results


# ========== CLI ==========

def main():
    parser = argparse.ArgumentParser(
        description='LLM-based Evaluation for LongMemEval (Official Method)'
    )
    parser.add_argument(
        '--hypothesis', required=True,
        help='Path to hypothesis JSONL file'
    )
    parser.add_argument(
        '--reference', '-r', required=True,
        help='Path to reference JSON file (longmemeval_oracle.json)'
    )
    parser.add_argument(
        '--output', '-o', required=True,
        help='Output JSONL file for evaluated results'
    )
    parser.add_argument(
        '--api-key', '-k',
        default=os.environ.get('EVAL_API_KEY') or os.environ.get('MINIMAX_API_KEY') or os.environ.get('OPENAI_API_KEY', ''),
        help='API key (uses EVAL_API_KEY, MINIMAX_API_KEY, or OPENAI_API_KEY env var)'
    )
    parser.add_argument(
        '--base-url', '-b',
        default=os.environ.get('EVAL_BASE_URL', 'https://api.minimaxi.com/v1'),
        help='API base URL (default: EVAL_BASE_URL env or MiniMax)'
    )
    parser.add_argument(
        '--model', '-m',
        default=os.environ.get('EVAL_MODEL', 'MiniMax-M2.7'),
        help='Model to use for judgment (default: EVAL_MODEL env or MiniMax-M2.7)'
    )
    parser.add_argument(
        '--limit', '-l', type=int, default=None,
        help='Limit number of questions to evaluate'
    )
    parser.add_argument(
        '--workers', '-w', type=int, default=5,
        help='Number of concurrent workers (default: 5)'
    )

    args = parser.parse_args()

    if not args.api_key:
        print("Error: --api-key required or set EVAL_API_KEY / MINIMAX_API_KEY / OPENAI_API_KEY")
        sys.exit(1)

    client = LLMClient(
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model,
    )
    print(f"Evaluator: {client.model} @ {client.base_url} (backend: {client._backend})")

    evaluate(
        hypothesis_file=args.hypothesis,
        reference_file=args.reference,
        output_file=args.output,
        client=client,
        limit=args.limit,
        workers=args.workers,
    )


if __name__ == '__main__':
    main()
