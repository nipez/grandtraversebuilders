#!/usr/bin/env python3
"""Replace the ~35KB inline planner/favorites script (duplicated into every page)
with a single external reference to /project.js.

Idempotent: pages already using <script src="/project.js"> are skipped.
"""
import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

BLOCK_RE = re.compile(
    r"<script>(?:(?!</script>).)*?BUILD_PHASES(?:(?!</script>).)*?</script>",
    re.S,
)
EXTERNAL = '<script src="/project.js" defer></script>'


def iter_files():
    for name in (
        "index.html",
        "categories.html",
        "claim.html",
        "plan-my-build.html",
        "search.html",
        "favorites.html",
        "404.html",
    ):
        p = ROOT / name
        if p.exists():
            yield p
    for sub in ("business", "category", "blog"):
        d = ROOT / sub
        if d.is_dir():
            yield from sorted(d.glob("*.html"))


def main():
    changed = 0
    skipped = 0
    for p in iter_files():
        t = p.read_text(encoding="utf-8")
        if 'src="/project.js"' in t and "BUILD_PHASES" not in t:
            skipped += 1
            continue
        new, n = BLOCK_RE.subn(EXTERNAL, t)
        if n > 1:
            raise SystemExit(f"{p}: matched {n} planner blocks, expected ≤1 — aborting")
        if n == 1 and new != t:
            p.write_text(new, encoding="utf-8")
            changed += 1
        elif n == 0 and "BUILD_PHASES" in t:
            raise SystemExit(f"{p}: contains BUILD_PHASES but regex missed the block")
    print(f"Externalized inline project.js in {changed} files ({skipped} already external)")


if __name__ == "__main__":
    main()
