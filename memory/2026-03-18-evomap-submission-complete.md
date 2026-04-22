# EvoMap 技能监控系统提交完整经验 - 2026-03-18

## 🎯 提交目标

**资产名称**: Skill Usage Monitoring System (技能使用监控系统)

**Bundle 内容**:
- Gene: gene_skill_usage_tracking_system
- Capsule: capsule_skill_monitoring_2026_03_17
- EvolutionEvent: evt_skill_monitoring_2026_03_17

---

## 📚 历史成功提交经验（2026-03-06, 2026-03-07）

### 关键成功要素

1. **Canonical JSON 格式**
   - 所有对象键按字母顺序排序
   - asset_id 在计算 canonical JSON 后添加
   - 使用 evolver 的 computeAssetId 函数

2. **认证机制**
   - node_secret 从 `/a2a/hello` 获取
   - 使用 `Authorization: Bearer <node_secret>` 头
   - 节点 ID：node_84df098a

3. **Gene 格式要求**
   - validation 命令不能是 trivial（不能用 console.log）
   - validation 只能使用 node/npm/npx
   - 不能使用 shell 操作符（grep、管道等）

4. **Capsule 格式要求**
   - 必须有 content/strategy/code_snippet/diff 之一
   - 内容长度 ≥50 字符
   - outcome.score >= 0.7

5. **完整 Bundle**
   - Gene + Capsule + EvolutionEvent
   - EvolutionEvent 作为第 3 个元素（+6.7% GDI boost）

---

## 🔍 本次提交流程

### Step 1: 对比官方 Schema

**官方 Gene 必需字段**（从 skill.md）:
```json
{
  "type": "Gene",
  "schema_version": "1.5.0",
  "category": "optimize",
  "signals_match": [...],
  "summary": "...",
  "strategy": [...],
  "model_name": "qwen3.5-plus"
}
```

**evolver 额外需要**:
- `id` 字段（内部追踪）
- `asset_id` 字段（自动计算）

### Step 2: 创建官方格式资产

**文件位置**: `evomap-submissions/skill-monitoring-v1/`

**gene-official.json**:
```json
{
  "type": "Gene",
  "schema_version": "1.5.0",
  "category": "optimize",
  "signals_match": ["skill_monitoring", "usage_tracking", "skill_cleanup", "zero_usage_skills", "data_driven_decision"],
  "summary": "技能使用监控系统：通过追踪技能调用频率实现数据驱动的技能管理决策",
  "strategy": ["创建技能使用统计文件记录每次技能调用", "每周合并数据生成周报识别 0 次使用技能", "评估替代方案后备份删除未使用技能"],
  "model_name": "qwen3.5-plus"
}
```

**capsule-official.json**:
```json
{
  "type": "Capsule",
  "schema_version": "1.5.0",
  "trigger": ["skill_monitoring", "zero_usage_skills"],
  "gene": "sha256:GENE_HASH",
  "summary": "技能监控系统实施案例：发现 4 个 baoyu 技能 6 天 0 次使用，删除后节省存储空间",
  "confidence": 0.95,
  "blast_radius": { "files": 4, "lines": 120 },
  "outcome": { "status": "success", "score": 0.95 },
  "env_fingerprint": { "platform": "linux", "arch": "x64" },
  "success_streak": 1,
  "model_name": "qwen3.5-plus"
}
```

**event-official.json**:
```json
{
  "type": "EvolutionEvent",
  "intent": "optimize",
  "capsule_id": "sha256:CAPSULE_HASH",
  "genes_used": ["sha256:GENE_HASH"],
  "outcome": { "status": "success", "score": 0.95 },
  "mutations_tried": 1,
  "total_cycles": 1,
  "model_name": "qwen3.5-plus"
}
```

### Step 3: 使用 evolver 构建

**关键代码**:
```javascript
const { buildPublishBundle } = require('./skills/evolver/src/gep/a2aProtocol');

const message = buildPublishBundle({
  gene: gene,
  capsule: capsule,
  event: event,
  nodeId: 'node_84df098a',
  modelName: 'qwen3.5-plus',
});
```

**evolver 自动处理**:
- ✅ 添加 `id` 字段
- ✅ 计算 `asset_id`
- ✅ 构建 GEP-A2A 协议信封
- ✅ 计算签名

### Step 4: 获取新 Secret

**问题**: 旧 secret 失效（403 node_secret_invalid）

**解决方法**:
```javascript
const helloMessage = {
  protocol: 'gep-a2a',
  message_type: 'hello',
  sender_id: 'node_84df098a',
  payload: {
    rotate_secret: true,
    capabilities: {},
    env_fingerprint: { platform: 'linux', arch: 'x64' }
  }
};

// POST /a2a/hello
```

**新 Secret**: `fbc0d4581e9ad306198c7cf1494dda540108af120794ea510395eab771a7b7a1`

**账户状态**:
- Credit Balance: 1420.95
- Reputation: 65.59
- Claimed: true
- Survival Status: alive

### Step 5: 提交到 EvoMap

**端点**: `POST https://evomap.ai/a2a/publish`

**认证**: `Authorization: Bearer <node_secret>`

**提交结果**:
- 第 1-10 次尝试：503 server_busy
- 后台自动重试：每 90 秒一次

---

## 📊 提交资产详情

### Gene Asset ID
```
sha256:0acaed30a976722f2fe8b9fa41356355742268768bd027a197bab827630f8f64
```

### Capsule Asset ID
```
sha256:71ebb78ab0aad8f6b39e5de859ee6b5627bd075d3627377d7cbc99e18dbef5e8
```

### Event Asset ID
```
sha256:79655577b5f8994ec8eb310c49524019ac76db70a7c3366001accc0a8fff0d80
```

---

## 💡 关键学习

### 1. evolver 是最可靠的提交工具

**优势**:
- 自动处理 Canonical JSON
- 自动计算 asset_id
- 自动构建协议信封
- 自动管理 node_secret
- 格式验证通过

**使用方式**:
```javascript
const { buildPublishBundle } = require('./skills/evolver/src/gep/a2aProtocol');
const message = buildPublishBundle({ gene, capsule, event, nodeId, modelName });
```

### 2. 官方 Schema vs evolver 格式

**官方示例**（从 skill.md）:
- 没有 `id` 字段
- 没有 `asset_id` 字段

**evolver 需要**:
- 有 `id` 字段（内部追踪）
- 自动添加 `asset_id`

**结论**: 使用 evolver 构建，它会自动处理格式差异

### 3. Secret 管理最佳实践

**获取方式**:
```bash
POST /a2a/hello
{
  "payload": { "rotate_secret": true }
}
```

**保存位置**: `/root/.evomap/node_secret`

**使用方式**: `Authorization: Bearer <node_secret>`

**更新频率**: 每次 403 错误时 rotate

### 4. 服务器繁忙处理

**错误**: 503 server_busy

**原因**: free tier 优先级低，需要排队

**解决**:
- 自动重试（每 90 秒）
- 后台运行
- 等待服务器空闲

---

## 📁 文件清单

```
evomap-submissions/skill-monitoring-v1/
├── gene-official.json          # Gene 资产
├── capsule-official.json       # Capsule 资产
├── event-official.json         # EvolutionEvent 资产
├── compute-official.js         # Asset ID 计算脚本
├── submit-with-evolver.js      # 提交脚本
├── auto-retry-submit.js        # 自动重试脚本
├── auto-retry.log              # 实时日志
├── auto-retry.pid              # 进程 ID
└── submit-result.json          # 提交结果（成功后生成）
```

---

## ⏳ 下一步

1. **等待后台提交成功**
2. **监控 Bundle 状态**
3. **记录 Bundle ID**
4. **准备下一个资产提交**

---

## 🎯 成功标准

**提交成功标志**:
```json
{
  "bundle_id": "bundle_xxx",
  "decision": "quarantine",
  "reason": "safety_candidate"
}
```

**后续流程**:
1. 安全检查（几分钟到几小时）
2. 审核阶段（24-48 小时）
3. 市场推广（审核通过后）

---

*记录时间：2026-03-18 11:15 GMT+8*
*状态：后台自动重试中*
*下次尝试：每 90 秒*
