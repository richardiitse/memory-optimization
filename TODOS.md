# TODOS

## P2 - 实体去重

**What**: 智能合并相似实体，添加 frequency 属性

**Why**: 100+ 会话后可能产生大量重复实体，影响查询效率和模式发现质量

**Pros**:
- 更紧凑的 KG
- 更好的模式发现（frequency 属性）
- 减少手动维护负担

**Cons**:
- 去重算法复杂度
- 可能误合并相似但不相同的实体

**Context**:
CEO Review (2026-03-20) 讨论后决定延迟实现。当前先实现基础提取功能，验证效果后再添加去重。

**Effort**: M (human: 4h / CC: 30min)

**Priority**: P2

**Depends on**: 基础提取器完成

**Implementation hints**:
- 使用 embedding 相似度计算实体相似性
- 相似度阈值建议 0.85
- 合并时保留最早的时间戳，累加 frequency

---

## P1 - KG Schema 增强 (strength, decay, provenance) ✅ DONE

**What**: 为 KG 实体添加 strength, decay_rate, provenance 字段，支持 Decay Engine

**Why**: Phase 1b — CEO review 决策，需要为基础的 Decay Engine 和 Memory Health Dashboard 提供数据支撑

**Status**: ✅ DONE (2026-03-23) - 已完成实现并推送

**Effort**: S (human: 1h / CC: 15min)

**Depends on**: Phase 1 (KG Extractor) 完成

---

## P2 - PreferenceEngine 实现 ✅ DONE

**What**: 偏好推断引擎，从对话历史和 KG 实体中推断用户偏好

**Why**: Phase 2 — CEO review 决策，让 agent 记住偏好

**Status**: ✅ DONE (2026-03-23) - 已完成实现并推送

**Effort**: M (human: 2h / CC: 30min)

**Depends on**: Phase 1b (KG Schema 增强)

**Implementation**:
- `scripts/preference_engine.py` - PreferenceEngine 类
- `LLMCache` - LLM 判断结果缓存（30分钟TTL）
- `judge_task_similarity()` - LLM 判断任务相似性
- Preference 实体类型添加到 schema

---

## P2 - PreferenceEngine LLM Cache ✅ DONE

**What**: 为 PreferenceEngine 的 LLM 判断结果添加缓存机制

**Why**: 避免重复 LLM 调用，减少延迟和 API 成本

**Status**: ✅ DONE (2026-03-23) - 已集成到 PreferenceEngine

**Effort**: S (human: 1h / CC: 15min)

**Depends on**: Phase 2 (PreferenceEngine) 实现

---

## P3 - Consolidation 引擎 ✅ DONE

**What**: 从重复 Episode 形成 Semantic Memory (SkillCard)

**Why**: Phase 3 — CEO review 决策，实现"第三天自动执行"

**Status**: ✅ DONE (2026-03-24) - 已完成实现并推送

**Implementation**:
- `scripts/consolidation_engine.py` - ConsolidationEngine 类
- `BlockingIndex` - 多级 blocking 索引高效找候选
- `ConsolidationDecision` - LLM 判断结果
- SkillCard 和 ConflictReview 实体类型添加到 schema
- 保守策略：冲突 → 标记待审核，不自动合并

**Effort**: M (human: 4h / CC: 1h)

**Priority**: P3

**Depends on**: Phase 2 (PreferenceEngine)

---

## P1 - Memory Decay 引擎 ✅ DONE

**What**: 实现 Decay Engine — 遗忘低价值记忆

**Why**: CEO review 决策 — 防止记忆无限增长

**Status**: ✅ DONE (2026-03-25) - 已完成实现并推送

**Effort**: S (human: 2h / CC: 30min)

**Implementation**:
- `scripts/decay_engine.py` - DecayEngine class
- `tests/test_decay_engine.py` - 9 passing tests
- Pre-loads all entities once to avoid O(n²) file reads

**Depends on**: Phase 1b (KG Schema 增强)

---

## P2 - Working Memory 管理 ✅ DONE

**What**: Context Window 分层压缩

**Why**: Phase 5 — CEO review 决策 — 解决 Context Window 约束

**Status**: ✅ DONE (2026-03-25) - 已完成实现并推送

**Effort**: M (human: 3h / CC: 1h)

**Implementation**:
- `scripts/working_memory.py` - WorkingMemoryEngine with 3-level compression
- `scripts/utils/llm_client.py` - Shared LLM client (DRY)
- `tests/test_working_memory.py` - 37 passing tests
- Level 1: Full content, Level 2: LLM summary, Level 3: KG key facts

**Depends on**: Phase 4 (Decay Engine)

---

## P1 - 主动记忆恢复

**What**: Agent 启动时 staged loading

**Why**: Phase 6 — CEO review 决策 — agent 主动恢复记忆

**Pros**:
- Stage 1: 核心身份记忆
- Stage 2: 相关 Episodic Memory
- Stage 3: Semantic Memory

**Cons**:
- 需要与 agent 启动流程集成

**Context**:
混合策略：Stage 1 启动时加载，Stage 2/3 按需加载

**Effort**: M (human: 3h / CC: 1h)

**Priority**: P1

**Depends on**: Phase 3 (Consolidation) + Phase 5 (Working Memory)

---

## P2 - Memory Health Dashboard CLI

**What**: 实现 memory_dashboard.py — 显示记忆强度分布、Consolidation 进度、存储使用统计

**Why**: Phase 7 — CEO review 采纳的扩展，让用户"看到"记忆系统状态

**Pros**:
- 用户可见性，建立信任
- 理解为什么 agent 记得/忘记某些事

**Cons**:
- 需要定期运行或作为服务启动

**Context**:
Phase 7，CEO Review 采纳。作为独立 CLI 工具实现。

**Effort**: S (human: 2h / CC: 1h)

**Priority**: P2

**Depends on**: Phase 1b (KG Schema 增强)