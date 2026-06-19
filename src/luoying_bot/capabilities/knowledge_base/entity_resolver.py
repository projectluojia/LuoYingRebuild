from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from luoying_bot.capabilities.knowledge_base.entities import EntityMatch, normalize_entity_text, parse_metadata
from luoying_bot.capabilities.knowledge_base.models import KnowledgeQuery
from luoying_bot.capabilities.knowledge_base.ports import EntityBackend


@dataclass(frozen=True, slots=True)
class EntityResolution:
    matches: tuple[EntityMatch, ...]

    @property
    def has_matches(self) -> bool:
        return bool(self.matches)

    def prompt_context(self) -> str:
        if not self.matches:
            return "无"
        return "\n".join(f"- {match.prompt_line()}" for match in self.matches)

    def by_type(self, entity_type: str) -> tuple[EntityMatch, ...]:
        return tuple(match for match in self.matches if match.entity_type == entity_type)

    def fact_entities(self) -> tuple[EntityMatch, ...]:
        return tuple(
            match
            for match in self.matches
            if match.metadata.get("fact_table") and match.metadata.get("fact_column")
            and (match.score >= 100.0 or match.alias_type == "relation_resolution")
        )


class EntityResolver:
    def __init__(self, backend: EntityBackend, *, max_matches: int = 12):
        self.backend = backend
        self.max_matches = max_matches

    async def resolve(self, query: KnowledgeQuery) -> EntityResolution:
        rows = await self.backend.search_kb_items(
            query=query.question,
            space_id=query.space_id,
            item_types=["entity"],
            limit=self.max_matches * 6,
        )
        direct_matches = [entity_from_search_item(row, query.question) for row in rows if row.get("entity_id")]
        resolved_matches = await self._resolve_related_entities(query, direct_matches)
        return EntityResolution(matches=tuple(dedupe_matches([*direct_matches, *resolved_matches])[: self.max_matches]))

    async def _resolve_related_entities(
        self,
        query: KnowledgeQuery,
        direct_matches: list[EntityMatch],
    ) -> list[EntityMatch]:
        schools = [match for match in direct_matches if match.entity_type == "school" and match.score >= 100.0]
        program_types = [
            match for match in direct_matches if match.entity_type == "program_type" and match.score >= 100.0
        ]
        if not schools or not program_types:
            return []
        relations = await self.backend.fetch_entity_relations(
            space_id=query.space_id,
            entity_ids=[match.entity_id for match in [*schools, *program_types]],
        )
        related_by_program: dict[str, set[str]] = {}
        type_by_program: dict[str, set[str]] = {}
        relation_rows_by_program: dict[str, dict[str, Any]] = {}
        school_ids = {match.entity_id for match in schools}
        program_type_ids = {match.entity_id for match in program_types}
        for relation in relations:
            subject_id = str(relation.get("subject_entity_id") or "")
            object_id = str(relation.get("object_entity_id") or "")
            predicate = str(relation.get("predicate") or "")
            if predicate == "related_to" and object_id in school_ids:
                related_by_program.setdefault(subject_id, set()).add(object_id)
                relation_rows_by_program[subject_id] = relation
            elif predicate == "is_a" and object_id in program_type_ids:
                type_by_program.setdefault(subject_id, set()).add(object_id)
                relation_rows_by_program[subject_id] = relation
        matches: list[EntityMatch] = []
        for program_id in sorted(set(related_by_program) & set(type_by_program)):
            relation = relation_rows_by_program[program_id]
            matches.append(
                EntityMatch(
                    entity_id=program_id,
                    space_id=str(relation["space_id"]),
                    entity_type=str(relation["subject_type"]),
                    canonical_name=str(relation["subject_name"]),
                    metadata=parse_metadata(relation.get("subject_metadata")),
                    matched_alias="relation:school+program_type",
                    alias_type="relation_resolution",
                    score=140.0,
                    confidence=float(relation.get("confidence") or 1.0),
                )
            )
        return matches


def entity_from_search_item(row: dict[str, Any], query: str) -> EntityMatch:
    metadata = parse_metadata(row.get("metadata_json") or row.get("metadata") or {})
    entity_metadata = parse_metadata(metadata.get("entity_metadata") or {})
    query_norm = normalize_entity_text(query)
    aliases = [str(alias) for alias in metadata.get("aliases") or []]
    canonical_name = str(metadata.get("canonical_name") or row.get("title") or "")
    matched_alias = canonical_name
    score = float(row.get("score") or 0.0)
    for alias in [canonical_name, *aliases]:
        alias_norm = normalize_entity_text(alias)
        if alias_norm and alias_norm in query_norm:
            matched_alias = alias
            score = max(score, 100.0 + len(alias_norm))
            break
    return EntityMatch(
        entity_id=str(row["entity_id"]),
        space_id=str(row["space_id"]),
        entity_type=str(metadata.get("entity_type") or ""),
        canonical_name=canonical_name,
        description=str(metadata.get("description") or ""),
        metadata=entity_metadata,
        matched_alias=matched_alias,
        alias_type=str(metadata.get("alias_type") or "search_item"),
        score=score,
        confidence=float(metadata.get("confidence") or 1.0),
    )


def dedupe_matches(matches: list[EntityMatch]) -> list[EntityMatch]:
    best: dict[str, EntityMatch] = {}
    for match in matches:
        previous = best.get(match.entity_id)
        if previous is None or match.score > previous.score:
            best[match.entity_id] = match
    return sorted(best.values(), key=lambda item: item.score, reverse=True)
