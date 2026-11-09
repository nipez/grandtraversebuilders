#!/usr/bin/env python3
"""Submit changed (or selected) sitemap URLs to IndexNow.

Posts JSON to https://api.indexnow.org/indexnow with host, key, keyLocation,
and urlList. The key file is public by design at /<key>.txt on the site root.

Modes:
  (default)  Diff sitemap.xml <loc>/<lastmod> against the previous commit
             (or a git ref passed as a positional argument) and submit new
             or changed URLs.
  --all      Submit every <loc> in the current sitemap.xml.
  --urls     Submit the given URL(s) only (space-separated).

Flags:
  --dry-run  Print the payload; do not POST.
  --verbose  Log each URL in the submission set.

Examples:
  python3 scripts/indexnow_submit.py --dry-run
  python3 scripts/indexnow_submit.py HEAD~1
  python3 scripts/indexnow_submit.py --all
  python3 scripts/indexnow_submit.py --urls https://grandtraversebuilders.com/about

Weekly SEO blog posts are added to sitemap.xml, so the default sitemap-diff
mode picks them up automatically after deploy (see README).

Exit codes:
  0  Success (HTTP 200/202), dry-run, or nothing to submit. Non-2xx IndexNow
     responses also exit 0 after a warning so deploy/CI is never failed.
  1  Local/usage error (bad args, missing sitemap, git failure).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITEMAP = ROOT / "sitemap.xml"
HOST = "grandtraversebuilders.com"
KEY = "07a8cebdaa07da33e0ad820b1a1ec2de"
KEY_LOCATION = f"https://{HOST}/{KEY}.txt"
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
MAX_URLS_PER_REQUEST = 10_000
SM_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def parse_sitemap_entries(xml_text: str) -> dict[str, str | None]:
    """Return {loc: lastmod_or_None} from sitemap XML text."""
    root = ET.fromstring(xml_text)
    entries: dict[str, str | None] = {}
    for url_el in root.findall("sm:url", SM_NS):
        loc_el = url_el.find("sm:loc", SM_NS)
        if loc_el is None or not (loc_el.text or "").strip():
            continue
        loc = loc_el.text.strip()
        lastmod_el = url_el.find("sm:lastmod", SM_NS)
        lastmod = (lastmod_el.text or "").strip() if lastmod_el is not None else None
        entries[loc] = lastmod or None
    return entries


def load_current_sitemap() -> dict[str, str | None]:
    if not SITEMAP.is_file():
        raise FileNotFoundError(f"missing sitemap: {SITEMAP}")
    return parse_sitemap_entries(SITEMAP.read_text(encoding="utf-8"))


def load_sitemap_at_ref(git_ref: str) -> dict[str, str | None] | None:
    """Load sitemap.xml at git_ref. Returns None if the file did not exist."""
    result = subprocess.run(
        ["git", "show", f"{git_ref}:sitemap.xml"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        err = (result.stderr or "").strip()
        # Missing path at that ref → treat as empty prior sitemap.
        if "does not exist" in err or "exists on disk" in err or "Path" in err:
            return None
        # Also handle empty / unknown revision gently for CI first push.
        if "invalid" in err.lower() or "unknown revision" in err.lower():
            return None
        print(f"error: git show {git_ref}:sitemap.xml failed: {err}", file=sys.stderr)
        raise RuntimeError(err)
    return parse_sitemap_entries(result.stdout)


def is_usable_git_ref(git_ref: str) -> bool:
    if not git_ref or set(git_ref) <= {"0"}:
        return False
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{git_ref}^{{commit}}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    return result.returncode == 0


def diff_sitemap_urls(
    current: dict[str, str | None],
    previous: dict[str, str | None] | None,
) -> list[str]:
    """URLs that are new or whose lastmod changed vs previous sitemap."""
    if previous is None:
        return list(current.keys())
    changed: list[str] = []
    for loc, lastmod in current.items():
        if loc not in previous or previous[loc] != lastmod:
            changed.append(loc)
    return changed


def chunked(urls: list[str], size: int) -> list[list[str]]:
    return [urls[i : i + size] for i in range(0, len(urls), size)]


def build_payload(url_list: list[str]) -> dict:
    return {
        "host": HOST,
        "key": KEY,
        "keyLocation": KEY_LOCATION,
        "urlList": url_list,
    }


def post_indexnow(payload: dict) -> int:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        INDEXNOW_ENDPOINT,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "GrandTraverseBuildersIndexNow/1.0 (+https://grandtraversebuilders.com)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            # Drain body for connection reuse / completeness.
            resp.read()
            return int(code)
    except urllib.error.HTTPError as exc:
        try:
            exc.read()
        except Exception:
            pass
        return int(exc.code)


def resolve_urls(args: argparse.Namespace) -> list[str]:
    if args.urls is not None:
        urls = [u.strip() for u in args.urls if u.strip()]
        if not urls:
            raise SystemExit("error: --urls requires at least one URL")
        return urls

    current = load_current_sitemap()

    if args.all:
        return list(current.keys())

    git_ref = args.git_ref
    if git_ref is None:
        # Default: previous commit on this branch.
        git_ref = "HEAD~1"

    if not is_usable_git_ref(git_ref):
        print(
            f"warning: git ref {git_ref!r} is unusable; treating prior sitemap as empty",
            file=sys.stderr,
        )
        previous = None
    else:
        previous = load_sitemap_at_ref(git_ref)

    return diff_sitemap_urls(current, previous)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Submit sitemap URLs to IndexNow (Bing et al.).",
    )
    parser.add_argument(
        "git_ref",
        nargs="?",
        default=None,
        help="Git ref to diff sitemap.xml against (default: HEAD~1). Ignored with --all/--urls.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--all",
        action="store_true",
        help="Submit every URL in the current sitemap.xml.",
    )
    mode.add_argument(
        "--urls",
        nargs="+",
        metavar="URL",
        help="Submit only these URLs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the JSON payload(s); do not POST.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print each URL that would be submitted.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        urls = resolve_urls(args)
    except (FileNotFoundError, RuntimeError, ET.ParseError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # Stable order for logs / diffs.
    urls = sorted(dict.fromkeys(urls))

    if not urls:
        print("IndexNow: nothing to submit (no new/changed sitemap URLs).")
        return 0

    print(f"IndexNow: {len(urls)} URL(s) to submit (keyLocation={KEY_LOCATION})")
    if args.verbose or args.dry_run:
        for u in urls:
            print(f"  {u}")

    batches = chunked(urls, MAX_URLS_PER_REQUEST)
    overall_ok = True

    for i, batch in enumerate(batches, start=1):
        payload = build_payload(batch)
        if len(batches) > 1:
            print(f"IndexNow: batch {i}/{len(batches)} ({len(batch)} URLs)")

        if args.dry_run:
            print(json.dumps(payload, indent=2))
            continue

        try:
            code = post_indexnow(payload)
        except Exception as exc:  # noqa: BLE001 — never fail deploy
            print(f"warning: IndexNow request failed: {exc}", file=sys.stderr)
            overall_ok = False
            continue

        print(f"IndexNow: response HTTP {code}")
        if code in (200, 202):
            print("IndexNow: success")
        else:
            print(
                f"warning: IndexNow returned HTTP {code} (expected 200 or 202)",
                file=sys.stderr,
            )
            overall_ok = False

    if args.dry_run:
        print("IndexNow: dry-run complete (no request sent).")
    elif not overall_ok:
        # Warn only — never fail the GitHub Action / deploy.
        print("IndexNow: completed with warnings (see above).", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
