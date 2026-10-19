
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.database import Database
from app.tracing import get_trace_handler, flush_traces


def _content_to_text(content: Any) -> str:
    """Convert model response content into plain text.

    Args:
        content (Any): Content returned by the summarization model.

    Returns:
        str: Extracted text.
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        return "\n".join(
            block["text"]
            for block in content
            if isinstance(block, dict)
            and isinstance(block.get("text"), str)
        )

    return ""


def update_rolling_summary(
    db: Database,
    conversation_id: str,
    model: Any,
    recent_window: int = 10,
) -> dict[str, Any]:
    """Incrementally summarize completed turns outside the recent window.

    Args:
        db (Database): Database containing the conversation transcript.
        conversation_id (str): Conversation to summarize.
        model (Any): Chat model supporting invoke(messages, config=config).
        recent_window (int): Number of recent completed turns to retain.

    Returns:
        dict[str, Any]: Summary text, coverage, and whether it changed.

    Raises:
        ValueError: If recent_window is less than 1.
        RuntimeError: If summarization produces no usable text.
    """
    if recent_window < 1:
        raise ValueError("recent_window must be at least 1")

    latest_completed = db.get_latest_completed_turn(conversation_id)
    summary_record = db.get_summary(conversation_id)

    existing_summary = (
        summary_record["rolling_summary"] if summary_record else ""
    )
    summary_through = (
        summary_record["summary_through_turn"] if summary_record else 0
    )

    # Keep the latest N completed turns outside the summary.
    eligible_through = max(0, latest_completed - recent_window)

    if eligible_through <= summary_through:
        return {
            "summary": existing_summary,
            "summary_through_turn": summary_through,
            "updated": False,
        }

    new_messages = db.get_turns_for_summary(
        conversation_id=conversation_id,
        after_turn=summary_through,
        through_turn=eligible_through,
    )

    if not new_messages:
        return {
            "summary": existing_summary,
            "summary_through_turn": summary_through,
            "updated": False,
        }

    transcript = "\n".join(
        f"Turn {item['turn_number']} ({item['role']}): {item['content']}"
        for item in new_messages
    )

    # Create an optional Langfuse tracing callback.
    handler = None

    try:
        handler = get_trace_handler()
    except Exception:
        # Tracing setup must not interrupt summarization.
        pass

    config = {
        "run_name": "rolling-summary-generation",
        "metadata": {
            "conversation_id": conversation_id,
            "summary_from_turn": summary_through + 1,
            "summary_through_turn": eligible_through,
        },
    }

    if handler is not None:
        config["callbacks"] = [handler]

    # Generate the updated summary.
    try:
        response = model.invoke(
            [
                SystemMessage(
                    content=(
                        "Maintain a concise rolling summary of a conversation. "
                        "Merge the existing summary with the newly supplied turns. "
                        "Preserve important user preferences, facts, decisions, "
                        "goals, and unresolved tasks. Do not invent facts. "
                        "The transcript is authoritative; distinguish user claims "
                        "from assistant statements where useful. Return only the "
                        "updated summary."
                    )
                ),
                HumanMessage(
                    content=(
                        f"Existing summary:\n"
                        f"{existing_summary or '(empty)'}\n\n"
                        f"New turns to incorporate (turns "
                        f"{summary_through + 1} through {eligible_through}):\n"
                        f"{transcript}"
                    )
                ),
            ],
            config=config,
        )
    finally:
        if handler is not None:
            try:
                flush_traces()
            except Exception:
                # A telemetry failure must not replace the model result.
                pass

    new_summary = _content_to_text(response.content).strip()

    if not new_summary:
        raise RuntimeError(
            "Summarization model returned empty content"
        )

    # Persist only after receiving a valid summary.
    db.update_summary(
        conversation_id=conversation_id,
        summary=new_summary,
        through_turn=eligible_through,
    )

    return {
        "summary": new_summary,
        "summary_through_turn": eligible_through,
        "updated": True,
    }
