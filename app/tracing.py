import os
from dotenv import load_dotenv
from langfuse import get_client
from langfuse.langchain import CallbackHandler

load_dotenv()

def is_tracing_enabled() -> bool:
    """Check whether Langfuse credentials are configured.

    Returns:
        bool: True when both required API keys are present.
    """
    return bool(
        os.getenv("LANGFUSE_PUBLIC_KEY")
        and os.getenv("LANGFUSE_SECRET_KEY")
    )


def get_trace_handler() -> CallbackHandler | None:
    """Create a Langfuse callback handler when configured.

    Returns:
        CallbackHandler | None: Handler or None when tracing is disabled.
    """
    if not is_tracing_enabled():
        return None

    return CallbackHandler()


def flush_traces() -> None:
    """Flush pending Langfuse telemetry when configured."""
    if is_tracing_enabled():
        get_client().flush()
