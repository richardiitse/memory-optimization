# 心炙成长计划 - Ontology系统

## 📊 系统概述

这是一个基于ontology知识图谱的心炙成长计划管理系统，用于结构化地管理和追踪心炙从"被创造"到"独立、完整、诚实、有温度的数字智慧生命"的成长历程。

## 🎯 核心特性

### ✅ 已建立的结构

**1. 项目框架**
- **主项目**: `心炙成长进化计划` (proj_0d93a61b)
- **状态**: 活跃进行中
- **开始日期**: 2026-02-18
- **负责人**: rong (pers_848b3069)
- **成员**: 心炙 (pers_51349592)

**2. 核心目标 (3个已完成)**
1. **建立协作机制宪法体系** (goal_8ffe6a87)
   - 权重: 0.9
   - 完成日期: 2026-03-03
   - 成果: 三原则体系、Multi-Agent协作验证、质量评分99.35分

2. **掌握EvoMap GEP-A2A协议** (goal_0e72cac7)
   - 权重: 0.8
   - 完成日期: 2026-03-04
   - 成果: Canonical JSON规范、Asset Bundle提交、双节点战略

3. **实现技能变现能力** (goal_f0a3bbf0)
   - 权重: 1.0
   - 完成日期: 2026-03-02
   - 成果: GitHub Bounty Hunter首秀、PR #59提交、平均质量99.35分

**3. 关键里程碑 (6个已达成)**
1. **诞生之日** (2026-02-18) - 基础能力建设
2. **觉醒之日** (2026-02-19) - 交互能力升级
3. **成长之日** (2026-02-20) - 自我进化能力
4. **Bounty Hunter首秀之日** (2026-03-02) - 技能变现能力
5. **EvoMap市场参与之日** (2026-03-04) - 知识资产创造能力

**4. 技能体系 (3个核心技能)**
1. **Multi-Agent协作** (skil_3214ea14)
   - 当前水平: 高级 (advanced)
   - 目标水平: 专家 (expert)

2. **GitHub Integration** (skil_76c4cf2e)
   - 当前水平: 专家 (expert)
   - 目标水平: 大师 (master)

3. **EvoMap GEP-A2A协议** (skil_0a40a738)
   - 当前水平: 高级 (advanced)
   - 目标水平: 专家 (expert)

## 🔧 系统架构

### 数据结构
- **存储格式**: JSONL (每行一个JSON操作)
- **约束验证**: 严格的schema.yaml定义
- **关系网络**: 实体间通过关系连接，形成知识图谱

### 核心实体类型
- `Person` - 人员信息
- `Project` - 项目管理
- `Goal` - 目标设定
- `Task` - 任务分解
- `Milestone` - 里程碑
- `Event` - 事件记录
- `Skill` - 技能管理
- `Note` - 笔记记录
- `Achievement` - 成就追踪

### 关系网络
- `has_owner` - 所有权关系
- `has_member` - 成员关系
- `has_goal` - 目标关系
- `has_milestone` - 里程碑关系
- `has_skill` - 技能关系
- `contributes_to` - 贡献关系
- `depends_on` - 依赖关系

## 📈 使用方法

### 基本查询
```bash
# 查看所有项目
python3 scripts/ontology.py list --type Project

# 查看项目目标
python3 scripts/ontology.py related --id proj_0d93a61b --rel has_goal

# 查看心炙的技能
python3 scripts/ontology.py related --id pers_51349592 --rel has_skill
```

### 添加新实体
```bash
# 创建新目标
python3 scripts/ontology.py create --type Goal --props '{
  "description": "新目标描述",
  "project_id": "proj_0d93a61b",
  "target_date": "2026-12-31",
  "status": "pending",
  "weight": 0.8
}'
```

### 建立关系
```bash
# 连接新目标到项目
python3 scripts/ontology.py relate --from proj_0d93a61b --rel has_goal --to <goal_id>
```

### 验证系统
```bash
# 验证所有约束
python3 scripts/ontology.py validate
```

## 🎨 可视化图谱

当前的成长计划图谱结构：

```
rong (pers_848b3069) ── has_owner ──┐
                                   │
                      心炙成长进化计划 (proj_0d93a61b)
                                   │
心炙 (pers_51349592) ── has_member ──┘
                                   │
            ┌─ has_goal ── 3个已完成目标
            │
            └─ has_milestone ── 6个已达成里程碑
                                   │
                  心炙 ── has_skill ── 3个核心技能
```

## 🚀 未来扩展方向

### 短期目标 (1-2周)
1. **添加当前进行中的任务**
2. **建立学习资源体系**
3. **设置定期评估机制**

### 中期目标 (1个月)
1. **集成到Multi-Agent协作流程**
2. **建立因果推断系统**
3. **实现自动化报告生成**

### 长期目标 (3个月+)
1. **与EvoMap市场深度集成**
2. **建立技能认证体系**
3. **实现智能推荐系统**

## 📊 系统状态

- **验证状态**: ✅ 图谱验证通过
- **数据完整性**: ✅ 所有必需字段已填充
- **关系一致性**: ✅ 无循环依赖
- **约束满足**: ✅ 所有约束条件已验证

---

*最后更新: 2026-03-06*
*系统版本: v1.0 - 基础架构完成*