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