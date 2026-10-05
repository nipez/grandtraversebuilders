#!/usr/bin/env python3
"""Inject a contextual Traverse City home builders hub link on every business page.

Idempotent. Inserts a short related-context line after the breadcrumbs block when
missing. Uses extensionless /traverse-city-home-builders and a stable HTML
comment marker so re-runs are safe.

Run:  python3 scripts/add_hub_links_business.py
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
BIZ_DIR = ROOT / "business"
MARKER = "<!-- gtb-hub-link -->"
HUB_BLOCK = (
    f"{MARKER}\n"
    '<p class="biz-hub-context" style="max-width:1340px;margin:0 auto;padding:0 40px 12px;'
    'font-size:.88rem;line-height:1.7;color:var(--text-light);">'
    "Exploring the local market? See our "
    '<a href="../traverse-city-home-builders" '
    'style="color:var(--copper-warm);font-weight:600;text-decoration:none;">'
    "Traverse City home builders</a> hub for an overview, then compare listings "
    "in the full directory."
    "</p>\n"
)

BREADCRUMBS_RE = re.compile(
    r'(<div class="breadcrumbs">\s*.*?\s*</div>\s*\n)',
    re.DOTALL,
)


def main() -> None:
    changed = 0
    skipped = 0
    missing = 0
    for path in sorted(BIZ_DIR.glob("*.html")):
        text = path.read_text(encoding="utf-8")
        if MARKER in text or 'href="../traverse-city-home-builders"' in text:
            skipped += 1
            continue
        new, n = BREADCRUMBS_RE.subn(r"\1" + HUB_BLOCK, text, count=1)
        if n:
            path.write_text(new, encoding="utf-8")
            changed += 1
        else:
            missing += 1
            print(f"[MISS] no breadcrumbs match: {path.name}")
    print(
        f"Added hub links to {changed} business pages "
        f"({skipped} already linked, {missing} unmatched)"
    )


if __name__ == "__main__":
    main()
