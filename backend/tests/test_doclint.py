"""Seed-document lint (spec §13): the build/dev gate for `.skill.md` and
`.agent.md`.

The first test is the standing regression gate — the documents this repo
actually ships must always lint clean. The rest prove the linter rejects
what the seed would reject, and only warns where a document is legal but
worth fixing."""

from pathlib import Path

from app.doclint import lint_all, lint_skills, main

SKILL = """---
name: {name}
description: does a thing
persona: You are a thing doer.
tools:
{tools}
---
# Purpose
Use {{tool:{mention}}} to do the thing.
"""

AGENT = """---
name: {name}
description: an agent from a file
persona: You are an agent.
{extra}workflow:
  nodes:
    - id: work
      type: skill
      skill: {skill}
  edges:
    - {{ from: START, to: work }}
    - {{ from: work, to: END }}
---
# Notes
"""


def write_skill(d: Path, name: str, *, tools: str = "  - fs.read", mention: str = "fs.read") -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.skill.md"
    p.write_text(SKILL.format(name=name, tools=tools, mention=mention))
    return p


def write_agent(d: Path, name: str, *, skill: str = "s1", extra: str = "") -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.agent.md"
    p.write_text(AGENT.format(name=name, skill=skill, extra=extra))
    return p


def test_shipped_documents_lint_clean() -> None:
    """Standing gate: every seed document in this repo is valid."""
    base = Path(__file__).resolve().parents[1] / "app" / "native"
    errors, warnings = lint_all(base / "skills", base / "sub_agents")
    assert errors == [], f"shipped seed documents have lint errors: {errors}"
    assert warnings == [], f"shipped seed documents have lint warnings: {warnings}"


def test_missing_directories_are_not_errors(tmp_path: Path) -> None:
    errors, warnings = lint_all(tmp_path / "nope", tmp_path / "also-nope")
    assert errors == [] and warnings == []


class TestSkillErrors:
    def test_missing_frontmatter(self, tmp_path: Path) -> None:
        (tmp_path / "x.skill.md").write_text("# just a body")
        errors, _, _ = lint_skills(tmp_path)
        assert any("frontmatter" in e for e in errors)

    def test_unresolved_tool_mention(self, tmp_path: Path) -> None:
        write_skill(tmp_path, "s1", tools="  - fs.read", mention="fs.write")
        errors, _, _ = lint_skills(tmp_path)
        assert any("fs.write" in e and "not a bound tool" in e for e in errors)

    def test_duplicate_names_across_files(self, tmp_path: Path) -> None:
        write_skill(tmp_path, "dup")
        (tmp_path / "other.skill.md").write_text(
            SKILL.format(name="dup", tools="  - fs.read", mention="fs.read")
        )
        errors, _, _ = lint_skills(tmp_path)
        assert any("duplicate skill name" in e for e in errors)

    def test_whitespace_and_duplicate_tool_keys(self, tmp_path: Path) -> None:
        write_skill(tmp_path, "s1", tools="  - 'fs read'\n  - fs.read\n  - fs.read")
        errors, _, _ = lint_skills(tmp_path)
        assert any("whitespace" in e for e in errors)
        assert any("duplicate entries" in e for e in errors)

    def test_bad_max_tool_iterations(self, tmp_path: Path) -> None:
        (tmp_path / "s.skill.md").write_text(
            "---\nname: s\ntools: []\nmax_tool_iterations: 0\n---\nbody"
        )
        errors, _, _ = lint_skills(tmp_path)
        assert any("max_tool_iterations" in e for e in errors)


class TestSkillWarnings:
    def test_filename_mismatch_and_empty_prose_warn_only(self, tmp_path: Path) -> None:
        (tmp_path / "wrong-name.skill.md").write_text(
            "---\nname: s1\ntools: []\n---\n"
        )
        errors, warnings, names = lint_skills(tmp_path)
        assert errors == []
        assert names == {"s1"}
        joined = " ".join(warnings)
        assert "filename does not match" in joined
        assert "empty description" in joined
        assert "empty persona" in joined
        assert "empty instructions" in joined

    def test_unknown_frontmatter_key_warns(self, tmp_path: Path) -> None:
        (tmp_path / "s1.skill.md").write_text(
            "---\nname: s1\ndescription: d\npersona: p\ntools: []\ntoolz: []\n---\nbody"
        )
        errors, warnings, _ = lint_skills(tmp_path)
        assert errors == []
        assert any("unknown frontmatter keys" in w and "toolz" in w for w in warnings)


class TestAgentErrors:
    def test_unknown_skill_name(self, tmp_path: Path) -> None:
        skills, agents = tmp_path / "s", tmp_path / "a"
        write_skill(skills, "s1")
        write_agent(agents, "a1", skill="ghost-skill")
        errors, _ = lint_all(skills, agents)
        assert any("ghost-skill" in e and "not a scanned .skill.md" in e for e in errors)

    def test_missing_workflow(self, tmp_path: Path) -> None:
        agents = tmp_path / "a"
        agents.mkdir()
        (agents / "a1.agent.md").write_text("---\nname: a1\ndescription: d\n---\nbody")
        errors, _ = lint_all(tmp_path / "s", agents)
        assert any("workflow" in e for e in errors)

    def test_bad_model_reference(self, tmp_path: Path) -> None:
        skills, agents = tmp_path / "s", tmp_path / "a"
        write_skill(skills, "s1")
        write_agent(agents, "a1", extra="model: claude-sonnet-4-6\n")
        errors, _ = lint_all(skills, agents)
        assert any("provider:model" in e for e in errors)

    def test_bad_model_params_against_runtime_contract(self, tmp_path: Path) -> None:
        skills, agents = tmp_path / "s", tmp_path / "a"
        write_skill(skills, "s1")
        write_agent(
            agents,
            "a1",
            extra="model: anthropic:claude-sonnet-4-6\nmodel_params: { effort: extreme }\n",
        )
        errors, _ = lint_all(skills, agents)
        assert any("invalid model_params" in e for e in errors)

        write_agent(
            agents,
            "a2",
            extra="model: anthropic:claude-sonnet-4-6\nmodel_params: { efort: low }\n",
        )
        errors, _ = lint_all(skills, agents)
        assert any("invalid model_params" in e for e in errors)

    def test_dag_structure_is_enforced(self, tmp_path: Path) -> None:
        skills, agents = tmp_path / "s", tmp_path / "a"
        write_skill(skills, "s1")
        agents.mkdir(parents=True, exist_ok=True)
        # cycle with no path to END
        (agents / "cyc.agent.md").write_text(
            "---\nname: cyc\ndescription: d\nworkflow:\n"
            "  nodes:\n"
            "    - { id: a, type: skill, skill: s1 }\n"
            "    - { id: b, type: skill, skill: s1 }\n"
            "  edges:\n"
            "    - { from: START, to: a }\n"
            "    - { from: a, to: b }\n"
            "    - { from: b, to: a }\n"
            "---\n"
        )
        errors, _ = lint_all(skills, agents)
        assert errors, "a cyclic workflow with no END must be rejected"

    def test_malformed_form_gate(self, tmp_path: Path) -> None:
        skills, agents = tmp_path / "s", tmp_path / "a"
        write_skill(skills, "s1")
        agents.mkdir(parents=True, exist_ok=True)
        (agents / "g.agent.md").write_text(
            "---\nname: g\ndescription: d\nworkflow:\n"
            "  nodes:\n"
            "    - { id: w, type: skill, skill: s1 }\n"
            "    - id: gate\n"
            "      type: hitl\n"
            "      prompt: ok?\n"
            "      questions:\n"
            "        - { id: q1, kind: choice, prompt: pick, options: [only-one] }\n"
            "  edges:\n"
            "    - { from: START, to: w }\n"
            "    - { from: w, to: gate }\n"
            "    - { from: gate, to: END }\n"
            "---\n"
        )
        errors, _ = lint_all(skills, agents)
        assert any("choice needs >=2 options" in e for e in errors)

    def test_duplicate_agent_names(self, tmp_path: Path) -> None:
        skills, agents = tmp_path / "s", tmp_path / "a"
        write_skill(skills, "s1")
        write_agent(agents, "a1")
        (agents / "clone.agent.md").write_text(AGENT.format(name="a1", skill="s1", extra=""))
        errors, _ = lint_all(skills, agents)
        assert any("duplicate agent name" in e for e in errors)


class TestCli:
    def test_exit_codes(self, tmp_path: Path, capsys: object) -> None:
        skills, agents = tmp_path / "s", tmp_path / "a"
        write_skill(skills, "s1")
        write_agent(agents, "a1")
        assert main(["doclint", str(skills), str(agents)]) == 0
        write_agent(agents, "bad", skill="ghost")
        assert main(["doclint", str(skills), str(agents)]) == 1
