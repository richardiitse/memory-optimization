# Changelog

All notable changes to this project are documented in this file.

## [1.0.2] - 2026-03-27

### Added

- **Entity Deduplication Engine (Phase 2)**: Embedding-based duplicate detection and merging using cosine similarity. Keeps earliest timestamp as canonical entity, accumulates `frequency` property across duplicates, chain merge flattening (e3→e2→e1 → e3→e1), 24h embedding cache to avoid repeated API calls.

### Changed

- **KG_DIR environment variable support**: `memory_dashboard.py` now supports `KG_DIR` env var with path traversal validation.

## [1.0.1] - 2026-03-23

### Added

- **Memory Health Dashboard (Phase 7)**: CLI dashboard visualizing complete memory system state — Health Score (A-F), strength histogram, consolidation progress, storage stats, decay forecast, age distribution.

### Fixed

- LLM returns `None` without fallback causing silent failures.

## [1.0.0] - 2026-03-22

### Added

- **KG Schema Enhancement (Phase 1b)**: Added `strength`, `decay_rate`, `provenance` fields to KG entities for Decay Engine and Memory Health Dashboard support.
- **Preference Engine (Phase 2)**: User preference inference from conversation history and KG entities.
- **LLMClient Consolidation**: Refactored duplicate `LLMClient` implementations into `scripts/utils/llm_client.py` with unified `call()`, `call_with_retry()`, and new `embed()` methods.
- **Memory Loader (Phase 6)**: Proactive memory recovery with 3-stage staged loading — Stage 1 (core identity at startup), Stage 2 (episodic memory on demand), Stage 3 (semantic memory with proactive hints).
- **Working Memory (Phase 5)**: Context Window layered compression — 3 levels (完整/摘要/关键事实) for managing context overflow.
- **Consolidation Engine (Phase 3)**: Semantic memory consolidation — merges similar Episode patterns into SkillCards.
- **Decay Engine**: Batch decay engine for memory strength management with 30-day decay forecast.
- **Knowledge Graph Management Tool**: Full CLI for creating, querying, relating, validating KG entities.
- **KG Extractor**: LLM-driven entity extraction from agent session logs.
- **TL;DR Summary System**: 30-second context recovery at top of daily logs.
- **Three-File Pattern**: Structured project tracking (task_plan/findings/progress).
- **Fixed Tags System**: Grep-able tags (#memory, #decision, #improvement, #daily-log, #learning).
- **Daily Cleanup Script**: 3-minute automated memory maintenance.
- **Testing Framework**: 6 automated tests for memory system health.
