"""Classify sample files into drum categories using, in priority order:

  1. The folder they're sitting in (kit authors already sort these —
     "808s", "CLAPS", "HIHAT", "OPEN HAT", "PERC", etc. — this is the
     highest-confidence signal, so it's checked first, closest folder up).
  2. Filename keywords ("808", "kick", "hh", "snare", "clap", ...).
  3. Basic audio analysis as a fallback, restricted to files that aren't
     obviously something else (a preset, MIDI, loop, vocal chain, melodic
     one-shot) so we don't mislabel a bell/organ/choir stem as a drum hit.
  4. Excluded entirely if none of the above apply.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

AUDIO_EXTENSIONS = {".wav", ".wave", ".aif", ".aiff", ".flac", ".ogg", ".m4a", ".mp3"}

CATEGORIES = [
    "808", "kick", "snare", "clap", "hihat_closed", "hihat_open", "percussion",
    "fx", "vox",
]

CATEGORY_FOLDER_NAMES = {
    "808": "808s",
    "kick": "Kicks",
    "snare": "Snares",
    "clap": "Claps",
    "hihat_closed": "Hi-Hats",
    "hihat_open": "Open Hats",
    "percussion": "Percussion",
    "fx": "FX",
    "vox": "Vox",
}

# Ordered (most specific first) — first match wins. Order matters: "808"
# before "kick" (an "808 kick" should be an 808), "open hat" before the
# generic "hat" pattern.
_KEYWORD_RULES: list[tuple[str, re.Pattern]] = [
    ("808", re.compile(r"808", re.IGNORECASE)),
    ("hihat_open", re.compile(r"(open[\s_-]?hat|\boh\b|ohh|oh[\s_-]?hat|\bo[\s_-]hat\b)", re.IGNORECASE)),
    ("hihat_closed", re.compile(r"(hi[\s_-]?hat|hihat|\bhh\b|chh|closed[\s_-]?hat)", re.IGNORECASE)),
    ("clap", re.compile(r"(clap|\bclp\b)", re.IGNORECASE)),
    ("snare", re.compile(r"(snare|\bsd\b|rimshot|\brim\b)", re.IGNORECASE)),
    ("kick", re.compile(r"(kick|\bbd\b|bassdrum|bass[\s_-]?drum)", re.IGNORECASE)),
    ("vox", re.compile(r"(\bvox\b|vocal|acapella|adlib|\bchoir\b)", re.IGNORECASE)),
    ("fx", re.compile(r"(\bfx\b|\bsfx\b|\beffects?\b|riser|impact|whoosh|transition)", re.IGNORECASE)),
    ("percussion", re.compile(
        r"(perc|shaker|tom|conga|bongo|tamb|cymbal|\bride\b|crash|cowbell|"
        r"clave|woodblock|triangle|bell)", re.IGNORECASE)),
]

# Folder names containing any of these are clearly not drum/fx/vox one-shots
# at all (presets, MIDI, loops, melodic instrument stems, mixer state) —
# skip audio-analysis fallback for files sitting under them. Audio analysis
# only ever returns a drum-category guess (never fx/vox), so this only
# gates that last-resort fallback, not folder/filename matching above.
_NON_DRUM_FOLDER_BLOCKLIST = re.compile(
    r"(preset|midi|loop|serum|chord|melod|arp\b|lead|pad\b|"
    r"keys|organ|reverse|bank|stem|mix|image|artwork|read.?terms|"
    r"\btags?\b)",
    re.IGNORECASE,
)


@dataclass
class Classification:
    category: str
    method: str  # "folder" | "filename" | "audio_analysis"
    confidence: str  # "high" | "medium" | "low"


def _match_keywords(text: str) -> str | None:
    for category, pattern in _KEYWORD_RULES:
        if pattern.search(text):
            return category
    return None


_MAX_ANCESTOR_DEPTH = 10


def classify_by_folder(file_path: Path) -> str | None:
    """Walk ancestor folder names from the file's parent upward (closest
    first, up to a sane depth), since samples resolved from .flp
    references can live anywhere on disk — there's no single "kit root"
    to bound the walk to."""
    for folder in list(file_path.parents)[:_MAX_ANCESTOR_DEPTH]:
        match = _match_keywords(folder.name)
        if match:
            return match
    return None


def classify_by_filename(filename: str) -> str | None:
    return _match_keywords(filename)


def is_plausible_drum_location(file_path: Path) -> bool:
    """True unless the file sits under a folder that's clearly not drums
    (presets, MIDI, loops, vocals, melodic one-shots, ...)."""
    for folder in list(file_path.parents)[:_MAX_ANCESTOR_DEPTH]:
        if _NON_DRUM_FOLDER_BLOCKLIST.search(folder.name):
            return False
    return True


def classify_by_audio(path: Path) -> str | None:
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
    if duration <= 0 or duration > 3.0:
        return None  # loops / long recordings aren't one-shots

    peak = float(abs(audio).max()) or 1e-9
    norm = audio / peak

    n = len(norm)
    window = np.hanning(n) if n > 1 else np.ones(n)
    spectrum = np.abs(np.fft.rfft(norm * window))
    freqs = np.fft.rfftfreq(n, d=1.0 / sr)

    spectrum_sum = float(spectrum.sum()) or 1e-9
    spectral_centroid = float((freqs * spectrum).sum() / spectrum_sum)
    low_energy_ratio = float(spectrum[(freqs >= 20) & (freqs < 250)].sum() / spectrum_sum)

    signs = np.sign(norm)
    signs[signs == 0] = 1
    zcr = float((signs[:-1] != signs[1:]).mean()) if n > 1 else 0.0

    if low_energy_ratio > 0.55 and spectral_centroid < 400:
        return "808" if duration >= 0.35 else "kick"

    if zcr > 0.25 and spectral_centroid > 3000:
        return "hihat_closed" if duration <= 0.12 else "hihat_open"

    if zcr > 0.15 and 0.05 <= duration <= 0.35 and spectral_centroid > 1200:
        return "snare" if low_energy_ratio > 0.15 else "clap"

    if duration <= 1.0:
        return "percussion"

    return None


def classify_sample(
    file_path: Path,
    use_audio_analysis: bool,
) -> Classification | None:
    folder_match = classify_by_folder(file_path)
    filename_match = classify_by_filename(file_path.name)

    if folder_match:
        # "FX"/"SFX" folders are frequently used as a catch-all dumping
        # ground in real kits (a vocal chop or riser tossed in with the
        # rest) — if the filename itself names something more specific,
        # trust that over the generic folder.
        if folder_match == "fx" and filename_match and filename_match != "fx":
            return Classification(filename_match, "filename", "high")
        return Classification(folder_match, "folder", "high")

    if filename_match:
        return Classification(filename_match, "filename", "high")

    if use_audio_analysis and is_plausible_drum_location(file_path):
        audio_match = classify_by_audio(file_path)
        if audio_match:
            return Classification(audio_match, "audio_analysis", "medium")

    return None
