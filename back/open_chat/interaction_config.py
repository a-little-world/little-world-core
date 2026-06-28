"""Safe Open Chat interaction overrides for Little World bots.

Open Chat ``context`` is the number of prior *interaction chat messages* to load,
not a token budget. The default bots use ``qwen3-8b-instruct_vllm`` (8192 tokens).
Keep message history and tool payloads small so multi-round tool use stays in window.
"""

# Aligned with backend/little_world_default_bots/*.json in open-chat-go.
DEFAULT_OPEN_CHAT_MESSAGE_CONTEXT = 20
DEFAULT_OPEN_CHAT_MAX_TOKENS = 2048
DEFAULT_OPEN_CHAT_SUGGESTION_MAX_TOKENS = 1024
DEFAULT_OPEN_CHAT_BASIC_TEMPERATURE = 0.2
DEFAULT_OPEN_CHAT_SUGGESTION_TEMPERATURE = 0.1


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
