"""
SemanticRetriever — hybrid scoring + MMR diversification over KG entities.

Loads entities from graph.jsonl, computes hybrid relevance scores
(semantic similarity + temporal proximity), and diversifies results
using Maximal Marginal Relevance (MMR).
"""

import hashlib
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils import cosine_similarity
from utils.llm_client import LLMClient

logger = logging.getLogger(__name__)

MAX_ENTITY_TEXT_BYTES = 100_000  # 100KB safety limit per entity text


@dataclass
class Entity:
    id: str
    type: str
    name: str
    description: str
    tags: List[str] = field(default_factory=list)
    created_at: Optional[str] = None
    properties: Dict = field(default_factory=dict)
    embedding: Optional[List[float]] = None


@dataclass
class ScoredEntity:
    entity: Entity
    hybrid_score: float
    semantic_score: float
    temporal_score: float


def _cache_key(model: str, base_url: str, text: str) -> str:
    text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
    return f"{model}:{base_url}:{text_hash[:32]}"


class SemanticRetriever:
    """Semantic retrieval over KG entities with hybrid scoring and MMR."""

    def __init__(
        self,
        kg_path: str,
        llm_client: LLMClient,
        embedding_cache: Optional[Dict[str, List[float]]] = None,
        alpha: float = 0.6,
        tau_days: int = 30,
    ):
        self.kg_path = Path(kg_path)
        self.llm = llm_client
        self.alpha = alpha
        self.tau_days = tau_days
        self._cache = embedding_cache if embedding_cache is not None else {}
        self.entities: List[Entity] = []
        self._load_entities()

    # ========== Entity Loading ==========

    def _load_entities(self) -> None:
        self.entities = []
        self._relations: List[Dict] = []
        if not self.kg_path.exists():
            logger.warning("KG file not found: %s", self.kg_path)
            return

        skipped = 0
        relations: List[Dict] = []
        with open(self.kg_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    skipped += 1
                    continue

                op = data.get("op")
                if op == "create":
                    entity = self._parse_entity(data)
                    if entity:
                        self.entities.append(entity)
                elif op == "relate":
                    relations.append(data)
                elif op == "merge_into":
                    self._apply_merge(data)

        self._relations = relations
        if skipped:
            logger.warning("Skipped %d corrupt JSONL lines", skipped)
        logger.info(
            "Loaded %d entities, %d relations from %s",
            len(self.entities), len(relations), self.kg_path,
        )

    @staticmethod
    def _parse_entity(data: Dict) -> Optional[Entity]:
        raw = data.get("entity", {})
        if not raw or "id" not in raw:
            return None
        props = raw.get("properties", {})
        return Entity(
            id=raw["id"],
            type=raw.get("type", "Unknown"),
            name=props.get("name", ""),
            description=props.get("description", ""),
            tags=props.get("tags", []),
            created_at=raw.get("created") or raw.get("timestamp"),
            properties=props,
        )

    def _apply_merge(self, data: Dict) -> None:
        source_id = data.get("source")
        target_id = data.get("target")
        if not source_id or not target_id:
            return
        # Remove source entity if it exists
        self.entities = [e for e in self.entities if e.id != source_id]

    # ========== Search ==========

    def search(
        self,
        query: str,
        top_k: int = 10,
        mmr_lambda: float = 0.7,
    ) -> List[ScoredEntity]:
        query_vec = self.get_embedding(query)
        if query_vec is None:
            logger.error("Failed to embed query, returning empty results")
            return []

        # Score all entities with embeddings
        scored: List[ScoredEntity] = []
        for entity in self.entities:
            if entity.embedding is None:
                continue
            sem = cosine_similarity(query_vec, entity.embedding)
            temp = self._temporal_score(entity)
            hybrid = self.alpha * sem + (1 - self.alpha) * temp
            scored.append(ScoredEntity(
                entity=entity,
                hybrid_score=hybrid,
                semantic_score=sem,
                temporal_score=temp,
            ))

        if not scored:
            return []

        scored.sort(key=lambda s: s.hybrid_score, reverse=True)

        # MMR diversification over top candidate pool
        pool = scored[:top_k * 3]  # over-select pool
        return self._mmr_diversify(pool, query_vec, mmr_lambda, top_k)

    def _mmr_diversify(
        self,
        candidates: List[ScoredEntity],
        query_vec: List[float],
        lambda_param: float,
        k: int,
    ) -> List[ScoredEntity]:
        selected: List[ScoredEntity] = []
        selected_embeddings: List[List[float]] = []
        remaining_indices = set(range(len(candidates)))

        while len(selected) < k and remaining_indices:
            best_idx = self._mmr_select_next_idx(
                candidates, remaining_indices, selected_embeddings, lambda_param,
            )
            if best_idx is None:
                break
            best = candidates[best_idx]
            selected.append(best)
            if best.entity.embedding:
                selected_embeddings.append(best.entity.embedding)
            remaining_indices.discard(best_idx)

        return selected

    def _mmr_select_next_idx(
        self,
        candidates: List[ScoredEntity],
        remaining_indices: set,
        selected_embeddings: List[List[float]],
        lambda_param: float,
    ) -> Optional[int]:
        best_score = -math.inf
        best_idx = None

        for idx in remaining_indices:
            candidate = candidates[idx]
            if candidate.entity.embedding is None:
                continue
            if not selected_embeddings:
                mmr = candidate.hybrid_score
            else:
                max_sim = max(
                    cosine_similarity(candidate.entity.embedding, sel_emb)
                    for sel_emb in selected_embeddings
                )
                mmr = (
                    lambda_param * candidate.hybrid_score
                    - (1 - lambda_param) * max_sim
                )

            if mmr > best_score:
                best_score = mmr
                best_idx = idx

        return best_idx

    # ========== Related Entities ==========

    def get_related(self, entity_id: str) -> List[Entity]:
        related_ids = set()
        for rel in self._relations:
            if rel.get("from") == entity_id:
                related_ids.add(rel.get("to"))
            elif rel.get("to") == entity_id:
                related_ids.add(rel.get("from"))

        id_to_entity = {e.id: e for e in self.entities}
        return [id_to_entity[rid] for rid in related_ids if rid in id_to_entity]

    # ========== Embedding ==========

    def get_embedding(self, text: str) -> Optional[List[float]]:
        if len(text.encode('utf-8')) > MAX_ENTITY_TEXT_BYTES:
            logger.warning("Text exceeds %d bytes, truncating", MAX_ENTITY_TEXT_BYTES)
            # Binary search for the longest prefix within byte limit
            lo, hi = 0, len(text)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if len(text[:mid].encode('utf-8')) <= MAX_ENTITY_TEXT_BYTES:
                    lo = mid
                else:
                    hi = mid - 1
            text = text[:lo]
        key = _cache_key(self.llm.embed_model, self.llm.embed_base_url, text)
        if key in self._cache:
            return self._cache[key]
        vec = self.llm.embed(text)
        if vec is not None:
            self._cache[key] = vec
        return vec

    def embed_entities(self) -> int:
        """Pre-compute embeddings for all entities. Returns count newly embedded."""
        to_embed = []
        for e in self.entities:
            text = f"{e.name} {e.description}"
            key = _cache_key(self.llm.embed_model, self.llm.embed_base_url, text)
            if key in self._cache:
                e.embedding = self._cache[key]
            elif e.embedding is None:
                to_embed.append((e, text))

        if not to_embed:
            return 0

        texts = [t for _, t in to_embed]
        vectors = self.llm.embed_batch(texts, max_workers=8)

        count = 0
        for (entity, text), vec in zip(to_embed, vectors):
            if vec is not None:
                entity.embedding = vec
                key = _cache_key(self.llm.embed_model, self.llm.embed_base_url, text)
                self._cache[key] = vec
                count += 1

        return count

    # ========== Temporal Scoring ==========

    def _temporal_score(self, entity: Entity) -> float:
        if not entity.created_at:
            return 0.5
        try:
            created = datetime.fromisoformat(entity.created_at)
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            days_ago = max(0, (now - created).total_seconds() / 86400)
            return math.exp(-days_ago / self.tau_days)
        except (ValueError, TypeError):
            return 0.5

    # ========== Stats ==========

    def stats(self) -> Dict[str, Any]:
        types: Dict[str, int] = {}
        with_embedding = 0
        with_date = 0
        for e in self.entities:
            types[e.type] = types.get(e.type, 0) + 1
            if e.embedding is not None:
                with_embedding += 1
            if e.created_at:
                with_date += 1
        return {
            "total": len(self.entities),
            "by_type": types,
            "with_embedding": with_embedding,
            "with_date": with_date,
            "cache_size": len(self._cache),
        }
