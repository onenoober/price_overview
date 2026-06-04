from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from .database import FILE_TYPES


REPO_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_ROOT = REPO_ROOT / "uploads"
CHUNK_SIZE = 1024 * 1024


class FileTooLargeError(ValueError):
    pass


@dataclass(frozen=True)
class StoredFile:
    file_id: str
    task_id: str
    file_type: str
    filename: str
    storage_path: str
    version: int
    size_bytes: int
    checksum: str


def sanitize_identifier(value: str, label: str) -> str:
    safe_value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    if not safe_value:
        raise ValueError(f"{label} is required")
    return safe_value


def sanitize_original_filename(filename: str) -> str:
    original_name = Path(filename).name
    if not original_name:
        return "file"

    path = Path(original_name)
    suffix = re.sub(r"[^A-Za-z0-9.]+", "", path.suffix)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem).strip("._-")

    if not stem:
        stem = "file"

    return f"{stem}{suffix}"


def build_storage_directory(
    task_id: str,
    file_type: str,
    upload_root: Path = UPLOAD_ROOT,
) -> Path:
    if file_type not in FILE_TYPES:
        raise ValueError(f"Unsupported file_type: {file_type}")

    safe_task_id = sanitize_identifier(task_id, "task_id")
    return upload_root / safe_task_id / file_type


def build_storage_filename(version: int, file_id: str, original_filename: str) -> str:
    if version <= 0:
        raise ValueError("version must be greater than 0")

    safe_file_id = sanitize_identifier(file_id, "file_id")
    safe_filename = sanitize_original_filename(original_filename)
    return f"v{version}_{safe_file_id}_{safe_filename}"


def save_stream_to_storage(
    stream: BinaryIO,
    *,
    task_id: str,
    file_type: str,
    file_id: str,
    version: int,
    original_filename: str,
    upload_root: Path = UPLOAD_ROOT,
    max_size_bytes: int | None = None,
) -> StoredFile:
    storage_dir = build_storage_directory(task_id, file_type, upload_root)
    storage_dir.mkdir(parents=True, exist_ok=True)

    storage_filename = build_storage_filename(version, file_id, original_filename)
    target_path = storage_dir / storage_filename

    checksum = hashlib.sha256()
    size_bytes = 0

    try:
        with target_path.open("xb") as target:
            while True:
                chunk = stream.read(CHUNK_SIZE)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if max_size_bytes is not None and size_bytes > max_size_bytes:
                    raise FileTooLargeError(
                        f"file size exceeds limit: {max_size_bytes} bytes"
                    )
                checksum.update(chunk)
                target.write(chunk)
    except FileExistsError as exc:
        raise FileExistsError(f"File already exists: {target_path}") from exc
    except Exception:
        if target_path.exists():
            target_path.unlink()
        raise

    if size_bytes == 0:
        target_path.unlink()
        raise ValueError("empty file is not allowed")

    return StoredFile(
        file_id=file_id,
        task_id=task_id,
        file_type=file_type,
        filename=original_filename,
        storage_path=format_storage_path(target_path),
        version=version,
        size_bytes=size_bytes,
        checksum=checksum.hexdigest(),
    )


def format_storage_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def calculate_sha256(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        while True:
            chunk = source.read(CHUNK_SIZE)
            if not chunk:
                break
            checksum.update(chunk)
    return checksum.hexdigest()
