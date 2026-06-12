"""Pure CREDITS.md parsing, license normalization, and allowlist enforcement.

PLAN §8.8. Shared by test_audio_credits.py and runtime mood-availability check.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


# License allowlist (PLAN §8.8)
ALLOWED_LICENSES = {"CC0 1.0", "self-generated"}

# CC0 badge text normalization
_CC0_PATTERNS = [
    "cc0 1.0",
    "cc0 1.0 universal",
    "creative commons 0",
    "cc0",
    "public domain (cc0)",
    "cc0 (public domain)",
]

# Self-generated deed-host allowlist
_SELF_GEN_HOSTS = {"bfxr.net", "sfxr.me", "drpetter.se"}

# Vintage source hosts
_VINTAGE_HOSTS = {"archive.org", "musopen.org"}


@dataclass
class CreditRow:
    """A single row from CREDITS.md."""
    filename: str
    source_url: str
    author: str
    license_badge: str
    license_normalized: str
    deed_url: str
    date_verified: str
    sha256: str
    publication_year: int | None = None  # for vintage


def parse_credits(credits_path: Path | str) -> list[CreditRow]:
    """Parse a CREDITS.md file into CreditRow objects."""
    path = Path(credits_path)
    text = path.read_text(encoding="utf-8")
    return parse_credits_text(text)


def parse_credits_text(text: str) -> list[CreditRow]:
    """Parse CREDITS.md text into CreditRow objects."""
    rows = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("|---"):
            continue
        if not line.startswith("|"):
            continue

        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 7:
            continue

        filename = cells[0]

        # Skip header rows
        if filename.lower() in ("filename", "file", "name"):
            continue
        source_url = cells[1]
        author = cells[2]
        license_badge = cells[3]
        deed_url = cells[4]
        date_verified = cells[5]
        sha256 = cells[6]

        # Publication year for vintage (optional 8th column)
        pub_year = None
        if len(cells) > 7 and cells[7].strip():
            try:
                pub_year = int(cells[7].strip())
            except ValueError:
                pass

        license_normalized = normalize_license(license_badge)

        rows.append(CreditRow(
            filename=filename,
            source_url=source_url,
            author=author,
            license_badge=license_badge,
            license_normalized=license_normalized,
            deed_url=deed_url,
            date_verified=date_verified,
            sha256=sha256,
            publication_year=pub_year,
        ))

    return rows


def normalize_license(badge_text: str) -> str:
    """Normalize verbatim badge text to an allowlisted token.

    Returns the normalized token, or the original if no match.
    """
    lower = badge_text.strip().lower()
    for pattern in _CC0_PATTERNS:
        if lower == pattern:
            return "CC0 1.0"
    if lower == "self-generated":
        return "self-generated"
    return badge_text.strip()


def validate_credit_row(row: CreditRow) -> list[str]:
    """Validate a single credit row. Returns list of error messages."""
    errors = []

    # Check normalized license is allowlisted
    if row.license_normalized not in ALLOWED_LICENSES:
        errors.append(f"{row.filename}: license '{row.license_badge}' not in allowlist")

    # Mandatory sha256
    if not row.sha256 or not row.sha256.strip():
        errors.append(f"{row.filename}: missing sha256")

    # Self-generated validation
    if row.license_normalized == "self-generated":
        if not row.author or not row.author.strip():
            errors.append(f"{row.filename}: self-generated requires author")
        if not row.deed_url or not row.deed_url.strip():
            errors.append(f"{row.filename}: self-generated requires deed_url")
        else:
            # Check deed host
            host = _extract_host(row.deed_url)
            if host not in _SELF_GEN_HOSTS:
                errors.append(f"{row.filename}: deed host '{host}' not in allowlist")
        if not row.date_verified or not row.date_verified.strip():
            errors.append(f"{row.filename}: self-generated requires date_verified")

    # Vintage year gate
    if row.publication_year is not None:
        current_year = datetime.now().year
        if row.publication_year > current_year - 100:
            errors.append(
                f"{row.filename}: publication_year {row.publication_year} "
                f"is not > {current_year} - 100 = {current_year - 100}"
            )

    return errors


def validate_credits_against_files(
    credits_path: Path | str,
    audio_dir: Path | str,
) -> list[str]:
    """Validate credits against actual audio files (bidirectional).

    Returns list of error messages.
    """
    credits_path = Path(credits_path)
    audio_dir = Path(audio_dir)

    errors = []

    # Parse credits
    rows = parse_credits(credits_path)
    credited_files = {r.filename for r in rows}

    # Check every file has a credit row
    actual_files = set()
    for f in audio_dir.rglob("*"):
        if f.is_file() and f.suffix.lower() in (".wav", ".ogg", ".mp3", ".flac"):
            actual_files.add(f.name)

    # Orphan files (no credit row)
    for f in actual_files - credited_files:
        errors.append(f"Orphan file: {f} has no credit row")

    # Stale rows (credit for non-existent file)
    for f in credited_files - actual_files:
        errors.append(f"Stale row: {f} referenced in credits but not found")

    # Validate each row
    for row in rows:
        errors.extend(validate_credit_row(row))

    return errors


def verify_sha256(filepath: Path | str, expected_hash: str) -> bool:
    """Verify a file's SHA256 matches the expected hash."""
    path = Path(filepath)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    return actual == expected_hash


def mood_available(mood: str, credits_path: Path | str, audio_dir: Path | str) -> bool:
    """Check if a mood has at least one allowlisted track.

    Used by both test and runtime to determine if a mood is selectable.
    """
    credits_path = Path(credits_path)
    audio_dir = Path(audio_dir)

    if not credits_path.exists():
        return False

    rows = parse_credits(credits_path)
    mood_dir = audio_dir / mood

    for row in rows:
        if row.license_normalized not in ALLOWED_LICENSES:
            continue
        # Check if the file exists in the mood directory
        if (mood_dir / row.filename).exists():
            return True

    return False


def _extract_host(url: str) -> str:
    """Extract hostname from a URL."""
    match = re.search(r"https?://([^/]+)", url)
    if match:
        return match.group(1).lower()
    return ""
