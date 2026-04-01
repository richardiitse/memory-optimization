# Architecture Overview

## System Type
Python CLI tool / Agent Memory Skill (No web frontend)

## Core Components

```
┌─────────────────────────────────────────────────────────────────┐
│                        Agent Session                              │
│                    (Claude Code Sessions)                        │
└─────────────────────────────────────────────────────────────────┘
                                 ↓
                    ┌─────────────────────────┐
                    │    kg_extractor.py     │  Phase 1: Extract KG entities
                    │   (LLM-driven)        │    from session JSONL files
                    └──────────┬────────────┘
                               ↓
┌──────────────────────────────────────────────────────────────────┐
│                     Knowledge Graph (KG)                          │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  graph.jsonl (JSON Lines)                                │  │
│  │  Entity Types: Decision, Finding, LessonLearned,        │  │
│  │               Commitment, SkillCard, Preference,         │  │
│  │               SignificanceScore, MemorySource,             │  │
│  │               GatingPolicy, ArchivedMemory                │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                                 ↓
┌──────────────────────────────────────────────────────────────────┐
│                      Memory Engines                                │
│  ┌──────────────┐ ┌──────────────┐ ┌───────────────────────┐  │
│  │ write_time_   │ │consolidation │ │    decay_engine.py    │  │
│  │ gating.py     │ │_engine.py    │ │  (FSRS-like decay)    │  │
│  │ Phase 8:     │ │ Phase 3:     │ │  Phase 1b:           │  │
│  │ Source×      │ │ Episodes→    │ │  Strength decay       │  │
│  │ Novelty×     │ │ SkillCards   │ │                       │  │
│  │ Reliability │ │              │ │                       │  │
│  └──────────────┘ └──────────────┘ └───────────────────────┘  │
│  ┌──────────────┐ ┌──────────────┐ ┌───────────────────────┐  │
│  │entity_dedup  │ │preference_   │ │   working_memory.py  │  │
│  │.py           │ │engine.py     │ │  Phase 5:           │  │
│  │ Phase 2:     │ │ Phase 2:     │ │  Context window      │  │
│  │ Merge dup    │ │ User pref    │ │  3-level compress   │  │
│  └──────────────┘ └──────────────┘ └───────────────────────┘  │
│  ┌──────────────┐ ┌──────────────┐ ┌───────────────────────┐  │
│  │memory_loader │ │memory_      │ │archived_memory_       │  │
│  │.py           │ │dashboard.py  │ │store.py              │  │
│  │ Phase 6:     │ │ Phase 7:    │ │  Cold storage mgmt   │  │
│  │ 3-stage      │ │ Health viz   │ │  Recovery/search     │  │
│  │ recovery     │ │              │ │                      │  │
│  └──────────────┘ └──────────────┘ └───────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
Session JSONL
    ↓ kg_extractor.py
Extract entities (LLM)
    ↓ write_time_gating.py
Gate decision (STORE/ARCHIVE/REJECT)
    ↓
graph.jsonl (KG)
    ↓
┌───────────────────────────────────────┐
│  Consolidation (periodic)              │
│  Episodes → SkillCards (via LLM)      │
└───────────────────────────────────────┘
    ↓
┌───────────────────────────────────────┐
│  Decay Engine (on access/time)       │
│  Weak entities → ArchivedMemory        │
└───────────────────────────────────────┘
```

## Key Files

| File | Lines | Purpose |
|------|-------|---------|
| memory_ontology.py | 1586 | KG CRUD + CLI (entity, relation, query) |
| kg_extractor.py | 764 | LLM-driven entity extraction |
| consolidation_engine.py | ~500 | Episode→SkillCard merging |
| decay_engine.py | ~400 | Strength decay + archival |

## Phase Mapping

| Phase | Component | Status |
|-------|-----------|--------|
| Phase 1 | KG Extractor | ✅ Done |
| Phase 1b | Decay Engine | ✅ Done |
| Phase 2 | Entity Dedup + Preference | ✅ Done |
| Phase 3 | Consolidation Engine | ✅ Done |
| Phase 5 | Working Memory | ✅ Done |
| Phase 6 | Memory Loader | ✅ Done |
| Phase 7 | Memory Dashboard | ✅ Done |
| Phase 8 | Write-Time Gating | ✅ Done |
| Future | Concept-Mediated Graph | ⏳ |
| Future | Value-Aware Retrieval | ⏳ |

<!-- Generated: 2026-04-02 | Files scanned: 45 | Token estimate: ~600 -->
