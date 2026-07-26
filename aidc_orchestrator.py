"""Builder for the nc-aidc-orchestrator agent (deployed as NC-Document-Controller).

The orchestrator is the single interface for all document requests. It handles
document-location queries directly via the shared Foundry toolbox and delegates
document generation and impact assessment to its two sub-agents, which are
attached to it as tools.
"""

from __future__ import annotations

from agent_framework import Agent, FunctionTool, ToolTypes
from agent_framework.foundry import FoundryChatClient

from agents._shared import build_agent

AGENT_NAME = "nc-aidc-orchestrator"
INSTRUCTIONS_FILE = "aidc_orchestrator_instructions.md"
DESCRIPTION = (
    "Nexa Holdings AI Document Controller orchestrator: routes document "
    "requests, coordinates its sub-agents, and returns the final result."
)


def build_aidc_orchestrator(
    chat_client: FoundryChatClient,
    toolbox: ToolTypes,
    subagent_tools: list[FunctionTool],
) -> Agent:
    """Build the nc-aidc-orchestrator agent.

    Args:
        chat_client: The shared Foundry chat client.
        toolbox: The shared toolbox MCP tool.
        subagent_tools: The sub-agents exposed as tools (document generator and
            impact assessor), produced via :meth:`Agent.as_tool`.

    Returns:
        The configured :class:`~agent_framework.Agent`.
    """
    return build_agent(
        chat_client,
        name=AGENT_NAME,
        instructions_file=INSTRUCTIONS_FILE,
        description=DESCRIPTION,
        tools=[toolbox, *subagent_tools],
    )
