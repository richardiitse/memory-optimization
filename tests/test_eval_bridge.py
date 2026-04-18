"""Tests for eval_bridge — pipeline orchestration and output format."""

import json
import pytest
from unittest.mock import MagicMock

from longmemeval_adapter import QuestionInstance, TurnEntity, EmbeddingIndex
from qa_reader import ReaderResult, RetrievalResult
from eval_bridge import EvalPipeline, build_flight_record


# ========== Helpers ==========

def make_question(qid='test_1', qtype='single-session-user', is_abs=False):
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
                entity_id=f"{qid}_s0_t0", role="user",
                content="I love the color blue.",
                session_id="sess_1", session_date="2023-04-10T17:50",
                question_id=qid, question_type=qtype,
                has_answer=True, turn_index=0,
            ),
        ],
    )


# ========== Flight Record ==========

class TestFlightRecord:
    def test_flight_record_structure(self):
        qi = make_question()
        index = EmbeddingIndex(
            question_id='test_1',
            entity_ids=['test_1_s0_t0'],
            embeddings=[[0.1, 0.2]],
            entity_map={'test_1_s0_t0': qi.entities[0]},
        )
        retrieved = [
            RetrievalResult(entity=qi.entities[0], score=0.9, rank=1),
        ]
        result = ReaderResult(
            question_id='test_1', hypothesis="Blue",
            confidence=0.9, abstained=False,
            n_retrieved=1, top_score=0.9, timing_ms=100.0,
        )

        flight = build_flight_record(qi, retrieved, result, index, 150.0)

        assert flight.question_id == 'test_1'
        assert flight.question_type == 'single-session-user'
        assert flight.retrieval['n_candidates'] == 1
        assert flight.retrieval['candidates'][0]['score'] == 0.9
        assert flight.reader['confidence'] == 0.9
        assert flight.reader['abstained'] is False
        assert flight.timing_ms == 150.0

    def test_flight_record_empty_retrieval(self):
        """build_flight_record should handle empty retrieval and empty index."""
        qi = make_question()
        index = EmbeddingIndex(
            question_id='test_1',
            entity_ids=[],
            embeddings=[],
            entity_map={},
        )
        result = ReaderResult(
            question_id='test_1', hypothesis="I don't know",
            confidence=0.0, abstained=True,
            n_retrieved=0, top_score=0.0, timing_ms=50.0,
        )

        flight = build_flight_record(qi, [], result, index, 80.0)

        assert flight.retrieval['n_candidates'] == 0
        assert flight.retrieval['candidates'] == []
        assert flight.retrieval['kg_snapshot']['total_entities'] == 0
        assert flight.retrieval['kg_snapshot']['embedding_dim'] == 0
        assert flight.reader['abstained'] is True

    def test_flight_record_json_serializable(self):
        """FlightRecord should be JSON-serializable via asdict."""
        from dataclasses import asdict
        qi = make_question()
        index = EmbeddingIndex(
            question_id='test_1',
            entity_ids=['test_1_s0_t0'],
            embeddings=[[0.1, 0.2]],
            entity_map={'test_1_s0_t0': qi.entities[0]},
        )
        retrieved = [RetrievalResult(entity=qi.entities[0], score=0.9, rank=1)]
        result = ReaderResult("test_1", "Blue", 0.9, False, 1, 0.9, 100.0)

        flight = build_flight_record(qi, retrieved, result, index, 150.0)

        # Should not raise
        serialized = json.dumps(asdict(flight), ensure_ascii=False)
        parsed = json.loads(serialized)
        assert parsed['question_id'] == 'test_1'


# ========== Pipeline ==========

class TestEvalPipeline:
    def test_dry_run_parse(self):
        """eval_bridge dry-run should parse data without LLM calls."""
        import tempfile

        sample = [{
            "question_id": "dry_1",
            "question_type": "single-session-user",
            "question": "q", "answer": "a",
            "question_date": "2023/01/01 (Sun) 12:00",
            "haystack_session_ids": ["s1"],
            "haystack_dates": ["2023/01/01 (Sun) 12:00"],
            "haystack_sessions": [[
                {"role": "user", "content": "hello"},
            ]],
            "answer_session_ids": ["s1"],
        }]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(sample, f)
            tmppath = f.name

        from longmemeval_adapter import LongMemEvalAdapter
        adapter = LongMemEvalAdapter()
        questions = adapter.parse_file(tmppath)
        assert len(questions) == 1
        assert questions[0].question_id == "dry_1"

    def test_output_jsonl_format(self, tmp_path):
        """Output JSONL should have question_id and hypothesis per line."""
        results = [
            ReaderResult("q1", "Blue", 0.9, False, 3, 0.9, 100.0),
            ReaderResult("q2", "Red", 0.8, False, 5, 0.8, 120.0),
        ]

        output_path = tmp_path / "test_output.jsonl"
        with open(output_path, 'w') as f:
            for r in results:
                f.write(json.dumps({
                    'question_id': r.question_id,
                    'hypothesis': r.hypothesis,
                }) + '\n')

        # Read back and verify
        lines = output_path.read_text().strip().split('\n')
        assert len(lines) == 2

        entry1 = json.loads(lines[0])
        assert entry1['question_id'] == 'q1'
        assert entry1['hypothesis'] == 'Blue'

        entry2 = json.loads(lines[1])
        assert entry2['question_id'] == 'q2'
        assert entry2['hypothesis'] == 'Red'

    def test_output_compatible_with_evaluate_qa(self, tmp_path):
        """Output format must match evaluate_qa.py expectations."""
        results = [
            ReaderResult("gpt4_2655b836", "GPS issue", 0.85, False, 10, 0.85, 200.0),
        ]

        output_path = tmp_path / "hypothesis.jsonl"
        with open(output_path, 'w') as f:
            for r in results:
                f.write(json.dumps({
                    'question_id': r.question_id,
                    'hypothesis': r.hypothesis,
                }) + '\n')

        # Verify it can be loaded the same way evaluate_qa.py does
        hypotheses = [json.loads(line) for line in open(output_path)]
        assert len(hypotheses) == 1
        assert 'question_id' in hypotheses[0]
        assert 'hypothesis' in hypotheses[0]
        assert len(hypotheses[0].keys()) >= 2  # At minimum these two fields

    def test_pipeline_run_single(self):
        """EvalPipeline.run_single should return (ReaderResult, FlightRecord)."""
        embed_client = MagicMock()
        embed_client.embed.return_value = [1.0, 0.0, 0.0, 0.0]
        # build_embedding_index calls embed_batch — mock it too
        embed_client.embed_batch.return_value = [[1.0, 0.0, 0.0, 0.0]] * 10

        reader_client = MagicMock()
        reader_client.call.return_value = "Blue"

        pipeline = EvalPipeline(
            embed_client=embed_client,
            reader_client=reader_client,
            top_k=10,
        )

        qi = make_question()
        result, flight = pipeline.run_single(qi)

        assert isinstance(result, ReaderResult)
        assert result.question_id == 'test_1'
        assert result.hypothesis == "Blue"
        assert result.abstained is False

        assert flight.question_id == 'test_1'
        assert flight.retrieval['n_candidates'] >= 1
        assert flight.reader['confidence'] > 0

    def test_pipeline_run_multiple(self):
        """EvalPipeline.run should process multiple questions."""
        embed_client = MagicMock()
        embed_client.embed.return_value = [1.0, 0.0, 0.0, 0.0]
        embed_client.embed_batch.return_value = [[1.0, 0.0, 0.0, 0.0]] * 10

        reader_client = MagicMock()
        reader_client.call.return_value = "answer"

        pipeline = EvalPipeline(
            embed_client=embed_client,
            reader_client=reader_client,
        )

        questions = [make_question(qid=f"q_{i}") for i in range(3)]
        results, flights = pipeline.run(questions, progress=False)

        assert len(results) == 3
        assert len(flights) == 3
        assert all(r.question_id.startswith("q_") for r in results)

    def test_pipeline_abstention_below_threshold(self):
        """Pipeline should abstain when retrieval score is below threshold."""
        embed_client = MagicMock()
        # Query embedding (Retriever.retrieve calls embed(question))
        embed_client.embed.return_value = [1.0, 0.0, 0.0, 0.0]
        # Entity embeddings via batch (low similarity to query)
        embed_client.embed_batch.return_value = [[0.01, 0.01, 0.01, 0.01]] * 10

        reader_client = MagicMock()

        pipeline = EvalPipeline(
            embed_client=embed_client,
            reader_client=reader_client,
            abstention_threshold=0.9,  # High threshold
        )

        qi = make_question()
        result, flight = pipeline.run_single(qi)

        assert result.abstained is True
        assert result.hypothesis == "I don't know"
        # Reader LLM should NOT be called when abstaining
        reader_client.call.assert_not_called()


class TestPrintReport:
    """Tests for print_report function."""

    def test_print_report_empty(self, capsys):
        """Should handle empty results gracefully."""
        from eval_bridge import print_report
        questions = []
        results = []
        print_report(results, questions)
        captured = capsys.readouterr()
        assert 'Total questions: 0' in captured.out

    def test_print_report_single_type(self, capsys):
        """Should show per-type breakdown."""
        from eval_bridge import print_report
        q1 = make_question(qid='q1', qtype='temporal-reasoning')
        r1 = ReaderResult(
            question_id='q1', hypothesis='blue', confidence=0.8,
            abstained=False, n_retrieved=5, top_score=0.8, timing_ms=100,
        )
        print_report([r1], [q1])
        captured = capsys.readouterr()
        assert 'temporal-reasoning' in captured.out
        assert 'Total questions: 1' in captured.out

    def test_print_report_abstention_grouping(self, capsys):
        """Should group abstention questions separately."""
        from eval_bridge import print_report
        q_abs = make_question(qid='q1_abs', qtype='single-session-user', is_abs=True)
        r_abs = ReaderResult(
            question_id='q1_abs', hypothesis="I don't know", confidence=0.1,
            abstained=True, n_retrieved=5, top_score=0.1, timing_ms=50,
        )
        print_report([r_abs], [q_abs])
        captured = capsys.readouterr()
        assert 'abstention' in captured.out

