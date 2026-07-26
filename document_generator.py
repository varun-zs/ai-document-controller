"""Builder for the nc-aidc-document-generator sub-agent.

The Document Generator physically creates and files Nexa Holdings Word
documents. It runs in-process inside the NC-Document-Controller container and is
exposed to the orchestrator as a tool. All of its capabilities (WorkIQ Word,
WorkIQ SharePoint, and the document skills) are provided by the shared
Foundry toolbox.
"""

from __future__ import annotations

from agent_framework import Agent, ToolTypes
from agent_framework.foundry import FoundryChatClient

from agents._shared import build_agent

AGENT_NAME = "nc-aidc-document-generator"
INSTRUCTIONS_FILE = "document_generator_instructions.md"
DESCRIPTION = (
    "Physically creates, populates and files Nexa Holdings Word documents "
    "(such as the Annual Business Plan) from SharePoint templates."
)


def build_document_generator(
    chat_client: FoundryChatClient, toolbox: ToolTypes
) -> Agent:
    """Build the nc-aidc-document-generator sub-agent.

    Args:
        chat_client: The shared Foundry chat client.
        toolbox: The shared toolbox MCP tool.

    Returns:
        The configured :class:`~agent_framework.Agent`.
    """
    return build_agent(
        chat_client,
        name=AGENT_NAME,
        instructions_file=INSTRUCTIONS_FILE,
        description=DESCRIPTION,
        tools=[toolbox],
    )
