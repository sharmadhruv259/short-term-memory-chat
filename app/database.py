
"""Manage session-based conversation history in SQLite."""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


class Database:
    """Store and retrieve session messages.

    Attributes:
        db_path (Path): SQLite database location.

    Functions:
        initialize: Initialize or migrate the database.
        create_session: Generate a new session ID.
        create_conversation: Compatibility alias for create_session.
        session_exists: Check whether a session has messages.
        save_message: Store a user or assistant message.
        get_recent_messages: Retrieve the latest messages.
        get_all_messages: Retrieve the complete session history.
        get_message_by_number: Retrieve a numbered message.
        search_messages: Search messages within a session.
        get_message_count: Count messages in a session.
    """

    def __init__(self, db_path: str = "chat_history.db") -> None:
        """Initialize the database.

        Args:
            db_path (str): SQLite database path.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        """Open a configured SQLite connection.

        Returns:
            sqlite3.Connection: Database connection.
        """
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _backup_database(self) -> Path:
        """Back up the existing SQLite database.

        Returns:
            Path: Backup file path.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_path = self.db_path.with_name(
            f"{self.db_path.stem}_backup_{timestamp}.db"
        )

        with self._connect() as source:
            with sqlite3.connect(backup_path) as destination:
                source.backup(destination)

        return backup_path

    def initialize(self) -> None:
        """Create or migrate the five-column messages table."""
        with self._connect() as connection:
            tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table'"
                ).fetchall()
            }

            columns = set()
            if "messages" in tables:
                columns = {
                    row["name"]
                    for row in connection.execute(
                        "PRAGMA table_info(messages)"
                    ).fetchall()
                }

        expected = {
            "session_id",
            "role",
            "content",
            "created_at",
            "updated_at",
        }

        legacy_tables = {
            "conversations",
            "memory_facts",
            "memory_decisions",
        }

        needs_migration = (
            ("messages" in tables and columns != expected)
            or bool(tables & legacy_tables)
        )

        if needs_migration:
            backup_path = self._backup_database()
            print(f"[Database] Backup created: {backup_path}")
            self._migrate_database(columns)

        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL
                        CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                        DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL
                        DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages (session_id)
                """
            )

    def _migrate_database(self, columns: set[str]) -> None:
        """Migrate old messages and remove obsolete tables.

        Args:
            columns (set[str]): Columns in the existing messages table.

        Raises:
            RuntimeError: If the old message schema is unsupported.
        """
        with self._connect() as connection:
            connection.execute("PRAGMA foreign_keys = OFF")

            try:
                connection.execute("BEGIN IMMEDIATE")

                connection.execute(
                    """
                    CREATE TABLE messages_new (
                        session_id TEXT NOT NULL,
                        role TEXT NOT NULL
                            CHECK (role IN ('user', 'assistant')),
                        content TEXT NOT NULL,
                        created_at TEXT NOT NULL
                            DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL
                            DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )

                if columns:
                    session_column = (
                        "session_id"
                        if "session_id" in columns
                        else "conversation_id"
                        if "conversation_id" in columns
                        else None
                    )

                    if (
                        session_column is None
                        or "role" not in columns
                        or "content" not in columns
                    ):
                        raise RuntimeError(
                            "Unsupported messages schema. "
                            "The original database was not modified."
                        )

                    created = (
                        "created_at"
                        if "created_at" in columns
                        else "CURRENT_TIMESTAMP"
                    )

                    updated = (
                        "updated_at"
                        if "updated_at" in columns
                        else created
                    )

                    ordering = (
                        "message_number"
                        if "message_number" in columns
                        else "rowid"
                    )

                    connection.execute(
                        f"""
                        INSERT INTO messages_new (
                            session_id,
                            role,
                            content,
                            created_at,
                            updated_at
                        )
                        SELECT
                            {session_column},
                            role,
                            content,
                            COALESCE({created}, CURRENT_TIMESTAMP),
                            COALESCE({updated}, CURRENT_TIMESTAMP)
                        FROM messages
                        ORDER BY {session_column}, {ordering}
                        """
                    )

                    connection.execute("DROP TABLE messages")

                connection.execute(
                    "ALTER TABLE messages_new RENAME TO messages"
                )

                for table in (
                    "memory_decisions",
                    "memory_facts",
                    "conversations",
                ):
                    connection.execute(
                        f"DROP TABLE IF EXISTS {table}"
                    )

                connection.execute("COMMIT")

            except Exception:
                connection.execute("ROLLBACK")
                raise

            finally:
                connection.execute("PRAGMA foreign_keys = ON")

    def create_session(self) -> str:
        """Generate a new session identifier.

        Returns:
            str: Unique session ID.
        """
        return str(uuid.uuid4())

    def create_conversation(self) -> str:
        """Generate a session ID using the previous API name.

        Returns:
            str: Unique session ID.
        """
        return self.create_session()

    def session_exists(self, session_id: str) -> bool:
        """Check whether a session contains stored messages.

        Args:
            session_id (str): Session identifier.

        Returns:
            bool: True if the session exists in message history.
        """
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM messages
                WHERE session_id = ?
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()

        return row is not None

    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> int:
        """Save a message and return its session position.

        Args:
            session_id (str): Active session identifier.
            role (str): User or assistant.
            content (str): Message content.

        Returns:
            int: One-based position within the session.

        Raises:
            ValueError: If input is invalid.
        """
        if not session_id.strip():
            raise ValueError("session_id cannot be empty")

        if role not in {"user", "assistant"}:
            raise ValueError("role must be 'user' or 'assistant'")

        if not content.strip():
            raise ValueError("content cannot be empty")

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO messages (session_id, role, content)
                VALUES (?, ?, ?)
                """,
                (session_id, role, content),
            )

            row = connection.execute(
                """
                SELECT COUNT(*)
                FROM messages
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()

        return int(row[0])

    def get_recent_messages(
        self,
        session_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Retrieve the latest messages in chronological order.

        Args:
            session_id (str): Session identifier.
            limit (int): Maximum number of messages.

        Returns:
            list[dict[str, Any]]: Recent messages.

        Raises:
            ValueError: If limit is invalid.
        """
        if limit < 1:
            raise ValueError("limit must be at least 1")

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT session_id, role, content,
                       created_at, updated_at
                FROM (
                    SELECT rowid, session_id, role, content,
                           created_at, updated_at
                    FROM messages
                    WHERE session_id = ?
                    ORDER BY rowid DESC
                    LIMIT ?
                )
                ORDER BY rowid ASC
                """,
                (session_id, limit),
            ).fetchall()

        return [dict(row) for row in rows]

    def get_all_messages(
        self,
        session_id: str,
    ) -> list[dict[str, Any]]:
        """Retrieve all messages belonging to a session.

        Args:
            session_id (str): Session identifier.

        Returns:
            list[dict[str, Any]]: Complete session history.
        """
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT session_id, role, content,
                       created_at, updated_at
                FROM messages
                WHERE session_id = ?
                ORDER BY rowid
                """,
                (session_id,),
            ).fetchall()

        return [dict(row) for row in rows]

    def get_message_by_number(
        self,
        session_id: str,
        number: int,
        user_messages_only: bool = True,
    ) -> dict[str, Any] | None:
        """Retrieve a numbered message within a session.

        Args:
            session_id (str): Session identifier.
            number (int): One-based message position.
            user_messages_only (bool): Count user messages only.

        Returns:
            dict[str, Any] | None: Matching message, if found.

        Raises:
            ValueError: If number is invalid.
        """
        if number < 1:
            raise ValueError("number must be at least 1")

        role_filter = (
            "AND role = 'user'"
            if user_messages_only
            else ""
        )

        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT session_id, role, content,
                       created_at, updated_at
                FROM messages
                WHERE session_id = ?
                {role_filter}
                ORDER BY rowid
                LIMIT 1 OFFSET ?
                """,
                (session_id, number - 1),
            ).fetchone()

        return dict(row) if row else None

    def search_messages(
        self,
        session_id: str,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search stored messages in one session.

        Args:
            session_id (str): Session identifier.
            query (str): Search phrase.
            limit (int): Maximum number of matches.

        Returns:
            list[dict[str, Any]]: Matching messages.

        Raises:
            ValueError: If query or limit is invalid.
        """
        if not query.strip():
            raise ValueError("query cannot be empty")

        if limit < 1:
            raise ValueError("limit must be at least 1")

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT session_id, role, content,
                       created_at, updated_at
                FROM messages
                WHERE session_id = ?
                  AND instr(lower(content), lower(?)) > 0
                ORDER BY rowid
                LIMIT ?
                """,
                (session_id, query.strip(), limit),
            ).fetchall()

        return [dict(row) for row in rows]

    def get_message_count(self, session_id: str) -> int:
        """Count stored messages in a session.

        Args:
            session_id (str): Session identifier.

        Returns:
            int: Number of messages.
        """
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*)
                FROM messages
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()

        return int(row[0])

















# import sqlite3
# import uuid
# from pathlib import Path
# from typing import Any


# class Database:
#     """Manage conversation history, summaries, and selected memories in SQLite.

#     Attributes:
#         db_path (Path): Path to the SQLite database file.

#     Functions:
#         initialize: Create the required database tables.
#         create_conversation: Create a new conversation.
#         save_message: Persist a user or assistant message.
#         get_message_by_number: Retrieve a numbered message.
#         get_recent_turns: Retrieve the latest completed turns.
#         get_latest_completed_turn: Get the latest fully completed turn.
#         get_turns_for_summary: Retrieve turns not yet covered by a summary.
#         get_summary: Retrieve the rolling conversation summary.
#         update_summary: Save a new rolling summary.
#         search_messages: Search the stored conversation history.
#         get_next_turn_number: Get the next available turn number.
#         apply_memory_decision: Apply and audit a selective-memory decision.
#         get_memory_facts: List selected memory facts.
#         get_memory_decisions: List memory extraction decisions.
#         clear_session_memory: Clear selected facts for a session.
#     """

#     def __init__(self, db_path: str = "conversation.db") -> None:
#         """Initialize the database manager.

#         Args:
#             db_path (str): Path to the SQLite database file.
#         """
#         self.db_path = Path(db_path)
#         self.db_path.parent.mkdir(parents=True, exist_ok=True)
#         self.initialize()

#     def _connect(self) -> sqlite3.Connection:
#         """Create a configured SQLite connection.

#         Returns:
#             sqlite3.Connection: An open database connection.
#         """
#         connection = sqlite3.connect(self.db_path)
#         connection.row_factory = sqlite3.Row
#         connection.execute("PRAGMA foreign_keys = ON")
#         return connection

#     def initialize(self) -> None:
#         """Create conversation, message, and selective-memory tables."""
#         with self._connect() as connection:
#             connection.executescript(
#                 """
#                 CREATE TABLE IF NOT EXISTS conversations (
#                     conversation_id TEXT PRIMARY KEY,
#                     rolling_summary TEXT NOT NULL DEFAULT '',
#                     summary_through_turn INTEGER NOT NULL DEFAULT 0,
#                     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
#                     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
#                 );

#                 CREATE TABLE IF NOT EXISTS messages (
#                     id INTEGER PRIMARY KEY AUTOINCREMENT,
#                     conversation_id TEXT NOT NULL,
#                     message_number INTEGER NOT NULL,
#                     turn_number INTEGER NOT NULL,
#                     role TEXT NOT NULL
#                         CHECK (role IN ('user', 'assistant')),
#                     content TEXT NOT NULL,
#                     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

#                     FOREIGN KEY (conversation_id)
#                         REFERENCES conversations(conversation_id),

#                     UNIQUE (conversation_id, message_number)
#                 );

#                 CREATE INDEX IF NOT EXISTS idx_messages_conversation_turn
#                 ON messages (conversation_id, turn_number);

#                 CREATE INDEX IF NOT EXISTS idx_messages_conversation_role
#                 ON messages (conversation_id, role);

#                 CREATE TABLE IF NOT EXISTS memory_facts (
#                     id INTEGER PRIMARY KEY AUTOINCREMENT,
#                     conversation_id TEXT NOT NULL,
#                     fact_key TEXT NOT NULL,
#                     fact_value TEXT NOT NULL,
#                     source_turn INTEGER NOT NULL CHECK (source_turn >= 1),
#                     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
#                     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
#                     FOREIGN KEY (conversation_id)
#                         REFERENCES conversations(conversation_id),
#                     UNIQUE (conversation_id, fact_key)
#                 );

#                 CREATE TABLE IF NOT EXISTS memory_decisions (
#                     id INTEGER PRIMARY KEY AUTOINCREMENT,
#                     conversation_id TEXT NOT NULL,
#                     turn_number INTEGER NOT NULL CHECK (turn_number >= 1),
#                     decision TEXT NOT NULL
#                         CHECK (decision IN ('SAVE', 'SKIP', 'UPDATE')),
#                     fact_key TEXT,
#                     fact_value TEXT,
#                     reason TEXT NOT NULL DEFAULT '',
#                     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
#                     FOREIGN KEY (conversation_id)
#                         REFERENCES conversations(conversation_id)
#                 );

#                 CREATE INDEX IF NOT EXISTS idx_memory_decisions_conversation_turn
#                 ON memory_decisions (conversation_id, turn_number);
#                 """
#             )

#     def create_conversation(self) -> str:
#         """Create a conversation and return its identifier.

#         Returns:
#             str: The new conversation identifier.
#         """
#         conversation_id = str(uuid.uuid4())

#         with self._connect() as connection:
#             connection.execute(
#                 """
#                 INSERT INTO conversations (conversation_id)
#                 VALUES (?)
#                 """,
#                 (conversation_id,),
#             )

#         return conversation_id

#     def save_message(
#         self,
#         conversation_id: str,
#         turn_number: int,
#         role: str,
#         content: str,
#     ) -> int:
#         """Save a message and return its conversation-wide number.

#         Args:
#             conversation_id (str): Conversation that owns the message.
#             turn_number (int): Turn shared by the user message and reply.
#             role (str): Either 'user' or 'assistant'.
#             content (str): Message content.

#         Returns:
#             int: Sequential message number within the conversation.

#         Raises:
#             ValueError: If the role or turn number is invalid.
#         """
#         if role not in {"user", "assistant"}:
#             raise ValueError("role must be 'user' or 'assistant'")

#         if turn_number < 1:
#             raise ValueError("turn_number must be at least 1")

#         with self._connect() as connection:
#             row = connection.execute(
#                 """
#                 SELECT COALESCE(MAX(message_number), 0) + 1
#                 FROM messages
#                 WHERE conversation_id = ?
#                 """,
#                 (conversation_id,),
#             ).fetchone()

#             message_number = row[0]

#             connection.execute(
#                 """
#                 INSERT INTO messages (
#                     conversation_id,
#                     message_number,
#                     turn_number,
#                     role,
#                     content
#                 )
#                 VALUES (?, ?, ?, ?, ?)
#                 """,
#                 (
#                     conversation_id,
#                     message_number,
#                     turn_number,
#                     role,
#                     content,
#                 ),
#             )

#         return message_number

#     def get_message_by_number(
#         self,
#         conversation_id: str,
#         number: int,
#         user_messages_only: bool = True,
#     ) -> dict[str, Any] | None:
#         """Retrieve a numbered message from the conversation.

#         Args:
#             conversation_id (str): Conversation to search.
#             number (int): One-based message position.
#             user_messages_only (bool): Count only user messages when true.

#         Returns:
#             dict[str, Any] | None: The message record, or None if not found.

#         Raises:
#             ValueError: If number is less than 1.
#         """
#         if number < 1:
#             raise ValueError("number must be at least 1")

#         role_filter = "AND role = 'user'" if user_messages_only else ""

#         with self._connect() as connection:
#             row = connection.execute(
#                 f"""
#                 SELECT message_number, turn_number, role, content, created_at
#                 FROM messages
#                 WHERE conversation_id = ?
#                 {role_filter}
#                 ORDER BY message_number
#                 LIMIT 1 OFFSET ?
#                 """,
#                 (conversation_id, number - 1),
#             ).fetchone()

#         return dict(row) if row else None

#     def get_recent_turns(
#         self,
#         conversation_id: str,
#         limit: int = 10,
#     ) -> list[dict[str, Any]]:
#         """Retrieve the most recent completed conversation turns.

#         Args:
#             conversation_id (str): Conversation to retrieve.
#             limit (int): Maximum number of completed turns.

#         Returns:
#             list[dict[str, Any]]: Messages ordered from oldest to newest.

#         Raises:
#             ValueError: If limit is less than 1.
#         """
#         if limit < 1:
#             raise ValueError("limit must be at least 1")

#         with self._connect() as connection:
#             rows = connection.execute(
#                 """
#                 WITH completed_turns AS (
#                     SELECT turn_number
#                     FROM messages
#                     WHERE conversation_id = ?
#                     GROUP BY turn_number
#                     HAVING SUM(
#                         CASE WHEN role = 'user' THEN 1 ELSE 0 END
#                     ) > 0
#                     AND SUM(
#                         CASE WHEN role = 'assistant' THEN 1 ELSE 0 END
#                     ) > 0
#                     ORDER BY turn_number DESC
#                     LIMIT ?
#                 )
#                 SELECT message_number, turn_number, role, content, created_at
#                 FROM messages
#                 WHERE conversation_id = ?
#                   AND turn_number IN (
#                       SELECT turn_number FROM completed_turns
#                   )
#                 ORDER BY turn_number, message_number
#                 """,
#                 (conversation_id, limit, conversation_id),
#             ).fetchall()

#         return [dict(row) for row in rows]

#     def get_latest_completed_turn(self, conversation_id: str) -> int:
#         """Return the latest turn containing both user and assistant messages.

#         Args:
#             conversation_id (str): Conversation to inspect.

#         Returns:
#             int: Latest completed turn number, or 0 if none exists.
#         """
#         with self._connect() as connection:
#             row = connection.execute(
#                 """
#                 SELECT MAX(turn_number)
#                 FROM (
#                     SELECT turn_number
#                     FROM messages
#                     WHERE conversation_id = ?
#                     GROUP BY turn_number
#                     HAVING SUM(
#                         CASE WHEN role = 'user' THEN 1 ELSE 0 END
#                     ) > 0
#                     AND SUM(
#                         CASE WHEN role = 'assistant' THEN 1 ELSE 0 END
#                     ) > 0
#                 )
#                 """,
#                 (conversation_id,),
#             ).fetchone()

#         return int(row[0] or 0)

#     def get_turns_for_summary(
#         self,
#         conversation_id: str,
#         after_turn: int,
#         through_turn: int,
#     ) -> list[dict[str, Any]]:
#         """Retrieve messages from turns not yet covered by a summary.

#         Args:
#             conversation_id (str): Conversation to retrieve.
#             after_turn (int): Exclusive lower turn boundary.
#             through_turn (int): Inclusive upper turn boundary.

#         Returns:
#             list[dict[str, Any]]: Messages ordered by turn and message number.

#         Raises:
#             ValueError: If either turn boundary is negative.
#         """
#         if after_turn < 0 or through_turn < 0:
#             raise ValueError("Turn boundaries cannot be negative")

#         if through_turn <= after_turn:
#             return []

#         with self._connect() as connection:
#             rows = connection.execute(
#                 """
#                 SELECT message_number, turn_number, role, content, created_at
#                 FROM messages
#                 WHERE conversation_id = ?
#                   AND turn_number > ?
#                   AND turn_number <= ?
#                 ORDER BY turn_number, message_number
#                 """,
#                 (conversation_id, after_turn, through_turn),
#             ).fetchall()

#         return [dict(row) for row in rows]

#     def get_summary(self, conversation_id: str) -> dict[str, Any] | None:
#         """Retrieve the saved rolling summary and its coverage.

#         Args:
#             conversation_id (str): Conversation to retrieve.

#         Returns:
#             dict[str, Any] | None: Summary information, or None if absent.
#         """
#         with self._connect() as connection:
#             row = connection.execute(
#                 """
#                 SELECT rolling_summary, summary_through_turn
#                 FROM conversations
#                 WHERE conversation_id = ?
#                 """,
#                 (conversation_id,),
#             ).fetchone()

#         return dict(row) if row else None

#     def update_summary(
#         self,
#         conversation_id: str,
#         summary: str,
#         through_turn: int,
#     ) -> None:
#         """Save a rolling summary and the latest turn it covers.

#         Args:
#             conversation_id (str): Conversation to update.
#             summary (str): Updated rolling summary.
#             through_turn (int): Latest turn represented by the summary.

#         Raises:
#             ValueError: If through_turn is negative.
#             LookupError: If the conversation does not exist.
#         """
#         if through_turn < 0:
#             raise ValueError("through_turn cannot be negative")

#         with self._connect() as connection:
#             cursor = connection.execute(
#                 """
#                 UPDATE conversations
#                 SET rolling_summary = ?,
#                     summary_through_turn = ?,
#                     updated_at = CURRENT_TIMESTAMP
#                 WHERE conversation_id = ?
#                 """,
#                 (summary, through_turn, conversation_id),
#             )

#             if cursor.rowcount == 0:
#                 raise LookupError(
#                     f"Conversation not found: {conversation_id}"
#                 )

#     def search_messages(
#         self,
#         conversation_id: str,
#         query: str,
#         limit: int = 10,
#     ) -> list[dict[str, Any]]:
#         """Search message content using a case-insensitive text match.

#         Args:
#             conversation_id (str): Conversation to search.
#             query (str): Text to look for.
#             limit (int): Maximum number of matching messages.

#         Returns:
#             list[dict[str, Any]]: Matching messages in chronological order.

#         Raises:
#             ValueError: If query is empty or limit is less than 1.
#         """
#         if not query.strip():
#             raise ValueError("query cannot be empty")

#         if limit < 1:
#             raise ValueError("limit must be at least 1")

#         with self._connect() as connection:
#             rows = connection.execute(
#                 """
#                 SELECT message_number, turn_number, role, content, created_at
#                 FROM messages
#                 WHERE conversation_id = ?
#                   AND instr(lower(content), lower(?)) > 0
#                 ORDER BY message_number
#                 LIMIT ?
#                 """,
#                 (conversation_id, query.strip(), limit),
#             ).fetchall()

#         return [dict(row) for row in rows]

#     def get_next_turn_number(self, conversation_id: str) -> int:
#         """Return the next available conversation turn number.

#         Args:
#             conversation_id (str): Conversation to inspect.

#         Returns:
#             int: Next turn number, starting at 1.
#         """
#         with self._connect() as connection:
#             row = connection.execute(
#                 """
#                 SELECT COALESCE(MAX(turn_number), 0) + 1
#                 FROM messages
#                 WHERE conversation_id = ?
#                 """,
#                 (conversation_id,),
#             ).fetchone()

#         return int(row[0])

#     def apply_memory_decision(
#         self,
#         conversation_id: str,
#         turn_number: int,
#         decision: str,
#         fact_key: str | None = None,
#         fact_value: str | None = None,
#         reason: str = "",
#     ) -> int:
#         """Apply a memory decision and record its outcome atomically.

#         Args:
#             conversation_id (str): Conversation that owns the memory.
#             turn_number (int): Source conversation turn.
#             decision (str): SAVE, SKIP, or UPDATE.
#             fact_key (str | None): Stable fact category, such as llm_provider.
#             fact_value (str | None): Selected fact value.
#             reason (str): Brief explanation of the decision.

#         Returns:
#             int: Identifier of the recorded decision.

#         Raises:
#             ValueError: If decision or fact information is invalid.
#             LookupError: If UPDATE targets a nonexistent fact.
#             sqlite3.IntegrityError: If the conversation does not exist.
#         """
#         if turn_number < 1:
#             raise ValueError("turn_number must be at least 1")

#         if decision not in {"SAVE", "SKIP", "UPDATE"}:
#             raise ValueError("decision must be SAVE, SKIP, or UPDATE")

#         if decision != "SKIP" and (
#             not fact_key or not fact_key.strip()
#             or not fact_value or not fact_value.strip()
#         ):
#             raise ValueError(
#                 "SAVE and UPDATE require a fact_key and fact_value"
#             )

#         if decision == "SKIP" and (
#             fact_key is not None or fact_value is not None
#         ):
#             raise ValueError("SKIP cannot include a fact")

#         with self._connect() as connection:
#             if decision == "SAVE":
#                 connection.execute(
#                     """
#                     INSERT INTO memory_facts (
#                         conversation_id,
#                         fact_key,
#                         fact_value,
#                         source_turn
#                     )
#                     VALUES (?, ?, ?, ?)
#                     """,
#                     (
#                         conversation_id,
#                         fact_key.strip(),
#                         fact_value.strip(),
#                         turn_number,
#                     ),
#                 )

#             elif decision == "UPDATE":
#                 cursor = connection.execute(
#                     """
#                     UPDATE memory_facts
#                     SET fact_value = ?,
#                         source_turn = ?,
#                         updated_at = CURRENT_TIMESTAMP
#                     WHERE conversation_id = ?
#                       AND fact_key = ?
#                     """,
#                     (
#                         fact_value.strip(),
#                         turn_number,
#                         conversation_id,
#                         fact_key.strip(),
#                     ),
#                 )

#                 if cursor.rowcount == 0:
#                     raise LookupError(
#                         f"Memory fact not found: {fact_key}"
#                     )

#             cursor = connection.execute(
#                 """
#                 INSERT INTO memory_decisions (
#                     conversation_id,
#                     turn_number,
#                     decision,
#                     fact_key,
#                     fact_value,
#                     reason
#                 )
#                 VALUES (?, ?, ?, ?, ?, ?)
#                 """,
#                 (
#                     conversation_id,
#                     turn_number,
#                     decision,
#                     fact_key.strip() if fact_key else None,
#                     fact_value.strip() if fact_value else None,
#                     reason,
#                 ),
#             )

#             return int(cursor.lastrowid)

#     def get_memory_facts(
#         self,
#         conversation_id: str,
#     ) -> list[dict[str, Any]]:
#         """List selected facts for one conversation.

#         Args:
#             conversation_id (str): Conversation to inspect.

#         Returns:
#             list[dict[str, Any]]: Selected facts and their source turns.
#         """
#         with self._connect() as connection:
#             rows = connection.execute(
#                 """
#                 SELECT id, fact_key, fact_value, source_turn,
#                        created_at, updated_at
#                 FROM memory_facts
#                 WHERE conversation_id = ?
#                 ORDER BY id
#                 """,
#                 (conversation_id,),
#             ).fetchall()

#         return [dict(row) for row in rows]

#     def get_memory_decisions(
#         self,
#         conversation_id: str,
#     ) -> list[dict[str, Any]]:
#         """List recorded selective-memory decisions.

#         Args:
#             conversation_id (str): Conversation to inspect.

#         Returns:
#             list[dict[str, Any]]: Decisions in execution order.
#         """
#         with self._connect() as connection:
#             rows = connection.execute(
#                 """
#                 SELECT id, turn_number, decision, fact_key,
#                        fact_value, reason, created_at
#                 FROM memory_decisions
#                 WHERE conversation_id = ?
#                 ORDER BY id
#                 """,
#                 (conversation_id,),
#             ).fetchall()

#         return [dict(row) for row in rows]

#     def clear_session_memory(
#         self,
#         conversation_id: str,
#     ) -> int:
#         """Clear selected facts for a conversation session.

#         Conversation messages and memory decision records
#         are preserved for auditing and historical retrieval.

#         Args:
#             conversation_id (str): Conversation whose selected
#                 memory facts should be cleared.

#         Returns:
#             int: Number of selected memory facts deleted.
#         """
#         with self._connect() as connection:
#             cursor = connection.execute(
#                 """
#                 DELETE FROM memory_facts
#                 WHERE conversation_id = ?
#                 """,
#                 (conversation_id,),
#             )

#             return int(cursor.rowcount)
