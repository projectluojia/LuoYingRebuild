from __future__ import annotations

from pathlib import Path

from luoying_bot.capabilities.knowledge_base.entities import GLOBAL_ENTITY_SPACE_ID
from scripts.import_whu_admission_data import build_admission_entities, build_search_items


def test_seed_entities_are_materialized_in_global_space(tmp_path: Path):
    seed_path = tmp_path / "entities.json"
    seed_path.write_text(
        """
        {
          "entities": [
            {
              "key": "recommended_exemption",
              "entity_type": "admission_method",
              "canonical_name": "推荐免试研究生",
              "aliases": [
                {"alias": "推免", "alias_type": "short_name", "confidence": 0.98},
                {"alias": "保研", "alias_type": "colloquial", "confidence": 0.95}
              ]
            }
          ],
          "relations": []
        }
        """,
        encoding="utf-8",
    )

    payload = build_admission_entities(
        plans=[{"major_name": "人工智能", "province": "湖北"}],
        scores=[],
        strong_foundation_scores=[],
        site_majors=[],
        seed_path=seed_path,
    )
    seed_entity = next(entity for entity in payload["entities"] if entity["canonical_name"] == "推荐免试研究生")
    generated_entity = next(entity for entity in payload["entities"] if entity["canonical_name"] == "人工智能")
    search_items = build_search_items(
        entity_payload=payload,
        plans=[],
        scores=[],
        strong_foundation_scores=[],
    )
    seed_search_item = next(item for item in search_items if item["entity_id"] == seed_entity["entity_id"])

    assert seed_entity["space_id"] == GLOBAL_ENTITY_SPACE_ID
    assert seed_search_item["space_id"] == GLOBAL_ENTITY_SPACE_ID
    assert generated_entity["space_id"] != GLOBAL_ENTITY_SPACE_ID
