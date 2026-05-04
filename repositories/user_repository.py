from clients.base import SnowflakeClientProtocol
from models.user import User


class UserRepository:
    def __init__(self, client: SnowflakeClientProtocol):
        self._client = client

    def load_active_users(self) -> list[User]:
        rows = self._client.execute_query(
            "SELECT user_id, email, full_name, brand, persona, is_active "
            "FROM users WHERE is_active = TRUE"
        )
        return [User.from_row(row) for row in rows]

    def get_user_by_id(self, user_id: str) -> User | None:
        rows = self._client.execute_query(
            "SELECT user_id, email, full_name, brand, persona, is_active "
            "FROM users WHERE user_id = %(user_id)s",
            {"user_id": user_id},
        )
        return User.from_row(rows[0]) if rows else None
