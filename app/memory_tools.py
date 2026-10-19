import json
from typing import Any
from langchain_core.tools import tool
from app.database import Database


def build_memory_tools(
    db: Database,
    conversation_id: str,
) -> list[Any]:
    """Build memory tools scoped to a single conversation.

    Args:
        db (Database): Database instance containing conversation history.
        conversation_id (str): Identifier of the active conversation.

    Returns:
        list[Any]: LangChain tools for historical memory retrieval.
    """

    @tool(parse_docstring=True)
    def get_message_by_number(
        number: int,
        user_messages_only: bool = True,
    ) -> str:
        """Retrieve an exact historical message by its position.

        Args:
            number: One-based message position. Defaults to counting user
                messages only, unless user_messages_only is false.
            user_messages_only: If true, count only user-authored messages.
                If false, count both user and assistant messages.

        Returns:
            A JSON string containing the message, or a not-found result.
        """
        message = db.get_message_by_number(
            conversation_id=conversation_id,
            number=number,
            user_messages_only=user_messages_only,
        )

        if message is None:
            return json.dumps({
                "found": False,
                "message": f"No message found at position {number}.",
            })

        return json.dumps({
            "found": True,
            "message": message,
        }, ensure_ascii=False)

    @tool(parse_docstring=True)
    def search_conversation(query: str, limit: int = 10) -> str:
        """Search stored conversation messages for a text phrase.

        Args:
            query: Word or phrase to search for in the transcript.
            limit: Maximum number of matching messages to return.

        Returns:
            A JSON string containing matching messages or a no-results result.
        """
        messages = db.search_messages(
            conversation_id=conversation_id,
            query=query,
            limit=limit,
        )

        if not messages:
            return json.dumps({
                "found": False,
                "results": [],
                "message": "No matching messages were found.",
            })

        return json.dumps({
            "found": True,
            "results": messages,
        }, ensure_ascii=False)

    @tool(parse_docstring=True)
    def get_conversation_summary() -> str:
        """Retrieve the saved rolling summary of this conversation.

        Returns:
            A JSON string containing the summary and its covered turn number.
        """
        summary = db.get_summary(conversation_id)

        if summary is None:
            return json.dumps({
                "found": False,
                "message": "Conversation summary was not found.",
            })

        return json.dumps({
            "found": True,
            "summary": summary["rolling_summary"],
            "summary_through_turn": summary["summary_through_turn"],
        }, ensure_ascii=False)

    return [
        get_message_by_number,
        search_conversation,
        get_conversation_summary,
    ]