#!/usr/bin/env python3
"""
Agent Memory Ontology Manager
知识图谱记忆管理工具

提供命令行接口用于创建、查询和管理 Agent 记忆实体

使用方法:
    python3 memory_ontology.py create --type Decision --props '{"title":"...","rationale":"..."}'
    python3 memory_ontology.py query --type Finding --tags "#memory"
    python3 memory_ontology.py relate --from find_001 --rel led_to_decision --to dec_001
    python3 memory_ontology.py validate
"""

import json
import os
import sys
import hashlib
import time
import fcntl
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any
import yaml

# 路径配置 - 支持 KG_DIR 环境变量
# 开发环境: ontology/ (相对路径)
# 生产环境: /root/.openclaw/workspace/memory/ontology/
SCRIPT_DIR = Path(__file__).parent
WORKSPACE_ROOT = SCRIPT_DIR.parent


def load_env_file():
    """从 .env 文件加载环境变量

    查找 WORKSPACE_ROOT/.env 文件并设置环境变量。
    跳过注释和空行，支持带引号的值。
    """
    env_file = WORKSPACE_ROOT / ".env"
    if not env_file.exists():
        return

    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # 跳过空行和注释
            if not line or line.startswith('#'):
                continue
            # 解析 KEY=value
            if '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value:
                os.environ[key] = value


# 加载 .env 文件（必须在读取 KG_DIR 之前）
load_env_file()

# 现在根据环境变量设置路径
_kg_dir = os.environ.get('KG_DIR', '')  # 可配置的知识图谱目录
ONTOLOGY_DIR = Path(_kg_dir) if _kg_dir else WORKSPACE_ROOT / "ontology"
GRAPH_FILE = ONTOLOGY_DIR / "graph.jsonl"
SCHEMA_FILE = ONTOLOGY_DIR / "memory-schema.yaml"
BASE_SCHEMA_FILE = ONTOLOGY_DIR / "schema.yaml"

# ========== Phase 1b: 记忆进化字段配置 ==========

# 各实体类型的默认衰减率 (每月)
DECAY_RATES = {
    'Decision': 0.95,
    'LessonLearned': 0.90,
    'Finding': 0.80,
    'SkillCard': 0.99,
    'Commitment': 0.85,
    'ContextSnapshot': 0.75,
    'Note': 0.85,
    'Task': 0.80,
    'Project': 0.90,
    'Preference': 0.90,  # Phase 2
    # 默认值
    'default': 0.90
}

# 衰减阈值，低于此值标记为归档候选
DECAY_THRESHOLD = 0.10

# 访问时衰减阈值（小时），超过此时间才触发衰减
ACCESS_DECAY_THRESHOLD_HOURS = 1


def _write_to_graph(data: str):
    """写入 graph.jsonl（带文件锁）

    使用 fcntl.flock 实现原子写入，防止并发写入冲突。
    使用 'a' 模式避免 TOCTOU race（truncate-before-lock）。
    """
    lock_file = GRAPH_FILE.with_suffix('.lock')
    lock_f = open(lock_file, 'a')
    try:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        try:
            with open(GRAPH_FILE, 'a', encoding='utf-8') as f:
                f.write(data)
        finally:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
    finally:
        lock_f.close()


def ensure_ontology_dir():
    """确保 ontology 目录存在"""
    ONTOLOGY_DIR.mkdir(parents=True, exist_ok=True)
    if not GRAPH_FILE.exists():
        GRAPH_FILE.touch()
        print(f"✓ Created graph file: {GRAPH_FILE}")


def generate_entity_id(entity_type: str) -> str:
    """生成实体 ID"""
    timestamp = str(time.time()).encode('utf-8')
    random_seed = str(time.time_ns()).encode('utf-8')
    hash_input = timestamp + random_seed
    hash_hex = hashlib.md5(hash_input).hexdigest()[:8]
    
    prefix_map = {
        'Decision': 'dec',
        'Finding': 'find',
        'LessonLearned': 'lesson',
        'Commitment': 'commit',
        'ContextSnapshot': 'snapshot',
        'Note': 'note',
        'Task': 'task',
        'Project': 'proj',
        'Goal': 'goal',
        'Person': 'pers',
        'Milestone': 'mile',
        'Skill': 'skil',
        'Event': 'event',
        'SkillCard': 'skc',
        'ConflictReview': 'conf'
    }
    
    prefix = prefix_map.get(entity_type, 'ent')
    return f"{prefix}_{hash_hex}"


def get_default_decay_rate(entity_type: str) -> float:
    """获取实体类型的默认衰减率"""
    return DECAY_RATES.get(entity_type, DECAY_RATES['default'])


def add_memory_evolution_fields(entity_type: str, properties: Dict) -> Dict:
    """为实本添加记忆进化字段（Phase 1b）"""
    now = datetime.now().astimezone().isoformat()

    # 如果没有提供 strength，使用默认值
    if 'strength' not in properties:
        properties['strength'] = 1.0

    # 如果没有提供 decay_rate，使用类型默认值
    if 'decay_rate' not in properties:
        properties['decay_rate'] = get_default_decay_rate(entity_type)

    # 如果没有提供 last_accessed，设置为当前时间
    if 'last_accessed' not in properties:
        properties['last_accessed'] = now

    # 如果没有提供 source_trust，使用默认值
    if 'source_trust' not in properties:
        properties['source_trust'] = 'medium'

    return properties


def load_schema() -> Dict:
    """加载 schema 定义"""
    schema = {'types': {}, 'relations': {}, 'validations': [], 'examples': {}}
    
    # 加载记忆 schema（优先，包含新类型）
    if SCHEMA_FILE.exists():
        try:
            with open(SCHEMA_FILE, 'r', encoding='utf-8') as f:
                memory_schema = yaml.safe_load(f)
                if memory_schema:
                    schema['types'].update(memory_schema.get('types', {}))
                    schema['relations'].update(memory_schema.get('relations', {}))
                    schema['validations'].extend(memory_schema.get('validations', []))
        except Exception as e:
            print(f"Warning: Could not load memory schema: {e}")
    
    # 加载基础 schema（补充）
    if BASE_SCHEMA_FILE.exists():
        try:
            with open(BASE_SCHEMA_FILE, 'r', encoding='utf-8') as f:
                base_schema = yaml.safe_load(f)
                if base_schema:
                    # 只添加不存在的类型，避免覆盖
                    for key, value in base_schema.get('types', {}).items():
                        if key not in schema['types']:
                            schema['types'][key] = value
                    for key, value in base_schema.get('relations', {}).items():
                        if key not in schema['relations']:
                            schema['relations'][key] = value
        except Exception as e:
            print(f"Warning: Could not load base schema: {e}")
    
    return schema


def validate_entity(entity_type: str, properties: Dict) -> List[str]:
    """验证实体属性"""
    errors = []
    schema = load_schema()
    
    if entity_type not in schema['types']:
        errors.append(f"未知实体类型：{entity_type}")
        return errors
    
    type_schema = schema['types'][entity_type]
    required_fields = type_schema.get('required', [])
    
    # 检查必填字段
    for field in required_fields:
        if field not in properties:
            errors.append(f"缺少必填字段：{field}")
    
    # 检查属性类型
    properties_schema = type_schema.get('properties', {})
    for field, value in properties.items():
        if field in properties_schema:
            field_schema = properties_schema[field]
            
            # 检查 enum
            if 'enum' in field_schema and value not in field_schema['enum']:
                errors.append(f"字段 {field} 的值 {value} 不在允许范围内：{field_schema['enum']}")
            
            # 检查类型
            expected_type = field_schema.get('type')
            if expected_type == 'number' and not isinstance(value, (int, float)):
                errors.append(f"字段 {field} 应该是数字类型")
            elif expected_type == 'string' and not isinstance(value, str):
                errors.append(f"字段 {field} 应该是字符串类型")
            elif expected_type == 'array' and not isinstance(value, list):
                errors.append(f"字段 {field} 应该是数组类型")
    
    return errors


def create_entity(entity_type: str, properties: Dict, entity_id: Optional[str] = None,
                 provenance: Optional[List[str]] = None) -> Dict:
    """创建实体

    Phase 1b 增强: 自动添加 strength, decay_rate, last_accessed, provenance 字段
    """
    # 添加记忆进化字段
    properties = add_memory_evolution_fields(entity_type, properties)

    # 添加 provenance（如果提供）
    if provenance:
        existing_provenance = properties.get('provenance', [])
        if isinstance(existing_provenance, list):
            properties['provenance'] = existing_provenance + provenance
        else:
            properties['provenance'] = provenance

    # 验证
    errors = validate_entity(entity_type, properties)
    if errors:
        raise ValueError(f"实体验证失败:\n" + "\n".join(f"  - {e}" for e in errors))

    # 生成 ID
    if not entity_id:
        entity_id = generate_entity_id(entity_type)

    # 创建实体对象
    now = datetime.now().astimezone().isoformat()
    entity = {
        "id": entity_id,
        "type": entity_type,
        "properties": properties,
        "created": now,
        "updated": now
    }
    
    # 写入 graph.jsonl
    operation = {
        "op": "create",
        "entity": entity,
        "timestamp": now
    }

    _write_to_graph(json.dumps(operation, ensure_ascii=False) + '\n')

    return entity


def create_relation(from_id: str, rel_type: str, to_id: str, properties: Optional[Dict] = None):
    """创建关系"""
    schema = load_schema()
    
    # 验证关系类型
    if rel_type not in schema['relations']:
        raise ValueError(f"未知关系类型：{rel_type}")
    
    # 验证实体存在
    entities = load_all_entities()
    if from_id not in entities:
        raise ValueError(f"实体不存在：{from_id}")
    if to_id not in entities:
        raise ValueError(f"实体不存在：{to_id}")
    
    # 验证关系类型匹配
    rel_schema = schema['relations'][rel_type]
    from_entity = entities[from_id]
    to_entity = entities[to_id]
    
    from_types = rel_schema.get('from_types', [])
    to_types = rel_schema.get('to_types', [])
    
    if from_entity['type'] not in from_types:
        raise ValueError(f"关系 {rel_type} 不能从 {from_entity['type']} 类型发起，允许的类型：{from_types}")
    
    if to_entity['type'] not in to_types:
        raise ValueError(f"关系 {rel_type} 不能指向 {to_entity['type']} 类型，允许的类型：{to_types}")
    
    # 创建关系
    now = datetime.now().astimezone().isoformat()
    operation = {
        "op": "relate",
        "from": from_id,
        "rel": rel_type,
        "to": to_id,
        "properties": properties or {},
        "timestamp": now
    }

    _write_to_graph(json.dumps(operation, ensure_ascii=False) + '\n')

    return operation


def load_all_entities() -> Dict[str, Dict]:
    """加载所有实体（带共享锁）

    使用 fcntl.LOCK_SH 共享锁，允许并发读取。
    与 _write_to_graph 的独占锁互斥，防止读到部分写入的数据。
    """
    entities = {}

    if not GRAPH_FILE.exists():
        return entities

    lock_file = GRAPH_FILE.with_suffix('.lock')
    lock_f = open(lock_file, 'a')
    try:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_SH)
        try:
            with open(GRAPH_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        operation = json.loads(line)
                        if operation['op'] == 'create':
                            entity = operation['entity']
                            entities[entity['id']] = entity
                        elif operation['op'] == 'update':
                            entity_id = operation['entity']['id']
                            if entity_id in entities:
                                entities[entity_id]['properties'].update(operation['entity']['properties'])
                                entities[entity_id]['updated'] = operation['entity']['updated']
                    except json.JSONDecodeError:
                        continue
        finally:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
    finally:
        lock_f.close()

    return entities


def _read_entity_from_graph(entity_id: str) -> Optional[Dict]:
    """从 graph.jsonl 读取单个实体（不触发衰减）

    这是 get_entity() 的内部辅助方法，用于在不触发访问时衰减的情况下读取实体。
    """
    entities = load_all_entities()
    return entities.get(entity_id)


def refresh_entity_strength(entity_id: str) -> Optional[float]:
    """刷新实体 strength 并更新 last_accessed

    当实体被访问时调用，计算基于时间的衰减而非硬重置。
    衰减公式: new_strength = old_strength * (decay_rate ^ (days_elapsed / 30))

    Returns:
        更新后的 strength 值，如果实体不存在返回 None
    """
    entity = _read_entity_from_graph(entity_id)
    if not entity:
        return None

    now = datetime.now().astimezone().isoformat()
    props = entity['properties']
    last_accessed = props.get('last_accessed')

    if last_accessed:
        # 计算自上次访问以来的衰减
        try:
            last_dt = datetime.fromisoformat(last_accessed.replace('Z', '+00:00'))
            hours_elapsed = (datetime.now().astimezone() - last_dt).total_seconds() / 3600

            if hours_elapsed >= ACCESS_DECAY_THRESHOLD_HOURS:
                # 应用衰减
                days_elapsed = hours_elapsed / 24.0
                old_strength = props.get('strength', 1.0)
                decay_rate = props.get('decay_rate', 0.95)
                months_elapsed = days_elapsed / 30.0
                new_strength = old_strength * (decay_rate ** months_elapsed)
                new_strength = max(0.0, min(1.0, new_strength))
            else:
                # 刚访问过，不衰减
                new_strength = props.get('strength', 1.0)
        except (ValueError, TypeError) as e:
            # last_accessed 格式错误，静默跳过衰减
            new_strength = props.get('strength', 1.0)
    else:
        # 首次访问，strength 保持不变（已在创建时初始化为 1.0）
        new_strength = props.get('strength', 1.0)

    props['strength'] = new_strength
    props['last_accessed'] = now

    # 更新实体
    update_operation = {
        "op": "update",
        "entity": {
            "id": entity_id,
            "properties": {
                "strength": new_strength,
                "last_accessed": now
            },
            "updated": now
        },
        "timestamp": now
    }

    # 追加到 graph.jsonl（带文件锁）
    _write_to_graph(json.dumps(update_operation, ensure_ascii=False) + '\n')

    return new_strength


def mark_entity_consolidated(entity_id: str, skillcard_id: str) -> bool:
    """标记实体已被合并到 SkillCard

    使用 op: update 模式标记原始实体，这样在后续的 Consolidation Cycle 中
    不会再次被考虑合并。

    Args:
        entity_id: 被合并的原始实体 ID
        skillcard_id: 合并后生成的 SkillCard ID

    Returns:
        成功返回 True，失败返回 False
    """
    entity = get_entity(entity_id)
    if not entity:
        print(f"Warning: Entity {entity_id} not found for consolidation marking")
        return False

    now = datetime.now().astimezone().isoformat()

    # 使用 op: update 模式标记实体已被合并
    update_op = {
        "op": "update",
        "entity": {
            "id": entity_id,
            "properties": {"consolidated_into": skillcard_id},
            "updated": now
        },
        "timestamp": now
    }

    _write_to_graph(json.dumps(update_op, ensure_ascii=False) + '\n')
    return True


def apply_decay_to_entity(entity_id: str, days_elapsed: float) -> Optional[float]:
    """对实体应用衰减

    根据经过的时间和实体类型的衰减率计算新的 strength 值

    Args:
        entity_id: 实体 ID
        days_elapsed: 经过的天数

    Returns:
        新的 strength 值，如果实体不存在返回 None
    """
    # 使用 _read_entity_from_graph 避免递归调用 get_entity
    entity = _read_entity_from_graph(entity_id)
    if not entity:
        return None

    props = entity['properties']
    decay_rate = props.get('decay_rate', 0.95)

    # 计算衰减：strength *= decay_rate^(days_elapsed/30)
    # 假设 decay_rate 是每月的衰减率
    old_strength = props.get('strength', 1.0)
    months_elapsed = days_elapsed / 30.0
    new_strength = old_strength * (decay_rate ** months_elapsed)

    # 限制在 0-1 之间
    new_strength = max(0.0, min(1.0, new_strength))

    # 更新实体
    now = datetime.now().astimezone().isoformat()
    update_operation = {
        "op": "update",
        "entity": {
            "id": entity_id,
            "properties": {
                "strength": new_strength
            },
            "updated": now
        },
        "timestamp": now
    }

    _write_to_graph(json.dumps(update_operation, ensure_ascii=False) + '\n')

    return new_strength


def get_entities_by_strength(threshold: float = 0.1) -> List[Dict]:
    """获取 strength 低于阈值的实体列表（归档候选）

    Args:
        threshold: strength 阈值，默认 0.1

    Returns:
        strength 低于阈值的实体列表
    """
    entities = load_all_entities()
    weak_entities = []

    for entity in entities.values():
        props = entity.get('properties', {})
        strength = props.get('strength', 1.0)
        if strength < threshold:
            weak_entities.append(entity)

    return weak_entities


def get_entities_by_type(entity_type: str) -> List[Dict]:
    """获取指定类型的所有实体"""
    entities = load_all_entities()
    return [e for e in entities.values() if e['type'] == entity_type]


def get_strength_distribution() -> Dict[str, Dict]:
    """获取各类型实体的 strength 分布统计

    Returns:
        Dict[type -> {count, avg_strength, min_strength, max_strength}]
    """
    entities = load_all_entities()
    distribution = {}

    for entity in entities.values():
        entity_type = entity['type']
        props = entity.get('properties', {})
        strength = props.get('strength', 1.0)

        if entity_type not in distribution:
            distribution[entity_type] = {
                'count': 0,
                'total_strength': 0.0,
                'min_strength': 1.0,
                'max_strength': 0.0
            }

        d = distribution[entity_type]
        d['count'] += 1
        d['total_strength'] += strength
        d['min_strength'] = min(d['min_strength'], strength)
        d['max_strength'] = max(d['max_strength'], strength)

    # 计算平均值
    for d in distribution.values():
        if d['count'] > 0:
            d['avg_strength'] = d['total_strength'] / d['count']
        else:
            d['avg_strength'] = 0.0

    return distribution


def compact_graph() -> Dict[str, int]:
    """压缩 graph.jsonl — 保留每个实体的最新版本

    读取所有操作，只保留每个实体的最新版本（create 或 update），
    然后重写文件。可选的维护操作，用于减少文件大小。

    Returns:
        Dict with 'kept' (entities retained) and 'total_ops' (original operations)
    """
    import tempfile

    if not GRAPH_FILE.exists():
        return {'kept': 0, 'total_ops': 0}

    # Step 1: Load with read lock — collect entities and relations
    entities: Dict[str, Dict] = {}
    relations: List[Dict] = []
    total_ops = 0

    lock_file = GRAPH_FILE.with_suffix('.lock')
    lock_f = open(lock_file, 'a')
    try:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_SH)
        try:
            with open(GRAPH_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        op = json.loads(line)
                        total_ops += 1
                        if op.get('op') == 'create':
                            entities[op['entity']['id']] = op['entity']
                        elif op.get('op') == 'update':
                            eid = op['entity']['id']
                            if eid in entities:
                                entities[eid]['properties'].update(op['entity']['properties'])
                                entities[eid]['updated'] = op['entity'].get('updated', op.get('timestamp', ''))
                        elif op.get('op') == 'relate':
                            relations.append(op)
                    except json.JSONDecodeError:
                        continue
        finally:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
    finally:
        lock_f.close()

    if total_ops == len(entities) + len(relations):
        # No compaction needed
        return {'kept': len(entities), 'total_ops': total_ops}

    # Step 2: Write compacted version atomically
    compacted_lines = 0
    tmp_file = GRAPH_FILE.with_suffix('.jsonl.tmp')
    tmp_lock = GRAPH_FILE.with_suffix('.tmp.lock')

    tmp_lock_f = open(tmp_lock, 'a')
    try:
        fcntl.flock(tmp_lock_f.fileno(), fcntl.LOCK_EX)
        try:
            with open(tmp_file, 'w', encoding='utf-8') as f:
                for entity in entities.values():
                    op = {'op': 'create', 'entity': entity, 'timestamp': entity.get('updated', entity.get('timestamp', ''))}
                    f.write(json.dumps(op, ensure_ascii=False) + '\n')
                    compacted_lines += 1
                for rel in relations:
                    f.write(json.dumps(rel, ensure_ascii=False) + '\n')
                    compacted_lines += 1
            # Atomic rename
            tmp_file.rename(GRAPH_FILE)
        finally:
            fcntl.flock(tmp_lock_f.fileno(), fcntl.LOCK_UN)
    finally:
        tmp_lock_f.close()
        if tmp_lock.exists():
            tmp_lock.unlink()

    return {'kept': len(entities), 'total_ops': total_ops, 'compacted_to': compacted_lines}


def load_all_relations() -> List[Dict]:
    """加载所有关系（带共享锁）"""
    relations = []

    if not GRAPH_FILE.exists():
        return relations

    lock_file = GRAPH_FILE.with_suffix('.lock')
    lock_f = open(lock_file, 'a')
    try:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_SH)
        try:
            with open(GRAPH_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        operation = json.loads(line)
                        if operation['op'] == 'relate':
                            relations.append(operation)
                    except json.JSONDecodeError:
                        continue
        finally:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
    finally:
        lock_f.close()

    return relations


def query_entities(entity_type: Optional[str] = None, 
                   tags: Optional[List[str]] = None,
                   status: Optional[str] = None,
                   date_from: Optional[str] = None,
                   date_to: Optional[str] = None) -> List[Dict]:
    """查询实体"""
    entities = load_all_entities()
    results = []
    
    for entity in entities.values():
        # 类型过滤
        if entity_type and entity['type'] != entity_type:
            continue
        
        props = entity.get('properties', {})
        
        # 标签过滤
        if tags:
            entity_tags = props.get('tags', [])
            if not any(tag in entity_tags for tag in tags):
                continue
        
        # 状态过滤
        if status and props.get('status') != status:
            continue
        
        # 日期过滤
        if date_from or date_to:
            # 尝试获取时间字段
            time_field = None
            for field in ['made_at', 'discovered_at', 'learned_at', 'created_at', 'captured_at']:
                if field in props:
                    time_field = field
                    break
            
            if time_field:
                entity_time = props[time_field]
                if date_from and entity_time < date_from:
                    continue
                if date_to and entity_time > date_to:
                    continue
        
        results.append(entity)
    
    return results


def get_entity(entity_id: str, refresh_strength: bool = True) -> Optional[Dict]:
    """获取单个实体

    访问时实时衰减：如果 last_accessed 超过 ACCESS_DECAY_THRESHOLD_HOURS 小时，
    自动应用衰减计算。

    Args:
        entity_id: 实体 ID
        refresh_strength: 是否刷新 strength 并更新 last_accessed（默认 True）
    """
    entity = _read_entity_from_graph(entity_id)
    if not entity:
        return None

    if refresh_strength:
        # 访问时实时衰减
        last_accessed = entity['properties'].get('last_accessed')
        if last_accessed:
            try:
                last_dt = datetime.fromisoformat(last_accessed.replace('Z', '+00:00'))
                hours_elapsed = (datetime.now().astimezone() - last_dt).total_seconds() / 3600

                if hours_elapsed >= ACCESS_DECAY_THRESHOLD_HOURS:
                    # 超过阈值，应用衰减
                    days_elapsed = hours_elapsed / 24.0
                    apply_decay_to_entity(entity_id, days_elapsed)
                    # 重新读取以获取更新后的值
                    entity = _read_entity_from_graph(entity_id)
                else:
                    # 刚访问过，只更新时间戳
                    refresh_entity_strength(entity_id)
                    entity = _read_entity_from_graph(entity_id)
            except (ValueError, TypeError):
                # last_accessed 格式错误，静默跳过
                pass
        else:
            # 首次访问，初始化 strength
            refresh_entity_strength(entity_id)
            entity = _read_entity_from_graph(entity_id)

    return entity


def get_related_entities(entity_id: str, relation_type: Optional[str] = None) -> List[Dict]:
    """获取相关实体"""
    entities = load_all_entities()
    relations = load_all_relations()
    related = []
    
    for rel in relations:
        if rel['from'] == entity_id:
            if relation_type is None or rel['rel'] == relation_type:
                if rel['to'] in entities:
                    related.append(entities[rel['to']])
        elif rel['to'] == entity_id:
            if relation_type is None or rel['rel'] == relation_type:
                if rel['from'] in entities:
                    related.append(entities[rel['from']])
    
    return related


def validate_graph() -> List[str]:
    """验证图谱"""
    errors = []
    entities = load_all_entities()
    relations = load_all_relations()
    schema = load_schema()
    
    # 验证实体
    for entity_id, entity in entities.items():
        entity_type = entity['type']
        props = entity['properties']
        
        entity_errors = validate_entity(entity_type, props)
        for error in entity_errors:
            errors.append(f"实体 {entity_id}: {error}")
    
    # 验证关系
    for rel in relations:
        rel_type = rel['rel']
        if rel_type not in schema['relations']:
            errors.append(f"未知关系类型：{rel_type} (from: {rel['from']}, to: {rel['to']})")
    
    return errors


def export_to_markdown(output_file: Optional[Path] = None):
    """导出为 Markdown 文档"""
    entities = load_all_entities()
    relations = load_all_relations()
    
    if not output_file:
        output_file = WORKSPACE_ROOT / "memory" / "ontology-export.md"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# Agent Memory Ontology Export\n\n")
        f.write(f"*Exported at: {datetime.now().astimezone().isoformat()}*\n\n")
        
        # 按类型分组
        by_type = {}
        for entity in entities.values():
            entity_type = entity['type']
            if entity_type not in by_type:
                by_type[entity_type] = []
            by_type[entity_type].append(entity)
        
        # 输出每个类型
        for entity_type, type_entities in sorted(by_type.items()):
            f.write(f"## {entity_type} ({len(type_entities)})\n\n")
            
            for entity in sorted(type_entities, key=lambda x: x.get('created', '')):
                props = entity['properties']
                f.write(f"### {entity['id']}\n\n")
                
                # 标题
                if 'title' in props:
                    f.write(f"**标题**: {props['title']}\n\n")
                elif 'name' in props:
                    f.write(f"**名称**: {props['name']}\n\n")
                elif 'description' in props:
                    f.write(f"**描述**: {props['description']}\n\n")
                
                # 状态
                if 'status' in props:
                    f.write(f"**状态**: {props['status']}\n\n")
                
                # 时间
                for time_field in ['made_at', 'discovered_at', 'learned_at', 'created_at', 'captured_at']:
                    if time_field in props:
                        f.write(f"**时间**: {props[time_field]}\n\n")
                        break
                
                # 标签
                if 'tags' in props:
                    f.write(f"**标签**: {', '.join(props['tags'])}\n\n")
                
                # 内容/理由
                for content_field in ['rationale', 'content', 'lesson', 'description']:
                    if content_field in props:
                        f.write(f"**{content_field}**: {props[content_field]}\n\n")
                        break
                
                # 关联关系
                related = get_related_entities(entity['id'])
                if related:
                    f.write("**关联实体**:\n")
                    for rel_entity in related:
                        rel_title = rel_entity['properties'].get('title') or rel_entity['properties'].get('name') or rel_entity['id']
                        f.write(f"- {rel_entity['id']}: {rel_title}\n")
                    f.write("\n")
                
                f.write("---\n\n")
    
    print(f"✓ 导出完成：{output_file}")


def print_entity(entity: Dict, verbose: bool = False):
    """打印实体"""
    props = entity['properties']
    
    # 基本信息
    entity_id = entity['id']
    entity_type = entity['type']
    
    # 标题/名称
    title = props.get('title') or props.get('name') or props.get('description', 'N/A')
    
    print(f"\n{'='*60}")
    print(f"{entity_type}: {entity_id}")
    print(f"{'='*60}")
    print(f"标题：{title}")
    
    # 状态
    if 'status' in props:
        print(f"状态：{props['status']}")
    
    # 时间
    for time_field in ['made_at', 'discovered_at', 'learned_at', 'created_at', 'captured_at']:
        if time_field in props:
            print(f"时间：{props[time_field]}")
            break
    
    # 标签
    if 'tags' in props:
        print(f"标签：{', '.join(props['tags'])}")

    # Phase 1b: 记忆进化字段
    if 'strength' in props:
        strength = props['strength']
        bar_len = int(strength * 20)
        bar = '█' * bar_len + '░' * (20 - bar_len)
        print(f"强度：[{bar}] {strength:.0%}")
    if 'last_accessed' in props:
        print(f"最后访问：{props['last_accessed']}")
    if 'provenance' in props and props['provenance']:
        provenance_str = ', '.join(props['provenance']) if isinstance(props['provenance'], list) else props['provenance']
        print(f"来源：{provenance_str}")
    if 'source_trust' in props:
        print(f"信任度：{props['source_trust']}")

    # 详细内容
    if verbose:
        for field, value in props.items():
            if field not in ['title', 'name', 'status', 'tags'] and not field.endswith('_at'):
                if isinstance(value, str) and len(value) > 200:
                    print(f"{field}: {value[:200]}...")
                else:
                    print(f"{field}: {value}")
    
    # 关联实体
    related = get_related_entities(entity_id)
    if related:
        print(f"\n关联实体 ({len(related)}):")
        for rel_entity in related:
            rel_title = rel_entity['properties'].get('title') or rel_entity['properties'].get('name') or rel_entity['id']
            print(f"  - {rel_entity['id']}: {rel_title}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Agent Memory Ontology Manager')
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    # create 命令
    create_parser = subparsers.add_parser('create', help='创建实体')
    create_parser.add_argument('--type', required=True, help='实体类型')
    create_parser.add_argument('--props', required=True, help='属性 JSON')
    create_parser.add_argument('--id', help='实体 ID (可选，自动生成)')
    
    # relate 命令
    relate_parser = subparsers.add_parser('relate', help='创建关系')
    relate_parser.add_argument('--from', dest='from_id', required=True, help='源实体 ID')
    relate_parser.add_argument('--rel', required=True, help='关系类型')
    relate_parser.add_argument('--to', required=True, help='目标实体 ID')
    relate_parser.add_argument('--props', help='关系属性 JSON')
    
    # query 命令
    query_parser = subparsers.add_parser('query', help='查询实体')
    query_parser.add_argument('--type', help='实体类型')
    query_parser.add_argument('--tags', nargs='+', help='标签列表')
    query_parser.add_argument('--status', help='状态')
    query_parser.add_argument('--from', dest='date_from', help='起始日期')
    query_parser.add_argument('--to', dest='date_to', help='结束日期')
    query_parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    
    # get 命令
    get_parser = subparsers.add_parser('get', help='获取实体')
    get_parser.add_argument('--id', required=True, help='实体 ID')
    get_parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    
    # related 命令
    related_parser = subparsers.add_parser('related', help='获取相关实体')
    related_parser.add_argument('--id', required=True, help='实体 ID')
    related_parser.add_argument('--rel', help='关系类型')
    related_parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    
    # validate 命令
    validate_parser = subparsers.add_parser('validate', help='验证图谱')
    
    # list 命令
    list_parser = subparsers.add_parser('list', help='列出所有实体')
    list_parser.add_argument('--type', help='实体类型')
    list_parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    
    # export 命令
    export_parser = subparsers.add_parser('export', help='导出为 Markdown')
    export_parser.add_argument('--output', '-o', help='输出文件路径')
    
    # stats 命令
    stats_parser = subparsers.add_parser('stats', help='显示统计信息')

    # compact 命令
    compact_parser = subparsers.add_parser('compact', help='压缩 graph.jsonl，保留每个实体的最新版本')

    args = parser.parse_args()
    
    # 确保目录存在
    ensure_ontology_dir()
    
    if args.command == 'create':
        try:
            props = json.loads(args.props)
            entity = create_entity(args.type, props, args.id)
            print(f"✓ 创建实体成功：{entity['id']}")
            print_entity(entity, verbose=True)
        except Exception as e:
            print(f"✗ 创建失败：{e}", file=sys.stderr)
            sys.exit(1)
    
    elif args.command == 'relate':
        try:
            props = json.loads(args.props) if args.props else None
            relation = create_relation(args.from_id, args.rel, args.to, props)
            print(f"✓ 创建关系成功：{args.from_id} --[{args.rel}]--> {args.to}")
        except Exception as e:
            print(f"✗ 创建关系失败：{e}", file=sys.stderr)
            sys.exit(1)
    
    elif args.command == 'query':
        results = query_entities(
            entity_type=args.type,
            tags=args.tags,
            status=args.status,
            date_from=args.date_from,
            date_to=args.date_to
        )
        print(f"找到 {len(results)} 个实体:\n")
        for entity in results:
            print_entity(entity, verbose=args.verbose)
    
    elif args.command == 'get':
        entity = get_entity(args.id)
        if entity:
            print_entity(entity, verbose=args.verbose)
        else:
            print(f"✗ 实体不存在：{args.id}", file=sys.stderr)
            sys.exit(1)
    
    elif args.command == 'related':
        related = get_related_entities(args.id, args.rel)
        print(f"找到 {len(related)} 个相关实体:\n")
        for entity in related:
            print_entity(entity, verbose=args.verbose)
    
    elif args.command == 'validate':
        errors = validate_graph()
        if errors:
            print(f"✗ 验证失败，发现 {len(errors)} 个错误:\n")
            for error in errors:
                print(f"  - {error}")
            sys.exit(1)
        else:
            print("✓ 图谱验证通过")
    
    elif args.command == 'list':
        entities = load_all_entities()
        if args.type:
            entities = {k: v for k, v in entities.items() if v['type'] == args.type}
        
        print(f"共 {len(entities)} 个实体:\n")
        for entity in entities.values():
            print_entity(entity, verbose=args.verbose)
    
    elif args.command == 'export':
        export_to_markdown(Path(args.output) if args.output else None)
    
    elif args.command == 'stats':
        entities = load_all_entities()
        relations = load_all_relations()

        # 按类型统计
        by_type = {}
        for entity in entities.values():
            entity_type = entity['type']
            by_type[entity_type] = by_type.get(entity_type, 0) + 1

        print(f"\n📊 Agent Memory Ontology 统计\n")
        print(f"实体总数：{len(entities)}")
        print(f"关系总数：{len(relations)}")
        print(f"\n按类型分布:")
        for entity_type, count in sorted(by_type.items(), key=lambda x: -x[1]):
            print(f"  {entity_type}: {count}")

        # Phase 1b: Strength 分布
        print(f"\n📈 记忆强度分布 (Phase 1b):")
        strength_dist = get_strength_distribution()
        for entity_type, stats in sorted(strength_dist.items()):
            avg = stats.get('avg_strength', 0)
            bar_len = int(avg * 20)
            bar = '█' * bar_len + '░' * (20 - bar_len)
            print(f"  {entity_type}: [{bar}] {avg:.0%}")

        # 衰减候选
        weak_entities = get_entities_by_strength(DECAY_THRESHOLD)
        if weak_entities:
            print(f"\n🗑️ 衰减候选 (strength < {DECAY_THRESHOLD}): {len(weak_entities)} 个")
            for entity in weak_entities[:5]:
                props = entity['properties']
                title = props.get('title', entity['id'])
                strength = props.get('strength', 0)
                print(f"  - {entity['id']}: {title} (strength={strength:.2f})")
            if len(weak_entities) > 5:
                print(f"  ... 还有 {len(weak_entities) - 5} 个")

        # 最近创建的实体
        print(f"\n最近创建的实体:")
        sorted_entities = sorted(entities.values(), key=lambda x: x.get('created', ''), reverse=True)[:5]
        for entity in sorted_entities:
            props = entity['properties']
            title = props.get('title') or props.get('name') or entity['id']
            print(f"  - {entity['id']}: {title} ({entity['type']})")

    elif args.command == 'compact':
        result = compact_graph()
        kept = result.get('kept', 0)
        total = result.get('total_ops', 0)
        compacted = result.get('compacted_to', kept)
        if compacted == total:
            print(f"✓ 图谱已是最优状态，无需压缩 ({kept} 个实体)")
        else:
            print(f"✓ 图谱压缩完成: {total} → {compacted} 行 (保留 {kept} 个实体最新版本)")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
