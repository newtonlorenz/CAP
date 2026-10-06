"""Bounded storage and integrity checks for reusable preparation evidence."""

import hashlib
import re
from pathlib import Path

from fastapi import HTTPException

from app.config import settings

# Match the review evidence formats; downloads are always attachments.
ALLOWED_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".csv",
    ".txt",
    ".md",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".zip",
}


def evidence_root() -> Path:
    return Path(settings.upload_dir).resolve() / "preparation-evidence"


def clean_filename(filename: str | None) -> str:
    name = (filename or "evidence").replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip(". ")
    # Bound the filename in bytes as well as characters for the host filesystem.
    suffix = Path(name).suffix.lower()
    stem = Path(name).stem.encode("utf-8")[:160].decode("utf-8", errors="ignore")
    return f"{stem or 'evidence'}{suffix[:16]}"


def checked_evidence_path(item) -> Path:
    if item.kind != "file" or not item.file_path:
        raise HTTPException(404, "Evidence file not found")
    root = evidence_root().resolve()
    path = Path(item.file_path)
    if not path.is_absolute():
        path = Path(settings.upload_dir).resolve() / path
    path = path.resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, "Evidence file not found")
    return path


def file_digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def verify_evidence_file(item) -> Path:
    path = checked_evidence_path(item)
    if path.stat().st_size != item.size_bytes or file_digest(path) != item.sha256:
        raise HTTPException(
            409, "Evidence file has changed. Upload a new verified copy before using it."
        )
    return path
