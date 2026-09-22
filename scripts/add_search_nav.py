#!/usr/bin/env python3
"""Add a root-relative Search nav link before the List Your Business CTA.

Idempotent. Matches the current claim CTA pattern across top-level and nested
pages:

    <li><a class="nav-cta" href="claim">List Your Business</a></li>
    <li><a class="nav-cta" href="../claim">List Your Business</a></li>
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
CTA_RE = re.compile(
    r'(<li><a class="nav-cta" href="[^"]*claim">List Your Business</a></li>)'
)
SEARCH_LI = '<li><a href="/search">Search</a></li>'
SKIP_NAMES = {"404.html"}


def iter_html() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for p in ROOT.rglob("*.html"):
        if any(part.startswith(".") for part in p.parts):
            continue
        if p.name in SKIP_NAMES:
            continue
        files.append(p)
    return sorted(files)


def main() -> None:
    changed = 0
    skipped = 0
    for path in iter_html():
        text = path.read_text(encoding="utf-8")
        if 'href="/search"' in text or "href='/search'" in text:
            skipped += 1
            continue
        new, n = CTA_RE.subn(SEARCH_LI + r"\1", text, count=1)
        if n:
            path.write_text(new, encoding="utf-8")
            changed += 1
        else:
            skipped += 1
    print(f"Added Search nav link to {changed} files ({skipped} skipped)")


if __name__ == "__main__":
    main()
