# Dependencies & External Services

## Python Packages

| Package | Purpose | Used By |
|---------|---------|---------|
| PyYAML | Schema parsing | memory_ontology.py |
| requests | HTTP client for LLM API | llm_client.py |
| (stdlib) fcntl | File locking (Linux/macOS) | memory_ontology.py |

## External APIs

| Service | Endpoint | Purpose |
|---------|----------|---------|
| GLM API (BigModel) | `https://open.bigmodel.cn/api/paas/v4` | LLM chat completions |
| Ollama (local) | `http://localhost:11434/api` | Embeddings (qwen3-embedding) |

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENAI_API_KEY` | - | API authentication |
| `OPENAI_MODEL` | `glm-5` | Chat completion model |
| `OPENAI_BASE_URL` | `https://open.bigmodel.cn/api/paas/v4` | API base URL |
| `OPENAI_EMBED_MODEL` | `qwen3-embedding` | Embedding model |
| `OPENAI_EMBED_BASE_URL` | `http://localhost:11434/api` | Embedding endpoint |
| `KG_DIR` | `ontology/` | KG storage path |

## File Dependencies

| File | Depends On | Purpose |
|------|------------|---------|
| kg_extractor.py | memory_ontology.py, llm_client.py | Entity extraction |
| consolidation_engine.py | memory_ontology.py, llm_client.py | SkillCard merging |
| write_time_gating.py | memory_ontology.py, llm_client.py | Gating decisions |
| decay_engine.py | memory_ontology.py | Strength decay |
| entity_dedup.py | memory_ontology.py, llm_client.py | Deduplication |

## Shared Utilities

| Module | Purpose |
|--------|---------|
| scripts/utils/llm_client.py | Unified LLM + embedding client |
| scripts/utils/__init__.py | Package init |

## Data Flow to External Services

```
Agent Session JSONL
        ↓
kg_extractor.py
        ↓ (LLM call)
GLM API → chat/completions → Extracted entities
        ↓
write_time_gating.py
        ↓ (embedding call if cache miss)
Ollama → /api/embeddings → Significance scores
        ↓
graph.jsonl (KG)
```

<!-- Generated: 2026-04-02 | External deps: 2 APIs, 1 local service | Token estimate: ~300 -->
