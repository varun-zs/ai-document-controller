"""Client-side authenticated MCP tool for the shared Foundry toolbox.

The pinned ``agent-framework-foundry-hosting==1.0.0a260618`` (required because
it speaks agent protocol 1.0.0, the version the current Foundry hosted
environment serves) predates the ``FoundryToolbox`` helper that later alphas
(a260630+) export. This module vendors the minimal equivalent on top of
:class:`agent_framework.MCPStreamableHTTPTool`:

- every outbound MCP request (the connection handshake as well as tool calls)
  carries a fresh Entra bearer token, which the Azure AI Services gateway in
  front of the project toolbox requires, and
- when running inside the hosted environment, the platform's per-request
  headers (e.g. ``x-agent-foundry-call-id``) are forwarded so the Foundry MCP
  proxy can resolve the caller context server-side; outside a request these
  resolve to no headers.

When the hosting pin moves to a260630 or later, this module can be replaced by
``from agent_framework_foundry_hosting import FoundryToolbox``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import httpx
from agent_framework import MCPStreamableHTTPTool

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

    from azure.core.credentials import TokenCredential

logger = logging.getLogger(__name__)

# Microsoft Entra scope for Foundry data-plane access.
DEFAULT_TOOLBOX_SCOPE = "https://ai.azure.com/.default"
# Default timeout (seconds) for toolbox MCP requests.
_DEFAULT_TIMEOUT = 120.0
# The only functions the toolbox is exposed to the model as. The toolbox has
# started *flattening* its underlying tools into the ``tools/list`` response
# (e.g. ``WorkIQSharePoint___findSite`` alongside the ``tool_search`` /
# ``call_tool`` meta-tools). Exposing those flattened names is dangerous: the
# model reformats the ``___`` separator into a dot (``WorkIQSharePoint.findSite``)
# when emitting the tool call, and the Foundry Responses API rejects any
# request whose historical function-call ``name`` does not match
# ``^[a-zA-Z0-9_-]+$`` (dots are illegal). That failed call is echoed back in
# the conversation history, so every subsequent turn 400s and the user gets no
# response at all. Restricting the exposed surface to the two meta-tools keeps
# real tool names (which may legally contain dots) inside ``call_tool``'s
# *arguments*, never in a function-name position.
_EXPOSED_TOOL_NAMES = ("tool_search", "call_tool")


def _platform_headers() -> dict[str, str]:
    """Return the hosting platform's per-request headers, if any.

    Inside the hosted environment the request-scoped context carries headers
    such as ``x-agent-foundry-call-id``. Outside a request (local runs, the
    connection handshake at startup) there are none. Failures are swallowed:
    authentication never depends on these headers.
    """
    try:
        from azure.ai.agentserver.core import get_request_context

        return dict(get_request_context().platform_headers())
    except Exception:  # noqa: BLE001 - headers are best-effort by design
        return {}


class _ToolboxAuth(httpx.Auth):
    """Injects a fresh bearer token and platform headers on every request."""

    def __init__(self, credential: TokenCredential, scope: str) -> None:
        self._credential = credential
        self._scope = scope

    def _apply(self, request: httpx.Request, token: str) -> None:
        request.headers["Authorization"] = f"Bearer {token}"
        for key, value in _platform_headers().items():
            request.headers[key] = value

    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        # Synchronous path (used only outside a running event loop, e.g. by a
        # sync httpx client). azure-identity caches the token internally and
        # only refreshes near expiry, so calling get_token per request is cheap.
        self._apply(request, self._credential.get_token(self._scope).token)
        yield request

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        # ``DefaultAzureCredential.get_token`` is a BLOCKING network call
        # (managed-identity/IMDS). httpx's default ``async_auth_flow`` runs the
        # sync ``auth_flow`` generator directly on the event loop, so doing the
        # token fetch there stalls the loop. During a live streamed chat that
        # stall tears down the Foundry Responses SSE stream mid tool call, so
        # the agent "tries to call the toolbox" and then the chat ends without
        # finishing. Fetch the token off the loop to keep streaming alive.
        token = (
            await asyncio.to_thread(self._credential.get_token, self._scope)
        ).token
        self._apply(request, token)
        yield request


def _toolbox_name_from_endpoint(endpoint: str) -> str:
    """Extract the toolbox name from a toolbox MCP endpoint URL."""
    segments = urlsplit(endpoint).path.split("/")
    if "toolboxes" in segments:
        idx = segments.index("toolboxes")
        if idx + 1 < len(segments) and segments[idx + 1]:
            return segments[idx + 1]
    return "toolbox"


class FoundryToolbox(MCPStreamableHTTPTool):
    """A Foundry toolbox exposed as an authenticated client-side MCP tool.

    The connection lifecycle is driven by the agent: the hosting server enters
    the agent, which connects the toolbox on first use and closes it (and the
    HTTP client it owns) at shutdown.
    """

    def __init__(
        self,
        credential: TokenCredential,
        *,
        url: str,
        name: str | None = None,
        token_scope: str = DEFAULT_TOOLBOX_SCOPE,
        load_prompts: bool = False,
        load_tools: bool = True,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the toolbox tool.

        Args:
            credential: Entra credential used for bearer tokens; in the deployed
                container this resolves to the agent's managed identity.

        Keyword Args:
            url: The toolbox MCP endpoint URL.
            name: The local tool name; derived from the URL when omitted.
            token_scope: The token scope to request.
            load_prompts: Whether to load prompts (toolboxes expose tools).
            load_tools: Whether to load tools.
            timeout: Request timeout in seconds for the HTTP client.
        """
        http_client = httpx.AsyncClient(
            auth=_ToolboxAuth(credential, token_scope),
            timeout=timeout,
        )
        super().__init__(
            name=name or _toolbox_name_from_endpoint(url),
            url=url,
            http_client=http_client,
            load_prompts=load_prompts,
            load_tools=load_tools,
            allowed_tools=_EXPOSED_TOOL_NAMES,
        )

    async def load_tools(self) -> None:
        """Load tools, degrading to an empty tool set on discovery failure.

        The toolbox fails the whole ``tools/list`` call when *any* of its tool
        sources cannot enumerate (e.g. the WorkIQ Microsoft 365 preview sources
        currently fail with ``TenantIdInvalid``). Without this guard that one
        server-side error aborts the agent's startup and every chat request
        dies with ``Failed to enter context manager``. The MCP session itself
        is healthy — only discovery failed — so log the failure loudly and let
        the agent continue without toolbox tools rather than taking the whole
        agent down.
        """
        try:
            await super().load_tools()
        except Exception as exc:  # noqa: BLE001 - degrade instead of crashing chat
            logger.error(
                "Toolbox '%s' tool discovery failed; continuing WITHOUT toolbox "
                "tools. Fix the toolbox's failing tool sources to restore them. "
                "Error: %s",
                self.name,
                exc,
            )
            return

        tool_names = [getattr(func, "name", "?") for func in self.functions]
        if tool_names:
            logger.info(
                "Toolbox '%s' loaded %d tool(s): %s",
                self.name,
                len(tool_names),
                ", ".join(tool_names),
            )
        else:
            logger.warning(
                "Toolbox '%s' loaded ZERO tools. The agent will be unable to "
                "call any toolbox tool (e.g. WorkIQ SharePoint / WorkIQ Word) "
                "and will only narrate its intent. Verify the toolbox's tool "
                "sources enumerate successfully.",
                self.name,
            )
