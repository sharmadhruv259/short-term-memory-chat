
import os

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq

from app.database import Database
from app.memory_tools import build_memory_tools


load_dotenv()


def _extract_answer(result: dict) -> str:
    """Extract the final assistant response from an agent result.

    Args:
        result (dict): Agent execution result.

    Returns:
        str: Final assistant response or a fallback message.
    """
    for message in reversed(result.get("messages", [])):
        if isinstance(message, AIMessage) and not message.tool_calls:
            content = message.content

            if isinstance(content, str) and content.strip():
                return content

            if isinstance(content, list):
                text = "\n".join(
                    block["text"]
                    for block in content
                    if isinstance(block, dict)
                    and isinstance(block.get("text"), str)
                )

                if text.strip():
                    return text

    return "No historical information could be retrieved."


def build_agents(
    db: Database,
    conversation_id: str,
) -> dict:
    """Build the main chat agent and specialized memory agent.

    Args:
        db (Database): Database containing conversation history.
        conversation_id (str): Identifier of the active conversation.

    Returns:
        dict: Main and memory agents with their associated tools.

    Raises:
        ValueError: If GROQ_API_KEY is not configured.
    """
    if not os.getenv("GROQ_API_KEY"):
        raise ValueError("GROQ_API_KEY is missing from the environment")

    model = ChatGroq(
        model="openai/gpt-oss-120b",
        temperature=0.1,
    )

    memory_tools = build_memory_tools(db, conversation_id)

    # Specialized agent responsible for historical retrieval.
    memory_agent = create_agent(
        model=model,
        tools=memory_tools,
        system_prompt=(
            "You are the Memory Agent. Answer questions about previous "
            "conversation content using the available memory tools. "
            "Retrieve evidence before making claims about historical messages. "
            "Use get_message_by_number for exact turn lookups. "
            "Use search_conversation for historical topics or phrases. "
            "Use get_conversation_summary for summarized context. "
            "Distinguish exact stored messages from summaries. "
            "Never invent conversation details. "
            "If evidence is unavailable, clearly say so."
        ),
    )

    @tool
    def ask_memory_agent(question: str) -> str:
        """Retrieve reliable historical conversation information.

        Args:
            question (str): Question about earlier conversation content.

        Returns:
            str: Evidence-based answer from the Memory Agent.
        """
        result = memory_agent.invoke(
            {
                "messages": [
                    HumanMessage(content=question)
                ]
            }
        )

        return _extract_answer(result)

    # Main agent handles conversation and delegates memory questions.
    main_agent = create_agent(
        model=model,
        tools=[ask_memory_agent],
        system_prompt=(
            "You are the Main Chat Agent. Respond naturally to the user. "
            "You have access to recent conversation turns and a rolling "
            "summary of older conversation history. "
            "For questions requiring exact historical messages, previous "
            "decisions, or information not reliably available in the "
            "recent context, call ask_memory_agent. "
            "Do not guess historical facts. "
            "Use the Memory Agent's retrieved evidence when answering. "
            "For normal conversational questions, answer directly "
            "without calling the Memory Agent."
        ),
    )

    return {
        "main_agent": main_agent,
        "memory_agent": memory_agent,
        "memory_tools": memory_tools,
    }
