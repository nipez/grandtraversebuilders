#!/usr/bin/env python3
"""Refresh sitemap.xml <lastmod> dates from git history of each page's source.

For every <url> already in sitemap.xml, map the <loc> to its HTML file and set
<lastmod> to the date of the newest commit that changed that page's content —
skipping directory-wide inventory chrome (top-bar listing counts, hero totals,
results-count numerals) that get rewritten on every listing audit without
changing the page itself.

Does not add/remove URLs, and leaves <changefreq> / <priority> untouched.

Shallow clones (Cloudflare Pages default): best-effort `git fetch --deepen`;
if a file has no usable history, its existing <lastmod> is kept. Never stamps
today's date as a fallback.

  python3 scripts/update_sitemap_lastmod.py
  python3 scripts/update_sitemap_lastmod.py --dry-run
  python3 scripts/update_sitemap_lastmod.py --verbose

Run after content or listing rebuilds (see README).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITEMAP = ROOT / "sitemap.xml"
SITE = "https://grandtraversebuilders.com"

# URL block: preserve changefreq/priority; only swap lastmod.
URL_BLOCK_RE = re.compile(
    r"(<url><loc>)([^<]+)(</loc><lastmod>)([^<]+)(</lastmod>)",
    re.M,
)

# Inventory counters rewritten whenever listing counts change site-wide.
_NOISE_SUBS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\d+ Builders & Contractors"), "N Builders & Contractors"),
    (
        re.compile(r"Showing <strong>\d+</strong> businesses"),
        "Showing <strong>N</strong> businesses",
    ),
    (
        re.compile(
            r'(<div class="ph-stat-num">)\d+(</div>\s*'
            r'<div class="ph-stat-label">Total Businesses</div>)',
            re.S,
        ),
        r"\1N\2",
    ),
    (
        re.compile(r"We list <strong>\d+</strong> businesses"),
        "We list <strong>N</strong> businesses",
    ),
    (
        re.compile(r"directory of \d+ businesses", re.I),
        "directory of N businesses",
    ),
    (
        re.compile(r"\b\d+ businesses across \d+ trade"),
        "N businesses across M trade",
    ),
    (re.compile(r'"numberOfItems"\s*:\s*\d+'), '"numberOfItems":N'),
]


def normalize_content(text: str) -> str:
    """Strip site-wide inventory chrome so count-only commits don't bump lastmod."""
    for pat, repl in _NOISE_SUBS:
        text = pat.sub(repl, text)
    return text


def run_git(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=check,
    )


def is_shallow_repo() -> bool:
    r = run_git(["rev-parse", "--is-shallow-repository"])
    return r.returncode == 0 and r.stdout.strip() == "true"


def deepen_history(verbose: bool = False) -> None:
    """Best-effort fetch so shallow Cloudflare Pages clones can see real dates."""
    if not is_shallow_repo():
        return
    if verbose:
        print("shallow clone detected; trying git fetch --deepen=200", file=sys.stderr)
    r = run_git(["fetch", "--deepen=200"])
    if r.returncode != 0 and verbose:
        print(
            f"deepen failed (keeping whatever history is available): {r.stderr.strip()}",
            file=sys.stderr,
        )


def loc_to_source(loc: str) -> Path | None:
    """Map a canonical sitemap loc to the HTML file that renders it."""
    if not loc.startswith(SITE):
        return None
    path = loc[len(SITE) :] or "/"
    if path in ("", "/"):
        return ROOT / "index.html"
    if path in ("/blog", "/blog/"):
        return ROOT / "blog" / "index.html"
    rel = path.strip("/")
    html = ROOT / f"{rel}.html"
    if html.is_file():
        return html
    index = ROOT / rel / "index.html"
    if index.is_file():
        return index
    return None


def commit_has_parent(commit: str) -> bool:
    r = run_git(["rev-parse", "--verify", f"{commit}^"])
    return r.returncode == 0


def show_file_at(commit: str, rel: str) -> str | None:
    r = run_git(["show", f"{commit}:{rel}"])
    if r.returncode != 0:
        return None
    return r.stdout


def last_meaningful_date(source: Path, *, content_cache: dict) -> str | None:
    """Newest commit date where normalized page content changed; None if unknown."""
    try:
        rel = source.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return None

    r = run_git(["log", "--format=%H %cs", "--", rel])
    if r.returncode != 0 or not r.stdout.strip():
        return None

    lines = r.stdout.strip().splitlines()
    for i, line in enumerate(lines):
        parts = line.split()
        if len(parts) < 2:
            continue
        commit, date = parts[0], parts[1]
        cache_key = (commit, rel)
        if cache_key not in content_cache:
            content_cache[cache_key] = show_file_at(commit, rel)
        cur = content_cache[cache_key]
        if cur is None:
            continue

        # Oldest commit in log (file introduction, or history truncated).
        if i == len(lines) - 1:
            return date

        # Shallow clone: parent missing — trust this commit's date (file was
        # touched here) rather than inventing today or wiping lastmod.
        if not commit_has_parent(commit):
            return date

        parent = lines[i + 1].split()[0]
        parent_key = (parent, rel)
        if parent_key not in content_cache:
            content_cache[parent_key] = show_file_at(parent, rel)
        prev = content_cache[parent_key]
        if prev is None:
            return date
        if normalize_content(cur) != normalize_content(prev):
            return date

    return lines[0].split()[1] if lines else None


def update_sitemap(*, dry_run: bool = False, verbose: bool = False) -> int:
    deepen_history(verbose=verbose)

    text = SITEMAP.read_text(encoding="utf-8")
    content_cache: dict = {}
    dates: Counter[str] = Counter()
    kept = 0
    updated = 0
    missing_source = 0
    no_history = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal kept, updated, missing_source, no_history
        prefix, loc, mid, old_date, suffix = match.groups()
        source = loc_to_source(loc)
        if source is None:
            missing_source += 1
            if verbose:
                print(f"keep {old_date} (no source file) {loc}", file=sys.stderr)
            dates[old_date] += 1
            kept += 1
            return match.group(0)

        new_date = last_meaningful_date(source, content_cache=content_cache)
        if not new_date:
            no_history += 1
            if verbose:
                print(f"keep {old_date} (no git history) {loc}", file=sys.stderr)
            dates[old_date] += 1
            kept += 1
            return match.group(0)

        dates[new_date] += 1
        if new_date == old_date:
            kept += 1
            if verbose:
                print(f"same {new_date} {loc}", file=sys.stderr)
            return match.group(0)

        updated += 1
        if verbose:
            print(f"{old_date} -> {new_date} {loc}", file=sys.stderr)
        return f"{prefix}{loc}{mid}{new_date}{suffix}"

    new_text = URL_BLOCK_RE.sub(repl, text)
    url_count = len(re.findall(r"<url>", text))
    new_url_count = len(re.findall(r"<url>", new_text))
    if url_count != new_url_count:
        print(
            f"ERROR: URL count changed {url_count} -> {new_url_count}; aborting",
            file=sys.stderr,
        )
        return 1

    if not dry_run and new_text != text:
        SITEMAP.write_text(new_text, encoding="utf-8")

    print(
        f"sitemap lastmod: {url_count} URLs, "
        f"{updated} updated, {kept} unchanged"
        + (" [dry-run]" if dry_run else "")
    )
    if missing_source:
        print(f"  missing source file: {missing_source}", file=sys.stderr)
    if no_history:
        print(f"  no usable git history (kept existing): {no_history}", file=sys.stderr)
    print("  lastmod distribution:")
    for d, n in sorted(dates.items(), reverse=True):
        print(f"    {d}: {n}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and print stats without writing sitemap.xml",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-URL old -> new lastmod lines",
    )
    args = parser.parse_args()
    if not SITEMAP.is_file():
        print(f"missing {SITEMAP}", file=sys.stderr)
        return 1
    if run_git(["rev-parse", "--is-inside-work-tree"]).returncode != 0:
        print("not a git work tree; cannot derive lastmod", file=sys.stderr)
        return 1
    return update_sitemap(dry_run=args.dry_run, verbose=args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
