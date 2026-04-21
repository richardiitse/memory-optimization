"""Tests for MetacogEnhancer — bias keywords, query enhancement."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from metacog_enhancer import BIAS_PATTERNS, MetacogEnhancer


# ── Bias Pattern Coverage ──────────────────────────────────────────

class TestBiasPatterns:
    def test_all_patterns_have_required_fields(self):
        for p in BIAS_PATTERNS:
            assert "name" in p, f"Missing name in {p}"
            assert "keywords" in p, f"Missing keywords in {p}"
            assert "questions" in p, f"Missing questions in {p}"
            assert len(p["keywords"]) >= 2
            assert len(p["questions"]) >= 2

    def test_pattern_count(self):
        assert len(BIAS_PATTERNS) >= 5


# ── Query Enhancement ─────────────────────────────────────────────

class TestQueryEnhancement:
    def setup_method(self):
        self.enhancer = MetacogEnhancer()

    def test_simplification_bias_triggers(self):
        e = self.enhancer.enhance("这个方案最佳实践是什么？")
        assert "单维度简化倾向" in e.matched_biases
        assert len(e.challenge_questions) >= 2
        assert "enhanced" not in e.enhanced_query or e.enhanced_query != "这个方案最佳实践是什么？"

    def test_binary_opposition_triggers(self):
        e = self.enhancer.enhance("用React还是Vue？")
        assert "二元对立" in e.matched_biases

    def test_unverified_assumption_triggers(self):
        e = self.enhancer.enhance("默认用这个库就行了")
        assert "默认假设未验证" in e.matched_biases

    def test_more_is_better_triggers(self):
        e = self.enhancer.enhance("增加更多功能让它更全面")
        assert "更多更好谬误" in e.matched_biases

    def test_tool_boundary_triggers(self):
        e = self.enhancer.enhance("让AI自动完成所有测试")
        assert "工具能力边界忽视" in e.matched_biases

    def test_irrelevant_query_no_trigger(self):
        e = self.enhancer.enhance("今天天气怎么样")
        assert e.matched_biases == []
        assert e.challenge_questions == []
        assert e.enhanced_query == "今天天气怎么样"

    def test_multiple_biases_merge_questions(self):
        e = self.enhancer.enhance("默认选择最佳方案还是次优方案")
        assert len(e.matched_biases) >= 2  # 默认假设 + 最佳 + 还是
        assert len(e.challenge_questions) >= 4  # 2 per bias

    def test_enhanced_query_includes_original(self):
        original = "这个架构最佳方案是什么？"
        e = self.enhancer.enhance(original)
        assert e.enhanced_query.startswith(original)


# ── Context Loading ────────────────────────────────────────────────

class TestContextLoading:
    def test_load_from_real_ai_wiki(self):
        ai_wiki = Path.home() / "Documents" / "52VisionWorld" / "projects" / "Ai-wiki"
        if not ai_wiki.exists():
            pytest.skip("AI-wiki not found")
        m = MetacogEnhancer(str(ai_wiki))
        assert len(m.context) >= 4  # at least blind-spots, thinking-patterns, beliefs, surprises

    def test_load_missing_path_returns_zero(self):
        m = MetacogEnhancer("/nonexistent/path")
        assert len(m.context) == 0

    def test_reload_clears_and_reloads(self):
        m = MetacogEnhancer()
        ai_wiki = Path.home() / "Documents" / "52VisionWorld" / "projects" / "Ai-wiki"
        if not ai_wiki.exists():
            pytest.skip("AI-wiki not found")
        count = m.reload(str(ai_wiki))
        assert count >= 4
