#!/usr/bin/env python3
"""Add a "Search" link to the main nav on every page (before "List Your
Business"). Uses a root-relative /search href so it works at any URL depth.
Idempotent."""
import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
NAV_RE = re.compile(r'(<li><a class="nav-cta" href="[^"]*claim\.html">List Your Business</a></li>)')
SEARCH_LI = '<li><a href="/search">Search</a></li>'


def iter_files():
    for name in ("index.html", "categories.html", "claim.html", "plan-my-build.html"):
        p = ROOT / name
        if p.exists():
            yield p
    for sub in ("business", "category", "blog"):
        yield from sorted((ROOT / sub).glob("*.html"))


def main():
    changed = 0
    for p in iter_files():
        t = p.read_text(encoding="utf-8")
        if '<a href="/search"' in t:
            continue
        new, n = NAV_RE.subn(SEARCH_LI + r"\1", t, count=1)
        if n:
            p.write_text(new, encoding="utf-8")
            changed += 1
    print(f"Added Search nav link to {changed} files")


if __name__ == "__main__":
    main()
