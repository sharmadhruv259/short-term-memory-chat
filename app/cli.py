
"""Interactive CLI for the session-based memory chatbot."""

from datetime import datetime, timezone

from app.chat import chat
from app.database import Database


def format_timestamp(value: str) -> str:
    """Convert a SQLite UTC timestamp to local time.

    Args:
        value (str): SQLite timestamp.

    Returns:
        str: Formatted local date and time.
    """
    if not value:
        return "N/A"

    try:
        utc_time = datetime.strptime(
            value,
            "%Y-%m-%d %H:%M:%S",
        ).replace(tzinfo=timezone.utc)

        return utc_time.astimezone().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    except ValueError:
        return value


def display_history_table(messages: list[dict]) -> None:
    """Display messages in a five-column table.

    Args:
        messages (list[dict]): Messages retrieved from SQLite.
    """
    if not messages:
        print("\nNo messages found.\n")
        return

    columns = [
        "session_id",
        "role",
        "content",
        "created_at",
        "updated_at",
    ]

    widths = {
        "session_id": 36,
        "role": 9,
        "content": 40,
        "created_at": 19,
        "updated_at": 19,
    }

    def format_cell(value: str, width: int) -> str:
        """Format a table cell."""
        text = str(value).replace("\n", " ")

        if len(text) > width:
            return text[: width - 3] + "..."

        return text.ljust(width)

    def make_row(values: dict) -> str:
        """Format a complete table row."""
        return "| " + " | ".join(
            format_cell(values[column], widths[column])
            for column in columns
        ) + " |"

    separator = "+-" + "-+-".join(
        "-" * widths[column]
        for column in columns
    ) + "-+"

    print("\n" + separator)

    print(
        make_row({
            column: column.upper()
            for column in columns
        })
    )

    print(separator)

    for item in messages:
        row = {
            "session_id": item["session_id"],
            "role": item["role"],
            "content": item["content"],
            "created_at": format_timestamp(
                item["created_at"]
            ),
            "updated_at": format_timestamp(
                item["updated_at"]
            ),
        }

        print(make_row(row))

    print(separator)
    print(f"\nTotal messages: {len(messages)}\n")


def main() -> None:
    """Run the interactive chatbot."""
    db = Database("chat_history.db")

    session_id: str | None = None

    # Clean welcome screen without displaying commands.
    print("\n===================================")
    print("         AI CHAT ASSISTANT")
    print("===================================")
    print("How can I help you today?\n")

    while True:
        try:
            user_input = input("You: ").strip()

            if not user_input:
                continue

            command = user_input.lower()

            # Exit the chatbot.
            if command == "/exit":
                print("\nGoodbye! Have a great day.")
                break

            # Start a new session.
            if command == "/new":
                session_id = None

                print(
                    "\nNew conversation started.\n"
                )
                continue

            # Resume an existing session.
            if command == "/resume":
                saved_id = input(
                    "Enter session ID: "
                ).strip()

                if (
                    not saved_id
                    or not db.session_exists(saved_id)
                ):
                    print(
                        "\nNo stored session found "
                        "for that ID.\n"
                    )
                    continue

                session_id = saved_id

                print(
                    "\nConversation resumed successfully.\n"
                )
                continue

            # Display the current session ID.
            if command == "/id":
                print(
                    f"\nSession ID: "
                    f"{session_id or 'None'}\n"
                )
                continue

            # Developer inspection commands.
            if command in {
                "/memory",
                "/history",
                "/status",
            } or command.startswith("/get "):

                if session_id is None:
                    print(
                        "\nNo active conversation yet.\n"
                    )
                    continue

                # Display session information.
                if command == "/status":
                    count = db.get_message_count(
                        session_id
                    )

                    print("\n--- SESSION STATUS ---")
                    print(f"Session ID: {session_id}")
                    print(f"Stored messages: {count}")
                    print("Recent context limit: 10 messages")
                    print("Historical retrieval: Enabled")
                    print()
                    continue

                # Retrieve a numbered user message.
                if command.startswith("/get "):
                    try:
                        number = int(
                            command.split()[1]
                        )

                        record = db.get_message_by_number(
                            session_id=session_id,
                            number=number,
                        )

                        if record:
                            display_history_table([record])
                        else:
                            print(
                                "\nNo such user message.\n"
                            )

                    except (ValueError, IndexError):
                        print("\nUsage: /get 5\n")

                    continue

                # Display the latest 10 messages.
                if command == "/memory":
                    messages = db.get_recent_messages(
                        session_id=session_id,
                        limit=10,
                    )

                    print(
                        "\n--- RECENT CONVERSATION ---"
                    )

                    display_history_table(messages)
                    continue

                # Display complete conversation history.
                if command == "/history":
                    messages = db.get_all_messages(
                        session_id=session_id,
                    )

                    print(
                        "\n--- CONVERSATION HISTORY ---"
                    )

                    display_history_table(messages)
                    continue

            # Handle unknown slash commands.
            if command.startswith("/"):
                print(
                    "\nUnknown command.\n"
                )
                continue

            # Process a normal user message.
            result = chat(
                db=db,
                message=user_input,
                session_id=session_id,
            )

            session_id = result["session_id"]

            print(
                f"\nAssistant: {result['answer']}\n"
            )

        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye! Have a great day.")
            break

        except Exception as exc:
            print(f"\nError: {exc}\n")


if __name__ == "__main__":
    main()



# """Interactive CLI for the session-based memory chatbot."""

# from datetime import datetime, timezone

# from app.chat import chat
# from app.database import Database


# def format_timestamp(value: str) -> str:
#     """Convert a SQLite UTC timestamp to local time.

#     Args:
#         value (str): SQLite timestamp.

#     Returns:
#         str: Formatted local date and time.
#     """
#     if not value:
#         return "N/A"

#     try:
#         utc_time = datetime.strptime(
#             value,
#             "%Y-%m-%d %H:%M:%S",
#         ).replace(tzinfo=timezone.utc)

#         return utc_time.astimezone().strftime(
#             "%Y-%m-%d %H:%M:%S"
#         )
#     except ValueError:
#         return value


# def display_history_table(messages: list[dict]) -> None:
#     """Display stored messages in a five-column table.

#     Args:
#         messages (list[dict]): Messages retrieved from SQLite.
#     """
#     if not messages:
#         print("\nNo messages found.\n")
#         return

#     columns = [
#         "session_id",
#         "role",
#         "content",
#         "created_at",
#         "updated_at",
#     ]

#     widths = {
#         "session_id": 36,
#         "role": 9,
#         "content": 40,
#         "created_at": 19,
#         "updated_at": 19,
#     }

#     def format_cell(value: str, width: int) -> str:
#         """Fit a value into a fixed-width table cell."""
#         text = str(value).replace("\n", " ")

#         if len(text) > width:
#             return text[: width - 3] + "..."

#         return text.ljust(width)

#     def make_row(values: dict) -> str:
#         """Format a row using the five database columns."""
#         return "| " + " | ".join(
#             format_cell(values[column], widths[column])
#             for column in columns
#         ) + " |"

#     separator = "+-" + "-+-".join(
#         "-" * widths[column]
#         for column in columns
#     ) + "-+"

#     print("\n" + separator)

#     print(
#         make_row({
#             column: column.upper()
#             for column in columns
#         })
#     )

#     print(separator)

#     for item in messages:
#         row = {
#             "session_id": item["session_id"],
#             "role": item["role"],
#             "content": item["content"],
#             "created_at": format_timestamp(
#                 item["created_at"]
#             ),
#             "updated_at": format_timestamp(
#                 item["updated_at"]
#             ),
#         }

#         print(make_row(row))

#     print(separator)
#     print(f"\nTotal messages: {len(messages)}\n")


# def main() -> None:
#     """Run the interactive chatbot."""
#     db = Database("chat_history.db")

#     session_id: str | None = None

#     commands = (
#         "/new, /resume, /id, /memory, "
#         "/history, /status, /get N, /help, /exit"
#     )

#     print("\n===================================")
#     print("     SHORT-TERM MEMORY CHAT")
#     print("===================================")
#     print("Commands:", commands)
#     print("===================================\n")

#     while True:
#         try:
#             user_input = input("You: ").strip()

#             if not user_input:
#                 continue

#             command = user_input.lower()

#             if command == "/exit":
#                 print("\nGoodbye! Conversation history saved.")
#                 break

#             if command == "/help":
#                 print("\nCommands:", commands, "\n")
#                 continue

#             if command == "/new":
#                 session_id = None

#                 print(
#                     "\nStarted a new session. "
#                     "Previous history remains stored.\n"
#                 )
#                 continue

#             if command == "/resume":
#                 saved_id = input(
#                     "Enter session ID: "
#                 ).strip()

#                 if (
#                     not saved_id
#                     or not db.session_exists(saved_id)
#                 ):
#                     print(
#                         "\nNo stored session found "
#                         "for that ID.\n"
#                     )
#                     continue

#                 session_id = saved_id

#                 print(
#                     f"\nResumed session: {session_id}"
#                 )
#                 print(
#                     "Stored history is available "
#                     "for retrieval.\n"
#                 )
#                 continue

#             if command == "/id":
#                 print(
#                     f"\nSession ID: "
#                     f"{session_id or 'None'}\n"
#                 )
#                 continue

#             if command.startswith("/"):
#                 valid_commands = {
#                     "/memory",
#                     "/history",
#                     "/status",
#                 }

#                 if (
#                     command not in valid_commands
#                     and not command.startswith("/get ")
#                 ):
#                     print(
#                         "\nUnknown command. "
#                         "Type /help.\n"
#                     )
#                     continue

#                 if session_id is None:
#                     print(
#                         "\nNo active session yet.\n"
#                     )
#                     continue

#                 if command == "/status":
#                     count = db.get_message_count(
#                         session_id
#                     )

#                     print("\n--- SESSION STATUS ---")
#                     print(f"Session ID: {session_id}")
#                     print(f"Stored messages: {count}")
#                     print("Recent context limit: 10 messages")
#                     print("Historical retrieval: Enabled")
#                     print()
#                     continue

#                 if command.startswith("/get "):
#                     try:
#                         number = int(
#                             command.split()[1]
#                         )

#                         record = db.get_message_by_number(
#                             session_id=session_id,
#                             number=number,
#                         )

#                         if record:
#                             display_history_table([record])
#                         else:
#                             print(
#                                 "\nNo such user message.\n"
#                             )

#                     except (ValueError, IndexError):
#                         print("\nUsage: /get 5\n")

#                     continue

#                 if command == "/memory":
#                     messages = db.get_recent_messages(
#                         session_id=session_id,
#                         limit=10,
#                     )

#                     print(
#                         "\n--- LAST 10 MESSAGES ---"
#                     )

#                     display_history_table(messages)
#                     continue

#                 if command == "/history":
#                     messages = db.get_all_messages(
#                         session_id=session_id,
#                     )

#                     print(
#                         "\n--- FULL SESSION HISTORY ---"
#                     )

#                     display_history_table(messages)
#                     continue

#             # Normal conversation.
#             result = chat(
#                 db=db,
#                 message=user_input,
#                 session_id=session_id,
#             )

#             session_id = result["session_id"]

#             print(
#                 f"\nAssistant: {result['answer']}\n"
#             )

#         except (KeyboardInterrupt, EOFError):
#             print(
#                 "\nGoodbye! Conversation history saved."
#             )
#             break

#         except Exception as exc:
#             print(f"\nError: {exc}\n")


# if __name__ == "__main__":
#     main()
