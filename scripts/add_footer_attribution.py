#!/usr/bin/env python3
"""Add "Built by Solution Studio" (linked) to the footer on every page.
Idempotent: pages already containing the link are skipped."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

LINK = '<a href="https://solutionstud.io/" target="_blank" rel="noopener">Solution Studio</a>'
# Standard footer (505 content pages): add a span after the copyright span.
ANCHOR = "<span>&copy; 2026 Grand Traverse Builders. All rights reserved.</span>"
ADDITION = f"<span>Built by {LINK}</span>"
# search.html has a single-line <footer>.
SEARCH_ANCHOR = " &middot; Wexford</footer>"
SEARCH_ADDITION = f" &middot; Wexford &middot; Built by {LINK}</footer>"


def iter_files():
    for name in ("index.html", "categories.html", "claim.html", "plan-my-build.html", "search.html"):
        p = ROOT / name
        if p.exists():
            yield p
    for sub in ("business", "category", "blog"):
        yield from sorted((ROOT / sub).glob("*.html"))


def main():
    changed = 0
    for p in iter_files():
        t = p.read_text(encoding="utf-8")
        if "solutionstud.io" in t:
            continue
        new = t
        if ANCHOR in new:
            new = new.replace(ANCHOR, ANCHOR + ADDITION, 1)
        elif SEARCH_ANCHOR in new:
            new = new.replace(SEARCH_ANCHOR, SEARCH_ADDITION, 1)
        if new != t:
            p.write_text(new, encoding="utf-8")
            changed += 1
    print(f"Added footer attribution to {changed} files")


if __name__ == "__main__":
    main()
