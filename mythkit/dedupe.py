"""Duplicate detection for candidate samples within a category.

Two layers, cheapest first:
  1. Exact byte-hash — catches the same file copied across multiple kits
     (very common — producers share/resell packs).
  2. Basic audio fingerprint (amplitude-envelope vector + duration) — catches
     the same sound re-exported/re-named/re-encoded, when audio analysis
     is enabled.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

_HASH_CHUNK = 1 << 20


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(_HASH_CHUNK):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class Fingerprint:
    envelope: "object"  # numpy array, 32-bucket amplitude envelope
    duration: float


def compute_fingerprint(path: Path) -> Fingerprint | None:
    try:
        import numpy as np
        import soundfile as sf
    except ImportError:
        return None

    try:
        audio, sr = sf.read(str(path), always_2d=False)
    except Exception:
        return None

    if audio is None or len(audio) == 0 or sr <= 0:
        return None
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    audio = audio.astype("float64")
    duration = len(audio) / sr
    peak = float(abs(audio).max()) or 1e-9
    norm = abs(audio) / peak

    buckets = 32
    n = len(norm)
    if n < buckets:
        envelope = np.pad(norm, (0, buckets - n))
    else:
        edges = np.linspace(0, n, buckets + 1).astype(int)
        envelope = np.array([
            norm[edges[i]:edges[i + 1]].mean() if edges[i + 1] > edges[i] else 0.0
            for i in range(buckets)
        ])

    return Fingerprint(envelope=envelope, duration=duration)


def is_near_duplicate(a: Fingerprint, b: Fingerprint, threshold: float = 0.985) -> bool:
    import numpy as np

    if a.duration <= 0 or b.duration <= 0:
        return False
    if abs(a.duration - b.duration) / max(a.duration, b.duration) > 0.03:
        return False

    va, vb = a.envelope, b.envelope
    denom = (np.linalg.norm(va) * np.linalg.norm(vb)) or 1e-9
    similarity = float(np.dot(va, vb) / denom)
    return similarity >= threshold
