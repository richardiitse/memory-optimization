# Data Model

## Storage Format
**JSON Lines** (`ontology/graph.jsonl`)
- One JSON object per line (append-only log)
- Entities stored as `{op, entity, timestamp}`
- Relations stored as `{op, from, rel, to, properties, timestamp}`

## Entity Types

### Core Memory Entities

| Type | Prefix | Key Fields | Decay Rate |
|------|--------|-------------|------------|
| Decision | `dec_` | title, rationale, made_at, status, confidence | 0.95/mo |
| Finding | `find_` | title, content, discovered_at, type, confidence | 0.80/mo |
| LessonLearned | `lesson_` | title, lesson, learned_at, mistake_or_success | 0.90/mo |
| Commitment | `commit_` | description, source, created_at, status, due_date | 0.85/mo |
| ContextSnapshot | `snapshot_` | title, captured_at, content_summary, session_id | 0.75/mo |

### Skill Entities

| Type | Prefix | Key Fields |
|------|--------|------------|
| SkillCard | `skc_` | title, summary, source_episodes, consolidated_at |
| Preference | `pref_` | title, pattern, preference_type, learned_at |
| ConflictReview | `conf_` | entity1_id, entity2_id, conflict_type, status |

### Phase 8: Gating Entities

| Type | Prefix | Key Fields |
|------|--------|------------|
| SignificanceScore | `sig_` | entity_id, total_score, breakdown{source/novelty/reliability} |
| MemorySource | `src_` | source_type, reliability, use_count, accuracy_history |
| GatingPolicy | `gate_` | threshold(0.5), auto_archive_below(0.3), weights |
| ArchivedMemory | `arch_` | original_id, archived_reason, cold_storage_path |

### Phase 4: Concept Entities

| Type | Prefix | Key Fields |
|------|--------|------------|
| Concept | `concept_` | name, description, related_concepts, instance_count |

## Concept Relations

| Relation | Description |
|----------|-------------|
| `is_a` | Hierarchical (parent-child) |
| `part_of` | Part-whole relationship |
| `synonym_of` | Equivalent concepts |
| `instance_of` | Entity to concept link |

## Common Fields (all entities)

```yaml
strength: float        # 0.0-1.0, default 1.0
decay_rate: float      # per month
last_accessed: str     # ISO 8601
provenance: array     # ['session:xxx', 'inference:yyy']
source_trust: enum    # high/medium/low
# Phase 8:
significance_score: float  # 0.0-1.0, default 0.5
source_id: str              # MemorySource reference
is_archived: bool           # default false
superseded_by: str|null    # version chain support
```

## Schema Files

| File | Purpose |
|------|---------|
| ontology/memory-schema.yaml | Entity definitions (primary) |
| ontology/schema.yaml | Base schema (supplemental) |

## Graph Operations

| Operation | Format |
|----------|--------|
| Create | `{op:"create", entity:{id,type,properties}, timestamp}` |
| Update | `{op:"update", entity:{id,properties}, timestamp}` |
| Relate | `{op:"relate", from, rel, to, properties, timestamp}` |

## Index Files

| File | Purpose |
|------|---------|
| `ontology/gating_embed_cache.jsonl` | Embedding cache (24h TTL) |
| `ontology/cold-storage/*.json` | Archived entity backups |

<!-- Generated: 2026-04-02 | Files scanned: 2 schema files | Token estimate: ~450 -->
