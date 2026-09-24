"""An index of audio filenames under one or more "sample library" search
roots, used as a fallback when an .flp's stored path doesn't resolve
directly (very common: projects get moved between computers/drives, so a
reference like "D:\\Kits\\WH 808 - CROWN.wav" won't exist here even though
the same file is sitting locally in a reorganized kit library)."""

from __future__ import annotations

from pathlib import Path

from .classify import AUDIO_EXTENSIONS


def build_filename_index(search_roots: list[Path]) -> dict[str, list[Path]]:
    """Map lowercased filename -> list of matching absolute paths found
    under any of the given roots."""
    index: dict[str, list[Path]] = {}
    for root in search_roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            key = path.name.lower()
            index.setdefault(key, []).append(path)
    return index


def lookup(index: dict[str, list[Path]], filename: str) -> Path | None:
    candidates = index.get(filename.lower())
    if not candidates:
        return None
    return candidates[0]
