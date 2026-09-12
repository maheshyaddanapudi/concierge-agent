"""Untrusted-content fencing — the ONE choke point (M52, arch-H9).

Every string an external party authored — a remote agent's output, a fired
event's payload, a fetched feed item, a delivery body, a candidate answer
under evaluation, a memory extracted from any of those — passes through
`fence_body` before it is rendered into a model context. Two guarantees
the prompt fences alone could not give:

- **the delimiter is neutralized inside the payload**: any tag that looks
  like one of our fences (`<untrusted_…>`, `</untrusted_…>`,
  `<remembered_context>`) is escaped, so a payload can neither close the
  fence early nor open a forged one;
- **the fence carries a per-invocation token**: the opening and closing
  tags both carry `token="…"` drawn fresh for every render, so a payload
  cannot guess the boundary it would need to forge.

The fence TEXT stays in the prompt files (spec §13: prompts live in
`app/prompts/`); this module supplies the neutralized body and the token
that `{fence_token}` binds to. `render()` is the single renderer every
untrusted-bearing prompt goes through, in the consumer's own mode
(`format` or `replace`, the two the M49 golden harness knows).
"""

from __future__ import annotations

import re
import secrets
from typing import Any

EMPTY = "(empty)"
_FENCE_TAG_RE = re.compile(r"<(/?)\s*(untrusted_[a-z0-9_]*|remembered_context)\b", re.IGNORECASE)


def fence_token() -> str:
    """Twelve hex chars, fresh per render — unguessable by a payload."""
    return secrets.token_hex(6)


def neutralize(text: str) -> str:
    """Escape every fence-shaped tag inside the payload. The content is kept
    verbatim otherwise — the model still sees what was said, it just
    cannot be tricked about where the untrusted block ends."""
    return _FENCE_TAG_RE.sub(lambda m: f"&lt;{m.group(1)}{m.group(2)}", text)


def fence_body(text: str | None, *, max_chars: int) -> tuple[str, str]:
    """(neutralized, clipped body — `(empty)` when blank; fresh token)."""
    body = neutralize((text or "").strip())[: max(int(max_chars), 1)]
    return (body or EMPTY), fence_token()


def render(
    prompt: str,
    *,
    mode: str,
    body_var: str,
    body: str | None,
    max_chars: int,
    **vars: Any,
) -> str:
    """Render one untrusted-bearing prompt through the choke point.

    `prompt` is the loaded prompt text (the consumer keeps its own
    `load_prompt("…")` call, which the golden harness ties to it);
    `body_var` names the placeholder the untrusted content fills;
    every other placeholder comes from `vars`. The token is bound to
    `{fence_token}`, which the prompt's opening AND closing fence tags carry.
    """
    text, token = fence_body(body, max_chars=max_chars)
    values: dict[str, Any] = {**vars, body_var: text, "fence_token": token}
    if mode == "format":
        return prompt.format(**values)
    if mode == "replace":
        out = prompt
        for key, value in values.items():
            out = out.replace("{" + key + "}", str(value))
        return out
    raise ValueError(f"unknown render mode {mode!r}")


def quote_attr(value: str) -> str:
    """A prompt-tag attribute value: no quotes, no angle brackets."""
    return value.replace('"', "'").replace("<", "‹").replace(">", "›")
