"""Scan a set of .flp project files and tally how often each real,
resolvable audio sample gets used across them — this is the "most used
sounds from your beats" signal the drumkit is built from."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .flp_parser import FlpParseError, extract_sample_paths
from .resolver import resolve_with_library


@dataclass
class SampleUsage:
    resolved_path: Path
    usage_count: int = 0
    referencing_flps: set[str] = field(default_factory=set)
    resolution_method: str = "direct"
    last_used_ts: float = 0.0  # newest mtime among referencing .flp files


@dataclass
class UsageScanResult:
    usage_by_key: dict[str, SampleUsage]  # key = lowercased resolved path
    missing: list[tuple[str, str]]  # (raw_path, flp_filename)
    flps_scanned: int
    flps_failed: int
    total_refs: int


def find_project_flps(folders: list[Path]) -> list[Path]:
    """Recursively find .flp files under the given folders, excluding FL
    Studio's autosave "Backup" subfolders (otherwise usage counts get
    massively skewed by dozens of near-identical autosaves of the same
    song rather than reflecting genuinely distinct beats)."""
    files: list[Path] = []
    seen: set[str] = set()
    for folder in folders:
        if not folder.is_dir():
            continue
        for path in folder.rglob("*.flp"):
            if any(part.lower() == "backup" for part in path.parts):
                continue
            key = str(path).lower()
            if key not in seen:
                seen.add(key)
                files.append(path)
    return files


def scan_usage(
    flp_files: list[Path],
    filename_index: dict[str, list[Path]] | None,
) -> UsageScanResult:
    usage_by_key: dict[str, SampleUsage] = {}
    missing: list[tuple[str, str]] = []
    flps_failed = 0
    total_refs = 0

    for flp_file in flp_files:
        try:
            raw_paths = extract_sample_paths(flp_file)
        except FlpParseError:
            flps_failed += 1
            continue
        except OSError:
            flps_failed += 1
            continue

        try:
            flp_mtime = flp_file.stat().st_mtime
        except OSError:
            flp_mtime = 0.0

        for raw in raw_paths:
            total_refs += 1
            resolved = resolve_with_library(raw, flp_file.parent, filename_index)
            if not resolved.found or resolved.resolved_path is None:
                missing.append((raw, flp_file.name))
                continue

            key = str(resolved.resolved_path).lower()
            usage = usage_by_key.get(key)
            if usage is None:
                usage = SampleUsage(
                    resolved_path=resolved.resolved_path,
                    resolution_method=resolved.method,
                )
                usage_by_key[key] = usage
            usage.usage_count += 1
            usage.referencing_flps.add(flp_file.stem)
            usage.last_used_ts = max(usage.last_used_ts, flp_mtime)

    return UsageScanResult(
        usage_by_key=usage_by_key,
        missing=missing,
        flps_scanned=len(flp_files) - flps_failed,
        flps_failed=flps_failed,
        total_refs=total_refs,
    )
