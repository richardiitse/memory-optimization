"""Tests for LongMemEval adapter — data parsing and entity mapping."""

import json
import pytest
from unittest.mock import MagicMock

from longmemeval_adapter import (
    LongMemEvalAdapter,
    QuestionInstance,
    parse_longmemeval_date,
    QUESTION_TYPES,
)


# ========== Fixtures ==========

def make_sample_oracle():
    """Create a minimal LongMemEval oracle data sample."""
    return [
        {
            "question_id": "test_single_user",
            "question_type": "single-session-user",
            "question": "What is my favorite color?",
            "answer": "Blue",
            "question_date": "2023/04/10 (Mon) 23:07",
            "haystack_session_ids": ["sess_1"],
            "haystack_dates": ["2023/04/10 (Mon) 17:50"],
            "haystack_sessions": [
                [
                    {"role": "user", "content": "I love the color blue, it reminds me of the ocean.", "has_answer": True},
                    {"role": "assistant", "content": "That's a nice preference! Blue is calming."},
                    {"role": "user", "content": "Yes, I painted my room blue."},
                ]
            ],
            "answer_session_ids": ["sess_1"],
        },
        {
            "question_id": "test_temporal",
            "question_type": "temporal-reasoning",
            "question": "What did I do first, buying groceries or going to the gym?",
            "answer": "Going to the gym",
            "question_date": "2023/05/01 (Mon) 10:00",
            "haystack_session_ids": ["sess_a", "sess_b"],
            "haystack_dates": ["2023/04/28 (Fri) 09:00", "2023/04/30 (Sun) 15:00"],
            "haystack_sessions": [
                [
                    {"role": "user", "content": "I went to the gym this morning.", "has_answer": True},
                    {"role": "assistant", "content": "Great workout routine!"},
                ],
                [
                    {"role": "user", "content": "Just bought groceries for the week.", "has_answer": True},
                    {"role": "assistant", "content": "Smart planning!"},
                ],
            ],
            "answer_session_ids": ["sess_a", "sess_b"],
        },
        {
            "question_id": "test_knowledge_update",
            "question_type": "knowledge-update",
            "question": "What is my current favorite food?",
            "answer": "Sushi (changed from pizza)",
            "question_date": "2023/06/15 (Thu) 20:00",
            "haystack_session_ids": ["sess_old", "sess_new"],
            "haystack_dates": ["2023/05/01 (Mon) 12:00", "2023/06/10 (Sat) 18:00"],
            "haystack_sessions": [
                [
                    {"role": "user", "content": "My favorite food is pizza.", "has_answer": True},
                    {"role": "assistant", "content": "Pizza is delicious!"},
                ],
                [
                    {"role": "user", "content": "Actually I've been really into sushi lately. It's my new favorite.", "has_answer": True},
                    {"role": "assistant", "content": "Sushi is great, what a change!"},
                ],
            ],
            "answer_session_ids": ["sess_old", "sess_new"],
        },
        {
            "question_id": "test_multi_session",
            "question_type": "multi-session",
            "question": "What are my hobbies?",
            "answer": "Reading, hiking, and photography",
            "question_date": "2023/07/01 (Sat) 14:00",
            "haystack_session_ids": ["sess_h1", "sess_h2", "sess_h3"],
            "haystack_dates": ["2023/06/01 (Thu) 10:00", "2023/06/15 (Thu) 15:00", "2023/06/28 (Wed) 09:00"],
            "haystack_sessions": [
                [
                    {"role": "user", "content": "I enjoy reading science fiction.", "has_answer": True},
                    {"role": "assistant", "content": "Sci-fi is a fascinating genre."},
                ],
                [
                    {"role": "user", "content": "Went hiking this weekend.", "has_answer": True},
                    {"role": "assistant", "content": "Hiking is great exercise!"},
                ],
                [
                    {"role": "user", "content": "I bought a new camera for photography.", "has_answer": True},
                    {"role": "assistant", "content": "Photography is a creative hobby."},
                ],
            ],
            "answer_session_ids": ["sess_h1", "sess_h2", "sess_h3"],
        },
        {
            "question_id": "test_abstention_abs",
            "question_type": "temporal-reasoning",
            "question": "What is the name of my pet dog?",
            "answer": "The information provided is not enough. You never mentioned having a pet dog.",
            "question_date": "2023/08/01 (Tue) 16:00",
            "haystack_session_ids": ["sess_no_dog"],
            "haystack_dates": ["2023/07/20 (Thu) 11:00"],
            "haystack_sessions": [
                [
                    {"role": "user", "content": "I like animals."},
                    {"role": "assistant", "content": "Animals are wonderful!"},
                ],
            ],
            "answer_session_ids": [],
        },
        {
            "question_id": "test_preference",
            "question_type": "single-session-preference",
            "question": "How should I respond to the user's greeting?",
            "answer": "Use a casual and friendly tone, address by first name, mention the weather",
            "question_date": "2023/09/01 (Fri) 08:00",
            "haystack_session_ids": ["sess_pref"],
            "haystack_dates": ["2023/08/30 (Wed) 10:00"],
            "haystack_sessions": [
                [
                    {"role": "user", "content": "I prefer when people greet me casually, not formally. Just use my first name.", "has_answer": True},
                    {"role": "assistant", "content": "Got it, casual greetings it is!"},
                    {"role": "user", "content": "Also I like when someone mentions the weather when greeting.", "has_answer": True},
                ],
            ],
            "answer_session_ids": ["sess_pref"],
        },
    ]


@pytest.fixture
def sample_file(tmp_path):
    """Write sample oracle data to a temp file."""
    fpath = tmp_path / "test_oracle.json"
    with open(fpath, 'w') as f:
        json.dump(make_sample_oracle(), f)
    return str(fpath)


@pytest.fixture
def adapter():
    return LongMemEvalAdapter()


# ========== Date Parsing ==========

class TestDateParsing:
    def test_standard_format(self):
        result = parse_longmemeval_date("2023/04/10 (Mon) 23:07")
        assert result == "2023-04-10T23:07"

    def test_different_day(self):
        result = parse_longmemeval_date("2023/05/28 (Sun) 06:47")
        assert result == "2023-05-28T06:47"

    def test_friday(self):
        result = parse_longmemeval_date("2023/03/10 (Fri) 23:15")
        assert result == "2023-03-10T23:15"


# ========== Parsing ==========

class TestParsing:
    def test_parse_all_questions(self, adapter, sample_file):
        questions = adapter.parse_file(sample_file)
        assert len(questions) == 6

    def test_question_types(self, adapter, sample_file):
        questions = adapter.parse_file(sample_file)
        types = {q.question_type for q in questions}
        assert types == {
            'single-session-user',
            'temporal-reasoning',
            'knowledge-update',
            'multi-session',
            'single-session-preference',
        }

    def test_abstention_detection(self, adapter, sample_file):
        questions = adapter.parse_file(sample_file)
        abs_q = [q for q in questions if q.is_abstention]
        assert len(abs_q) == 1
        assert abs_q[0].question_id == "test_abstention_abs"

    def test_single_session_entities(self, adapter, sample_file):
        questions = adapter.parse_file(sample_file)
        q = [q for q in questions if q.question_id == "test_single_user"][0]
        assert len(q.entities) == 3
        assert q.entities[0].role == "user"
        assert q.entities[0].has_answer is True
        assert q.entities[1].role == "assistant"
        assert q.entities[1].has_answer is False

    def test_multi_session_entities(self, adapter, sample_file):
        questions = adapter.parse_file(sample_file)
        q = [q for q in questions if q.question_id == "test_multi_session"][0]
        assert len(q.entities) == 6  # 2 turns × 3 sessions
        sessions = {e.session_id for e in q.entities}
        assert len(sessions) == 3

    def test_entity_dates(self, adapter, sample_file):
        questions = adapter.parse_file(sample_file)
        q = [q for q in questions if q.question_id == "test_temporal"][0]
        assert q.entities[0].session_date == "2023-04-28T09:00"
        assert q.entities[2].session_date == "2023-04-30T15:00"

    def test_knowledge_update_two_sessions(self, adapter, sample_file):
        questions = adapter.parse_file(sample_file)
        q = [q for q in questions if q.question_id == "test_knowledge_update"][0]
        assert len(q.entities) == 4  # 2 turns × 2 sessions
        sessions = {e.session_id for e in q.entities}
        assert len(sessions) == 2

    def test_answer_session_ids(self, adapter, sample_file):
        questions = adapter.parse_file(sample_file)
        q = [q for q in questions if q.question_id == "test_temporal"][0]
        assert len(q.answer_session_ids) == 2

    def test_question_date_iso(self, adapter, sample_file):
        questions = adapter.parse_file(sample_file)
        q = [q for q in questions if q.question_id == "test_single_user"][0]
        assert q.question_date_iso == "2023-04-10T23:07"


# ========== Validation ==========

class TestValidation:
    def test_unknown_question_type_raises(self, adapter, tmp_path):
        bad_data = [{"question_id": "bad_1", "question_type": "unknown-type",
                      "question": "q", "answer": "a", "question_date": "2023/01/01 (Sun) 12:00",
                      "haystack_session_ids": [], "haystack_dates": [], "haystack_sessions": []}]
        fpath = tmp_path / "bad.json"
        with open(fpath, 'w') as f:
            json.dump(bad_data, f)

        with pytest.raises(ValueError, match="Unknown question_type"):
            adapter.parse_file(str(fpath))

    def test_empty_sessions_ok(self, adapter, tmp_path):
        data = [{"question_id": "empty_1", "question_type": "single-session-user",
                 "question": "q", "answer": "a", "question_date": "2023/01/01 (Sun) 12:00",
                 "haystack_session_ids": [], "haystack_dates": [], "haystack_sessions": []}]
        fpath = tmp_path / "empty.json"
        with open(fpath, 'w') as f:
            json.dump(data, f)

        questions = adapter.parse_file(str(fpath))
        assert len(questions) == 1
        assert len(questions[0].entities) == 0

    def test_skips_empty_turns(self, adapter, tmp_path):
        data = [{"question_id": "skip_1", "question_type": "single-session-user",
                 "question": "q", "answer": "a", "question_date": "2023/01/01 (Sun) 12:00",
                 "haystack_session_ids": ["s1"],
                 "haystack_dates": ["2023/01/01 (Sun) 12:00"],
                 "haystack_sessions": [[
                     {"role": "user", "content": "valid content"},
                     {"role": "user", "content": ""},
                     {"role": "system", "content": "should be skipped"},
                 ]]}]
        fpath = tmp_path / "skip.json"
        with open(fpath, 'w') as f:
            json.dump(data, f)

        questions = adapter.parse_file(str(fpath))
        # "system" role is not user/assistant, empty content is skipped
        assert len(questions[0].entities) == 1

    def test_all_six_types_valid(self):
        assert len(QUESTION_TYPES) == 6
        assert 'single-session-preference' in QUESTION_TYPES

    def test_single_session_assistant_type(self, adapter, tmp_path):
        """single-session-assistant question type should parse correctly."""
        data = [{
            "question_id": "test_assistant",
            "question_type": "single-session-assistant",
            "question": "What did the assistant suggest?",
            "answer": "To try restarting",
            "question_date": "2023/01/01 (Sun) 12:00",
            "haystack_session_ids": ["s1"],
            "haystack_dates": ["2023/01/01 (Sun) 12:00"],
            "haystack_sessions": [[
                {"role": "user", "content": "My computer is slow"},
                {"role": "assistant", "content": "Try restarting it", "has_answer": True},
            ]],
            "answer_session_ids": ["s1"],
        }]
        fpath = tmp_path / "assistant.json"
        with open(fpath, 'w') as f:
            json.dump(data, f)

        questions = adapter.parse_file(str(fpath))
        assert len(questions) == 1
        assert questions[0].question_type == 'single-session-assistant'
        assert len(questions[0].entities) == 2

    def test_embedding_index_zero_vector_fallback(self, sample_file):
        """build_embedding_index should use zero vector when embed fails."""
        client = MagicMock()
        adapter = LongMemEvalAdapter(llm_client=client)

        # Parse to get a real QuestionInstance, then limit entities
        questions = adapter.parse_file(sample_file)
        qi = [q for q in questions if q.question_id == "test_single_user"][0]
        qi.entities = qi.entities[:2]

        # First embed succeeds, second fails
        # embed_batch returns list of results parallel to input texts
        client.embed_batch.return_value = [[0.5, 0.5, 0.5], None]

        index = adapter.build_embedding_index(qi)

        assert len(index.embeddings) == 2
        assert index.embeddings[0] == [0.5, 0.5, 0.5]
        # Second failed → zero vector with dim=3 from first
        assert index.embeddings[1] == [0.0, 0.0, 0.0]

    def test_embedding_index_raises_without_client(self, sample_file):
        """build_embedding_index should raise RuntimeError when no LLMClient."""
        adapter = LongMemEvalAdapter(llm_client=None)
        questions = adapter.parse_file(sample_file)
        qi = questions[0]

        with pytest.raises(RuntimeError, match="LLMClient"):
            adapter.build_embedding_index(qi)
