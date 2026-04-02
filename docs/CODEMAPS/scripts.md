# CLI Tools & Scripts

## Entry Points

| Script | Purpose | CLI Usage |
|--------|---------|-----------|
| memory_ontology.py | KG CRUD + management | See subcommands below |
| kg_extractor.py | Extract KG from sessions | `python3 kg_extractor.py --agents-dir agents/` |
| consolidation_engine.py | Merge to SkillCards | `python3 consolidation_engine.py run` |
| decay_engine.py | Apply decay, archive weak | `python3 decay_engine.py run` |
| entity_dedup.py | Merge duplicate entities | `python3 entity_dedup.py run` |
| preference_engine.py | Infer user preferences | `python3 preference_engine.py extract` |
| working_memory.py | Context compression | `python3 working_memory.py run --level 2` |
| memory_loader.py | Load memory at startup | `python3 memory_loader.py stage1` |
| memory_dashboard.py | Show health stats | `python3 memory_dashboard.py` |
| write_time_gating.py | Gate evaluation | `python3 write_time_gating.py gate --entity-id X` |
| archived_memory_store.py | Cold storage mgmt | `python3 archived_memory_store.py list` |
| concept_extractor.py | Extract concepts from entities | `python3 concept_extractor.py extract --dry-run` |
| concept_hierarchy.py | Concept hierarchy ops | `python3 concept_hierarchy.py subconcepts <id>` |
| concept_mediated_graph.py | Concept-based queries | `python3 concept_mediated_graph.py query --concept xxx` |

## memory_ontology.py Subcommands

```bash
# Entity operations
python3 memory_ontology.py create --type Decision --props '{"title":"..."}'
python3 memory_ontology.py get --id dec_xxx
python3 memory_ontology.py query --type Decision --tags "#memory"
python3 memory_ontology.py relate --from find_xxx --rel led_to_decision --to dec_xxx

# Management
python3 memory_ontology.py list --type Finding
python3 memory_ontology.py stats
python3 memory_ontology.py validate
python3 memory_ontology.py compact

# Phase 8: Gating
python3 memory_ontology.py gate --id dec_xxx --source kg_extractor
python3 memory_ontology.py archived --list
```

## Data Flow: Session → KG

```bash
agents/{main,altas}/sessions/*.jsonl
          ↓ (kg_extractor.py)
      LLM extraction
          ↓ (write_time_gating.py)
      Gate decision
          ↓
      graph.jsonl
          ↓
      ┌─────────────────────────────────────┐
      │  Periodic processing:                │
      │  • consolidation_engine.py           │
      │  • decay_engine.py                  │
      │  • entity_dedup.py                  │
      └─────────────────────────────────────┘
```

## Test Commands

```bash
# Run all tests
python3 -m pytest tests/ -v

# Run specific test file
python3 -m pytest tests/test_write_time_gating.py -v

# Run with coverage
python3 -m pytest tests/ --cov=scripts --cov-report=term
```

## Shell Scripts

| Script | Purpose |
|--------|---------|
| scripts/daily-cleanup.sh | 3-min daily maintenance |
| scripts/test-memory-system.sh | 6-system checks |

<!-- Generated: 2026-04-02 | Scripts: 12 Python + 2 Shell | Token estimate: ~400 -->
