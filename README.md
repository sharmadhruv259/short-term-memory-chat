# Short-Term Memory Chatbot

A session-based AI chatbot built using **Python, LangChain, LangGraph, Groq, and SQLite**, designed to manage conversation history efficiently while maintaining a limited context window.

The chatbot automatically uses the latest 10 stored messages as conversational context and provides SQLite retrieval tools to access older messages whenever required.

## Overview

Traditional chatbots often send the entire conversation history to the LLM with every request, increasing token usage as conversations grow.

This project implements a simpler approach:

- Automatically includes the latest **10 previous messages** in the LLM context.
- Stores the complete conversation history in SQLite.
- Retrieves older messages on demand using LangChain tools.
- Maintains separate conversations using unique session IDs.
- Supports resuming previously stored sessions.
- Integrates Langfuse for LLM tracing and observability.
- Uses a single tool-enabled Main Agent.

This approach keeps the automatic context limited without permanently losing access to older conversation messages.

## Tech Stack

| Technology | Purpose |
|---|---|
| Python 3.10+ | Backend development |
| LangChain | Agent creation and tool integration |
| LangGraph | Agent execution framework |
| Groq | LLM inference |
| GPT-OSS 120B | Language model |
| SQLite | Persistent conversation storage |
| Langfuse | LLM tracing and monitoring |
| uv | Python dependency management |

## Project Structure

```text
short-term-memory-chat/
│
├── app/
│   ├── __init__.py
│   ├── agents.py
│   ├── chat.py
│   ├── cli.py
│   ├── database.py
│   ├── memory_tools.py
│   └── tracing.py
│
├── .env
├── .gitignore
├── .python-version
├── pyproject.toml
├── README.md
└── uv.lock
```

### File Responsibilities

| File | Description |
|---|---|
| `agents.py` | Creates the Main Agent with Groq and SQLite retrieval tools |
| `chat.py` | Handles user messages, recent context, agent execution, and response storage |
| `cli.py` | Provides the interactive terminal chatbot |
| `database.py` | Manages SQLite storage and session history |
| `memory_tools.py` | Provides tools to retrieve numbered messages and search previous messages |
| `tracing.py` | Handles Langfuse tracing and telemetry |

## System Architecture

```text
                   User
                    |
                    v
             CLI Interface
                (cli.py)
                    |
                    v
              Chat Workflow
                (chat.py)
                    |
          +---------+---------+
          |                   |
          v                   v
   SQLite Database      Main Chat Agent
    (database.py)         (agents.py)
          |                   |
          |             Groq LLM
          |                   |
          +---- Retrieval ----+
                 Tools
            (memory_tools.py)
                    |
                    v
             Final Response
                    |
                    v
             SQLite Storage
```

Langfuse monitors LLM and agent execution through tracing callbacks.

## Key Features

### 1. Session-Based Memory

Each conversation is associated with a unique `session_id`.

Messages from different sessions are stored separately, allowing the chatbot to maintain independent conversation histories.

### 2. Sliding Context Window

The chatbot automatically retrieves the latest 10 previous messages from SQLite and includes them with the current user message.

This prevents the automatic conversation context from growing indefinitely.

### 3. Historical Message Retrieval

Even when an earlier message is outside the recent context window, the Main Agent can retrieve it using SQLite tools.

Available tools:

**`get_message_by_number`**

Retrieves a numbered message from the current session. By default, numbering counts user messages only, starting at 1.

**`search_conversation`**

Searches stored messages within the current session using a keyword or phrase.

### 4. Persistent SQLite Storage

The database stores the complete conversation history in a single `messages` table.

| Field | Description |
|---|---|
| `session_id` | Unique session identifier |
| `role` | User or assistant |
| `content` | Message content |
| `created_at` | Message creation timestamp |
| `updated_at` | Message update timestamp |

SQLite automatically populates the timestamps when messages are inserted. The update timestamp changes only when explicitly updated.

### 5. Langfuse Integration

Langfuse provides observability for LLM and agent operations.

It helps inspect model interactions, tool usage, and execution behavior during development.

### 6. Interactive CLI

The project provides a terminal-based chatbot with a minimal interface.

Conversation history can also be inspected in a five-column table during development.

## Installation

### Prerequisites

- Python 3.10 or higher
- uv package manager
- Groq API key
- Langfuse credentials (optional)

### 1. Clone the repository

```bash
git clone <YOUR_REPOSITORY_URL>
cd short-term-memory-chat
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Configure environment variables

Create a `.env` file in the project root.

```env
GROQ_API_KEY=your_groq_api_key

LANGFUSE_PUBLIC_KEY=your_langfuse_public_key
LANGFUSE_SECRET_KEY=your_langfuse_secret_key
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

Langfuse configuration is optional. The chatbot can run without tracing when Langfuse credentials are not configured.

Use the appropriate Langfuse host URL for your account and deployment.

### 4. Run the chatbot

```bash
uv run python -m app.cli
```

## Example Usage

```text
===================================
         AI CHAT ASSISTANT
===================================
How can I help you today?

You: Hello
Assistant: Hello! How can I help you?

You: My name is Rahul.
Assistant: Nice to meet you, Rahul!

You: I am learning Python.
Assistant: That's great! What are you learning in Python?

You: What is my name?
Assistant: Your name is Rahul!
```

### Retrieving Older Messages

Suppose the conversation contains 30 stored messages.

Only the latest 10 previous messages are automatically included in the LLM context.

If the user asks:

```text
You: What was the first message I sent?
```

The Main Agent can call `get_message_by_number` to retrieve the first user message from SQLite.

The model's choice to invoke a tool is dynamic, so historical retrieval depends on successful tool selection and execution.

## Development Commands

The CLI supports optional commands for session management and debugging. They are not displayed on the welcome screen.

| Command | Description |
|---|---|
| `/new` | Start a new session |
| `/resume` | Resume an existing session by ID |
| `/id` | Display the current session ID |
| `/history` | Display complete session history |
| `/memory` | Display the latest 10 stored messages |
| `/get N` | Retrieve the Nth user message |
| `/status` | Display session information |
| `/exit` | Exit the chatbot |

The history table displays `session_id`, `role`, `content`, `created_at`, and `updated_at`.

## How It Works

1. A user sends a message through the CLI.
2. The application creates or reuses a session ID.
3. The latest 10 previous messages are retrieved from SQLite.
4. Those messages and the current user message are sent to the Main Agent.
5. The Main Agent generates a response using Groq.
6. When necessary, the agent uses SQLite retrieval tools to access older messages.
7. The user message and assistant response are stored in SQLite.
8. Langfuse records tracing information when configured.

## Design Considerations

**Limited automatic context:** The chatbot avoids passing the entire conversation history on every request.

**Persistent history:** Older messages remain available in SQLite even after leaving the recent context window.

**Session isolation:** Retrieval tools query messages using the active session ID.

**Simplified architecture:** A single Main Agent handles both conversation generation and historical retrieval.

**No selective fact extraction:** The project does not use SAVE, SKIP, UPDATE, memory-facts tables, or rolling summaries.

**Message ordering:** SQLite's internal `rowid` is used to retrieve messages in insertion order without adding another stored column.

## Future Improvements

- Build a web-based chat interface.
- Add a session history sidebar.
- Support renaming and deleting conversations.
- Implement pagination for long conversation histories.
- Add authentication for multi-user access.
- Improve retrieval using semantic search.
- Add automated integration testing.

## Conclusion

The Short-Term Memory Chatbot demonstrates how to combine **LangChain agents, Groq inference, SQLite persistence, and Langfuse observability** to build an AI assistant with efficient conversation management.

Its central design is straightforward:

**Recent messages for automatic context, complete SQLite history for storage, and retrieval tools for older information.**
