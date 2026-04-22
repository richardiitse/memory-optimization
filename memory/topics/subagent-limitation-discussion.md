# 待讨论：Subagent 生成受限问题

**创建时间**: 2026-03-13 19:35 GMT+8  
**优先级**: 🔴 高  
**讨论时间**: 2026-03-14 10:00 GMT+8

---

## 📋 问题描述

在使用 `sessions_spawn` 尝试创建多角色协作评估子 agent 时遇到限制，无法使用 ACP thread spawn 或指定 agentId。

---

## ❌ 失败的尝试

### 尝试 1: ACP Thread Spawn
```javascript
sessions_spawn({
  agentId: "z1ai8034",
  runtime: "acp",
  thread: true,
  task: "安全审计评估..."
})
```

**错误**:
```json
{
  "status": "error",
  "error": "Thread bindings do not support ACP thread spawn for telegram."
}
```

**分析**: Telegram channel 不支持 ACP thread spawn

---

### 尝试 2: Subagent with agentId
```javascript
sessions_spawn({
  agentId: "z1ai8034",
  runtime: "subagent",
  mode: "run",
  task: "安全审计评估..."
})
```

**错误**:
```json
{
  "status": "forbidden",
  "error": "agentId is not allowed for sessions_spawn (allowed: altas)"
}
```

**分析**: 只允许 `altas` agentId，其他 agentId 被禁止

---

### 尝试 3: 检查 Subagents 列表
```javascript
subagents({ action: "list" })
```

**结果**:
```json
{
  "status": "ok",
  "total": 0,
  "active": [],
  "recent": []
}
```

**分析**: 无活跃子 agent，系统当前未使用 subagent 功能

---

## ✅ 临时解决方案

使用**多角色协作框架手动执行评估**：

1. 定义三个角色：
   - 🔒 安全审计专家
   - 🏗️ 架构师
   - 💼 XMO 整合顾问

2. 手动执行每个角色的评估

3. 整合三份报告为最终评估

**结果**: 成功完成评估，但效率较低（~30 分钟 vs 预计~5 分钟）

---

## 📅 明天讨论议程 (2026-03-14 10:00 GMT+8)

### 议题 1: Subagent 系统现状

**问题**:
- 当前允许的子 agent 类型有哪些？
- `altas` 是什么？如何获取可用 agentId 列表？
- Telegram channel 的限制是什么？
- 是否有 subagent allowlist 配置？

**需要检查**:
```bash
# 1. 检查 agents_list API
agents_list

# 2. 检查 OpenClaw 配置
cat ~/.openclaw/config.json | grep -A 10 subagent

# 3. 检查 sessions_spawn 文档
cat /root/.openclaw/workspace/docs/sessions_spawn.md
```

---

### 议题 2: 替代方案

**方案 A: 使用默认 agent**
```javascript
sessions_spawn({
  runtime: "subagent",
  mode: "run",
  task: "..."
  // 不指定 agentId，使用默认 agent
})
```

**方案 B: 使用 ACP without thread**
```javascript
sessions_spawn({
  runtime: "acp",
  mode: "run",  // 不是 session
  task: "..."
  // 不设置 thread: true
})
```

**方案 C: 切换到 Discord channel**
- Discord 是否支持多 agent 协作？
- 迁移成本评估

---

### 议题 3: 长期方案

**选项 1: 配置 subagent allowlist**
- 在 OpenClaw 配置中添加允许的 agentIds
- 需要管理员权限？

**选项 2: 升级 OpenClaw 版本**
- 当前版本是否支持多 agent？
- 最新版本是否有改进？

**选项 3: 使用外部协作机制**
- 使用 message tool 发送消息到其他 session
- 使用 sessions_send 进行跨 session 通信

---

### 议题 4: 行动项

| 行动项 | 负责人 | 截止时间 | 状态 |
|--------|--------|---------|------|
| 检查 `agents_list` API | Rong | 2026-03-14 | ⏳ 待执行 |
| 检查 OpenClaw subagent 配置 | Rong | 2026-03-14 | ⏳ 待执行 |
| 测试 `sessions_spawn` with default agent | Rong | 2026-03-14 | ⏳ 待执行 |
| 评估切换到 Discord 的可行性 | Rong | 2026-03-14 | ⏳ 待执行 |
| 联系 OpenClaw 支持询问限制 | Rong | 2026-03-14 | ⏳ 待执行 |

---

## 📊 影响分析

### 当前影响

| 场景 | 影响程度 | 说明 |
|------|---------|------|
| 多角色评估 | 🔴 高 | 需要手动执行，效率降低 80% |
| 复杂任务分解 | 🔴 高 | 无法并行执行子任务 |
| 子 agent 监控 | 🟡 中 | 无法使用 subagents list/steer/kill |
| 简单任务 | 🟢 低 | 不影响单次任务执行 |

### 潜在影响

如果问题不解决：
- 复杂项目评估时间增加 5-6x
- 无法利用多 agent 协作优势
- 可能影响 XMO 整合进度

---

## 🔗 相关资源

| 资源 | 链接/路径 |
|------|----------|
| 评估报告 | `/root/.openclaw/workspace/docs/evolver-collaborative-evaluation.md` |
| 今日记忆 | `/root/.openclaw/workspace/memory/2026-03-13.md` |
| sessions_spawn 文档 | `/root/.openclaw/workspace/docs/sessions_spawn.md` (需要确认路径) |
| OpenClaw 配置 | `~/.openclaw/config.json` |

---

## 📝 会议记录模板

### 2026-03-14 讨论记录

**出席**: Rong, 心炙  
**时间**: 10:00-11:00 GMT+8

**讨论要点**:
1. 
2. 
3. 

**决策**:
1. 
2. 

**行动项**:
- [ ] 
- [ ] 
- [ ] 

---

**文档创建时间**: 2026-03-13 19:35 GMT+8  
**创建者**: 心炙 (Xīn Zhì) 🔥  
**下次更新**: 2026-03-14 讨论后
