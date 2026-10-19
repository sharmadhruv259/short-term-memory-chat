import sqlite3
import uuid
from pathlib import Path
from typing import Any


class Database:
    """Manage conversation history and rolling summaries in SQLite.

    Attributes:
        db_path (Path): Path to the SQLite database file.

    Functions:
        initialize: Create the required database tables.
        create_conversation: Create a new conversation.
        save_message: Persist a user or assistant message.
        get_message_by_number: Retrieve a numbered message.
        get_recent_turns: Retrieve the latest completed turns.
        get_latest_completed_turn: Get the latest fully completed turn.
        get_turns_for_summary: Retrieve turns not yet covered by a summary.
        get_summary: Retrieve the rolling conversation summary.
        update_summary: Save a new rolling summary.
        search_messages: Search the stored conversation history.
        get_next_turn_number: Get the next available turn number.
    """

    def __init__(self, db_path: str = "conversation.db") -> None:
        """Initialize the database manager.

        Args:
            db_path (str): Path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        """Create a configured SQLite connection.

        Returns:
            sqlite3.Connection: An open database connection.
        """
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        """Create the conversation and message tables."""
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    rolling_summary TEXT NOT NULL DEFAULT '',
                    summary_through_turn INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    message_number INTEGER NOT NULL,
                    turn_number INTEGER NOT NULL,
                    role TEXT NOT NULL
                        CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                    FOREIGN KEY (conversation_id)
                        REFERENCES conversations(conversation_id),

                    UNIQUE (conversation_id, message_number)
                );

                CREATE INDEX IF NOT EXISTS idx_messages_conversation_turn
                ON messages (conversation_id, turn_number);

                CREATE INDEX IF NOT EXISTS idx_messages_conversation_role
                ON messages (conversation_id, role);
                """
            )

    def create_conversation(self) -> str:
        """Create a conversation and return its identifier.

        Returns:
            str: The new conversation identifier.
        """
        conversation_id = str(uuid.uuid4())

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO conversations (conversation_id)
                VALUES (?)
                """,
                (conversation_id,),
            )

        return conversation_id

    def save_message(
        self,
        conversation_id: str,
        turn_number: int,
        role: str,
        content: str,
    ) -> int:
        """Save a message and return its conversation-wide number.

        Args:
            conversation_id (str): Conversation that owns the message.
            turn_number (int): Turn shared by the user message and reply.
            role (str): Either 'user' or 'assistant'.
            content (str): Message content.

        Returns:
            int: Sequential message number within the conversation.

        Raises:
            ValueError: If the role or turn number is invalid.
        """
        if role not in {"user", "assistant"}:
            raise ValueError("role must be 'user' or 'assistant'")

        if turn_number < 1:
            raise ValueError("turn_number must be at least 1")

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(MAX(message_number), 0) + 1
                FROM messages
                WHERE conversation_id = ?
                """,
                (conversation_id,),
            ).fetchone()

            message_number = row[0]

            connection.execute(
                """
                INSERT INTO messages (
                    conversation_id,
                    message_number,
                    turn_number,
                    role,
                    content
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    message_number,
                    turn_number,
                    role,
                    content,
                ),
            )

        return message_number

    def get_message_by_number(
        self,
        conversation_id: str,
        number: int,
        user_messages_only: bool = True,
    ) -> dict[str, Any] | None:
        """Retrieve a numbered message from the conversation.

        Args:
            conversation_id (str): Conversation to search.
            number (int): One-based message position.
            user_messages_only (bool): Count only user messages when true.

        Returns:
            dict[str, Any] | None: The message record, or None if not found.

        Raises:
            ValueError: If number is less than 1.
        """
        if number < 1:
            raise ValueError("number must be at least 1")

        role_filter = "AND role = 'user'" if user_messages_only else ""

        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT message_number, turn_number, role, content, created_at
                FROM messages
                WHERE conversation_id = ?
                {role_filter}
                ORDER BY message_number
                LIMIT 1 OFFSET ?
                """,
                (conversation_id, number - 1),
            ).fetchone()

        return dict(row) if row else None

    def get_recent_turns(
        self,
        conversation_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Retrieve the most recent completed conversation turns.

        Args:
            conversation_id (str): Conversation to retrieve.
            limit (int): Maximum number of completed turns.

        Returns:
            list[dict[str, Any]]: Messages ordered from oldest to newest.

        Raises:
            ValueError: If limit is less than 1.
        """
        if limit < 1:
            raise ValueError("limit must be at least 1")

        with self._connect() as connection:
            rows = connection.execute(
                """
                WITH completed_turns AS (
                    SELECT turn_number
                    FROM messages
                    WHERE conversation_id = ?
                    GROUP BY turn_number
                    HAVING SUM(
                        CASE WHEN role = 'user' THEN 1 ELSE 0 END
                    ) > 0
                    AND SUM(
                        CASE WHEN role = 'assistant' THEN 1 ELSE 0 END
                    ) > 0
                    ORDER BY turn_number DESC
                    LIMIT ?
                )
                SELECT message_number, turn_number, role, content, created_at
                FROM messages
                WHERE conversation_id = ?
                  AND turn_number IN (
                      SELECT turn_number FROM completed_turns
                  )
                ORDER BY turn_number, message_number
                """,
                (conversation_id, limit, conversation_id),
            ).fetchall()

        return [dict(row) for row in rows]

    def get_latest_completed_turn(self, conversation_id: str) -> int:
        """Return the latest turn containing both user and assistant messages.

        Args:
            conversation_id (str): Conversation to inspect.

        Returns:
            int: Latest completed turn number, or 0 if none exists.
        """
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT MAX(turn_number)
                FROM (
                    SELECT turn_number
                    FROM messages
                    WHERE conversation_id = ?
                    GROUP BY turn_number
                    HAVING SUM(
                        CASE WHEN role = 'user' THEN 1 ELSE 0 END
                    ) > 0
                    AND SUM(
                        CASE WHEN role = 'assistant' THEN 1 ELSE 0 END
                    ) > 0
                )
                """,
                (conversation_id,),
            ).fetchone()

        return int(row[0] or 0)

    def get_turns_for_summary(
        self,
        conversation_id: str,
        after_turn: int,
        through_turn: int,
    ) -> list[dict[str, Any]]:
        """Retrieve messages from turns not yet covered by a summary.

        Args:
            conversation_id (str): Conversation to retrieve.
            after_turn (int): Exclusive lower turn boundary.
            through_turn (int): Inclusive upper turn boundary.

        Returns:
            list[dict[str, Any]]: Messages ordered by turn and message number.

        Raises:
            ValueError: If either turn boundary is negative.
        """
        if after_turn < 0 or through_turn < 0:
            raise ValueError("Turn boundaries cannot be negative")

        if through_turn <= after_turn:
            return []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT message_number, turn_number, role, content, created_at
                FROM messages
                WHERE conversation_id = ?
                  AND turn_number > ?
                  AND turn_number <= ?
                ORDER BY turn_number, message_number
                """,
                (conversation_id, after_turn, through_turn),
            ).fetchall()

        return [dict(row) for row in rows]

    def get_summary(self, conversation_id: str) -> dict[str, Any] | None:
        """Retrieve the saved rolling summary and its coverage.

        Args:
            conversation_id (str): Conversation to retrieve.

        Returns:
            dict[str, Any] | None: Summary information, or None if absent.
        """
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT rolling_summary, summary_through_turn
                FROM conversations
                WHERE conversation_id = ?
                """,
                (conversation_id,),
            ).fetchone()

        return dict(row) if row else None

    def update_summary(
        self,
        conversation_id: str,
        summary: str,
        through_turn: int,
    ) -> None:
        """Save a rolling summary and the latest turn it covers.

        Args:
            conversation_id (str): Conversation to update.
            summary (str): Updated rolling summary.
            through_turn (int): Latest turn represented by the summary.

        Raises:
            ValueError: If through_turn is negative.
            LookupError: If the conversation does not exist.
        """
        if through_turn < 0:
            raise ValueError("through_turn cannot be negative")

        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE conversations
                SET rolling_summary = ?,
                    summary_through_turn = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE conversation_id = ?
                """,
                (summary, through_turn, conversation_id),
            )

            if cursor.rowcount == 0:
                raise LookupError(
                    f"Conversation not found: {conversation_id}"
                )

    def search_messages(
        self,
        conversation_id: str,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search message content using a case-insensitive text match.

        Args:
            conversation_id (str): Conversation to search.
            query (str): Text to look for.
            limit (int): Maximum number of matching messages.

        Returns:
            list[dict[str, Any]]: Matching messages in chronological order.

        Raises:
            ValueError: If query is empty or limit is less than 1.
        """
        if not query.strip():
            raise ValueError("query cannot be empty")

        if limit < 1:
            raise ValueError("limit must be at least 1")

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT message_number, turn_number, role, content, created_at
                FROM messages
                WHERE conversation_id = ?
                  AND instr(lower(content), lower(?)) > 0
                ORDER BY message_number
                LIMIT ?
                """,
                (conversation_id, query.strip(), limit),
            ).fetchall()

        return [dict(row) for row in rows]

    def get_next_turn_number(self, conversation_id: str) -> int:
        """Return the next available conversation turn number.

        Args:
            conversation_id (str): Conversation to inspect.

        Returns:
            int: Next turn number, starting at 1.
        """
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(MAX(turn_number), 0) + 1
                FROM messages
                WHERE conversation_id = ?
                """,
                (conversation_id,),
            ).fetchone()

        return int(row[0])
