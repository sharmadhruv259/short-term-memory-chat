
"""Test chat persistence and selective-memory behavior."""

from langchain_core.messages import AIMessage

from app import chat as chat_module
from app.database import Database


class FakeAgent:
    """Simulate the Main Agent without calling Groq."""

    def invoke(self, payload, config=None):
        """Return a deterministic assistant response.

        Args:
            payload (dict): Agent input messages.
            config (dict | None): Optional invocation configuration.

        Returns:
            dict: Simulated agent result.
        """
        return {
            "messages": [
                AIMessage(content="Hello! How can I help?")
            ]
        }


def mock_build_agents(db, conversation_id):
    """Build fake agents for isolated chat tests.

    Args:
        db (Database): Test database.
        conversation_id (str): Conversation identifier.

    Returns:
        dict: Fake Main Agent mapping.
    """
    return {
        "main_agent": FakeAgent(),
    }


def setup_chat_mocks(monkeypatch, decision="SKIP"):
    """Replace external services with deterministic test doubles.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
        decision (str): Simulated memory classification.
    """
    monkeypatch.setattr(
        chat_module,
        "build_agents",
        mock_build_agents,
    )

    monkeypatch.setattr(
        chat_module,
        "get_trace_handler",
        lambda: None,
    )

    monkeypatch.setattr(
        chat_module,
        "process_memory_turn",
        lambda **kwargs: {
            "decision": decision,
            "fact_key": None,
            "fact_value": None,
        },
    )


def test_chat_saves_both_messages(tmp_path, monkeypatch):
    """Verify that user and assistant messages are saved in SQLite."""
    setup_chat_mocks(monkeypatch)

    db = Database(str(tmp_path / "test.db"))

    result = chat_module.chat(
        db=db,
        message="Hi",
    )

    conversation_id = result["conversation_id"]

    user_message = db.get_message_by_number(
        conversation_id,
        1,
    )

    assistant_message = db.get_message_by_number(
        conversation_id,
        2,
        user_messages_only=False,
    )

    assert user_message is not None
    assert assistant_message is not None

    assert user_message["role"] == "user"
    assert user_message["content"] == "Hi"
    assert user_message["turn_number"] == 1

    assert assistant_message["role"] == "assistant"
    assert assistant_message["content"] == (
        "Hello! How can I help?"
    )
    assert assistant_message["turn_number"] == 1

    assert result["answer"] == (
        "Hello! How can I help?"
    )
    assert result["turn_number"] == 1


def test_chat_processes_selective_memory(tmp_path, monkeypatch):
    """Verify that selective-memory classification is invoked."""
    setup_chat_mocks(monkeypatch, decision="SAVE")

    db = Database(str(tmp_path / "test.db"))

    result = chat_module.chat(
        db=db,
        message="I use Groq for my chatbot.",
    )

    assert result["memory_decision"] is not None
    assert result["memory_decision"]["decision"] == "SAVE"
    assert result["memory_error"] is None

    # Rolling summaries must remain disabled in selective mode.
    assert result["summary_update"]["updated"] is False
    assert result["summary_update"]["disabled"] is True


def test_chat_survives_memory_extraction_failure(
    tmp_path,
    monkeypatch,
):
    """Verify that extraction failures do not discard chat responses."""
    setup_chat_mocks(monkeypatch)

    def failing_memory_extraction(**kwargs):
        """Simulate a memory extraction failure.

        Args:
            **kwargs: Memory extraction arguments.

        Raises:
            RuntimeError: Always, to simulate an extraction error.
        """
        raise RuntimeError("Simulated extraction failure")

    monkeypatch.setattr(
        chat_module,
        "process_memory_turn",
        failing_memory_extraction,
    )

    db = Database(str(tmp_path / "test.db"))

    result = chat_module.chat(
        db=db,
        message="Hello",
    )

    assert result["answer"] == (
        "Hello! How can I help?"
    )

    assert result["memory_decision"] is None

    assert result["memory_error"] is not None
    assert "Simulated extraction failure" in (
        result["memory_error"]
    )

    # The assistant message must remain saved even if
    # selective-memory extraction fails.
    assistant_message = db.get_message_by_number(
        result["conversation_id"],
        2,
        user_messages_only=False,
    )

    assert assistant_message is not None
    assert assistant_message["role"] == "assistant"
    assert assistant_message["content"] == (
        "Hello! How can I help?"
    )
