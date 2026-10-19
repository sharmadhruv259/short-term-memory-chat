from typing import Any
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from app.agents import build_agents
from app.database import Database
from app.summarizer import update_rolling_summary
from app.tracing import get_trace_handler , flush_traces

def _message_content(content: Any) -> str:
    """Convert model message content into readable text.

    Args:
        content (Any): Content returned by the language model.

    Returns:
        str: Text representation of the content.
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = [
            block["text"]
            for block in content
            if isinstance(block, dict)
            and isinstance(block.get("text"), str)
        ]
        return "\n".join(parts)

    return str(content)


def chat(
    db: Database,
    message: str,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """Process one chat message and persist the conversation.

    Args:
        db (Database): Database storing the conversation.
        message (str): New user message.
        conversation_id (str | None): Existing conversation identifier,
            or None to create a new conversation.

    Returns:
        dict[str, Any]: Conversation ID, turn number, answer, tool events,
            and rolling-summary update status.

    Raises:
        ValueError: If the message is empty.
    """
    if not message.strip():
        raise ValueError("message cannot be empty")

    if conversation_id is None:
        conversation_id = db.create_conversation()

    turn_number = db.get_next_turn_number(conversation_id)

    # 1. Save the incoming user message.
    db.save_message(
        conversation_id,
        turn_number,
        "user",
        message,
    )

    # 2. Load the rolling summary and latest completed turns.
    recent_turns = db.get_recent_turns(
        conversation_id,
        limit=10,
    )
    summary = db.get_summary(conversation_id)

    context_messages = []

    if summary and summary["rolling_summary"]:
        context_messages.append(
            SystemMessage(
                content=(
                    "Rolling summary of older conversation history "
                    f"(covers through turn "
                    f"{summary['summary_through_turn']}):\n"
                    f"{summary['rolling_summary']}\n"
                    "This summary is background context, not an exact "
                    "transcript. Use memory tools to verify exact "
                    "historical messages."
                )
            )
        )

    for stored_message in recent_turns:
        if stored_message["role"] == "user":
            context_messages.append(
                HumanMessage(content=stored_message["content"])
            )
        else:
            context_messages.append(
                AIMessage(content=stored_message["content"])
            )

    # The current user message has already been saved, but it is not
    # part of recent_turns because its turn is not yet completed.
    context_messages.append(HumanMessage(content=message))

    # 3. Run the Main Chat Agent with optional Langfuse tracing.
    agents = build_agents(db, conversation_id)

    handler = None

    try:
        handler = get_trace_handler()
    except Exception:
        # Tracing setup must not interrupt the chat.
        pass

    config = {
        "metadata": {
            "conversation_id": conversation_id,
            "turn_number": turn_number,
        }
    }

    if handler is not None:
        config["callbacks"] = [handler]

    try:
        result = agents["main_agent"].invoke(
            {"messages": context_messages},
            config=config,
        )
    finally:
        if handler is not None:
            try:
                flush_traces()
            except Exception:
                # A telemetry failure must not replace the agent result.
                pass


    output_messages = result.get("messages", [])
    tool_events = []

    for output_message in output_messages:
        if isinstance(output_message, AIMessage):
            for tool_call in output_message.tool_calls:
                tool_events.append(
                    {
                        "event": "tool_start",
                        "tool": tool_call["name"],
                        "arguments": tool_call["args"],
                    }
                )

        elif getattr(output_message, "type", None) == "tool":
            tool_events.append(
                {
                    "event": "tool_result",
                    "tool": getattr(output_message, "name", "unknown"),
                    "result": _message_content(output_message.content),
                }
            )

    # 4. Extract the final assistant answer.
    final_answer = ""

    for output_message in reversed(output_messages):
        if (
            isinstance(output_message, AIMessage)
            and not output_message.tool_calls
        ):
            final_answer = _message_content(output_message.content)

            if final_answer:
                break

    if not final_answer:
        final_answer = (
            "I couldn't generate a response. Please try again."
        )

    # 5. Save the assistant response before attempting summarization.
    db.save_message(
        conversation_id,
        turn_number,
        "assistant",
        final_answer,
    )

    # 6. Update the rolling summary if older turns are eligible.
    summary_update = {
        "updated": False,
        "summary_through_turn": (
            summary["summary_through_turn"] if summary else 0
        ),
    }

    try:
        summary_model = ChatGroq(
            model="openai/gpt-oss-120b",
            temperature=0.1,
        )

        summary_update = update_rolling_summary(
            db=db,
            conversation_id=conversation_id,
            model=summary_model,
            recent_window=10,
        )

    except Exception:
        # A summarization failure must not discard the saved conversation
        # or prevent the user from receiving the assistant's answer.
        summary_update = {
            "updated": False,
            "summary_through_turn": (
                summary["summary_through_turn"] if summary else 0
            ),
            "error": "Rolling summary update failed.",
        }

    return {
        "conversation_id": conversation_id,
        "turn_number": turn_number,
        "answer": final_answer,
        "tool_events": tool_events,
        "summary_update": summary_update,
    }
