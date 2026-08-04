"""Skill schemas (spec §3.3, §4)."""

from typing import Any, Literal
from uuid import UUID

from app.schemas.common import ApiModel, RegistryOut, Status
from app.schemas.tool import ToolOut


class SkillCreate(ApiModel):
    name: str
    description: str = ""
    persona: str = ""
    instructions: str = ""
    tool_ids: list[UUID] = []
    direct_exposure: bool = False
    model: str | None = None
    model_params: dict[str, Any] | None = None


class SkillPatch(ApiModel):
    name: str | None = None
    description: str | None = None
    persona: str | None = None
    instructions: str | None = None
    tool_ids: list[UUID] | None = None
    direct_exposure: bool | None = None
    model: str | None = None
    model_params: dict[str, Any] | None = None
    status: Status | None = None


class SkillOut(RegistryOut):
    kind: Literal["native", "custom"]
    persona: str
    instructions: str
    direct_exposure: bool
    model: str | None
    model_params: dict[str, Any] | None
    tools: list[ToolOut] = []
