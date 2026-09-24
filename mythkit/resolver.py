"""Resolve raw sample path strings pulled out of an .flp file into real,
existing files on disk (or report that they're missing)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# FL Studio substitutes these tokens for shared/factory content locations.
# We try common installed locations for each; if none exist, the token is
# left unresolved and the sample is reported as missing.
_TOKEN_ENV_CANDIDATES = {
    "%FLStudioFactoryData%": [
        r"C:\Program Files\Image-Line\FL Studio 20\Data\Patches",
        r"C:\Program Files\Image-Line\FL Studio 21\Data\Patches",
        r"C:\Program Files\Image-Line\FL Studio 2024\Data\Patches",
        r"C:\Program Files (x86)\Image-Line\Shared\Data\Patches",
    ],
    "%FLStudioUserData%": [
        os.path.expandvars(r"%USERPROFILE%\Documents\Image-Line\FL Studio"),
    ],
    "FLStudioFactoryData": [
        r"C:\Program Files\Image-Line\FL Studio 20\Data\Patches",
        r"C:\Program Files\Image-Line\FL Studio 21\Data\Patches",
        r"C:\Program Files\Image-Line\FL Studio 2024\Data\Patches",
    ],
}


@dataclass
class ResolvedSample:
    raw_path: str          # exactly as stored in the .flp
    resolved_path: Path | None  # absolute path if found on disk, else None
    found: bool
    method: str = "direct"  # "direct" | "library_search"


def _substitute_tokens(raw_path: str) -> str:
    for token, candidates in _TOKEN_ENV_CANDIDATES.items():
        if token in raw_path:
            for candidate_root in candidates:
                if Path(candidate_root).exists():
                    return raw_path.replace(token, candidate_root)
    return raw_path


def resolve_sample_path(raw_path: str, flp_dir: Path) -> ResolvedSample:
    """Try to locate the real file for a raw path string extracted from an
    .flp project.

    Resolution order:
      1. Substitute known FL Studio path tokens if present.
      2. If already absolute and it exists, use it.
      3. Try relative to the .flp file's directory.
      4. Try relative to the .flp directory's parent (some projects
         reference "../Samples/...").
      5. Give up and report as missing (raw path preserved for reporting).
    """
    candidate = _substitute_tokens(raw_path.strip())
    candidate = candidate.replace("/", os.sep).replace("\\", os.sep)

    p = Path(candidate)
    if p.is_absolute():
        if p.exists():
            return ResolvedSample(raw_path, p.resolve(), True)
        # Absolute but from a different machine/drive: try re-anchoring
        # just the filename under the flp directory as a last resort.
        fallback = flp_dir / p.name
        if fallback.exists():
            return ResolvedSample(raw_path, fallback.resolve(), True)
        return ResolvedSample(raw_path, None, False)

    for base in (flp_dir, flp_dir.parent):
        candidate_path = (base / p).resolve()
        if candidate_path.exists():
            return ResolvedSample(raw_path, candidate_path, True)

    # Last resort: just the filename directly in the flp directory
    # (handles projects that only stored a bare filename).
    fallback = flp_dir / p.name
    if fallback.exists():
        return ResolvedSample(raw_path, fallback.resolve(), True)

    return ResolvedSample(raw_path, None, False)


def resolve_with_library(
    raw_path: str,
    flp_dir: Path,
    filename_index: dict[str, list[Path]] | None,
) -> ResolvedSample:
    """Try direct resolution first; if that fails and a filename index was
    built from local sample-library search roots, fall back to a
    filename-only lookup there. This is what actually recovers most
    references in practice — .flp files commonly store absolute paths from
    a different computer or drive letter that no longer exists locally."""
    direct = resolve_sample_path(raw_path, flp_dir)
    if direct.found:
        return direct

    if filename_index:
        from .library_index import lookup
        match = lookup(filename_index, Path(raw_path.strip()).name)
        if match is not None:
            return ResolvedSample(raw_path, match, True, method="library_search")

    return direct
