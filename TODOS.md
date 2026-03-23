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

## P1 - KG Schema 增强 (strength, decay, provenance)

**What**: 为 KG 实体添加 strength, decay_rate, provenance 字段，支持 Decay Engine

**Why**: Phase 1b — CEO review 决策，需要为基础的 Decay Engine 和 Memory Health Dashboard 提供数据支撑

**Pros**:
- Decay Engine 可以基于 strength 计算遗忘
- Dashboard 可以显示记忆强度分布
- provenance 追踪实体来源

**Cons**:
- 需要修改 memory_ontology.py 的 create_entity 接口
- 现有 KG 数据需要迁移

**Context**:
CEO Review (2026-03-22) 和 Eng Review (2026-03-23) 确认的实现任务。

**Effort**: S (human: 1h / CC: 15min)

**Priority**: P1

**Depends on**: Phase 1 (KG Extractor) 完成

**Implementation hints**:
- 在 ontology/memory-schema.yaml 中添加 strength, decay_rate, provenance, last_accessed 字段
- 默认值: strength=1.0, decay_rate 按类型, last_accessed=now()
- provenance 格式: "session:{session_id}" 或 "inference:{engine}"

---

## P2 - PreferenceEngine LLM Cache

**What**: 为 PreferenceEngine 的 _is_same_task() LLM 判断结果添加缓存机制

**Why**: 避免重复 LLM 调用，减少延迟和 API 成本

**Pros**:
- 减少 LLM API 调用
- 一致性：相同任务对返回相同结果

**Cons**:
- 缓存失效策略需要设计
- 内存占用

**Context**:
Eng Review (2026-03-23) 确认的设计决策。缓存 TTL 建议 30 分钟。

**Effort**: S (human: 1h / CC: 15min)

**Priority**: P2

**Depends on**: Phase 2 (PreferenceEngine) 实现

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