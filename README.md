# Memory Optimization

Comprehensive memory management system for AI agents — based on Moltbook community best practices. Addresses context compression amnesia and enables rapid context recovery (<30 seconds vs 5-10 minutes).

## Features

| Feature | Description |
|---------|-------------|
| **TL;DR Summary** | Quick recovery point at top of daily logs (50-100 tokens) |
| **Three-File Pattern** | Structured tracking: task_plan / findings / progress |
| **Knowledge Graph** | Entity relationships with strength, decay, provenance |
| **Daily Cleanup** | 3-minute automated maintenance script |
| **Memory Dashboard** | Visual health score, decay forecast, storage stats |
| **Entity Deduplication** | Embedding-based duplicate merging (cosine similarity) |
| **Memory Loader** | 3-stage proactive memory recovery at startup |

## Quick Start

```bash
# Run daily memory cleanup
./scripts/daily-cleanup.sh

# View memory health dashboard
python3 scripts/memory_dashboard.py

# Deduplicate KG entities (dry-run first)
python3 scripts/entity_dedup.py run --dry-run

# Query the knowledge graph
python3 scripts/memory_ontology.py query --tags "#memory"
```

## Requirements

- Python 3.8+
- PyYAML

## Documentation

- [SKILL.md](SKILL.md) — Full skill definition and usage guide
- [CLAUDE.md](CLAUDE.md) — Project guidance for Claude Code
- [scripts/README.md](scripts/README.md) — All scripts with usage examples
- [references/](references/) — Implementation guides and templates

## File Structure

```
memory-optimization/
├── SKILL.md                    # Skill definition
├── CLAUDE.md                   # Claude Code guidance
├── README.md                   # This file
├── VERSION                     # Current version
├── CHANGELOG.md               # Version history
├── TODOS.md                    # Project roadmap
├── scripts/
│   ├── daily-cleanup.sh       # Daily maintenance
│   ├── memory_ontology.py      # KG management CLI
│   ├── kg_extractor.py        # Session → KG extraction
│   ├── entity_dedup.py         # Embedding-based dedup
│   ├── consolidation_engine.py # Episode → SkillCard
│   ├── decay_engine.py         # Strength decay
│   ├── memory_loader.py        # Staged recovery
│   ├── memory_dashboard.py      # Health dashboard
│   └── utils/llm_client.py     # Unified LLM client
├── tests/                      # Test suite
├── ontology/                   # KG schema & templates
└── references/                 # Implementation docs
```

## Version

Current: **1.0.2** — See [CHANGELOG.md](CHANGELOG.md) for full history.
