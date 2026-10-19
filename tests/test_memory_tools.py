from app.database import Database
from app.memory_tools import build_memory_tools


def test_memory_tools_retrieve_messages_and_summary(tmp_path):
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
    tool_map = {memory_tool.name: memory_tool for memory_tool in tools}

    message_result = tool_map["get_message_by_number"].invoke(
        {"number": 2}
    )
    assert '"found": true' in message_result
    assert "I am learning Python" in message_result

    search_result = tool_map["search_conversation"].invoke(
        {"query": "Python"}
    )
    assert '"found": true' in search_result
    assert "I am learning Python" in search_result

    summary_result = tool_map["get_conversation_summary"].invoke({})
    assert "The user is learning Python." in summary_result
    assert '"summary_through_turn": 1' in summary_result