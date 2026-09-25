"""Orchestrates building a themed personal drumkit out of the samples you
actually use across your own beats: scan your .flp projects -> tally usage
-> classify -> dedupe -> keep the top N most-used per category -> generate
thematic unique names -> copy into an organized output folder."""

from __future__ import annotations

import math
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from .classify import CATEGORIES, CATEGORY_FOLDER_NAMES, classify_sample
from .dedupe import Fingerprint, compute_fingerprint, file_hash, is_near_duplicate
from .flp_scan import SampleUsage, UsageScanResult, find_project_flps, scan_usage
from .library_index import build_filename_index
from .naming import CATEGORY_TAGS, build_name_pool

MAX_PER_CATEGORY = 20
_SANITIZE_RE = re.compile(r"[^A-Za-z0-9 \-]+")

# Ranking blends usage count with recency (a project's .flp mtime stands
# in for "when it was last worked on"). Score = usage_count * decay, where
# decay halves every RECENCY_HALF_LIFE_DAYS since the sample's most recent
# use. At 90 days, something used 10x a year ago (decay ~0.017) loses out
# to something used just 5x in the last couple weeks (decay ~0.9) — matches
# the intent that recent rotation should outrank old, rarely-revisited
# favorites, while a sample that's still genuinely dominant (used 50x even
# 6 months back) can still out-rank light recent use.
RECENCY_HALF_LIFE_DAYS = 90.0


def _recency_score(usage: SampleUsage, now_ts: float) -> float:
    if usage.last_used_ts <= 0:
        return 0.0
    days_since = max(0.0, (now_ts - usage.last_used_ts) / 86400.0)
    decay = math.exp(-days_since / RECENCY_HALF_LIFE_DAYS)
    return usage.usage_count * decay


@dataclass
class SoundEntry:
    original_name: str
    new_name: str
    dest_path: str
    usage_count: int
    used_in: list[str]  # beat/project names (capped for display)
    classify_method: str
    resolution_method: str
    days_since_last_used: int | None


@dataclass
class CategoryResult:
    category: str
    folder: str
    tag: str
    entries: list[SoundEntry] = field(default_factory=list)
    candidates_considered: int = 0
    duplicates_skipped: int = 0


@dataclass
class BuildResult:
    kit_name: str
    output_path: str
    categories: dict[str, CategoryResult]
    total_unique: int
    total_flps_scanned: int
    total_flps_failed: int
    total_refs_found: int
    total_unique_samples_resolved: int
    total_missing_refs: int
    unclassified_count: int


def _sanitize(text: str) -> str:
    cleaned = _SANITIZE_RE.sub("", text).strip()
    return re.sub(r"\s+", " ", cleaned) or "Untitled"


def _find_unique_dir(base: Path) -> Path:
    if not base.exists():
        return base
    i = 2
    while True:
        candidate = base.with_name(f"{base.name} ({i})")
        if not candidate.exists():
            return candidate
        i += 1


def _unique_name(stem: str, suffix: str, used_names: set[str]) -> str:
    """Stash-mode naming: keep the original filename, only disambiguating
    with a "(2)", "(3)", ... suffix if two different source files that
    survived dedupe happen to share a name (common — lots of packs ship a
    generic "808 1.wav")."""
    name = f"{stem}{suffix}"
    i = 2
    while name.lower() in used_names:
        name = f"{stem} ({i}){suffix}"
        i += 1
    used_names.add(name.lower())
    return name


def build_drumkit(
    project_folders: list[Path],
    library_search_roots: list[Path],
    output_root: Path,
    producer_name: str,
    world_text: str,
    use_audio_analysis: bool = True,
    use_audio_dedupe: bool = True,
    stash_mode: bool = False,
) -> BuildResult:
    """stash_mode=True builds a "stash": same scan/classify/dedupe/rank/cap
    pipeline, but samples keep their original filenames instead of getting
    a thematic rename (world_text is ignored in this mode). Useful when you
    just want your most-used sounds organized, not reworded."""
    flp_files = find_project_flps(project_folders)

    filename_index = build_filename_index(library_search_roots) if library_search_roots else None
    scan: UsageScanResult = scan_usage(flp_files, filename_index)

    # Classify every unique resolved sample, most-used first within each
    # category (ties broken by path for determinism).
    per_category: dict[str, list[SampleUsage]] = {c: [] for c in CATEGORIES}
    unclassified_count = 0

    for usage in scan.usage_by_key.values():
        if not usage.resolved_path.is_file():
            continue
        result = classify_sample(usage.resolved_path, use_audio_analysis=use_audio_analysis)
        if result is None:
            unclassified_count += 1
            continue
        per_category[result.category].append(usage)

    now_ts = time.time()
    for category in CATEGORIES:
        per_category[category].sort(
            key=lambda u: (-_recency_score(u, now_ts), str(u.resolved_path).lower())
        )

    name_pool = None if stash_mode else build_name_pool(world_text, producer_name)
    kit_display_name = f"{_sanitize(producer_name)} {'Stash' if stash_mode else 'Drumkit'}"
    final_output_path = _find_unique_dir(output_root / kit_display_name)

    categories: dict[str, CategoryResult] = {}

    for category in CATEGORIES:
        result = CategoryResult(
            category=category,
            folder=CATEGORY_FOLDER_NAMES[category],
            tag=CATEGORY_TAGS[category],
        )
        seen_hashes: set[str] = set()
        accepted_fingerprints: list[Fingerprint] = []
        used_names: set[str] = set()
        dest_dir = final_output_path / result.folder

        for usage in per_category[category]:
            if len(result.entries) >= MAX_PER_CATEGORY:
                break
            result.candidates_considered += 1
            candidate = usage.resolved_path

            try:
                h = file_hash(candidate)
            except OSError:
                continue
            if h in seen_hashes:
                result.duplicates_skipped += 1
                continue
            seen_hashes.add(h)

            fp = None
            if use_audio_dedupe:
                fp = compute_fingerprint(candidate)
                if fp is not None and any(
                    is_near_duplicate(fp, existing) for existing in accepted_fingerprints
                ):
                    result.duplicates_skipped += 1
                    continue

            if stash_mode:
                new_filename = _unique_name(candidate.stem, candidate.suffix.lower(), used_names)
            else:
                new_word = name_pool.next_name()
                new_filename = f"{result.tag} - {new_word}{candidate.suffix.lower()}"
                used_names.add(new_filename.lower())
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_dir / new_filename

            try:
                shutil.copy2(candidate, dest_path)
            except OSError:
                continue

            if fp is not None:
                accepted_fingerprints.append(fp)

            used_in = sorted(usage.referencing_flps)
            days_since = (
                int((now_ts - usage.last_used_ts) / 86400.0)
                if usage.last_used_ts > 0 else None
            )
            result.entries.append(SoundEntry(
                original_name=candidate.name,
                new_name=new_filename,
                dest_path=str(dest_path),
                usage_count=usage.usage_count,
                used_in=used_in[:5],
                classify_method="folder/filename/audio",
                resolution_method=usage.resolution_method,
                days_since_last_used=days_since,
            ))

        categories[category] = result

    total_unique = sum(len(r.entries) for r in categories.values())

    return BuildResult(
        kit_name=kit_display_name,
        output_path=str(final_output_path),
        categories=categories,
        total_unique=total_unique,
        total_flps_scanned=scan.flps_scanned,
        total_flps_failed=scan.flps_failed,
        total_refs_found=scan.total_refs,
        total_unique_samples_resolved=len(scan.usage_by_key),
        total_missing_refs=len(scan.missing),
        unclassified_count=unclassified_count,
    )
