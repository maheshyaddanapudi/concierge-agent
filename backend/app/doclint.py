"""Seed-document lint (spec §13): offline validation for `.skill.md` and
`.agent.md` files — the same checks the seed applies, runnable at dev time,
in pytest, and as a Docker build gate, so a malformed document fails the
BUILD instead of landing as a status='error' row at boot.

Errors  = the seed would reject or error the document (build fails).
Warnings = legitimate but unverifiable-offline or advisable-to-fix.

Usage: python -m app.doclint  [skills_dir] [agents_dir]
"""

import re
import sys
from pathlib import Path
from uuid import UUID, uuid4

from app.agentdoc import AgentDocError, parse_agent_document, skill_name_refs
from app.factory.dag import validate_workflow
from app.skilldoc import SkillDocError, parse_skill_document, validate_mentions

_KNOWN_SKILL_KEYS = {
    "name", "description", "persona", "tools", "direct_exposure", "max_tool_iterations",
}
_KNOWN_AGENT_KEYS = {
    "name", "description", "persona", "model", "model_params", "direct_exposure", "workflow",
}
_MODEL_REF_RE = re.compile(r"^[a-z][a-z0-9_]*:[A-Za-z0-9._\-]+$")
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---", re.DOTALL)


def _frontmatter_keys(text: str) -> set[str]:
    import yaml

    match = _FRONTMATTER_RE.match(text)
    if not match:
        return set()
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return set()
    return set(meta) if isinstance(meta, dict) else set()


def lint_skills(directory: Path) -> tuple[list[str], list[str], set[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    names: set[str] = set()
    for path in sorted(directory.glob("*.skill.md")) if directory.exists() else []:
        text = path.read_text(encoding="utf-8")
        try:
            doc = parse_skill_document(text)
        except SkillDocError as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        if doc.name in names:
            errors.append(f"{path.name}: duplicate skill name {doc.name!r}")
        names.add(doc.name)
        for err in validate_mentions(doc.instructions, doc.tools):
            errors.append(f"{path.name}: {err}")
        for key in doc.tools:
            if not key.strip() or key != key.strip() or " " in key:
                errors.append(f"{path.name}: tool key {key!r} has whitespace")
        if len(set(doc.tools)) != len(doc.tools):
            errors.append(f"{path.name}: duplicate entries in 'tools'")
        if path.name != f"{doc.name}.skill.md":
            warnings.append(f"{path.name}: filename does not match name {doc.name!r}")
        if not doc.description.strip():
            warnings.append(f"{path.name}: empty description — the planner routes on it")
        if not doc.instructions.strip():
            warnings.append(f"{path.name}: empty instructions body")
        if not doc.persona.strip():
            warnings.append(f"{path.name}: empty persona")
        unknown = _frontmatter_keys(text) - _KNOWN_SKILL_KEYS
        if unknown:
            warnings.append(f"{path.name}: unknown frontmatter keys {sorted(unknown)}")
    return errors, warnings, names


def lint_agents(directory: Path, skill_names: set[str]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*.agent.md")) if directory.exists() else []:
        text = path.read_text(encoding="utf-8")
        try:
            doc = parse_agent_document(text, path.name)
        except AgentDocError as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        if doc.name in seen:
            errors.append(f"{path.name}: duplicate agent name {doc.name!r}")
        seen.add(doc.name)
        if doc.model is not None and not _MODEL_REF_RE.match(doc.model):
            errors.append(
                f"{path.name}: model {doc.model!r} is not a provider:model reference"
            )
        if doc.model_params is not None:
            # validate against the REAL runtime contract (extra='forbid', so
            # typos and bad effort values fail here instead of at first run)
            from pydantic import ValidationError

            from app.llm import ModelParams

            try:
                ModelParams.model_validate(doc.model_params)
            except ValidationError as exc:
                detail = "; ".join(
                    f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
                )
                errors.append(f"{path.name}: invalid model_params — {detail}")
        if doc.model_params is not None and doc.model is None:
            warnings.append(f"{path.name}: model_params set without an explicit model")
        if path.name != f"{doc.name}.agent.md":
            warnings.append(f"{path.name}: filename does not match name {doc.name!r}")
        if not doc.persona.strip():
            warnings.append(f"{path.name}: empty persona")
        if not doc.description.strip():
            warnings.append(f"{path.name}: empty description — the planner routes on it")
        unknown = _frontmatter_keys(text) - _KNOWN_AGENT_KEYS
        if unknown:
            warnings.append(f"{path.name}: unknown frontmatter keys {sorted(unknown)}")
        # resolve by-name refs against the scanned .skill.md set; uuid refs
        # point at dynamic records and cannot be verified offline
        for ref in skill_name_refs(doc.workflow):
            if ref not in skill_names:
                errors.append(
                    f"{path.name}: skill {ref!r} is not a scanned .skill.md — by-name "
                    "references must resolve to static skill files"
                )
        synthetic: dict[str, str] = {n: str(uuid4()) for n in skill_names}
        active_ids = set(synthetic.values())
        workflow = {"nodes": [], "edges": list(doc.workflow["edges"])}
        for node in doc.workflow["nodes"]:
            node = dict(node)
            ref = node.pop("skill", None)
            if ref is not None and ref in synthetic:
                node["skill_id"] = synthetic[ref]
            elif node.get("skill_id"):
                sid = str(node["skill_id"])
                try:
                    UUID(sid)
                    warnings.append(
                        f"{path.name}: node {node.get('id')!r} references skill by uuid — "
                        "unverifiable offline (verified at seed)"
                    )
                    active_ids.add(sid)
                except ValueError:
                    errors.append(f"{path.name}: node {node.get('id')!r} skill_id is not a uuid")
            workflow["nodes"].append(node)
        for err in validate_workflow(workflow, active_ids):
            # unresolved by-name refs already errored above with a better message
            if "skill nodes require an explicit" in err and any(
                n.get("type") == "skill" and not n.get("skill_id") for n in workflow["nodes"]
            ):
                continue
            errors.append(f"{path.name}: {err}")
    return errors, warnings


def lint_all(skills_dir: Path, agents_dir: Path) -> tuple[list[str], list[str]]:
    skill_errors, skill_warnings, names = lint_skills(skills_dir)
    agent_errors, agent_warnings = lint_agents(agents_dir, names)
    return skill_errors + agent_errors, skill_warnings + agent_warnings


def main(argv: list[str]) -> int:
    base = Path(__file__).resolve().parent / "native"
    skills_dir = Path(argv[1]) if len(argv) > 1 else base / "skills"
    agents_dir = Path(argv[2]) if len(argv) > 2 else base / "sub_agents"
    errors, warnings = lint_all(skills_dir, agents_dir)
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    n_skills = len(list(skills_dir.glob("*.skill.md"))) if skills_dir.exists() else 0
    n_agents = len(list(agents_dir.glob("*.agent.md"))) if agents_dir.exists() else 0
    print(
        f"doclint: {n_skills} skill file(s), {n_agents} agent file(s) — "
        f"{len(errors)} error(s), {len(warnings)} warning(s)"
    )
    return 1 if errors else 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main(sys.argv))
