"""M49 — the prompt regression harness (spec §15 golden sets).

Every prompt file in `app/prompts/` defines behavior, and until M49 nothing
gated a change to one. The harness renders each prompt exactly the way its
consumer does (format / replace / verbatim), grades the rendered text with
the §15 `contains` grader, and fails on placeholder drift. These tests pin
the harness contract: coverage is total, a deliberate regression fails, and
the offline CLI mirrors doclint's exit-code discipline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.prompts import check as prompt_check

PROMPTS_DIR = Path(prompt_check.__file__).resolve().parent
PROMPT_STEMS = sorted(p.stem for p in PROMPTS_DIR.glob("*.md"))


def test_every_prompt_file_has_a_golden_file() -> None:
    goldens = prompt_check.load_goldens()
    missing = [s for s in PROMPT_STEMS if s not in goldens]
    assert not missing, f"prompt files without a golden set: {missing}"
    orphans = [s for s in goldens if s not in PROMPT_STEMS]
    assert not orphans, f"golden sets without a prompt file: {orphans}"
    for stem, golden in goldens.items():
        assert golden.cases, f"{stem}: a golden set needs at least one case"
        for case in golden.cases:
            assert case.must_contain, f"{stem}/{case.name}: a case needs must_contain assertions"


def test_every_golden_names_a_real_consumer_that_loads_the_prompt() -> None:
    """The golden ties the prompt to the code that renders it, so a renamed
    or deleted consumer is caught here rather than at request time."""
    problems = prompt_check.consumer_problems(prompt_check.load_goldens())
    assert not problems, "\n".join(problems)


async def test_shipped_prompts_pass_their_golden_sets() -> None:
    report = await prompt_check.run_checks()
    failures = [r for r in report if not r.passed]
    assert not failures, "\n".join(prompt_check.format_result(r) for r in failures)
    # every prompt contributed at least one graded case
    assert {r.stem for r in report} == set(PROMPT_STEMS)


async def test_deliberate_regression_fails_the_harness() -> None:
    """Delete one binding sentence from the planner prompt: the harness must
    report that case as failed — this is the regression protection M49 buys."""
    original = prompt_check.read_prompt("planner")
    mutated = original.replace("no_confident_match", "no_match_found")
    assert mutated != original

    def reader(stem: str) -> str:
        return mutated if stem == "planner" else prompt_check.read_prompt(stem)

    report = await prompt_check.run_checks(reader=reader)
    planner = [r for r in report if r.stem == "planner"]
    assert planner and not all(r.passed for r in planner)
    reasons = " ".join(f.reason for r in planner for f in r.failures)
    assert "no_confident_match" in reasons


async def test_placeholder_drift_fails_the_harness() -> None:
    """Rename a placeholder in the file while the consumer still passes the
    old name: `.format` would KeyError at request time — the harness fails
    first, naming the placeholder."""
    original = prompt_check.read_prompt("router")
    mutated = original.replace("{conditions}", "{choices}")

    def reader(stem: str) -> str:
        return mutated if stem == "router" else prompt_check.read_prompt(stem)

    report = await prompt_check.run_checks(reader=reader)
    router = [r for r in report if r.stem == "router"]
    assert router and not all(r.passed for r in router)
    reasons = " ".join(f.reason for r in router for f in r.failures)
    assert "choices" in reasons


async def test_replace_mode_detects_leftover_placeholder() -> None:
    """Consumers that use str.replace never raise on a stale token — the
    harness asserts no declared placeholder survives rendering."""
    original = prompt_check.read_prompt("overlap_judge")
    mutated = original.replace("{draft}", "{draft_text}")

    def reader(stem: str) -> str:
        return mutated if stem == "overlap_judge" else prompt_check.read_prompt(stem)

    report = await prompt_check.run_checks(reader=reader)
    judge = [r for r in report if r.stem == "overlap_judge"]
    assert judge and not all(r.passed for r in judge)
    reasons = " ".join(f.reason for r in judge for f in r.failures)
    assert "{draft" in reasons


def test_cli_exit_codes(capsys: pytest.CaptureFixture[str]) -> None:
    """`python -m app.prompts.check` mirrors doclint: 0 when green, 1 with
    the failures listed — usable by hand and as a build gate."""
    assert prompt_check.main([]) == 0
    out = capsys.readouterr().out
    assert "prompt golden sets:" in out and "0 failed" in out
