
import pytest
from langchain_core.messages import AIMessage

from app.database import Database
from app.summarizer import update_rolling_summary


class FakeSummaryModel:
    """Simulate a model that updates rolling summaries.

    Attributes:
        response_text (str): Text returned by the simulated model.
        calls (list): Recorded model invocations.
        configs (list): Recorded LangChain configurations.

    Functions:
        invoke: Record a request and return a simulated response.
    """

    def __init__(self, response_text: str) -> None:
        """Initialize the fake model.

        Args:
            response_text (str): Summary text to return.
        """
        self.response_text = response_text
        self.calls = []
        self.configs = []

    def invoke(self, messages, config=None):
        """Record the request and return a simulated response.

        Args:
            messages: Messages sent to the summarization model.
            config (dict | None): Optional LangChain tracing configuration.

        Returns:
            AIMessage: Simulated model response.
        """
        self.calls.append(messages)
        self.configs.append(config)

        return AIMessage(content=self.response_text)


def add_completed_turn(db, conversation_id, turn_number):
    """Save a user message and assistant reply for one turn.

    Args:
        db (Database): Database for the test.
        conversation_id (str): Conversation to update.
        turn_number (int): Turn number to save.
    """
    db.save_message(
        conversation_id,
        turn_number,
        "user",
        f"User message {turn_number}",
    )

    db.save_message(
        conversation_id,
        turn_number,
        "assistant",
        f"Assistant reply {turn_number}",
    )


def test_summary_updates_only_turns_outside_recent_window(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    conversation_id = db.create_conversation()

    for turn in range(1, 13):
        add_completed_turn(db, conversation_id, turn)

    model = FakeSummaryModel("Summary of turns 1 and 2.")

    result = update_rolling_summary(
        db,
        conversation_id,
        model,
        recent_window=10,
    )

    assert result["updated"] is True
    assert result["summary_through_turn"] == 2
    assert result["summary"] == "Summary of turns 1 and 2."
    assert len(model.calls) == 1

    # Verify only eligible turns were sent to the model.
    prompt_text = "\n".join(
        str(message.content) for message in model.calls[0]
    )

    assert "User message 1" in prompt_text
    assert "User message 2" in prompt_text
    assert "User message 3" not in prompt_text

    # Verify Langfuse tracing configuration.
    config = model.configs[0]

    assert config["run_name"] == "rolling-summary-generation"

    assert config["metadata"]["conversation_id"] == conversation_id
    assert config["metadata"]["summary_from_turn"] == 1
    assert config["metadata"]["summary_through_turn"] == 2


def test_summary_processes_only_newly_eligible_turns(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    conversation_id = db.create_conversation()

    for turn in range(1, 13):
        add_completed_turn(db, conversation_id, turn)

    db.update_summary(
        conversation_id,
        "Summary through turn 2.",
        through_turn=2,
    )

    add_completed_turn(db, conversation_id, 13)

    model = FakeSummaryModel("Updated summary through turn 3.")

    result = update_rolling_summary(
        db,
        conversation_id,
        model,
        recent_window=10,
    )

    assert result["updated"] is True
    assert result["summary_through_turn"] == 3

    prompt_text = "\n".join(
        str(message.content) for message in model.calls[0]
    )

    assert "User message 3" in prompt_text
    assert "User message 2" not in prompt_text
    assert "User message 4" not in prompt_text

    # Verify incremental summary tracing metadata.
    config = model.configs[0]

    assert config["run_name"] == "rolling-summary-generation"
    assert config["metadata"]["summary_from_turn"] == 3
    assert config["metadata"]["summary_through_turn"] == 3


def test_empty_model_response_preserves_existing_summary(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    conversation_id = db.create_conversation()

    for turn in range(1, 13):
        add_completed_turn(db, conversation_id, turn)

    db.update_summary(
        conversation_id,
        "Original summary.",
        through_turn=1,
    )

    model = FakeSummaryModel("")

    with pytest.raises(RuntimeError, match="empty content"):
        update_rolling_summary(
            db,
            conversation_id,
            model,
            recent_window=10,
        )

    summary = db.get_summary(conversation_id)

    assert summary["rolling_summary"] == "Original summary."
    assert summary["summary_through_turn"] == 1

    # Verify that the model was invoked.
    assert len(model.calls) == 1

    # Verify tracing configuration was provided.
    assert model.configs[0]["run_name"] == (
        "rolling-summary-generation"
    )
