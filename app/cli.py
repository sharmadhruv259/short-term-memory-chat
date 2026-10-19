
"""Interactive command-line interface for the memory chatbot."""

from app.chat import chat
from app.database import Database


def display_messages(messages: list[dict]) -> None:
    """Display stored conversation messages.

    Args:
        messages (list[dict]): Messages retrieved from SQLite.
    """
    if not messages:
        print("No completed messages found.")
        return

    for item in messages:
        print(
            f"Turn {item['turn_number']} "
            f"[{item['role']}]: {item['content']}"
        )


def display_status(db: Database, conversation_id: str) -> None:
    """Display the current conversation memory distribution.

    Args:
        db (Database): Conversation database.
        conversation_id (str): Active conversation identifier.
    """
    latest = db.get_latest_completed_turn(conversation_id)
    summary = db.get_summary(conversation_id)

    summary_through = (
        summary["summary_through_turn"] if summary else 0
    )

    recent_start = max(1, latest - 9)

    print("\n========== MEMORY STATUS ==========")
    print(f"Conversation ID: {conversation_id}")
    print(f"Completed turns: {latest}")

    if latest:
        print(f"Recent memory: Turns {recent_start}–{latest}")
        print(f"SQLite transcript: Turns 1–{latest}")
    else:
        print("Recent memory: Empty")
        print("SQLite transcript: Empty")

    if summary_through:
        print(f"Rolling summary: Turns 1–{summary_through}")
    else:
        print("Rolling summary: Not generated yet")

    print("Memory Agent: Available for historical retrieval")
    print("===================================\n")


def main() -> None:
    """Run the interactive short-term memory chatbot."""
    db = Database("chat_history.db")
    conversation_id = None

    print("\n===================================")
    print("     SHORT-TERM MEMORY CHAT")
    print("===================================")
    print("Commands:")
    print("  /new      Start a new conversation")
    print("  /resume   Resume a saved conversation")
    print("  /id       Show current conversation ID")
    print("  /memory   Show latest 10 completed turns")
    print("  /summary  Show rolling summary")
    print("  /history  Show complete conversation history")
    print("  /status   Show memory distribution")
    print("  /help     Show available commands")
    print("  /exit     Exit the chatbot")
    print("===================================\n")

    while True:
        try:
            user_input = input("You: ").strip()

            if not user_input:
                continue

            command = user_input.lower()

            if command == "/exit":
                print("\nGoodbye! Conversation saved.")
                break

            if command == "/help":
                print("\nAvailable commands:")
                print("/new      - Start a new conversation")
                print("/resume   - Resume a saved conversation")
                print("/id       - Show conversation ID")
                print("/memory   - Show recent memory")
                print("/summary  - Show rolling summary")
                print("/history  - Show complete history")
                print("/status   - Show memory status")
                print("/exit     - Exit chatbot\n")
                continue

            if command == "/new":
                conversation_id = None
                print("\nStarted a new conversation.\n")
                continue

            if command == "/id":
                if conversation_id:
                    print(f"\nConversation ID: {conversation_id}\n")
                else:
                    print("\nNo active conversation yet.\n")
                continue

            if command == "/resume":
                saved_id = input("Enter conversation ID: ").strip()

                if not saved_id:
                    print("Conversation ID cannot be empty.\n")
                    continue

                if not db.get_latest_completed_turn(saved_id):
                    print("No completed conversation found for that ID.\n")
                    continue

                conversation_id = saved_id

                print(
                    f"\nResumed conversation: {conversation_id}\n"
                )
                continue

            # All memory inspection commands need an active conversation.
            if command in {
                "/memory",
                "/summary",
                "/history",
                "/status",
            } and not conversation_id:
                print("\nNo active conversation yet.\n")
                continue

            if command == "/memory":
                recent = db.get_recent_turns(
                    conversation_id,
                    limit=10,
                )

                print("\n========== RECENT MEMORY ==========")
                display_messages(recent)
                print("===================================\n")
                continue

            if command == "/summary":
                summary = db.get_summary(conversation_id)

                print("\n========== ROLLING SUMMARY ==========")

                if summary and summary["rolling_summary"]:
                    print(
                        "Summarized through turn:",
                        summary["summary_through_turn"],
                    )
                    print("\n" + summary["rolling_summary"])
                else:
                    print("No rolling summary generated yet.")

                print("=====================================\n")
                continue

            if command == "/history":
                latest = db.get_latest_completed_turn(
                    conversation_id
                )

                history = (
                    db.get_recent_turns(
                        conversation_id,
                        limit=latest,
                    )
                    if latest > 0
                    else []
                )

                print("\n========== FULL HISTORY ==========")
                display_messages(history)
                print("==================================\n")
                continue

            if command == "/status":
                display_status(db, conversation_id)
                continue

            if command.startswith("/"):
                print(
                    "\nUnknown command. Type /help "
                    "to see available commands.\n"
                )
                continue

            # Process a normal user message.
            result = chat(
                db=db,
                message=user_input,
                conversation_id=conversation_id,
            )

            conversation_id = result["conversation_id"]

            print(f"\nAssistant: {result['answer']}\n")

            # Inform the user when older turns are summarized.
            summary_update = result.get("summary_update", {})

            if summary_update.get("updated"):
                print(
                    "[Memory] Rolling summary updated through "
                    f"turn {summary_update['summary_through_turn']}.\n"
                )

            elif summary_update.get("error"):
                print(
                    "[Memory] Summary update failed; "
                    "saved messages remain available.\n"
                )

        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye! Conversation saved.")
            break

        except Exception as exc:
            print(f"\nError: {exc}\n")
            print("Please try again.\n")


if __name__ == "__main__":
    main()
