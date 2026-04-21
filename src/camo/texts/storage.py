from __future__ import annotations

from pathlib import Path


def save_source_text(*, data_root: Path, source_id: str, content: str) -> str:
    source_dir = data_root / "raw_texts" / source_id
    source_dir.mkdir(parents=True, exist_ok=True)
    file_path = source_dir / "original.txt"
    file_path.write_text(content, encoding="utf-8")
    return str(file_path.relative_to(data_root))
