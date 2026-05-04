from dataclasses import dataclass

from models.user import User


@dataclass
class BrandPersonaMapping:
    mapping_id: str
    brand: str
    persona: str
    question_template: str
    is_active: bool = True

    @classmethod
    def from_row(cls, row: dict) -> "BrandPersonaMapping":
        return cls(
            mapping_id=row["mapping_id"],
            brand=row["brand"],
            persona=row["persona"],
            question_template=row["question_template"],
            is_active=row.get("is_active", True),
        )

    def render_question(self, user: User) -> str:
        safe_values = {
            "user_name": user.full_name,
            "brand": user.brand,
            "persona": user.persona,
        }
        return self.question_template.format_map(safe_values)
