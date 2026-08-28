"""Untrusted fencing for remote-agent output (spec §19.5).

Every string a remote agent authored passes through here before reaching
any model context — tool results, gate questions embedded in traces, and
delivery bodies. The fence text lives in prompts/a2a_result_fence.md
(the §17 fixed never-follow-instructions paragraph, A2A flavor)."""

from app.prompts import load_prompt

_MAX_FENCED_CHARS = 8000


def fence_remote_output(text: str, *, agent_name: str, state: str = "completed") -> str:
    body = (text or "").strip()[:_MAX_FENCED_CHARS]
    return (
        load_prompt("a2a_result_fence")
        .replace("{agent_name}", agent_name.replace('"', "'"))
        .replace("{state}", state.replace('"', "'"))
        .replace("{output}", body or "(empty)")
    )
