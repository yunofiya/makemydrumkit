"""Low-level parser for FL Studio project (.flp) files.

The FLP format is a binary TLV (type-length-value) event stream:

    "FLhd" + u32 header_len + u16 format + u16 num_channels + u16 ppq
    "FLdt" + u32 data_len + <events...>

Each event begins with a 1-byte event ID that determines how its
value is encoded:

    0x00-0x3F (0-63):    Byte event   -> 1 byte value
    0x40-0x7F (64-127):  Word event   -> 2 byte value
    0x80-0xBF (128-191): DWord event  -> 4 byte value
    0xC0-0xCF (192-207): Text event   -> varint length + bytes (UTF-16LE
                          in modern FL Studio, plain ASCII/Latin-1 in
                          FL <= 11)
    0xD0-0xFF (208-255): Data event   -> varint length + raw bytes
                          (nested plugin/playlist state)

This module doesn't try to interpret *which* semantic field an event
represents (that mapping differs across FL Studio versions). Instead it
walks the event stream correctly so byte offsets never drift, and hands
every text/data event payload to the caller. Sample-path extraction
then works by pattern-matching decoded strings against audio file
extensions, which is robust across FL Studio versions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

AUDIO_EXTENSIONS = (
    ".wav", ".wave", ".mp3", ".ogg", ".flac", ".aif", ".aiff",
    ".m4a", ".wma", ".fst",
)

# Matches a plausible file path ending in a known audio extension.
_PATH_RE = re.compile(
    r"[^\x00-\x1f\"|?*<>]{3,260}\.(?:wav|wave|mp3|ogg|flac|aif|aiff|m4a|wma)",
    re.IGNORECASE,
)


class FlpParseError(Exception):
    pass


@dataclass
class FlpEvent:
    event_id: int
    raw: bytes
    text: str | None  # decoded text, if this looks like a text/data event


def _read_varlen(data: bytes, pos: int) -> tuple[int, int]:
    """Read an FLP variable-length integer starting at pos.

    Returns (value, new_pos). Format is the standard 7-bit-per-byte
    little-endian varint with the high bit as a continuation flag.
    """
    result = 0
    shift = 0
    while True:
        if pos >= len(data):
            raise FlpParseError("Truncated varint length while reading event")
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
        if shift > 35:
            raise FlpParseError("Varint length too large / corrupt data")
    return result, pos


def _decode_text(raw: bytes) -> str | None:
    """Best-effort decode of a text/data event payload.

    Modern FL Studio (12+) stores text as null-terminated UTF-16LE.
    Older FL Studio (<=11) stores plain ASCII/Latin-1. We try UTF-16LE
    first (only if the byte length is even, as UTF-16 requires), then
    fall back to Latin-1, and give up (return None) if neither yields
    printable text.
    """
    if not raw:
        return None

    if len(raw) % 2 == 0:
        try:
            text = raw.decode("utf-16-le")
        except UnicodeDecodeError:
            text = None
        if text is not None:
            text = text.rstrip("\x00")
            if text and all(c.isprintable() or c in "\t" for c in text):
                return text

    try:
        text = raw.decode("latin-1")
    except UnicodeDecodeError:
        return None
    text = text.rstrip("\x00")
    if text and all(c.isprintable() or c in "\t" for c in text):
        return text
    return None


def iter_events(data: bytes):
    """Yield FlpEvent objects for the raw event stream (post "FLdt" header)."""
    pos = 0
    n = len(data)
    while pos < n:
        event_id = data[pos]
        pos += 1
        if event_id < 64:  # byte event
            if pos + 1 > n:
                break
            raw = data[pos:pos + 1]
            pos += 1
            yield FlpEvent(event_id, raw, None)
        elif event_id < 128:  # word event
            if pos + 2 > n:
                break
            raw = data[pos:pos + 2]
            pos += 2
            yield FlpEvent(event_id, raw, None)
        elif event_id < 192:  # dword event
            if pos + 4 > n:
                break
            raw = data[pos:pos + 4]
            pos += 4
            yield FlpEvent(event_id, raw, None)
        else:  # text (192-207) or data (208-255) event: varint length prefix
            length, pos = _read_varlen(data, pos)
            if pos + length > n:
                # Truncated/corrupt tail; stop rather than misread garbage.
                break
            raw = data[pos:pos + length]
            pos += length
            text = _decode_text(raw) if event_id < 256 else None
            yield FlpEvent(event_id, raw, text)


def parse_flp_header(data: bytes) -> int:
    """Validate the FLP header and return the offset where the data chunk's
    event stream begins."""
    if len(data) < 8 or data[0:4] != b"FLhd":
        raise FlpParseError("Not a valid FLP file (missing 'FLhd' header)")
    header_len = int.from_bytes(data[4:8], "little")
    data_chunk_offset = 8 + header_len
    if len(data) < data_chunk_offset + 8 or data[data_chunk_offset:data_chunk_offset + 4] != b"FLdt":
        raise FlpParseError("Not a valid FLP file (missing 'FLdt' data chunk)")
    events_offset = data_chunk_offset + 8
    return events_offset


def extract_sample_paths(flp_path: Path) -> list[str]:
    """Extract candidate sample file paths referenced by an .flp project.

    Returns raw path strings exactly as stored in the project (may be
    relative, absolute, or use FL Studio's internal path tokens). Order
    is preserved but duplicates are removed.
    """
    data = flp_path.read_bytes()
    events_offset = parse_flp_header(data)

    seen: set[str] = set()
    results: list[str] = []
    for event in iter_events(data[events_offset:]):
        if not event.text:
            continue
        for match in _PATH_RE.finditer(event.text):
            candidate = match.group(0).strip()
            if candidate not in seen:
                seen.add(candidate)
                results.append(candidate)
    return results
