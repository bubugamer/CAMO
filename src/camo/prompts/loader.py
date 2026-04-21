from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

DEFAULT_PROMPTS_ROOT = Path(__file__).resolve().parents[3] / "prompts"


@lru_cache(maxsize=1)
def get_prompts_root() -> Path:
    candidates = []
    configured = os.getenv("CAMO_PROMPTS_ROOT", "").strip()
    if configured:
        candidates.append(Path(configured))
    candidates.extend(
        [
            Path.cwd() / "prompts",
            DEFAULT_PROMPTS_ROOT,
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0]


@lru_cache(maxsize=1)
def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(get_prompts_root())),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_prompt(template_path: str, **context: Any) -> str:
    template = _environment().get_template(template_path)
    return template.render(**context).strip()


@lru_cache(maxsize=16)
def load_json_schema(schema_path: str) -> dict[str, Any]:
    full_path = get_prompts_root() / schema_path
    return json.loads(full_path.read_text(encoding="utf-8"))
