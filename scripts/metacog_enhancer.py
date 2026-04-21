"""
Metacognitive query enhancer — bias-aware query expansion.

Reads AI-wiki self-layer files (blind-spots, thinking-patterns, beliefs, surprises)
and generates challenge questions when user queries match known cognitive biases.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Keywords derived from actual AI-wiki file content:
# - blind-spots.md: 单维度简化倾向 (tags: 简化, 二元对立, 默认假设)
# - thinking-patterns.md: 选择深度而非广度, 拒绝表面二元对立
# - beliefs.md: AI分析客观可靠, 更多更全更好, 对立矛盾需要解决
#
# Original English keywords (confirmation, bias, 确认, 偏误) had ZERO match rate.

BIAS_PATTERNS: List[Dict] = [
    {
        "name": "单维度简化倾向",
        "keywords": ["最好", "最优", "唯一的", "肯定是", "绝对是", "应该选择",
                      "最佳方案", "最佳实践", "最佳", "推荐", "建议用",
                      "架构选择", "技术选型", "方案对比", "决策"],
        "questions": [
            "是否有其他维度没有考虑到？",
            "是否过于简化了问题的复杂性？",
            "是否存在中间状态或折中方案？",
        ],
    },
    {
        "name": "二元对立",
        "keywords": ["还是", "或者", "vs", "对比", "选择A还是B",
                      "好还是坏", "对还是错", "用不用", "要不要",
                      "是否应该", "A还是B"],
        "questions": [
            "是否存在非此即彼之外的第三条路？",
            "两者的张力本身是否有价值？",
            "能否同时保留两者的优点？",
        ],
    },
    {
        "name": "默认假设未验证",
        "keywords": ["默认", "当然", "显然", "理所当然", "理应",
                      "按理说", "大家都知道", "常识是",
                      "假设", "以为", "认为"],
        "questions": [
            "这个假设是否经过验证？",
            "有哪些反例或反直觉的证据？",
            "如果假设是错的，结论会怎样？",
        ],
    },
    {
        "name": "更多更好谬误",
        "keywords": ["更多", "更全", "完整", "全面", "全覆盖",
                      "所有功能", "一体化", "all-in-one", "完整方案",
                      "丰富", "增加", "补充"],
        "questions": [
            "精简是否比堆砌更有效？",
            "减少认知负担是否比增加能力更有价值？",
            "哪些是真正需要的，哪些是冗余？",
        ],
    },
    {
        "name": "工具能力边界忽视",
        "keywords": ["AI可以", "LLM能", "模型会", "自动完成",
                      "帮我做", "让AI", "自动化", "智能化",
                      "工具会", "系统能"],
        "questions": [
            "工具的能力边界在哪里？",
            "哪些环节需要人的判断？",
            "是否存在工具结构性无法解决的问题？",
        ],
    },
]


@dataclass(frozen=True)
class Enhancement:
    matched_biases: List[str]
    challenge_questions: List[str]
    enhanced_query: str


class MetacogEnhancer:
    """Enhances queries with challenge questions based on known cognitive biases."""

    def __init__(self, ai_wiki_path: Optional[str] = None):
        self.context: Dict[str, str] = {}
        self.biases = BIAS_PATTERNS
        if ai_wiki_path:
            self.load_context(ai_wiki_path)

    def load_context(self, ai_wiki_path: str) -> int:
        self_path = Path(ai_wiki_path) / "wiki" / "self"
        if not self_path.exists():
            logger.warning("AI-wiki self path not found: %s", self_path)
            return 0

        count = 0
        for filename in [
            "thinking-patterns.md", "blind-spots.md",
            "beliefs.md", "surprises.md", "decisions.md",
        ]:
            fp = self_path / filename
            if fp.exists():
                try:
                    key = filename.replace(".md", "")
                    content = fp.read_text(encoding='utf-8')
                    if len(content.encode('utf-8')) > 1_000_000:  # 1MB limit
                        logger.warning("Skipping large file %s (>1MB)", filename)
                        continue
                    self.context[key] = content
                    count += 1
                except Exception as exc:
                    logger.warning("Failed to load %s: %s", filename, exc)

        logger.info("Loaded %d AI-wiki context files from %s", count, self_path)
        return count

    def enhance(self, query: str) -> Enhancement:
        matched_biases: List[str] = []
        challenge_questions: List[str] = []

        for pattern in self.biases:
            if self._matches(query, pattern["keywords"]):
                matched_biases.append(pattern["name"])
                # Pick up to 2 questions per matched bias
                challenge_questions.extend(pattern["questions"][:2])

        if challenge_questions:
            enhanced = f"{query} {' '.join(challenge_questions)}"
        else:
            enhanced = query

        return Enhancement(
            matched_biases=matched_biases,
            challenge_questions=challenge_questions,
            enhanced_query=enhanced,
        )

    @staticmethod
    def _matches(query: str, keywords: List[str]) -> bool:
        q = query.lower()
        return any(kw.lower() in q for kw in keywords)

    def reload(self, ai_wiki_path: str) -> int:
        self.context.clear()
        return self.load_context(ai_wiki_path)
