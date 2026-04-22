# 方案 A：记忆系统共存模式

**创建日期**: 2026-04-07  
**状态**: ✅ 已实施

---

## 📋 概述

OpenClaw 4.5 引入了 Memory Dreaming 功能，与现有的 XMO 和 memory-optimization 技能形成三套记忆系统。本方案实现三者共存，各自发挥优势。

---

## 🏗️ 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    用户交互层                                │
│         (Feishu / Telegram / Web UI / Discord)              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              OpenClaw 4.5 Dream (主记忆提升)                 │
│  - 输入：daily notes (memory/YYYY-MM-DD.md)                │
│  - 处理：Light → Deep → REM 三阶段                          │
│  - 输出：MEMORY.md + dreams.md                              │
│  - 频率：每日自动                                           │
│  - 配置：plugins.entries.memory-core.config.dreaming       │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│      XMO (跨 Agent)      │     │  memory-optimization    │
│  - 位置：~/.xmo/kg/     │     │  - 位置：workspace/     │
│  - 格式：entities.jsonl │     │    memory/ontology/     │
│  - 间隔：48 小时         │     │  - 格式：graph.jsonl    │
│  - 用途：共享层          │     │  - 功能：decay/dedup/   │
│                         │     │           working_mem   │
└─────────────────────────┘     └─────────────────────────┘
```

---

## 🔧 配置详情

### 1. OpenClaw 4.5 Dream

**文件**: `~/.openclaw/openclaw.json`

```json
{
  "plugins": {
    "entries": {
      "memory-core": {
        "config": {
          "dreaming": {
            "enabled": true
          }
        }
      }
    }
  }
}
```

**输出**:
- `~/.openclaw/workspace/dreams.md` - 梦境日记
- `~/.openclaw/workspace/MEMORY.md` - 长期记忆提升

**命令**:
- `/dreaming` - 手动触发
- `/dreaming status` - 查看状态

---

### 2. XMO (跨 Agent 共享)

**文件**: `~/.xmo/config.json`

```json
{
  "auto_consolidate": true,
  "consolidate_interval_hours": 48,
  "note": "Extended to 48h to coexist with OpenClaw 4.5 Dream (daily)"
}
```

**输出**: `~/.xmo/kg/entities.jsonl` (3,389 实体)

**MCP 工具**:
- `xmo_query` - 搜索记忆
- `xmo_extract` - 添加记忆
- `xmo_consolidate` - 手动整合
- `xmo_stats` - 查看统计

---

### 3. memory-optimization (高级功能)

**文件**: `~/.openclaw/workspace/skills/memory-optimization/.env`

```bash
# 禁用 consolidation (避免与 OpenClaw 4.5 Dream 重复)
DREAMING_ENABLED=false
CONSOLIDATION_ENABLED=false

# 启用的功能:
# - decay_engine (记忆衰减)
# - entity_dedup (实体去重)
# - working_memory (工作记忆)
# - memory_loader (记忆加载)
```

**输出**: `~/.openclaw/workspace/memory/ontology/graph.jsonl`

---

## 📊 功能对比

| 功能 | OpenClaw 4.5 Dream | XMO | memory-optimization |
|------|-------------------|-----|---------------------|
| 自动整合 | ✅ 每日 | ✅ 48 小时 | ❌ 已禁用 |
| 手动触发 | ✅ `/dreaming` | ✅ `xmo_consolidate` | ✅ CLI |
| 可视化 UI | ✅ Dreams UI | ❌ | ❌ |
| 记忆衰减 | ✅ 内置 | ❌ | ✅ decay_engine |
| 冲突检测 | ❓ | ✅ | ✅ |
| SkillCard | ❓ | ✅ | ✅ |
| LLM 判断 | ✅ | ✅ | ✅ |
| 多语言标签 | ✅ | ❌ | ❌ |
| 跨 Agent | ❓ | ✅ | ❌ |

---

## ⚠️ 注意事项

1. **避免重复整合**: XMO 设置为 48 小时，避免与 OpenClaw Dream 每日运行冲突

2. **存储隔离**: 三个系统使用不同存储位置，不会互相覆盖

3. **功能边界**:
   - OpenClaw Dream: 主记忆提升管道
   - XMO: Claude Code ↔ OpenClaw 共享层
   - memory-optimization: 高级功能 (衰减、去重)

4. **监控建议**: 定期检查 `dreams.md` 和 `MEMORY.md` 内容，确保 Dream 系统正常运行

---

## 🔍 验证命令

```bash
# 检查 OpenClaw Dream 配置
openclaw config show | grep -A 10 dreaming

# 查看梦境日记
cat ~/.openclaw/workspace/dreams.md

# 检查 XMO 状态
xmo_stats

# 检查 memory-optimization KG
python3 ~/.openclaw/workspace/skills/memory-optimization/scripts/memory_ontology.py status
```

---

*本方案于 2026-04-07 由 rong 确认实施*
