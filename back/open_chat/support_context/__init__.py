"""Loadable support context (handbook + reply templates) for reply suggestions.

The reply-suggestion interaction can only be steered through the system prompt,
so the Support Handbook and message templates are committed as markdown here and
injected into that prompt. ``README.md`` documents the convention and is never
loaded; add real content to ``handbook.md`` / ``message_templates.md``.

Files that contain only HTML-comment scaffolds resolve to an empty context, so
the feature stays dark (and prompts stay byte-identical) until real content is
dropped in.
"""

import re
from pathlib import Path

from django.conf import settings

SUPPORT_CONTEXT_DIR = Path(__file__).resolve().parent

# Explicit allow-list (rather than globbing) so README.md is never loaded.
CONTENT_FILENAMES = ("handbook.md", "message_templates.md")

DEFAULT_MAX_CHARS = 12000

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def resolve_support_context_dir(directory: str | Path | None = None) -> Path:
    """Resolve the support-context directory.

    Precedence: explicit ``directory`` argument, then
    ``settings.OPEN_CHAT_SUPPORT_CONTEXT_DIR``, then the committed directory.
    """
    if directory is not None:
        return Path(directory)
    override = getattr(settings, "OPEN_CHAT_SUPPORT_CONTEXT_DIR", None)
    if override:
        return Path(override)
    return SUPPORT_CONTEXT_DIR


def load_support_context(*, directory: str | Path | None = None, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Return the concatenated support-context content, or ``""`` when absent.

    HTML comments are stripped so scaffold files do not count as content. The
    result is truncated to ``max_chars`` (``None``/``0`` disables truncation).
    """
    base_dir = resolve_support_context_dir(directory)
    chunks: list[str] = []
    for filename in CONTENT_FILENAMES:
        path = base_dir / filename
        if not path.is_file():
            continue
        cleaned = _HTML_COMMENT_RE.sub("", path.read_text(encoding="utf-8")).strip()
        if cleaned:
            chunks.append(cleaned)

    context = "\n\n---\n\n".join(chunks).strip()
    if not context:
        return ""
    if max_chars and len(context) > max_chars:
        context = context[:max_chars].rstrip()
    return context


def build_support_context_prompt_section(
    *, directory: str | Path | None = None, max_chars: int = DEFAULT_MAX_CHARS
) -> str:
    """Return the labeled support-context block, or ``""`` when there is none."""
    context = load_support_context(directory=directory, max_chars=max_chars)
    if not context:
        return ""
    return f"Support handbook and reply templates (authoritative guidance — follow when drafting):\n{context}"
