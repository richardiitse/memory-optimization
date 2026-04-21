"""
AI-wiki MCP Server — metacognition-enhanced memory retrieval.

Exposes tools for Claude Code to query the knowledge graph with
bias-aware query enhancement and MMR-diversified semantic retrieval.

Transport: stdio (default for Claude Code MCP integration)

Usage:
    # In .claude/settings.json MCP servers config:
    {
      "mcpServers": {
        "memory": {
          "command": "python3",
          "args": ["scripts/ai_wiki_mcp_server.py"],
          "cwd": "/path/to/memory-optimization"
        }
      }
    }
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure scripts/ is on sys.path for sibling imports
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from mcp.server.fastmcp import FastMCP

from metacog_enhancer import MetacogEnhancer
from semantic_retriever import Entity, ScoredEntity, SemanticRetriever
from utils.llm_client import LLMClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_KG_PATH = PROJECT_ROOT / "ontology" / "graph.jsonl"
DEFAULT_AI_WIKI_PATH = Path(
    os.environ.get(
        "AI_WIKI_PATH",
        str(Path.home() / "Documents" / "52VisionWorld" / "projects" / "Ai-wiki"),
    )
)

# ── MCP Server ─────────────────────────────────────────────────────────

mcp = FastMCP(
    "memory",
    instructions=(
        "AI-wiki metacognition-enhanced memory server. "
        "Use search_with_metacognition to query the knowledge graph "
        "with bias-aware query expansion."
    ),
)

# Global state (initialized in _init)
_retriever: Optional[SemanticRetriever] = None
_enhancer: Optional[MetacogEnhancer] = None
_llm: Optional[LLMClient] = None


def _validate_kg_path(kg_path_str: str) -> Path:
    """Resolve KG_PATH and validate it's under an allowed directory."""
    resolved = Path(kg_path_str).resolve()
    allow_any = os.environ.get("ALLOW_ANY_KG_DIR", "").lower() in ("true", "1", "yes")

    if allow_any:
        return resolved

    allowed_roots = list({PROJECT_ROOT, _SCRIPT_DIR.parent.resolve()})

    for root in allowed_roots:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue

    raise ValueError(
        f"KG_PATH {resolved} is outside allowed directories. "
        f"Set ALLOW_ANY_KG_DIR=true to bypass."
    )


def _init() -> None:
    global _retriever, _enhancer, _llm

    _llm = LLMClient()

    # SemanticRetriever
    kg_path_str = os.environ.get("KG_PATH", str(DEFAULT_KG_PATH))
    try:
        kg_path = _validate_kg_path(kg_path_str)
        _retriever = SemanticRetriever(
            kg_path=str(kg_path),
            llm_client=_llm,
            alpha=0.6,
            tau_days=30,
        )
        logger.info(
            "SemanticRetriever loaded %d entities", len(_retriever.entities)
        )
    except Exception as exc:
        logger.error("Failed to initialize SemanticRetriever: %s", exc)
        _retriever = None

    # MetacogEnhancer
    try:
        _enhancer = MetacogEnhancer(str(DEFAULT_AI_WIKI_PATH))
        logger.info("MetacogEnhancer loaded %d context files", len(_enhancer.context))
    except Exception as exc:
        logger.error("Failed to initialize MetacogEnhancer: %s", exc)
        _enhancer = None


# ── Tools ──────────────────────────────────────────────────────────────


@mcp.tool()
def search_with_metacognition(query: str, top_k: int = 10) -> str:
    """Search the knowledge graph with metacognitive query enhancement.

    The query is first enhanced with challenge questions based on known
    cognitive biases, then used for semantic retrieval with MMR diversification.

    Args:
        query: The search query.
        top_k: Number of results to return (default 10, max 100).

    Returns:
        JSON with original_query, enhanced_query, matched_biases, and results.
    """
    top_k = max(1, min(top_k, 100))
    if not _retriever:
        return json.dumps({"error": "Server not initialized: retriever unavailable"})

    if _enhancer:
        enhancement = _enhancer.enhance(query)
        search_query = enhancement.enhanced_query
        matched_biases = enhancement.matched_biases
        challenge_questions = enhancement.challenge_questions
    else:
        search_query = query
        matched_biases = []
        challenge_questions = []

    results = _retriever.search(
        search_query, top_k=top_k, mmr_lambda=0.7,
    )

    out_results = []
    for sr in results:
        out_results.append({
            "id": sr.entity.id,
            "name": sr.entity.name,
            "type": sr.entity.type,
            "description": sr.entity.description[:200],
            "tags": sr.entity.tags,
            "scores": {
                "hybrid": round(sr.hybrid_score, 4),
                "semantic": round(sr.semantic_score, 4),
                "temporal": round(sr.temporal_score, 4),
            },
        })

    return json.dumps({
        "original_query": query,
        "enhanced_query": search_query,
        "matched_biases": matched_biases,
        "challenge_questions": challenge_questions,
        "results": out_results,
        "total_entities": len(_retriever.entities),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def get_entity_details(entity_id: str) -> str:
    """Get full details of a specific entity by ID.

    Args:
        entity_id: The entity ID (e.g. 'concept_8e8f966c').

    Returns:
        JSON with entity details, or error if not found.
    """
    if not _retriever:
        return json.dumps({"error": "Server not initialized"})

    for entity in _retriever.entities:
        if entity.id == entity_id:
            return json.dumps({
                "id": entity.id,
                "type": entity.type,
                "name": entity.name,
                "description": entity.description,
                "tags": entity.tags,
                "created_at": entity.created_at,
                "properties": {
                    k: v for k, v in entity.properties.items()
                    if k not in ("name", "description", "tags")
                },
            }, ensure_ascii=False, indent=2)

    return json.dumps({"error": f"Entity '{entity_id[:64]}' not found"})


@mcp.tool()
def get_related_entities(entity_id: str) -> str:
    """Get entities related to the given entity via KG relations.

    Args:
        entity_id: The entity ID to find relations for.

    Returns:
        JSON list of related entities with relation types.
    """
    if not _retriever:
        return json.dumps({"error": "Server not initialized"})

    related = _retriever.get_related(entity_id)
    out = []
    for e in related:
        out.append({
            "id": e.id,
            "name": e.name,
            "type": e.type,
            "description": e.description[:100],
        })

    return json.dumps({
        "entity_id": entity_id,
        "related_count": len(out),
        "related": out,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def reload_metacog_context() -> str:
    """Reload AI-wiki metacognitive context files.

    Use after editing AI-wiki self-layer files to pick up changes.

    Returns:
        JSON with count of files reloaded.
    """
    if not _enhancer:
        return json.dumps({"error": "Server not initialized"})

    count = _enhancer.reload(str(DEFAULT_AI_WIKI_PATH))
    return json.dumps({
        "status": "ok",
        "context_files_reloaded": count,
        "context_keys": list(_enhancer.context.keys()),
    })


@mcp.tool()
def memory_stats() -> str:
    """Get memory server statistics.

    Returns:
        JSON with entity counts, embedding status, cache info.
    """
    result: Dict[str, Any] = {}
    if _retriever:
        result["retriever"] = _retriever.stats()
    if _enhancer:
        result["enhancer"] = {
            "context_files": len(_enhancer.context),
            "bias_patterns": len(_enhancer.biases),
        }
    if not result:
        return json.dumps({"error": "Server not initialized"})
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def embed_all_entities() -> str:
    """Pre-compute embeddings for all KG entities.

    Call once after server startup for warm-cache retrieval.
    May take a few minutes for large KGs.

    Returns:
        JSON with count of newly embedded entities.
    """
    if not _retriever:
        return json.dumps({"error": "Server not initialized"})

    count = _retriever.embed_entities()
    return json.dumps({
        "status": "ok",
        "newly_embedded": count,
        "total_entities": len(_retriever.entities),
        "stats": _retriever.stats(),
    })


# ── Main ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="AI-wiki MCP Memory Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    parser.add_argument("--port", type=int, default=8765, help="HTTP port")
    args = parser.parse_args()

    _init()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.settings.host = "127.0.0.1"
        mcp.settings.port = args.port
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
