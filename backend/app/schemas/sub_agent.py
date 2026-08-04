"""Sub agent schemas (spec §3.4, §4)."""

from typing import Any, Literal

from app.schemas.common import ApiModel, RegistryOut, Status
from app.schemas.skill import SkillOut


class SubAgentCreate(ApiModel):
    name: str
    description: str = ""
    persona: str = ""
    model: str | None = None
    model_params: dict[str, Any] | None = None
    workflow: dict[str, Any]


class SubAgentPatch(ApiModel):
    name: str | None = None
    description: str | None = None
    persona: str | None = None
    model: str | None = None
    model_params: dict[str, Any] | None = None
    workflow: dict[str, Any] | None = None
    status: Status | None = None


class SubAgentOut(RegistryOut):
    kind: Literal["native", "custom"]
    persona: str
    model: str | None
    model_params: dict[str, Any] | None
    workflow: dict[str, Any] | None
    native_ref: str | None
    covers_skill_ids: list[Any] | None
    skills: list[SkillOut] = []


class ValidateResult(ApiModel):
    valid: bool
    errors: list[str] = []
