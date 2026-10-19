
from langchain_core.messages import AIMessage

from app import chat as chat_module
from app.database import Database


class FakeAgent:
    """Provide a predictable response for chat tests.

    Attributes:
        response (str): Answer returned by the fake agent.

    Functions:
        invoke: Return a simulated assistant response.
    """

    def __init__(self, response: str) -> None:
        """Initialize the fake agent.

        Args:
            response (str): Answer to return.
        """
        self.response = response

    def invoke(self, state: dict, config: dict | None) -> dict:
        """Return a simulated agent result.

        Args:
            state (dict): Input conversation state.

        Returns:
            dict: Simulated assistant messages.
        """
        return {
            "messages": state["messages"] + [
                AIMessage(content=self.response)
            ]
        }


def mock_build_agents(db, conversation_id):
    """Build fake agents for chat tests."""
    return {
        "main_agent": FakeAgent("Hello! I can help."),
        "memory_agent": FakeAgent("Memory result."),
        "memory_tools": [],
    }


def test_chat_saves_both_messages(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "test.db"))

    monkeypatch.setattr(
        chat_module,
        "build_agents",
        mock_build_agents,
    )

    # Prevent the test from running real summarization.
    monkeypatch.setattr(
        chat_module,
        "update_rolling_summary",
        lambda *args, **kwargs: None,
    )

    result = chat_module.chat(db, "Hello")

    assert result["answer"] == "Hello! I can help."
    assert result["turn_number"] == 1

    conversation_id = result["conversation_id"]
    turns = db.get_recent_turns(conversation_id, limit=10)

    assert len(turns) == 2
    assert turns[0]["role"] == "user"
    assert turns[0]["content"] == "Hello"
    assert turns[1]["role"] == "assistant"
    assert turns[1]["content"] == "Hello! I can help."


def test_chat_attempts_summary_update(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "test.db"))
    summary_calls = []

    monkeypatch.setattr(
        chat_module,
        "build_agents",
        mock_build_agents,
    )

    def fake_update_summary(*args, **kwargs):
        summary_calls.append((args, kwargs))
        return "Updated summary."

    monkeypatch.setattr(
        chat_module,
        "update_rolling_summary",
        fake_update_summary,
    )

    result = chat_module.chat(db, "Hello")

    assert result["answer"] == "Hello! I can help."
    assert len(summary_calls) == 1


def test_chat_survives_summary_update_failure(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "test.db"))

    monkeypatch.setattr(
        chat_module,
        "build_agents",
        mock_build_agents,
    )

    def failing_summary_update(*args, **kwargs):
        raise RuntimeError("Simulated summarization failure")

    monkeypatch.setattr(
        chat_module,
        "update_rolling_summary",
        failing_summary_update,
    )

    result = chat_module.chat(db, "Hello")

    assert result["answer"] == "Hello! I can help."
    assert result["turn_number"] == 1

    conversation_id = result["conversation_id"]
    turns = db.get_recent_turns(conversation_id, limit=10)

    assert len(turns) == 2
    assert turns[0]["content"] == "Hello"
    assert turns[1]["content"] == "Hello! I can help."
