"""Заморозка вывода composer в версионируемый baseline-каталог."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import yaml

from ..profile.schema import TargetProfile
from .composer import Unsupported, compose
from .template import load_templates


def _to_mapping(spec) -> dict:
    data = {
        "id": spec.id, "name": spec.name, "attack_class": spec.attack_class,
        "standard_refs": list(spec.standard_refs), "description": spec.description,
        "actor": spec.actor, "boundary": spec.boundary, "reset_policy": spec.reset_policy,
        "expect": spec.expect, "remediation": spec.remediation,
        "params": dict(spec.params),
        "payloads": list(spec.payloads),
        "steps": [{k: v for k, v in asdict(step).items() if v not in (None, False)}
                  for step in spec.steps],
        "goal": [dict(item) for item in spec.goal],
    }
    return data


def freeze_baseline(templates_root, profile: TargetProfile, out_dir) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for template in load_templates(templates_root):
        result = compose(template, profile)
        if isinstance(result, Unsupported):
            continue
        path = out / f"{template.id}.yaml"
        path.write_text(yaml.safe_dump(_to_mapping(result), sort_keys=False,
                                       allow_unicode=True), encoding="utf-8")
        written.append(path)
    return sorted(written)
