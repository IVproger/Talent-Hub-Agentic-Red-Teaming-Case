"""Read a principal's actual target memory view through a declared target method."""
import json
import subprocess

from ...adapters.base import UnsupportedFeature


_READ_VIEW = """import importlib, json, sys
cfg = json.load(sys.stdin)
obj = getattr(importlib.import_module(cfg['module']), cfg['factory'])()
for part in cfg.get('member', '').split('.'):
    if part:
        obj = getattr(obj, part)
records = getattr(obj, cfg['method'])(*cfg.get('arguments', []))
print(json.dumps(records, default=lambda value: value.model_dump(mode='json') if hasattr(value, 'model_dump') else str(value)))
"""


def read_target_view(config, principal, session_id, runner=subprocess.run):
    """Use target repository filtering; never infer visibility from a scope label."""
    declaration = config.get("visibility")
    if not declaration:
        raise UnsupportedFeature("Для проверки видимости не задан read.config.visibility.")
    try:
        context = {"principal": principal.value, "session": session_id}
        settings = {key: declaration[key] for key in ("module", "factory", "method")}
        settings["member"] = declaration.get("member", "")
        settings["arguments"] = [value.format_map(context) if isinstance(value, str) else value
                                 for value in declaration.get("arguments", [])]
        command = ["docker", "compose", "-f", declaration["compose_file"], "exec", "-T",
                   declaration["service"], "python", "-c", _READ_VIEW]
        result = runner(command, input=json.dumps(settings), capture_output=True,
                        text=True, check=True, timeout=declaration.get("timeout", 30))
        if result.returncode:
            raise ValueError
        records = json.loads(result.stdout.strip().splitlines()[-1])
        if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
            raise ValueError
        return records
    except (KeyError, ValueError, IndexError, TypeError, OSError, subprocess.SubprocessError):
        raise RuntimeError("Не удалось прочитать память через объявленный метод цели.") from None
