"""Prompt regression harness (M49, spec §15 golden sets).

Prompts in this package define behavior — the planner's refusal contract,
the ambient runner's abstain protocol, every untrusted-data fence — and
nothing gated a change to one until M49. This module renders each prompt
file exactly the way its consumer does, grades the result with the §15
`contains` grader, and fails on placeholder drift. It runs three ways, like
`app.doclint`: by hand (`python -m app.prompts.check`), as a pytest gate
(`tests/test_prompt_golden.py`), and as a Docker build gate.

Golden sets live beside the prompts in `golden/<stem>.yaml`:

    consumer: app/orchestrator/planner.py   # the file that load_prompt()s it
    render: format                          # format | replace | verbatim
    placeholders: [draft, candidates]       # replace mode only — the tokens
                                            # the consumer substitutes
    cases:
      - name: basic
        vars: {task: "...", ...}            # rendered into the prompt
        must_contain: ["..."]               # graded with the §15 grader
        must_not_contain: ["..."]           # optional

`render` names the consumer's mechanism: `format` is `str.format(**vars)`
(a missing or renamed placeholder raises — the harness reports it),
`replace` is a chain of `str.replace("{name}", value)` (nothing raises, so
the harness asserts no declared placeholder survives rendering), and
`verbatim` is a prompt used as-is (no vars, no placeholders).
"""

from __future__ import annotations

import asyncio
import string
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_PROMPTS_DIR = Path(__file__).resolve().parent
_GOLDEN_DIR = _PROMPTS_DIR / "golden"
_APP_DIR = _PROMPTS_DIR.parent
RENDER_MODES = {"format", "replace", "verbatim"}


@dataclass
class GoldenCase:
    name: str
    vars: dict[str, str]
    must_contain: list[str]
    must_not_contain: list[str] = field(default_factory=list)


@dataclass
class Golden:
    stem: str
    consumer: str
    render: str
    placeholders: list[str]
    cases: list[GoldenCase]


@dataclass
class Failure:
    case: str
    reason: str


@dataclass
class CheckResult:
    stem: str
    case: str
    failures: list[Failure]

    @property
    def passed(self) -> bool:
        return not self.failures


def read_prompt(stem: str) -> str:
    """Uncached read — the harness must see the file as it is NOW, and tests
    inject mutated readers to prove a regression is caught."""
    return (_PROMPTS_DIR / f"{stem}.md").read_text(encoding="utf-8").strip()


def load_goldens(golden_dir: Path = _GOLDEN_DIR) -> dict[str, Golden]:
    goldens: dict[str, Golden] = {}
    for path in sorted(golden_dir.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        render = str(raw.get("render", "format"))
        if render not in RENDER_MODES:
            raise ValueError(f"{path.name}: render must be one of {sorted(RENDER_MODES)}")
        cases = [
            GoldenCase(
                name=str(c.get("name") or f"case{i + 1}"),
                vars={str(k): str(v) for k, v in (c.get("vars") or {}).items()},
                must_contain=[str(s) for s in (c.get("must_contain") or [])],
                must_not_contain=[str(s) for s in (c.get("must_not_contain") or [])],
            )
            for i, c in enumerate(raw.get("cases") or [])
        ]
        goldens[path.stem] = Golden(
            stem=path.stem,
            consumer=str(raw.get("consumer") or ""),
            render=render,
            placeholders=[str(p) for p in (raw.get("placeholders") or [])],
            cases=cases,
        )
    return goldens


def format_placeholders(text: str) -> set[str]:
    """The `{name}` fields str.format would substitute (escaped `{{` excluded)."""
    names: set[str] = set()
    for _, field_name, _, _ in string.Formatter().parse(text):
        if field_name:
            names.add(field_name)
    return names


def consumer_problems(goldens: dict[str, Golden]) -> list[str]:
    """Each golden names the module that renders the prompt; that module
    must exist and must actually load this prompt by name."""
    problems: list[str] = []
    for stem, golden in goldens.items():
        if not golden.consumer:
            problems.append(f"{stem}: golden declares no consumer")
            continue
        path = _APP_DIR.parent / golden.consumer
        if not path.is_file():
            problems.append(f"{stem}: consumer {golden.consumer} does not exist")
            continue
        source = path.read_text(encoding="utf-8")
        if f'load_prompt("{stem}")' not in source:
            problems.append(f'{stem}: {golden.consumer} does not call load_prompt("{stem}")')
    return problems


def render(golden: Golden, case: GoldenCase, text: str) -> tuple[str, list[Failure]]:
    """Render the prompt the way the consumer does; report drift instead of
    raising so every case of every prompt is graded in one pass."""
    failures: list[Failure] = []
    if golden.render == "verbatim":
        if case.vars:
            failures.append(Failure(case.name, "verbatim prompts take no vars"))
        return text, failures
    if golden.render == "format":
        expected = format_placeholders(text)
        missing = sorted(expected - set(case.vars))
        if missing:
            failures.append(
                Failure(
                    case.name,
                    f"placeholder(s) {missing} in the file are not supplied by the "
                    "case — the consumer's .format() would raise KeyError",
                )
            )
            return text, failures
        extra = sorted(set(case.vars) - expected)
        if extra:
            failures.append(
                Failure(
                    case.name,
                    f"case supplies var(s) {extra} the file no longer uses — a "
                    "placeholder was renamed or removed",
                )
            )
        try:
            return text.format(**case.vars), failures
        except (KeyError, IndexError, ValueError) as exc:
            failures.append(Failure(case.name, f".format() failed: {exc!r}"))
            return text, failures
    # replace mode: the consumer substitutes declared tokens one by one
    rendered = text
    for name in golden.placeholders:
        token = "{" + name + "}"
        if token not in text:
            failures.append(
                Failure(case.name, f"declared placeholder {token} is absent from the file")
            )
        rendered = rendered.replace(token, case.vars.get(name, ""))
    unknown = sorted(set(case.vars) - set(golden.placeholders))
    if unknown:
        failures.append(Failure(case.name, f"case vars {unknown} are not declared placeholders"))
    for name in golden.placeholders:
        token = "{" + name + "}"
        if token in rendered:
            failures.append(
                Failure(case.name, f"placeholder {token} survived rendering (leftover token)")
            )
    return rendered, failures


async def grade(rendered: str, case: GoldenCase) -> list[Failure]:
    """§15 graders decide: `contains` for every assertion, both directions."""
    from app.evals.grade import grade_case

    failures: list[Failure] = []
    for needle in case.must_contain:
        verdict = await grade_case(
            grader="contains", answer=rendered, expected=needle, judge_notes=""
        )
        if not verdict["passed"]:
            failures.append(Failure(case.name, f"must_contain missing: {needle!r}"))
    for needle in case.must_not_contain:
        verdict = await grade_case(
            grader="contains", answer=rendered, expected=needle, judge_notes=""
        )
        if verdict["passed"]:
            failures.append(Failure(case.name, f"must_not_contain present: {needle!r}"))
    return failures


async def run_checks(
    reader: Callable[[str], str] = read_prompt,
    golden_dir: Path = _GOLDEN_DIR,
) -> list[CheckResult]:
    """One result per (prompt, case); prompts without a golden set fail."""
    goldens = load_goldens(golden_dir)
    results: list[CheckResult] = []
    for path in sorted(_PROMPTS_DIR.glob("*.md")):
        stem = path.stem
        golden = goldens.get(stem)
        if golden is None or not golden.cases:
            results.append(CheckResult(stem, "-", [Failure("-", "no golden set / no cases")]))
            continue
        text = reader(stem)
        for case in golden.cases:
            rendered, failures = render(golden, case, text)
            if not failures:
                failures = await grade(rendered, case)
            results.append(CheckResult(stem, case.name, failures))
    for problem in consumer_problems(goldens):
        stem = problem.split(":", 1)[0]
        results.append(CheckResult(stem, "consumer", [Failure("consumer", problem)]))
    return results


def format_result(result: CheckResult) -> str:
    lines = [f"FAIL {result.stem} [{result.case}]"]
    lines.extend(f"     - {f.reason}" for f in result.failures)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI: 0 when every case passes, 1 otherwise (doclint discipline)."""
    _ = argv  # no flags yet; the signature mirrors app.doclint
    results = asyncio.run(run_checks())
    failed = [r for r in results if not r.passed]
    prompts = {r.stem for r in results}
    for result in failed:
        print(format_result(result))
    print(f"prompt golden sets: {len(prompts)} prompts, {len(results)} cases, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
