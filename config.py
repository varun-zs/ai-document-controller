"""Runtime configuration for the NC-Document-Controller hosted agent.

Loads settings from environment variables (with a local ``.env`` file for
development via python-dotenv). In production the Foundry hosted-agent runtime
injects ``FOUNDRY_PROJECT_ENDPOINT`` and ``AZURE_AI_MODEL_DEPLOYMENT_NAME`` into
the container automatically; the deploy pipeline additionally injects
``FOUNDRY_TOOLBOX_MCP_URL``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

# Load variables from a local .env file if present. Existing environment
# variables always take precedence over values defined in the file.
load_dotenv(override=False)

# Default model deployment used when none is provided by the environment.
DEFAULT_MODEL = "claude-sonnet-4-6"


def _require(name: str, default: str | None = None) -> str:
    """Return an environment variable, falling back to ``default``.

    Raises:
        RuntimeError: if the variable is unset and no default is provided.
    """
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Required environment variable '{name}' is not set.")
    return value


@dataclass(frozen=True)
class Settings:
    """Strongly-typed runtime settings sourced from the environment."""

    # Foundry project endpoint (auto-injected by the hosted-agent runtime).
    foundry_project_endpoint: str
    # Model deployment name shared by the orchestrator and both sub-agents.
    foundry_model: str
    # Shared, externally-managed Foundry toolbox exposed over MCP.
    foundry_toolbox_mcp_url: str

    @classmethod
    def from_env(cls) -> "Settings":
        """Build a :class:`Settings` instance from environment variables."""
        return cls(
            foundry_project_endpoint=_require("FOUNDRY_PROJECT_ENDPOINT"),
            # The Foundry hosting runtime injects AZURE_AI_MODEL_DEPLOYMENT_NAME;
            # fall back to FOUNDRY_MODEL for compatibility, then to the default.
            foundry_model=os.getenv(
                "AZURE_AI_MODEL_DEPLOYMENT_NAME",
                os.getenv("FOUNDRY_MODEL", DEFAULT_MODEL),
            ),
            foundry_toolbox_mcp_url=_require("FOUNDRY_TOOLBOX_MCP_URL"),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings.from_env()
