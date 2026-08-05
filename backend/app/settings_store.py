"""app_settings store (spec §3.7) — defaults, live reads, validated writes.

Values are read live at runtime; a PATCH applies to the next run with no
restart. Provider API keys are env-only and deliberately absent here.
"""

from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import ModelParams, validate_model_selection
from app.models import AppSetting

DEFAULTS: dict[str, Any] = {
    "orchestrator_mode": "graph",
    "orchestrator_full_fallback_enabled": True,
    "default_model": "anthropic:claude-sonnet-4-6",
    "default_model_params": None,
    "planner_model": None,  # null → falls back to default_model
    "planner_model_params": None,
    "aggregator_model": None,  # null → falls back to default_model
    "aggregator_model_params": None,
    "max_parallel_dispatch": 4,
    "max_plan_steps": 6,
    "max_tool_iterations": 8,
    "dynamic_worker_fallback_enabled": True,
    "direct_exposure_cap_warning": 10,
    "answer_ui_enabled": True,
    "mcp_health_interval_s": 30,
    "log_level": "INFO",
    "langsmith_enabled": False,
    "langsmith_endpoint": "",
    "langsmith_project": "concierge-agent",
    "otlp_endpoint": "",
}

_MODEL_KEYS = {"default_model", "planner_model", "aggregator_model"}
_PARAMS_KEYS = {"default_model_params", "planner_model_params", "aggregator_model_params"}
_INT_KEYS = {
    "max_parallel_dispatch",
    "max_plan_steps",
    "max_tool_iterations",
    "direct_exposure_cap_warning",
    "mcp_health_interval_s",
}
_BOOL_KEYS = {
    "orchestrator_full_fallback_enabled",
    "dynamic_worker_fallback_enabled",
    "langsmith_enabled",
    "answer_ui_enabled",
}
_STR_KEYS = {"langsmith_endpoint", "langsmith_project", "otlp_endpoint"}
_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}


class SettingsValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


async def get_settings(session: AsyncSession) -> dict[str, Any]:
    """Merged view: defaults overlaid with stored rows (live from DB)."""
    merged = dict(DEFAULTS)
    for row in (await session.execute(select(AppSetting))).scalars():
        if row.key in merged:
            merged[row.key] = row.value.get("value")
    return merged


async def get_setting(session: AsyncSession, key: str) -> Any:
    row = await session.get(AppSetting, key)
    if row is not None:
        return row.value.get("value")
    return DEFAULTS[key]


def _validate_pair(merged: dict[str, Any], model_key: str, errors: list[str]) -> None:
    """Validate a model ref together with its params (spec §2.1: 422 at save)."""
    params_key = f"{model_key}_params"
    ref = merged.get(model_key)
    raw_params = merged.get(params_key)
    params: ModelParams | None = None
    if raw_params is not None:
        try:
            params = ModelParams.model_validate(raw_params)
        except ValidationError as exc:
            errors.append(f"{params_key}: {exc.errors()[0].get('msg', 'invalid')}")
            return
    if ref is None:
        if params is not None and model_key != "default_model":
            # params for a null model would apply to the default model's ref;
            # require the model to be set explicitly alongside its params
            errors.append(f"{params_key} requires {model_key} to be set")
        elif params is not None:
            errors.append(f"{params_key} requires {model_key} to be set")
        return
    if not isinstance(ref, str):
        errors.append(f"{model_key} must be a 'provider:model' string")
        return
    errors.extend(f"{model_key}: {e}" for e in validate_model_selection(ref, params))


def validate_updates(current: dict[str, Any], updates: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key, value in updates.items():
        if key not in DEFAULTS:
            errors.append(f"unknown setting {key!r}")
            continue
        if key == "orchestrator_mode" and value not in {"graph", "agentic"}:
            errors.append("orchestrator_mode must be 'graph' or 'agentic'")
        elif key == "log_level" and value not in _LOG_LEVELS:
            errors.append(f"log_level must be one of {sorted(_LOG_LEVELS)}")
        elif key in _INT_KEYS and (not isinstance(value, int) or value < 1):
            errors.append(f"{key} must be a positive integer")
        elif key in _BOOL_KEYS and not isinstance(value, bool):
            errors.append(f"{key} must be a boolean")
        elif key in _STR_KEYS and not isinstance(value, str):
            errors.append(f"{key} must be a string")
        elif key in _MODEL_KEYS and value is not None and not isinstance(value, str):
            errors.append(f"{key} must be a 'provider:model' string or null")
        elif key in _PARAMS_KEYS and value is not None and not isinstance(value, dict):
            errors.append(f"{key} must be an object or null")
    if errors:
        return errors

    merged = dict(current)
    merged.update(updates)
    touched_pairs = {
        k.removesuffix("_params") if k in _PARAMS_KEYS else k
        for k in updates
        if k in _MODEL_KEYS or k in _PARAMS_KEYS
    }
    for model_key in touched_pairs:
        # only validate refs being set (or whose params changed); null planner/
        # aggregator fall back to default_model
        if merged.get(model_key) is None and merged.get(f"{model_key}_params") is None:
            continue
        _validate_pair(merged, model_key, errors)
    return errors


async def update_settings(session: AsyncSession, updates: dict[str, Any]) -> dict[str, Any]:
    """Apply validated partial updates; returns the merged settings."""
    current = await get_settings(session)
    errors = validate_updates(current, updates)
    if errors:
        raise SettingsValidationError(errors)
    for key, value in updates.items():
        row = await session.get(AppSetting, key)
        if row is None:
            session.add(AppSetting(key=key, value={"value": value}))
        else:
            row.value = {"value": value}
    await session.commit()
    return await get_settings(session)
