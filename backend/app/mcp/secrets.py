"""Write-only MCP secrets (M52) — the A2A credentials pattern (spec §19.3),
applied to an MCP server's stdio `env` and HTTP `headers`.

- reads mask every value (`***`): the API never returns what it stored;
- writes merge: a value of `***` keeps what is stored, `null` removes the
  key, anything else replaces it — so a UI round-trip of a masked record
  cannot clobber a secret;
- `env:VAR_NAME` values are resolved from the process environment at
  connect time, so a credential can stay out of the database entirely.
"""

from __future__ import annotations

import os
from typing import Any

MASK = "***"


def mask_map(values: dict[str, Any] | None) -> dict[str, str] | None:
    if values is None:
        return None
    return dict.fromkeys(values, MASK)


def merge_secret_map(
    existing: dict[str, Any] | None, incoming: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Apply a PATCH: None clears everything; per key, MASK keeps, None
    removes, else replaces."""
    if incoming is None:
        return None
    merged = dict(existing or {})
    for key, value in incoming.items():
        if value is None:
            merged.pop(key, None)
        elif value == MASK:
            if key not in merged:
                continue  # a mask for a key we never had is nothing
        else:
            merged[key] = value
    return merged


def resolve_secret_map(values: dict[str, Any] | None) -> dict[str, str]:
    """Apply the env:VAR_NAME indirection; every value becomes a string."""
    out: dict[str, str] = {}
    for key, value in (values or {}).items():
        if isinstance(value, str) and value.startswith("env:"):
            out[str(key)] = os.environ.get(value[4:], "")
        else:
            out[str(key)] = str(value)
    return out


def secret_strings(values: dict[str, Any] | None) -> list[str]:
    """The resolved values, for the sanitizer's `extra_secrets`."""
    return [v for v in resolve_secret_map(values).values() if v]
