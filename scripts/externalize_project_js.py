#!/usr/bin/env python3
"""Replace the ~35KB inline planner/favorites script (duplicated verbatim into
every page) with a single external reference to /project.js.

The inline block is byte-identical to project.js on every page, so this is a
behaviour-preserving change that:
  - removes ~35KB of duplicated JS from each of the 505 pages (page-weight win),
  - makes project.js the single source of truth for planner/favorites/search JS.

Idempotent: pages already using <script src="/project.js"> are skipped.
"""
import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

# A bare <script>...</script> block (not type="application/ld+json"/gtag) that
# contains the planner constant BUILD_PHASES — i.e. the inlined project.js.
BLOCK_RE = re.compile(r"<script>(?:(?!</script>).)*?BUILD_PHASES(?:(?!</script>).)*?</script>", re.S)
EXTERNAL = '<script src="/project.js" defer></script>'


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
        new, n = BLOCK_RE.subn(EXTERNAL, t)
        if n > 1:
            raise SystemExit(f"{p}: matched {n} planner blocks, expected 1 — aborting")
        if n == 1 and new != t:
            p.write_text(new, encoding="utf-8")
            changed += 1
    print(f"Externalized inline project.js in {changed} files")


if __name__ == "__main__":
    main()
