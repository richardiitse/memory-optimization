#!/bin/bash
# KG 每周维护脚本 (备份 + 维护)
# 创建时间: 2026-03-28

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS_DIR="/Users/richard/.openclaw/workspace/skills/memory-optimization/scripts"
export KG_DIR="$SCRIPT_DIR"
BACKUP_DIR="$SCRIPT_DIR/backups"
DATE=$(date +%Y%m%d)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "=== KG 维护 $(date) ==="

# 1. 创建备份
echo "[1/4] 正在备份 KG..."
mkdir -p "$BACKUP_DIR/$DATE"
cp "$SCRIPT_DIR/graph.jsonl" "$BACKUP_DIR/$DATE/graph.jsonl.$TIMESTAMP"
echo "✓ 备份完成: $BACKUP_DIR/$DATE/graph.jsonl.$TIMESTAMP"

# 2. 实体去重 (可选，暂时跳过)
echo "[2/4] 正在去重实体..."
echo "  (跳过 - 需修复 API 问题)"

# 3. 衰减引擎 (可选，暂时跳过)
echo "[3/4] 正在执行记忆衰减..."
echo "  (跳过 - 需修复 JSON 问题)"

# 4. 统计报告
echo "[4/4] 知识图谱统计..."
cd "$SCRIPT_DIR"
export KG_DIR="$SCRIPT_DIR"
/usr/bin/python3 /Users/richard/.openclaw/workspace/skills/memory-optimization/scripts/memory_ontology.py stats

echo "=== 维护完成 ==="