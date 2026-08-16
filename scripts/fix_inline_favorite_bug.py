#!/usr/bin/env python3
"""Fix the favorite/Save button bug in the INLINE script copied into every page.

Every HTML page inlines the planner/favorites logic (none load the external
project.js). The inline `getCurrentBusinessSlug()` required a ".html" extension,
so it returned null under the clean/extensionless URLs the site is actually
served at, and the business-page Save button (#detailHeart) was never injected.

This makes the ".html" suffix optional (matching the external project.js fix)
across all inline copies. Idempotent.
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

OLD = (
    "  const h=window.location.pathname+window.location.href;\n"
    "  const m=h.match(/business\\/([^/.?#]+)\\.html/);\n"
)
NEW = "  const m=window.location.pathname.match(/\\/business\\/([^/]+?)(?:\\.html)?\\/?$/);\n"


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
        if OLD in t:
            p.write_text(t.replace(OLD, NEW), encoding="utf-8")
            changed += 1
    print(f"Fixed inline getCurrentBusinessSlug in {changed} files")


if __name__ == "__main__":
    main()
