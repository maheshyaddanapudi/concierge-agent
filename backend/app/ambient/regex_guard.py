"""Authored regexes, bounded (M52, ReDoS).

Trigger and watch filters carry `regex` patterns written by a user or
compiled by a model. Python's `re` backtracks, so a pattern like `(a+)+$`
on thirty characters runs for minutes on the event loop's thread — the
ambient tick's thread. Two layers:

- `check_pattern` refuses, at the API boundary and again before every
  match, the shapes that are catastrophic by construction: a quantified
  group that itself contains a quantifier (`(a+)+`, `(\\w+\\s?)*`),
  backreferences, and patterns past a length cap;
- `safe_search` runs the match in a worker thread with a timeout and a
  cap on the subject length; on timeout it returns "no match" and counts
  it, so one hostile filter costs a quarter second of a worker thread,
  never the tick.
"""

from __future__ import annotations

import concurrent.futures
import functools
import re

MAX_PATTERN_LEN = 200
MAX_SUBJECT_LEN = 10_000
TIMEOUT_S = 0.25
_QUANTIFIER_STARTS = frozenset("*+{")

_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="regex-guard")


def check_pattern(pattern: str) -> str | None:
    """A human-readable problem, or None when the pattern is admissible."""
    if len(pattern) > MAX_PATTERN_LEN:
        return f"regex is longer than {MAX_PATTERN_LEN} characters"
    try:
        re.compile(pattern)
    except re.error as exc:
        return f"regex does not compile: {exc}"
    if re.search(r"\\[1-9]|\(\?P=", pattern):
        return "regex uses a backreference, which is not allowed"
    # a quantified group containing a quantifier: nested repetition
    stack: list[bool] = []  # per open group: has a quantifier inside?
    i = 0
    escaped = False
    in_class = False
    while i < len(pattern):
        ch = pattern[i]
        if escaped:
            escaped = False
        elif ch == "\\":
            escaped = True
        elif in_class:
            if ch == "]":
                in_class = False
        elif ch == "[":
            in_class = True
        elif ch == "(":
            stack.append(False)
        elif ch == ")":
            had_quantifier = stack.pop() if stack else False
            nxt = pattern[i + 1] if i + 1 < len(pattern) else ""
            if had_quantifier and nxt in _QUANTIFIER_STARTS:
                return (
                    "regex nests a repetition inside a repeated group (catastrophic backtracking)"
                )
            if had_quantifier and stack:
                stack[-1] = True
        elif ch in _QUANTIFIER_STARTS and stack:
            stack[-1] = True
        i += 1
    return None


@functools.lru_cache(maxsize=256)
def _compiled(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


def _search(pattern: str, value: str) -> bool:
    return _compiled(pattern).search(value) is not None


def safe_search(pattern: str, value: str) -> bool:
    """`re.search` under the guard: refused patterns never run, the subject
    is clipped, the match runs off the calling thread under TIMEOUT_S."""
    from app import obs

    problem = check_pattern(pattern)
    if problem is not None:
        obs.REGEX_GUARD.labels(outcome="rejected").inc()
        return False
    subject = value[:MAX_SUBJECT_LEN]
    future = _pool.submit(_search, pattern, subject)
    try:
        return bool(future.result(timeout=TIMEOUT_S))
    except concurrent.futures.TimeoutError:
        obs.REGEX_GUARD.labels(outcome="timeout").inc()
        return False
    except re.error:
        obs.REGEX_GUARD.labels(outcome="rejected").inc()
        return False
