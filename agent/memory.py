"""Správa dlouhodobé paměti konverzace pomocí SQLite."""

import sqlite3
from contextlib import closing
from pathlib import Path

from config import DATABASE_PATH, MAX_HISTORY_MESSAGES


class AgentMemory:
    """Jednoduchá dlouhodobá paměť konverzace."""

    def __init__(self, database_path: Path = DATABASE_PATH) -> None:
        self.database_path = database_path
        self._initialize_database()

    def _connect(self) -> sqlite3.Connection:
        """Vytvoří nové databázové spojení."""
        return sqlite3.connect(self.database_path)

    def _initialize_database(self) -> None:
        """Vytvoří tabulku historie, pokud ještě neexistuje."""

        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS conversation (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )

    def save_message(self, role: str, content: str) -> None:
        """Uloží zprávu do databáze."""

        if role not in {"user", "assistant"}:
            raise ValueError("Nepovolená role zprávy.")

        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO conversation (role, content)
                    VALUES (?, ?)
                    """,
                    (role, content),
                )

    def get_history(self) -> list[dict[str, str]]:
        """Načte poslední zprávy v chronologickém pořadí."""

        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT role, content
                FROM conversation
                ORDER BY id DESC
                LIMIT ?
                """,
                (MAX_HISTORY_MESSAGES,),
            ).fetchall()

        rows.reverse()

        return [
            {"role": role, "content": content}
            for role, content in rows
        ]
