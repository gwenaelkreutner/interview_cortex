from clients.base import SnowflakeClientProtocol
from models.mapping import BrandPersonaMapping


class MappingRepository:
    def __init__(self, client: SnowflakeClientProtocol):
        self._client = client

    def resolve_question(self, brand: str, persona: str) -> BrandPersonaMapping | None:
        rows = self._client.execute_query(
            """
            SELECT mapping_id, brand, persona, question_template, is_active
            FROM brand_persona_mappings
            WHERE brand = %(brand)s AND persona = %(persona)s AND is_active = TRUE
            """,
            {"brand": brand, "persona": persona},
        )
        return BrandPersonaMapping.from_row(rows[0]) if rows else None
