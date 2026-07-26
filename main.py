"""Container entry point for the NC-Document-Controller hosted agent.

Builds the orchestrator (``nc-aidc-orchestrator``) with its two sub-agents
exposed as tools, all wired to the shared Foundry toolbox, and serves it over
the Foundry Responses protocol.

The Microsoft Agent Framework hosting runtime listens on port 8088 and exposes
an OpenAI-compatible ``/responses`` endpoint, which is the contract required by
``az cognitiveservices agent create --protocol responses``.
"""

from __future__ import annotations

import asyncio

from agent_framework import Agent
from agent_framework_foundry_hosting import ResponsesHostServer

from agents import aidc_orchestrator, document_generator, impact_assessor
from agents._shared import build_chat_client, build_toolbox_tool


def build_orchestrator() -> Agent:
    """Assemble the orchestrator with its sub-agents attached as tools.

    A single Foundry chat client and a single toolbox MCP tool are shared by all
    three agents. Each sub-agent is converted into a tool the orchestrator can
    call to delegate work, matching the routing logic in the orchestrator's
    instructions.

    Returns:
        The fully-wired orchestrator :class:`~agent_framework.Agent`.
    """
    chat_client = build_chat_client()
    toolbox = build_toolbox_tool()

    generator = document_generator.build_document_generator(chat_client, toolbox)
    assessor = impact_assessor.build_impact_assessor(chat_client, toolbox)

    subagent_tools = [
        generator.as_tool(
            name=document_generator.AGENT_NAME,
            description=document_generator.DESCRIPTION,
        ),
        assessor.as_tool(
            name=impact_assessor.AGENT_NAME,
            description=impact_assessor.DESCRIPTION,
        ),
    ]

    return aidc_orchestrator.build_aidc_orchestrator(
        chat_client, toolbox, subagent_tools
    )


async def main() -> None:
    """Build the orchestrator and serve it over the Foundry Responses protocol."""
    await ResponsesHostServer(build_orchestrator()).run_async()


if __name__ == "__main__":
    asyncio.run(main())
