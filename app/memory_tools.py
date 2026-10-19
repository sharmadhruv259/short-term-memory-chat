
"""Provide SQLite retrieval tools for the Main Chat Agent."""

import json
from typing import Any

from langchain_core.tools import tool

from app.database import Database


def build_memory_tools(
    db: Database,
    session_id: str,
) -> list[Any]:
    """Build session-specific message retrieval tools.

    Args:
        db (Database): SQLite database manager.
        session_id (str): Active session identifier.

    Returns:
        list[Any]: Numbered lookup and search tools.
    """

    @tool
    def get_message_by_number(
        number: int,
        user_messages_only: bool = True,
    ) -> str:
        """Retrieve a numbered message from this session.

        Args:
            number: One-based message position.
            user_messages_only: Count only user messages when true.

        Returns:
            JSON containing the matching message or a not-found result.
        """
        try:
            record = db.get_message_by_number(
                session_id=session_id,
                number=number,
                user_messages_only=user_messages_only,
            )

            if record is None:
                return json.dumps({
                    "found": False,
                    "message": "No message found at that position.",
                })

            return json.dumps({
                "found": True,
                "message": record,
            }, ensure_ascii=False)

        except ValueError as exc:
            return json.dumps({
                "found": False,
                "error": str(exc),
            })

    @tool
    def search_conversation(
        query: str,
        limit: int = 10,
    ) -> str:
        """Search messages from the active session.

        Args:
            query: Text to search for in stored messages.
            limit: Maximum number of results.

        Returns:
            JSON containing matching messages.
        """
        try:
            results = db.search_messages(
                session_id=session_id,
                query=query,
                limit=limit,
            )

            return json.dumps({
                "found": bool(results),
                "results": results,
            }, ensure_ascii=False)

        except ValueError as exc:
            return json.dumps({
                "found": False,
                "results": [],
                "error": str(exc),
            })

    return [
        get_message_by_number,
        search_conversation,
    ]

# import json
# from typing import Any
# from langchain_core.tools import tool
# from app.database import Database


# def build_memory_tools(
#     db: Database,
#     conversation_id: str,
#     session_start_turn: int = 1,
# ) -> list[Any]:
#     """Build memory tools restricted to the active session.

#     Args:
#         db (Database): Database containing conversation history.
#         conversation_id (str): Active conversation identifier.
#         session_start_turn (int): First turn belonging to the
#             current active session.

#     Returns:
#         list[Any]: LangChain tools for session-only retrieval.

#     Raises:
#         ValueError: If session_start_turn is less than 1.
#     """
#     if session_start_turn < 1:
#         raise ValueError(
#             "session_start_turn must be at least 1"
#         )

#     @tool(parse_docstring=True)
#     def get_message_by_number(
#         number: int,
#         user_messages_only: bool = True,
#     ) -> str:
#         """Retrieve a numbered message from the active session.

#         Args:
#             number: One-based message position within the
#                 current session.
#             user_messages_only: If true, count user messages
#                 only. Otherwise count user and assistant messages.

#         Returns:
#             A JSON string containing the message or a not-found result.
#         """
#         if number < 1:
#             return json.dumps({
#                 "found": False,
#                 "message": "Message number must be at least 1.",
#             })

#         role_filter = (
#             "AND role = 'user'"
#             if user_messages_only
#             else ""
#         )

#         with db._connect() as connection:
#             row = connection.execute(
#                 f"""
#                 SELECT
#                     message_number,
#                     turn_number,
#                     role,
#                     content,
#                     created_at
#                 FROM messages
#                 WHERE conversation_id = ?
#                   AND turn_number >= ?
#                   {role_filter}
#                 ORDER BY message_number
#                 LIMIT 1 OFFSET ?
#                 """,
#                 (
#                     conversation_id,
#                     session_start_turn,
#                     number - 1,
#                 ),
#             ).fetchone()

#         if row is None:
#             return json.dumps({
#                 "found": False,
#                 "message": (
#                     f"No message found at session position {number}."
#                 ),
#             })

#         return json.dumps({
#             "found": True,
#             "message": dict(row),
#         }, ensure_ascii=False)

#     @tool(parse_docstring=True)
#     def search_conversation(
#         query: str,
#         limit: int = 10,
#     ) -> str:
#         """Search messages within the active session.

#         Args:
#             query: Word or phrase to search for.
#             limit: Maximum number of matching messages.

#         Returns:
#             A JSON string containing matching session messages.
#         """
#         if not query.strip():
#             return json.dumps({
#                 "found": False,
#                 "results": [],
#                 "message": "Search query cannot be empty.",
#             })

#         if limit < 1:
#             return json.dumps({
#                 "found": False,
#                 "results": [],
#                 "message": "Search limit must be at least 1.",
#             })

#         with db._connect() as connection:
#             rows = connection.execute(
#                 """
#                 SELECT
#                     message_number,
#                     turn_number,
#                     role,
#                     content,
#                     created_at
#                 FROM messages
#                 WHERE conversation_id = ?
#                   AND turn_number >= ?
#                   AND instr(lower(content), lower(?)) > 0
#                 ORDER BY message_number
#                 LIMIT ?
#                 """,
#                 (
#                     conversation_id,
#                     session_start_turn,
#                     query.strip(),
#                     limit,
#                 ),
#             ).fetchall()

#         messages = [
#             dict(row)
#             for row in rows
#         ]

#         if not messages:
#             return json.dumps({
#                 "found": False,
#                 "results": [],
#                 "message": (
#                     "No matching messages were found "
#                     "in the active session."
#                 ),
#             })

#         return json.dumps({
#             "found": True,
#             "results": messages,
#         }, ensure_ascii=False)

#     @tool(parse_docstring=True)
#     def get_conversation_summary() -> str:
#         """Retrieve the active session's conversation summary.

#         Returns:
#             A JSON string containing an active-session summary
#             or a message explaining its unavailability.
#         """
#         # Rolling summaries are currently disabled.
#         # A previously saved summary may contain information
#         # from an earlier session, so it must not be exposed.
#         return json.dumps({
#             "found": False,
#             "summary": "",
#             "summary_through_turn": 0,
#             "message": (
#                 "Session summaries are disabled in "
#                 "selective short-term memory mode."
#             ),
#         })

#     return [
#         get_message_by_number,
#         search_conversation,
#         get_conversation_summary,
#     ]
