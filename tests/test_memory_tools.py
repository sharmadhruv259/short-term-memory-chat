import json

from app.database import Database
from app.memory_tools import build_memory_tools


def test_memory_tools_retrieve_messages_and_summary(tmp_path):
    """Verify message retrieval and disabled legacy summaries."""
    db = Database(str(tmp_path / "test.db"))
    conversation_id = db.create_conversation()

    db.save_message(conversation_id, 1, "user", "Hello")
    db.save_message(conversation_id, 1, "assistant", "Hi there")
    db.save_message(conversation_id, 2, "user", "I am learning Python")
    db.save_message(conversation_id, 2, "assistant", "That's great!")

    db.update_summary(
        conversation_id,
        "The user is learning Python.",
        through_turn=1,
    )

    tools = build_memory_tools(db, conversation_id)
    tool_map = {
        memory_tool.name: memory_tool
        for memory_tool in tools
    }

    message_result = json.loads(
        tool_map["get_message_by_number"].invoke(
            {"number": 2}
        )
    )

    assert message_result["found"] is True
    assert message_result["message"]["content"] == (
        "I am learning Python"
    )

    search_result = json.loads(
        tool_map["search_conversation"].invoke(
            {"query": "Python"}
        )
    )

    assert search_result["found"] is True
    assert any(
        item["content"] == "I am learning Python"
        for item in search_result["results"]
    )

    summary_result = json.loads(
        tool_map["get_conversation_summary"].invoke({})
    )

    # Historical rolling summaries must not enter
    # active-session memory.
    assert summary_result["found"] is False
    assert summary_result["summary"] == ""
    assert summary_result["summary_through_turn"] == 0


def test_memory_tools_restrict_previous_session_messages(tmp_path):
    """Verify that historical messages cannot cross session boundaries."""
    db = Database(str(tmp_path / "test.db"))
    conversation_id = db.create_conversation()

    # Previous session.
    db.save_message(
        conversation_id, 1, "user", "My secret color is blue"
    )
    db.save_message(
        conversation_id, 1, "assistant", "Understood"
    )

    # Current session begins at turn 2.
    db.save_message(
        conversation_id, 2, "user", "I am learning Django"
    )
    db.save_message(
        conversation_id, 2, "assistant", "Great!"
    )

    tools = build_memory_tools(
        db=db,
        conversation_id=conversation_id,
        session_start_turn=2,
    )

    tool_map = {
        memory_tool.name: memory_tool
        for memory_tool in tools
    }

    first_user_message = json.loads(
        tool_map["get_message_by_number"].invoke(
            {"number": 1}
        )
    )

    assert first_user_message["found"] is True
    assert first_user_message["message"]["content"] == (
        "I am learning Django"
    )

    old_message_search = json.loads(
        tool_map["search_conversation"].invoke(
            {"query": "secret color"}
        )
    )

    assert old_message_search["found"] is False
    assert old_message_search["results"] == []
