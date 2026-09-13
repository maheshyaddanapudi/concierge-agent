"""Scriptable fake provider — how every test injects LLM behavior (spec §11).

Registered through the same @model_provider port as real adapters, so tests
exercise the identical resolution path (`get_model("fake:...")`) without ever
touching a provider SDK. Enabled via FAKE_LLM_ENABLED env.
"""

from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.messages.ai import UsageMetadata
from langchain_core.outputs import ChatGeneration, ChatResult

from app.config import get_config
from app.llm.port import ModelInfo, ModelParams, ProviderNotConfiguredError
from app.llm.registry import model_provider

_SCRIPT: deque[AIMessage | BaseException] = deque()
_SEEN_TOOLS: list[list[str]] = []
# the rendered text of every message on each captured call, so a test can
# assert what a surface (planner, aggregator, formatter) was actually told
_SEEN_PROMPTS: list[str] = []
# M51: when strict, a provider call made with a DB session open in the
# current task raises — the test-time enforcement of "claim → commit →
# call → write back" (spec §16.2, PLAN M51)
_STRICT_SESSIONS = False

# Whether an UNSCRIPTED structured-output call may fall back to a canned
# answer. True out of the box, so a keyless `docker compose up` and the curl
# demos still complete a run with no script in sight. The suite turns it OFF
# (conftest): inside a test a default is not a convenience but a hole — a
# planner default that becomes a direct answer, an index-0 condition choice,
# a 0% overlap verdict and an empty answer document will each carry a run to
# `completed`, so "the run completed" proves nothing about the surface the
# test was written to exercise. Tests that genuinely want the canned answer
# say so with `allow_defaults()`.
_ALLOW_DEFAULTS = True


# Every unscripted structured call made while defaults were off, in order.
# The raise below is the local diagnostic; THIS is what makes the rule
# stick. Several of the surfaces that make one of these calls wrap it in a
# broad `except Exception` and degrade to a fallback — the overlap judge
# treats an error as "no overlap" and saves — so an exception alone can be
# swallowed and the test still pass on exactly the silence it is meant to
# expose. conftest reads this list at the test boundary and fails the test
# whether or not anything caught the exception.
_UNSCRIPTED: list[str] = []


class UnscriptedStructuredCall(Exception):
    """An unscripted structured-output call while defaults are off."""


def unscripted_calls() -> list[str]:
    return list(_UNSCRIPTED)


def clear_unscripted_calls() -> None:
    _UNSCRIPTED.clear()


def set_strict_sessions(value: bool) -> None:
    global _STRICT_SESSIONS
    _STRICT_SESSIONS = value


def set_allow_defaults(value: bool) -> None:
    """Suite-wide policy hook (conftest sets False)."""
    global _ALLOW_DEFAULTS
    _ALLOW_DEFAULTS = value


def defaults_allowed() -> bool:
    return _ALLOW_DEFAULTS


@contextmanager
def allow_defaults() -> Iterator[None]:
    """Opt back in, for a test whose subject is genuinely elsewhere — a
    seed, an API shape, a guard that trips before any model is consulted."""
    global _ALLOW_DEFAULTS
    previous = _ALLOW_DEFAULTS
    _ALLOW_DEFAULTS = True
    try:
        yield
    finally:
        _ALLOW_DEFAULTS = previous


def _assert_no_open_session(where: str) -> None:
    if not _STRICT_SESSIONS:
        return
    from app.db import open_sessions

    n = open_sessions()
    if n:
        raise RuntimeError(
            f"provider call ({where}) made with {n} DB session(s) open in this task — "
            "compute the model/embedding result BEFORE opening the write transaction"
        )


_DEFAULT_USAGE = UsageMetadata(input_tokens=7, output_tokens=11, total_tokens=18)


def _message_text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "\n".join(parts)


def push_ai(
    content: str,
    tool_calls: list[dict[str, Any]] | None = None,
    delay_s: float | None = None,
) -> None:
    """Queue the next scripted response (FIFO across all fake model calls)."""
    msg = AIMessage(content=content, tool_calls=tool_calls or [])
    msg.usage_metadata = _DEFAULT_USAGE
    if delay_s:
        msg.additional_kwargs["__delay_s"] = delay_s
    _SCRIPT.append(msg)


def push_structured(schema: str, args: dict[str, Any]) -> None:
    """Queue one structured-output answer — the scripted form of what the
    fake used to invent. `schema` is the tool name LangChain binds for
    `with_structured_output` (PlannerOutput, OverlapVerdict, …)."""
    push_ai("", tool_calls=[{"name": schema, "args": args, "id": f"fake-{schema.lower()}"}])


def push_plan(
    entries: list[dict[str, Any]] | None = None,
    direct_answer: str | None = None,
    no_confident_match: bool = False,
) -> None:
    """The planner's answer for the next planning call."""
    push_structured(
        "PlannerOutput",
        {
            "entries": entries or [],
            "direct_answer": direct_answer,
            "no_confident_match": no_confident_match,
        },
    )


def push_overlap(
    percent: int = 0,
    match_type: str = "none",
    match_name: str | None = None,
    reasoning: str = "scripted verdict",
) -> None:
    """The §4 overlap judge's verdict for the next registry save. The default
    is a clean 0% — say so out loud where a test wants the save to go
    through, instead of leaning on the provider to invent it."""
    push_structured(
        "OverlapVerdict",
        {
            "overlap_percent": percent,
            "match_type": match_type if percent else "none",
            "match_id": None,
            "match_name": match_name,
            "reasoning": reasoning,
        },
    )


def push_condition(index: int) -> None:
    """The router's branch choice for the next conditional edge."""
    push_structured("ConditionChoice", {"index": index})


def push_answer_ui(components: list[dict[str, Any]] | None = None) -> None:
    """The formatter's answer document for the next formatting call.

    The default is ONE text component, not an empty list: the formatter
    treats an empty document as a failed generation and asks again, which
    would leave the second call unscripted for no reason a test cares about.
    """
    push_structured(
        "AnswerUi",
        {"components": components or [{"type": "text", "markdown": "scripted answer document"}]},
    )


def push_error(exc: BaseException) -> None:
    """Queue an exception: the next fake model call raises it (LLM error path)."""
    _SCRIPT.append(exc)


def seen_tools() -> list[list[str]]:
    """Tool names bound on each captured model call (isolation assertions)."""
    return list(_SEEN_TOOLS)


def clear_seen_tools() -> None:
    _SEEN_TOOLS.clear()


def seen_prompts() -> list[str]:
    """The text each captured model call was given (all messages joined)."""
    return list(_SEEN_PROMPTS)


def push_message(msg: AIMessage) -> None:
    if msg.usage_metadata is None:
        msg.usage_metadata = _DEFAULT_USAGE
    _SCRIPT.append(msg)


def clear_script() -> None:
    _SCRIPT.clear()
    _SEEN_TOOLS.clear()
    _SEEN_PROMPTS.clear()
    _UNSCRIPTED.clear()


def script_len() -> int:
    return len(_SCRIPT)


# The structured-output schemas this fake knows how to answer. Exactly the
# set whose canned reply carries a run to `completed` on its own.
_STRUCTURED_SCHEMAS = ("PlannerOutput", "ConditionChoice", "OverlapVerdict", "AnswerUi")


class ScriptedChatModel(BaseChatModel):
    """Pops scripted AIMessages; falls back to a canned text answer.

    Records the normalized params it was constructed with so the adapter
    contract suite can assert the params → model mapping through the port.
    """

    model_name: str = "scripted"
    effort: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    # M51 port limits (the contract suite asserts every adapter carries them)
    timeout: float | None = None
    max_retries: int | None = None

    @property
    def _llm_type(self) -> str:
        return "scripted-fake"

    def bind_tools(
        self,
        tools: Any,
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Any:
        from langchain_core.utils.function_calling import convert_to_openai_tool

        formatted = [convert_to_openai_tool(t) for t in tools]
        return self.bind(tools=formatted, **kwargs)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        _assert_no_open_session("chat")
        bound_tools = kwargs.get("tools") or []
        _SEEN_TOOLS.append(
            [t.get("function", {}).get("name", t.get("name", "?")) for t in bound_tools]
        )
        _SEEN_PROMPTS.append("\n".join(_message_text(m) for m in messages))
        if _SCRIPT:
            item = _SCRIPT.popleft()
            if isinstance(item, BaseException):
                raise item
            msg = item
            delay = msg.additional_kwargs.pop("__delay_s", None)
            if delay:
                import time

                time.sleep(float(delay))
        else:
            msg = self._default_message(_SEEN_TOOLS[-1] if _SEEN_TOOLS else [])
        # real providers stamp model_name; usage callbacks key on it
        msg.response_metadata.setdefault("model_name", f"fake:{self.model_name}")
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def _default_message(self, tool_names: list[str]) -> AIMessage:
        """Unscripted default: satisfy known structured-output schemas so an
        unscripted server (curl demos, keyless compose) still completes runs.

        Under the suite this path is closed unless a test opened it — see
        `_ALLOW_DEFAULTS`. A structured schema with no scripted answer is a
        missing assertion, not a convenience.
        """
        schema = next((n for n in tool_names if n in _STRUCTURED_SCHEMAS), None)
        if schema is not None and not _ALLOW_DEFAULTS:
            _UNSCRIPTED.append(schema)
            raise UnscriptedStructuredCall(
                f"the fake provider was asked for {schema} with an empty script. "
                "Script the answer this surface should give "
                f"(fake.push_ai('', [{{'name': '{schema}', 'args': {{...}}}}])), "
                "or, if the canned answer is genuinely what the test wants, "
                "wrap it in `app.llm.fake.allow_defaults()`."
            )
        if "PlannerOutput" in tool_names:
            msg = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "PlannerOutput",
                        "args": {
                            "entries": [],
                            "direct_answer": f"fake-answer[{self.model_name}]",
                            "no_confident_match": False,
                        },
                        "id": "fake-plan",
                    }
                ],
            )
        elif "ConditionChoice" in tool_names:
            msg = AIMessage(
                content="",
                tool_calls=[{"name": "ConditionChoice", "args": {"index": 0}, "id": "fake-route"}],
            )
        elif "OverlapVerdict" in tool_names:
            msg = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "OverlapVerdict",
                        "args": {
                            "overlap_percent": 0,
                            "match_type": "none",
                            "match_id": None,
                            "match_name": None,
                            "reasoning": "unscripted default",
                        },
                        "id": "fake-overlap",
                    }
                ],
            )
        elif "AnswerUi" in tool_names:
            msg = AIMessage(
                content="",
                tool_calls=[{"name": "AnswerUi", "args": {"components": []}, "id": "fake-ui"}],
            )
        else:
            msg = AIMessage(content=f"fake-answer[{self.model_name}]")
        msg.usage_metadata = _DEFAULT_USAGE
        return msg


@model_provider
class FakeProvider:
    provider_id = "fake"

    def is_configured(self) -> bool:
        return get_config().fake_llm_enabled

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo("scripted", "Scripted fake model")]

    def get_chat_model(self, model: str, params: ModelParams | None = None) -> BaseChatModel:
        if not self.is_configured():
            raise ProviderNotConfiguredError("fake: FAKE_LLM_ENABLED not set")
        from app.llm.adapters import port_limits

        limits = port_limits()
        return ScriptedChatModel(
            model_name=model,
            effort=params.effort if params else None,
            temperature=params.temperature if params else None,
            max_output_tokens=params.max_output_tokens if params else None,
            timeout=limits["timeout"],
            max_retries=limits["max_retries"],
        )

    def supports_embeddings(self) -> bool:
        return True

    async def get_embeddings(self, model: str, texts: list[str]) -> list[list[float]]:
        """Deterministic bag-of-tokens vectors: shared tokens produce real
        cosine similarity, so ranking tests exercise genuine vector math."""
        if not self.is_configured():
            raise ProviderNotConfiguredError("fake: FAKE_LLM_ENABLED not set")
        _assert_no_open_session("embeddings")
        dims = 64
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * dims
            for token in text.lower().split():
                vec[hash(token) % dims] += 1.0
            out.append(vec)
        return out
