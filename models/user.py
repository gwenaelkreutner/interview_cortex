from dataclasses import dataclass


@dataclass
class User:
    user_id: str
    email: str
    full_name: str
    brand: str
    persona: str
    is_active: bool = True

    @classmethod
    def from_row(cls, row: dict) -> "User":
        return cls(
            user_id=row["user_id"],
            email=row["email"],
            full_name=row.get("full_name", ""),
            brand=row["brand"],
            persona=row["persona"],
            is_active=row.get("is_active", True),
        )

    def as_context(self) -> dict:
        return {
            "user_id": self.user_id,
            "email": self.email,
            "full_name": self.full_name,
            "brand": self.brand,
            "persona": self.persona,
        }
