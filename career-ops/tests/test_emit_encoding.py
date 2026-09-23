#!/usr/bin/env python3
"""Regression: `emit()` must survive a non-UTF-8 console code page.

Observed defect (2026-09-23): Windows Task Scheduler redirects stdout to a file
whose encoding defaults to the OEM/ANSI code page (cp1252 on this host). A
regional scan that had *succeeded* then aborted inside `emit()` with
UnicodeEncodeError while printing non-Latin job titles. The scheduled run
therefore reported exit code 1 for completed work and the run log captured a
traceback instead of the JSON result.

These tests pin the contract: exactly one JSON object on stdout, and never a
UnicodeEncodeError, whichever code page the console uses.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import career_ops_cli  # noqa: E402

# Job titles of the shape that actually crashed the scheduled run.
NON_LATIN_PAYLOAD = {
    "region": "uk",
    "ok": True,
    "eligible": [{"title": "サイバーセキュリティ アナリスト", "company": "株式会社テスト"}],
    "note": "Ünïcödé — naïve café",
}


class _FakeStdout:
    """A stdout whose encoding mimics a legacy Windows code page."""

    def __init__(self, encoding: str):
        self.encoding = encoding
        self.buffer: list[str] = []

    def write(self, text: str) -> int:
        # This is exactly what the real TextIOWrapper does: it raises when the
        # text cannot be represented in the console code page.
        text.encode(self.encoding)
        self.buffer.append(text)
        return len(text)

    def flush(self) -> None:
        pass

    @property
    def text(self) -> str:
        return "".join(self.buffer)


@pytest.mark.parametrize("encoding", ["cp1252", "ascii", "utf-8"])
def test_emit_never_raises_on_any_code_page(encoding, monkeypatch):
    fake = _FakeStdout(encoding)
    monkeypatch.setattr(career_ops_cli.sys, "stdout", fake)

    career_ops_cli.emit(NON_LATIN_PAYLOAD)  # must not raise

    parsed = json.loads(fake.text)
    assert parsed["ok"] is True
    assert parsed["region"] == "uk"
    assert len(parsed["eligible"]) == 1
    # The JSON object must survive intact, not be partially written: the
    # escaped form decodes back to the original string.
    assert parsed["eligible"][0]["title"] == "サイバーセキュリティ アナリスト"


def test_emit_writes_exactly_one_json_object(monkeypatch):
    fake = _FakeStdout("cp1252")
    monkeypatch.setattr(career_ops_cli.sys, "stdout", fake)

    career_ops_cli.emit(NON_LATIN_PAYLOAD)

    # One object, not a concatenation: decoding consumes the whole output.
    assert fake.text.endswith("\n")
    decoder = json.JSONDecoder()
    obj, end = decoder.raw_decode(fake.text)
    assert obj["region"] == "uk"
    assert fake.text[end:].strip() == ""


def test_emit_keeps_utf8_unescaped_when_the_console_supports_it(monkeypatch):
    fake = _FakeStdout("utf-8")
    monkeypatch.setattr(career_ops_cli.sys, "stdout", fake)

    career_ops_cli.emit({"title": "サイバー"})

    assert "サイバー" in fake.text
