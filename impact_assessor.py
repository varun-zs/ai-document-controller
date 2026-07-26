"""Builder for the nc-aidc-impact-assessor sub-agent.

The Impact Assessor determines which documents are affected by a change and
gates updates behind approvals. It runs in-process inside the
NC-Document-Controller container and is exposed to the orchestrator as a tool.
All of its capabilities (WorkIQ SharePoint and the impact-assessment
skill) are provided by the shared Foundry toolbox.
"""

from __future__ import annotations

from agent_framework import Agent, ToolTypes
from agent_framework.foundry import FoundryChatClient

from agents._shared import build_agent

AGENT_NAME = "nc-aidc-impact-assessor"
INSTRUCTIONS_FILE = "impact_assessor_instructions.md"
DESCRIPTION = (
    "Assesses the organisational impact of a proposed change or document, "
    "identifies affected documents, and returns the required approvers to the "
    "orchestrator."
)


def build_impact_assessor(
    chat_client: FoundryChatClient, toolbox: ToolTypes
) -> Agent:
    """Build the nc-aidc-impact-assessor sub-agent.

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
