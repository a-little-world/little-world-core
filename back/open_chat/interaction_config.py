"""Per-interaction Open Chat configuration for Little World automations.

These values are sent with every interaction so the automations do not depend
on mutable or missing defaults on pre-provisioned Open Chat bots.
"""

DEFAULT_OPEN_CHAT_MESSAGE_CONTEXT = 20
DEFAULT_OPEN_CHAT_MAX_TOKENS = 2048
DEFAULT_OPEN_CHAT_SUGGESTION_MAX_TOKENS = 1024
DEFAULT_OPEN_CHAT_BASIC_TEMPERATURE = 0.2
DEFAULT_OPEN_CHAT_SUGGESTION_TEMPERATURE = 0.1

# Reply-suggestion context bounds. The conversation transcript and the support
# handbook/templates are injected into the system prompt, so both are capped to
# keep prompt size (and cost) predictable.
DEFAULT_OPEN_CHAT_SUGGESTION_HISTORY_LIMIT = 12
DEFAULT_OPEN_CHAT_SUGGESTION_HISTORY_MAX_CHARS = 8000
DEFAULT_OPEN_CHAT_SUGGESTION_HISTORY_MESSAGE_MAX_CHARS = 2000
DEFAULT_OPEN_CHAT_SUPPORT_CONTEXT_MAX_CHARS = 12000


def build_interaction_overrides(
    *,
    system_prompt: str,
    tools: list[str],
    context: int = DEFAULT_OPEN_CHAT_MESSAGE_CONTEXT,
    max_tokens: int = DEFAULT_OPEN_CHAT_MAX_TOKENS,
    temperature: float | None = None,
) -> dict[str, object]:
    overrides: dict[str, object] = {
        "system_prompt": system_prompt,
        "context": context,
        "max_tokens": max_tokens,
        "tools": tools,
    }
    if temperature is not None:
        overrides["temperature"] = temperature
    return overrides
