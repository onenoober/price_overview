from __future__ import annotations

import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_ENV_FILES = (
    REPO_ROOT / ".env.local",
    REPO_ROOT / "backend" / ".env.local",
)


def load_local_env_files() -> None:
    for path in LOCAL_ENV_FILES:
        if path.exists():
            load_env_file(path)


def load_env_file(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        key, value = parse_env_line(line)
        if key and key not in os.environ:
            os.environ[key] = value


def parse_env_line(line: str) -> tuple[str | None, str]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None, ""
    if stripped.startswith("export "):
        stripped = stripped[len("export ") :].strip()
    if "=" not in stripped:
        return None, ""

    key, value = stripped.split("=", 1)
    key = key.strip()
    value = strip_inline_comment(value.strip())
    if (
        len(value) >= 2
        and value[0] == value[-1]
        and value[0] in {"'", '"'}
    ):
        value = value[1:-1]
    return key, value


def strip_inline_comment(value: str) -> str:
    if not value:
        return value
    if value[0] in {"'", '"'}:
        quote = value[0]
        end = value.find(quote, 1)
        if end > 0:
            return value[: end + 1]
        return value

    marker = value.find(" #")
    if marker >= 0:
        return value[:marker].rstrip()
    return value
