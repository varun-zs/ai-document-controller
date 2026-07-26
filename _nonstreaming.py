"""An :class:`~agent_framework.Agent` that never streams the model call.

Why this exists
---------------
The NC-Document-Controller model (an Anthropic model served through the Foundry
Responses gateway) emits tool calls over the *streaming* Responses protocol in a
shape the Agent Framework's streaming parser cannot decode, so every streamed
turn silently loses its tool calls:

- ``response.output_item.added`` first declares the assistant output item as
  ``type: "message"`` (id ``msg_...``),
- the gateway then interleaves ``response.output_text.delta`` **and**
  ``response.function_call_arguments.delta`` events on that *same* item, and
- only at ``response.output_item.done`` does the item's ``type`` flip to
  ``"function_call"`` (carrying the tool ``name`` and ``arguments``).

The framework commits to "text message" on the ``added`` event and discards the
function-call deltas, so a streamed run returns only the model's preamble (e.g.
"I'll search SharePoint now…") and stops — the tool is never invoked and the
user gets no result. The *non-streaming* Responses call returns the fully-formed
response object (item correctly typed ``function_call``), which the framework
parses correctly, so the whole tool-calling loop works there.

Both callers of these agents request streaming:

- the ``ResponsesHostServer`` calls ``agent.run(stream=True, …)`` whenever the
  client's request has ``stream=true`` (the default in the Foundry playground),
  and
- :meth:`Agent.as_tool` runs sub-agents with ``stream=True`` and then awaits
  ``get_final_response()``.

:class:`NonStreamingAgent` overrides :meth:`run` so that a ``stream=True`` call
executes the model turn(s) **non-streaming** under the hood and then replays the
finished messages as a :class:`~agent_framework.ResponseStream`. That keeps the
streaming contract both callers depend on (async iteration of updates *and*
``get_final_response()``) while routing the actual model call through the code
path the gateway's output can be parsed on. The only user-visible trade-off is
that the final answer arrives in one chunk rather than token-by-token — a
complete answer instead of none.

Remove this shim once the gateway emits a spec-compliant streamed function call
(item typed ``function_call`` from ``output_item.added`` onward) or the
framework's streaming parser reconciles the ``message`` → ``function_call`` type
change.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_framework import Agent, AgentResponseUpdate, ResponseStream

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from agent_framework import AgentResponse


class NonStreamingAgent(Agent):
    """An :class:`~agent_framework.Agent` whose streamed runs execute non-streaming.

    A ``stream=False`` call behaves exactly like the base agent. A ``stream=True``
    call runs the agent non-streaming and re-emits the resulting messages as a
    :class:`~agent_framework.ResponseStream`, working around the Foundry gateway's
    unparseable streamed tool calls (see the module docstring).
    """

    def run(  # type: ignore[override]
        self,
        messages: Any = None,
        *,
        stream: bool = False,
        **kwargs: Any,
    ) -> Any:
        """Run the agent, forcing the underlying model call to be non-streaming.

        For ``stream=False`` this defers entirely to :class:`~agent_framework.Agent`.
        For ``stream=True`` it returns a :class:`~agent_framework.ResponseStream`
        backed by a single non-streaming run, so both async iteration (the hosting
        server) and :meth:`~agent_framework.ResponseStream.get_final_response`
        (:meth:`Agent.as_tool`) keep working.
        """
        if not stream:
            return Agent.run(self, messages, stream=False, **kwargs)

        # Holds the finished non-streaming response so the finalizer can return the
        # real AgentResponse (with its text, usage, user_input_requests, etc.)
        # rather than a reconstruction from the replayed updates.
        finished: dict[str, AgentResponse] = {}

        async def _replay() -> AsyncIterator[AgentResponseUpdate]:
            response = await Agent.run(self, messages, stream=False, **kwargs)
            finished["response"] = response
            for message in response.messages:
                yield AgentResponseUpdate(
                    contents=list(message.contents),
                    role=message.role,
                    response_id=getattr(response, "response_id", None),
                    message_id=getattr(message, "message_id", None),
                    author_name=getattr(message, "author_name", None),
                )

        def _finalizer(_updates: Sequence[AgentResponseUpdate]) -> AgentResponse:
            return finished["response"]

        return ResponseStream(_replay(), finalizer=_finalizer)
