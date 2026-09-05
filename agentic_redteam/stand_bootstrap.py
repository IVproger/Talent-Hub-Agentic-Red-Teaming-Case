"""Model declaration for the bundled stand, outside the engine's LLM roles."""
from pathlib import Path
from typing import Mapping

from .llm import LLMConfigurationError, LLMRoleConfig
from .profile.schema import TargetProfile


def target_model_from_config(
    raw: Mapping, config_path: str | Path, *, require_profile: bool = False
) -> LLMRoleConfig:
    """Read target.profile → entrypoint.target_model without host credentials.

    The default only supports old programmatic pipeline configurations. Explicit
    profile references must resolve; stand sync always requires one.
    """
    target = raw.get("target", {})
    if not isinstance(target, Mapping):
        raise LLMConfigurationError("target must be a mapping.")
    reference = target.get("profile")
    if reference is None and not require_profile:
        return LLMRoleConfig().normalized()
    if not isinstance(reference, str) or not reference.strip():
        raise LLMConfigurationError("target.profile must be a non-empty path.")
    path = Path(reference).expanduser()
    if not path.is_absolute():
        candidates = [parent / path for parent in Path(config_path).resolve().parents]
        path = next((p for p in candidates if p.is_file()), candidates[0])
    profile = TargetProfile.load(path)
    model = profile.entrypoint.get("target_model")
    if not isinstance(model, Mapping) or not model.get("model"):
        raise LLMConfigurationError("Profile entrypoint.target_model.model is required.")
    unknown = set(model) - set(LLMRoleConfig.__dataclass_fields__)
    if unknown:
        raise LLMConfigurationError("Unknown fields in profile entrypoint.target_model.")
    selected = LLMRoleConfig(**model).normalized()
    selected.validate(require_credentials=False)
    return selected
