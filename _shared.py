"""Shared builders for the NC-Document-Controller hosted agent.

The orchestrator and both sub-agents are Microsoft Agent Framework
:class:`~agent_framework.Agent` instances backed by a single Foundry chat
client and wired to the shared, externally-managed Foundry toolbox through a
client-side :class:`~agents._toolbox.FoundryToolbox` (vendored — the pinned
hosting alpha predates the upstream helper; see ``agents/_toolbox.py``). The
toolbox sits behind the Azure AI Services gateway, which rejects unauthenticated
requests, so the tool must attach an Entra bearer token on every MCP call. The
same :class:`~azure.identity.DefaultAzureCredential` is shared by the chat client
and the toolbox. A single toolbox instance is shared across all three agents:
the orchestrator connects it once and the sub-agents reuse the live connection
(``Agent.run`` skips already-connected MCP tools), so no per-agent lifecycle
management is required here.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential

from agents._nonstreaming import NonStreamingAgent
from agents._toolbox import FoundryToolbox

from config import get_settings

# Label the shared toolbox is surfaced under on every agent.
TOOLBOX_TOOL_NAME = "nc-foundry-toolbox-sivris-core"


def read_instructions(filename: str) -> str:
    """Read an agent's system instructions from its markdown file.

    Args:
        filename: The instructions markdown filename, resolved relative to the
            ``agents`` package directory.

    Returns:
        The instructions text.

    Raises:
        RuntimeError: if the instructions file cannot be found.
    """
    path = Path(__file__).resolve().parent / filename
    if not path.exists():
        raise RuntimeError(f"Instructions file not found: {path}")
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def build_credential() -> DefaultAzureCredential:
    """Build the Entra credential shared by the chat client and the toolbox.

    Returns:
        A process-wide :class:`~azure.identity.DefaultAzureCredential`. In the
        deployed container this resolves to the agent's managed identity.
    """
    return DefaultAzureCredential()


def build_chat_client() -> FoundryChatClient:
    """Build the Foundry chat client shared by every agent.

    Returns:
        A :class:`~agent_framework.foundry.FoundryChatClient` bound to the
        configured project endpoint and model deployment.
    """
    settings = get_settings()
    return FoundryChatClient(
        project_endpoint=settings.foundry_project_endpoint,
        model=settings.foundry_model,
        credential=build_credential(),
    )


def build_toolbox_tool() -> FoundryToolbox:
    """Build the shared toolbox as a client-side authenticated MCP tool.

    Unlike a service-executed hosted MCP tool, :class:`FoundryToolbox` attaches
    a fresh Entra bearer token to every request, which the Azure AI Services
    gateway in front of the project toolbox requires (an unauthenticated call
    is rejected with ``401 PermissionDenied``).

    Returns:
        A connected-on-first-use :class:`FoundryToolbox` pointing at the
        configured toolbox MCP endpoint.
    """
    settings = get_settings()
    return FoundryToolbox(
        build_credential(),
        url=settings.foundry_toolbox_mcp_url,
        name=TOOLBOX_TOOL_NAME,
    )


def build_agent(
    chat_client: FoundryChatClient,
    *,
    name: str,
    instructions_file: str,
    description: str,
    tools: list,
) -> Agent:
    """Create an :class:`~agent_framework.Agent` from an instructions file.

    Args:
        chat_client: The shared Foundry chat client.
        name: The agent's stable name.
        instructions_file: The instructions markdown filename (in ``agents/``).
        description: A short human-readable description for the agent.
        tools: The tools available to the agent (typically the shared toolbox,
            plus sub-agent tools for the orchestrator).

    Returns:
        The configured agent. A :class:`~agents._nonstreaming.NonStreamingAgent`
        is used (rather than a plain :class:`~agent_framework.Agent`) because the
        Foundry gateway emits streamed tool calls in a shape the framework's
        streaming parser drops; running non-streaming under the hood keeps the
        tool-calling loop working. See ``agents/_nonstreaming.py``.
    """
    return NonStreamingAgent(
        client=chat_client,
        name=name,
        description=description,
        instructions=read_instructions(instructions_file),
        tools=tools,
        default_options={"store": False},
    )
