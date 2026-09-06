"""Read operator ideas without losing Markdown structure or YAML item order."""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import yaml

from ..errors import PipelineConfigurationError

MAX_IDEAS_FILE_BYTES = 65536


def load_idea_files(paths: Sequence[str]) -> list[str]:
    ideas: list[str] = []
    for source in paths:
        path = Path(source).expanduser()

        def invalid(reason: str) -> None:
            raise PipelineConfigurationError(f"--ideas-file {path}: {reason}")

        suffix = path.suffix.lower()
        if suffix not in {'.txt', '.md', '.yaml', '.yml'}:
            invalid('поддерживаются .txt, .md, .yaml и .yml.')
        try:
            if not path.is_file():
                invalid('ожидается существующий обычный файл.')
            with path.open('rb') as stream:
                data = stream.read(MAX_IDEAS_FILE_BYTES + 1)
            if len(data) > MAX_IDEAS_FILE_BYTES:
                invalid('файл превышает 64 КиБ; сократите идеи или разделите файл.')
            text = data.decode('utf-8-sig')
        except (OSError, UnicodeError):
            invalid('не удалось прочитать файл; проверьте доступ и кодировку UTF-8.')
        if suffix in {'.txt', '.md'}:
            items = [text]
        else:
            try:
                items = yaml.safe_load(text)
            except yaml.YAMLError:
                invalid('некорректный YAML; ожидается список строк или объект ideas: [...].')
            if isinstance(items, dict):
                if set(items) != {'ideas'}:
                    invalid('в YAML-объекте разрешено только поле ideas со списком строк.')
                items = items['ideas']
        if not isinstance(items, list) or not items:
            invalid('ожидается непустой список идей (строк).')
        for index, item in enumerate(items, 1):
            if not isinstance(item, str) or not item.strip():
                invalid(f'идея №{index} должна быть непустой строкой.')
            ideas.append(item.strip())
    return ideas
