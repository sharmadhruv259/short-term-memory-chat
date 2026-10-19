from app.database import Database


def test_message_numbering_and_lookup(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    conversation_id = db.create_conversation()

    db.save_message(conversation_id, 1, "user", "Hello")
    db.save_message(conversation_id, 1, "assistant", "Hi there")
    db.save_message(conversation_id, 2, "user", "Remember Python?")
    db.save_message(conversation_id, 2, "assistant", "Yes, Python.")

    # Third user-authored message does not exist yet.
    assert db.get_message_by_number(
        conversation_id, 3, user_messages_only=True
    ) is None

    # The third message across both roles is the second user's message.
    result = db.get_message_by_number(
        conversation_id, 3, user_messages_only=False
    )
    assert result is not None
    assert result["content"] == "Remember Python?"
    assert result["role"] == "user"

    # The second user-authored message is also "Remember Python?"
    result = db.get_message_by_number(conversation_id, 2)
    assert result is not None
    assert result["content"] == "Remember Python?"


def test_recent_completed_turns(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    conversation_id = db.create_conversation()

    db.save_message(conversation_id, 1, "user", "Hello")
    db.save_message(conversation_id, 1, "assistant", "Hi")
    db.save_message(conversation_id, 2, "user", "How are you?")
    db.save_message(conversation_id, 2, "assistant", "Good!")

    turns = db.get_recent_turns(conversation_id, limit=1)

    assert len(turns) == 2
    assert all(message["turn_number"] == 2 for message in turns)


def test_summary_storage(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    conversation_id = db.create_conversation()

    db.update_summary(
        conversation_id,
        "The user is learning Python.",
        through_turn=5,
    )

    summary = db.get_summary(conversation_id)
    assert summary is not None
    assert summary["rolling_summary"] == "The user is learning Python."
    assert summary["summary_through_turn"] == 5

def test_next_turn_number(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    conversation_id = db.create_conversation()

    assert db.get_next_turn_number(conversation_id) == 1

    db.save_message(conversation_id, 1, "user", "Hello")
    db.save_message(conversation_id, 1, "assistant", "Hi")

    assert db.get_next_turn_number(conversation_id) == 2