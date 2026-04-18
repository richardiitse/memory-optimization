#!/usr/bin/env python3
"""
Grid Search — Alpha/Tau Hyperparameter Search for Hybrid Retrieval.

Usage: python3 scripts/grid_search_alpha_tau.py
"""

import subprocess
import json
import time
import sys
import os
from pathlib import Path
from typing import List, Dict, Tuple
from dataclasses import dataclass
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

ALPHAS = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0]
TAUS = [7, 15, 30, 60, 90]
ORACLE_DATA = PROJECT_DIR / "data/longmemeval/longmemeval_oracle.json"
CACHE_DIR = PROJECT_DIR / "data/longmemeval/embed_cache"

# Number of questions to use for quick grid search (0 = use all)
QUICK_LIMIT = 20
CONFIRM_TOP_N = 3  # Run top-N combos on full 133 questions
# Set to True to skip Phase 1 and only run Phase 2 confirmation
SKIP_PHASE1 = True


@dataclass
class GridResult:
    alpha: float
    tau: float
    accuracy: float
    correct: int
    total: int
    abstained: int
    avg_confidence: float
    timing_ms: float


def load_ground_truth() -> Dict[str, str]:
    """Load oracle data, return dict of question_id -> answer."""
    with open(ORACLE_DATA) as f:
        data = json.load(f)
    return {item['question_id']: item['answer'] for item in data}


def string_match_score(hypothesis: str, answer) -> bool:
    """Simple substring match scoring."""
    if not hypothesis or not answer:
        return False
    a = str(answer).lower()
    h = hypothesis.lower()
    # Strip common punctuation
    h = h.strip('.,!?;:"\'-')
    a = a.strip('.,!?;:"\'-')
    return a in h or h in a


def score_results(jsonl_path: str, ground_truth: Dict[str, str]) -> Tuple[int, int, int]:
    """
    Score hypothesis JSONL against ground truth using string-match.
    Returns: (correct, total, abstained)
    """
    correct = 0
    total = 0
    abstained = 0
    with open(jsonl_path) as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            qid = item['question_id']
            hyp = item.get('hypothesis', '')
            is_abstain = hyp.strip().lower() in ('i don\'t know', "i don't know", 'i do not know', 'unknown', '')
            if qid in ground_truth:
                total += 1
                if is_abstain:
                    abstained += 1
                elif string_match_score(hyp, ground_truth[qid]):
                    correct += 1
    return correct, total, abstained


def run_eval(alpha: float, tau: float, ground_truth: Dict[str, str], limit: int = 0) -> GridResult:
    """Run eval_bridge for one alpha/tau combination on temporal-reasoning questions."""
    tag = f"a{int(alpha*10)}_t{tau}{'_l'+str(limit) if limit else ''}"
    filtered_data = f"/tmp/grid_{tag}_filtered.json"
    output_file = f"/tmp/grid_{tag}_results.jsonl"
    flight_file = f"/tmp/grid_{tag}_flight.jsonl"

    # Step 1: Filter temporal-reasoning questions
    if not Path(filtered_data).exists():
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "filter_temporal_questions.py"),
             "--input", str(ORACLE_DATA),
             "--output", filtered_data,
             "--type", "temporal-reasoning"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"  !! Filter error: {result.stderr[:200]}")
            return GridResult(alpha, tau, 0.0, 0, 0, 0, 0.0, 0)

    # Step 2: Run eval_bridge on filtered data
    cmd = [
        sys.executable, str(SCRIPT_DIR / "eval_bridge.py"),
        filtered_data,
        "--cache-dir", str(CACHE_DIR),
        "--alpha", str(alpha),
        "--tau", str(tau),
        "--output", output_file,
        "--flight-log", flight_file,
    ]
    if limit:
        cmd.extend(["--limit", str(limit)])
    # Use environment with API keys
    env = os.environ.copy()

    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    elapsed = (time.time() - start) * 1000

    if result.returncode != 0:
        print(f"  !! Eval error alpha={alpha}, tau={tau}: {result.stderr[:300]}")
        return GridResult(alpha, tau, 0.0, 0, 0, 0, 0.0, elapsed)

    # Step 3: Score results
    correct, total, abstained = score_results(output_file, ground_truth)
    accuracy = correct / total if total > 0 else 0.0

    return GridResult(
        alpha=alpha,
        tau=tau,
        accuracy=accuracy,
        correct=correct,
        total=total,
        abstained=abstained,
        avg_confidence=0.0,
        timing_ms=elapsed,
    )


def print_heatmap(results: List[GridResult]):
    """Print accuracy heatmap: rows=alpha, cols=tau."""
    # Get unique taus sorted
    taus_sorted = sorted(TAUS)
    alphas_sorted = sorted(set(r.alpha for r in results))

    print(f"\n{' '*8}", end='')
    for tau in taus_sorted:
        print(f"{tau:>8}", end='')
    print()

    for alpha in alphas_sorted:
        print(f"a={alpha:.1f}  ", end='')
        for tau in taus_sorted:
            r = next((x for x in results if x.alpha == alpha and x.tau == tau), None)
            if r:
                pct = r.accuracy * 100
                print(f"{pct:>7.1f}%", end='')
            else:
                print(f"   N/A  ", end='')
        print()


def print_full_table(results: List[GridResult]):
    """Print full results table sorted by accuracy."""
    print(f"\n{'='*90}")
    print(f"{'Alpha':>6} | {'Tau':>4} | {'Correct':>8} | {'Abstain':>8} | {'Acc%':>7} | {'Time(ms)':>9}")
    print(f"{'-'*6}-+-{'-'*4}-+-{'-'*8}-+-{'-'*8}-+-{'-'*7}-+-{'-'*9}")
    for r in sorted(results, key=lambda x: -x.accuracy):
        print(f"{r.alpha:>6.1f} | {r.tau:>4} | {r.correct:>6}/133 | {r.abstained:>8} | {r.accuracy*100:>6.1f}% | {r.timing_ms:>9.0f}")
    print(f"{'='*90}")


def main():
    print(f"Grid Search: {len(ALPHAS)} alphas × {len(TAUS)} taus = {len(ALPHAS)*len(TAUS)} combinations")
    print(f"Started: {datetime.now().strftime('%H:%M:%S')}")
    print(f"Dataset: {ORACLE_DATA}")
    print()

    ground_truth = load_ground_truth()
    print(f"Loaded {len(ground_truth)} ground truth answers")

    results: List[GridResult] = []

    # Phase 1: Quick grid search on subset
    if QUICK_LIMIT > 0:
        print(f"\n=== Phase 1: Quick grid search ({QUICK_LIMIT} questions) ===")
        for alpha in ALPHAS:
            for tau in TAUS:
                tag = f"a{int(alpha*10)}_t{tau}"
                print(f"Running alpha={alpha}, tau={tau}...", end=" ", flush=True)
                r = run_eval(alpha, tau, ground_truth, limit=QUICK_LIMIT)
                results.append(r)
                if r.total > 0:
                    print(f"→ {r.correct}/{r.total} ({r.accuracy*100:.1f}%), {r.timing_ms/1000:.1f}s")
                else:
                    print(f"→ ERROR (0 questions)")

        # Best from quick search
        best_quick = max(results, key=lambda x: x.accuracy)
        print(f"\nBest (quick): alpha={best_quick.alpha}, tau={best_quick.tau} → {best_quick.correct}/{QUICK_LIMIT} ({best_quick.accuracy*100:.1f}%)")

        # Phase 2: Confirm top-N on full dataset
        top_combos = sorted(results, key=lambda x: -x.accuracy)[:CONFIRM_TOP_N]
        print(f"\n=== Phase 2: Confirm Top-{CONFIRM_TOP_N} on full 133 questions ===")

        # Keep quick results for combos NOT in top-N; re-run top-N on full data
        top_alpha_tau = {(c.alpha, c.tau) for c in top_combos}
        other_results = [r for r in results if (r.alpha, r.tau) not in top_alpha_tau]
        for combo in top_combos:
            print(f"Confirming alpha={combo.alpha}, tau={combo.tau}...", end=" ", flush=True)
            r = run_eval(combo.alpha, combo.tau, ground_truth, limit=0)
            other_results.append(r)
            if r.total > 0:
                print(f"→ {r.correct}/{r.total} ({r.accuracy*100:.1f}%), {r.timing_ms/1000:.1f}s")
            else:
                print(f"→ ERROR")

        results = other_results

    else:
        # Full grid search
        for alpha in ALPHAS:
            for tau in TAUS:
                tag = f"a{int(alpha*10)}_t{tau}"
                print(f"Running alpha={alpha}, tau={tau}...", end=" ", flush=True)
                r = run_eval(alpha, tau, ground_truth, limit=0)
                results.append(r)
                if r.total > 0:
                    print(f"→ {r.correct}/{r.total} ({r.accuracy*100:.1f}%), {r.timing_ms/1000:.1f}s")
                else:
                    print(f"→ ERROR (0 questions)")

    # Save results
    out_path = Path("/tmp/grid_search_results.json")
    with open(out_path, "w") as f:
        json.dump([{
            "alpha": r.alpha,
            "tau": r.tau,
            "accuracy": r.accuracy,
            "correct": r.correct,
            "total": r.total,
            "abstained": r.abstained,
            "avg_confidence": r.avg_confidence,
            "timing_ms": r.timing_ms,
        } for r in results], f, indent=2)

    print(f"\nResults saved to: {out_path}")

    # Best
    best = max(results, key=lambda x: x.accuracy)
    print(f"\nBest: alpha={best.alpha}, tau={best.tau} → {best.correct}/133 ({best.accuracy*100:.1f}%)")

    # Heatmap
    print_heatmap(results)

    # Full table
    print_full_table(results)

    # Delta from baseline (alpha=1.0, tau=30)
    baseline = next((r for r in results if r.alpha == 1.0 and r.tau == 30), None)
    if baseline:
        delta = best.accuracy - baseline.accuracy
        print(f"\nBASELINE (alpha=1.0, tau=30): {baseline.correct}/133 ({baseline.accuracy*100:.1f}%)")
        print(f"DELTA: {delta*100:+.1f}% ({best.correct - baseline.correct:+,} questions)")

    print(f"\nFinished: {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    main()
