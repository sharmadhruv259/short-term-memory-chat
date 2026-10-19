from app.agents import build_agents
from app.database import Database


def test_build_agents(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    conversation_id = db.create_conversation()

    agents = build_agents(db, conversation_id)

    assert agents["main_agent"] is not None
    assert agents["memory_agent"] is not None

    tool_names = {tool.name for tool in agents["memory_tools"]}

    assert "get_message_by_number" in tool_names
    assert "search_conversation" in tool_names
    assert "get_conversation_summary" in tool_names
