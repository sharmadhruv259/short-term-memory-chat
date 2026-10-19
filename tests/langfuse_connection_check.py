
"""Test Langfuse authentication and trace delivery."""

import logging

from dotenv import load_dotenv
from langfuse import get_client, observe


logging.basicConfig(level=logging.DEBUG)

load_dotenv()

client = get_client()

print("Authenticated:", client.auth_check())


@observe(name="test-langfuse-connection")
def test_tracing() -> str:
    """Generate a test trace.

    Returns:
        str: Confirmation message.
    """
    return "Langfuse tracing works!"


print("Result:", test_tracing())

client.flush()

print("Trace flush completed.")
