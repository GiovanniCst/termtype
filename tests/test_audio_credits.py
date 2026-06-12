"""Tests for audio_credits.py — license normalization, validation."""
import pytest
from pathlib import Path
from termtype.game.audio_credits import (
    normalize_license, parse_credits_text, validate_credit_row,
    CreditRow, ALLOWED_LICENSES, _SELF_GEN_HOSTS,
)


class TestNormalizeLicense:
    def test_cc0_variants(self):
        for variant in ["CC0 1.0", "CC0", "Creative Commons 0", "Public Domain (CC0)",
                        "CC0 (Public Domain)", "CC0 1.0 Universal"]:
            assert normalize_license(variant) == "CC0 1.0"

    def test_self_generated(self):
        assert normalize_license("self-generated") == "self-generated"

    def test_unknown_license(self):
        assert normalize_license("CC-BY 4.0") == "CC-BY 4.0"

    def test_case_insensitive(self):
        assert normalize_license("cc0") == "CC0 1.0"
        assert normalize_license("SELF-GENERATED") == "self-generated"


class TestParseCredits:
    def test_parse_basic(self):
        text = """# Credits
| filename | source | author | license | deed | date | sha256 |
|---|---|---|---|---|---|---|
| click.wav | https://example.com | Kenney | CC0 1.0 | https://creativecommons.org/publicdomain/zero/1.0/ | 2025-01-01 | abc123 |
"""
        rows = parse_credits_text(text)
        assert len(rows) == 1
        assert rows[0].filename == "click.wav"
        assert rows[0].license_normalized == "CC0 1.0"
        assert rows[0].sha256 == "abc123"

    def test_parse_self_generated(self):
        text = """| blip.wav | https://bfxr.net | me | self-generated | https://bfxr.net | 2025-01-01 | def456 |"""
        rows = parse_credits_text(text)
        assert len(rows) == 1
        assert rows[0].license_normalized == "self-generated"
        assert rows[0].author == "me"

    def test_parse_vintage_year(self):
        text = """| rag.mp3 | https://archive.org | artist | CC0 1.0 | https://creativecommons.org/publicdomain/zero/1.0/ | 2025-01-01 | ghi789 | 1920 |"""
        rows = parse_credits_text(text)
        assert len(rows) == 1
        assert rows[0].publication_year == 1920


class TestValidateCreditRow:
    def test_valid_cc0(self):
        row = CreditRow(
            filename="click.wav", source_url="https://example.com",
            author="Kenney", license_badge="CC0 1.0",
            license_normalized="CC0 1.0",
            deed_url="https://creativecommons.org/publicdomain/zero/1.0/",
            date_verified="2025-01-01", sha256="abc123",
        )
        errors = validate_credit_row(row)
        assert errors == []

    def test_disallowed_license(self):
        row = CreditRow(
            filename="click.wav", source_url="https://example.com",
            author="Kenney", license_badge="CC-BY 4.0",
            license_normalized="CC-BY 4.0",
            deed_url="https://creativecommons.org/licenses/by/4.0/",
            date_verified="2025-01-01", sha256="abc123",
        )
        errors = validate_credit_row(row)
        assert any("not in allowlist" in e for e in errors)

    def test_missing_sha256(self):
        row = CreditRow(
            filename="click.wav", source_url="https://example.com",
            author="Kenney", license_badge="CC0 1.0",
            license_normalized="CC0 1.0",
            deed_url="https://creativecommons.org/publicdomain/zero/1.0/",
            date_verified="2025-01-01", sha256="",
        )
        errors = validate_credit_row(row)
        assert any("missing sha256" in e for e in errors)

    def test_self_generated_requires_deed(self):
        row = CreditRow(
            filename="blip.wav", source_url="https://bfxr.net",
            author="me", license_badge="self-generated",
            license_normalized="self-generated",
            deed_url="", date_verified="2025-01-01", sha256="abc",
        )
        errors = validate_credit_row(row)
        assert any("requires deed_url" in e for e in errors)

    def test_self_generated_bad_host(self):
        row = CreditRow(
            filename="blip.wav", source_url="https://bfxr.net",
            author="me", license_badge="self-generated",
            license_normalized="self-generated",
            deed_url="https://example.com/grant",
            date_verified="2025-01-01", sha256="abc",
        )
        errors = validate_credit_row(row)
        assert any("not in allowlist" in e for e in errors)

    def test_self_generated_valid(self):
        row = CreditRow(
            filename="blip.wav", source_url="https://bfxr.net",
            author="me", license_badge="self-generated",
            license_normalized="self-generated",
            deed_url="https://bfxr.net/license",
            date_verified="2025-01-01", sha256="abc",
        )
        errors = validate_credit_row(row)
        assert errors == []

    def test_vintage_year_gate(self):
        row = CreditRow(
            filename="rag.mp3", source_url="https://archive.org",
            author="artist", license_badge="CC0 1.0",
            license_normalized="CC0 1.0",
            deed_url="https://creativecommons.org/publicdomain/zero/1.0/",
            date_verified="2025-01-01", sha256="abc",
            publication_year=2020,  # Not > current_year - 100
        )
        errors = validate_credit_row(row)
        assert any("publication_year" in e for e in errors)
