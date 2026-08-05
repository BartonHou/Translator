"""Parsing/serialization for file translation.

A file is split into translatable *segments* (order preserved) plus enough
structure to reassemble the translated file in the original format. Kept as pure
functions so parse/serialize round-trips are unit-testable without real uploads.

Supported formats:
  * txt / md — one segment per non-empty line; blank lines preserved as structure.
  * srt      — subtitle text lines are segments; indices and timestamps preserved.
"""
import re

SUPPORTED_EXTENSIONS = {"txt", "md", "srt"}


def detect_format(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"unsupported file type '.{ext}'; supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
    return ext


# --- txt / md --------------------------------------------------------------
def parse_text(content: str) -> tuple[list[str], list]:
    """Return (segments, skeleton). Skeleton is a list of either the string
    ``None`` placeholder marking a segment slot, or literal text (blank lines)."""
    segments: list[str] = []
    skeleton: list = []
    for line in content.split("\n"):
        if line.strip():
            skeleton.append(("seg", len(segments)))
            segments.append(line)
        else:
            skeleton.append(("lit", line))
    return segments, skeleton


def serialize_text(translated: list[str], skeleton: list) -> str:
    out = []
    for kind, val in skeleton:
        out.append(translated[val] if kind == "seg" else val)
    return "\n".join(out)


# --- srt --------------------------------------------------------------------
_SRT_TS = re.compile(r"^\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}")


def parse_srt(content: str) -> tuple[list[str], list]:
    """Parse SubRip. Text lines become segments; index numbers and timestamp
    lines are preserved as literals in the skeleton."""
    segments: list[str] = []
    skeleton: list = []
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.isdigit() or _SRT_TS.match(stripped) or not stripped:
            skeleton.append(("lit", line))
        else:
            skeleton.append(("seg", len(segments)))
            segments.append(line)
    return segments, skeleton


def parse_file(content: str, fmt: str) -> tuple[list[str], list]:
    if fmt == "srt":
        return parse_srt(content)
    return parse_text(content)  # txt / md


def serialize_file(translated: list[str], skeleton: list, fmt: str) -> str:
    # Both formats reassemble the same way (segments slotted back into skeleton).
    return serialize_text(translated, skeleton)
