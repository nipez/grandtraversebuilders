#!/usr/bin/env python3
"""Crawl sitemap + historical URL list and report HTTP status codes.

Usage:
  python3 scripts/check_urls.py
  python3 scripts/check_urls.py --base https://<preview>.buildnorthernmichigan.pages.dev
  python3 scripts/check_urls.py --base https://grandtraversebuilders.com --fail-on-bad

Checks:
  - Every <loc> in sitemap.xml → must be HTTP 200 with zero redirects
  - Every path in scripts/historical-urls.txt → must be 200, or a single
    301/308 hop to a final 200 (no chains, no final 404)

Deliberate exceptions (reported, not failures):
  - /404 and /404.html → HTTP 404 by design (soft-404 fix)
"""

from __future__ import annotations

import argparse
import concurrent.futures
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITEMAP = ROOT / "sitemap.xml"
HISTORICAL = ROOT / "scripts" / "historical-urls.txt"
DEFAULT_BASE = "https://grandtraversebuilders.com"
UA = "GrandTraverseBuildersURLCheck/1.0 (+https://grandtraversebuilders.com)"

# Paths that must remain HTTP 404 (not soft-200).
DELIBERATE_404 = {"/404", "/404.html"}


def load_sitemap_paths() -> list[str]:
    tree = ET.parse(SITEMAP)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = []
    for loc in tree.getroot().findall("sm:url/sm:loc", ns):
        url = (loc.text or "").strip()
        if url.startswith("http"):
            # keep path (+ empty → /)
            from urllib.parse import urlparse

            path = urlparse(url).path or "/"
            locs.append(path)
        elif url:
            locs.append(url)
    return locs


def load_historical_paths() -> list[str]:
    if not HISTORICAL.exists():
        return []
    out = []
    for line in HISTORICAL.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


def curl_status(base: str, path: str, follow: bool) -> tuple[int, int, str, str]:
    """Return (first_http_code, redirect_count, final_url, first_location)."""
    url = base.rstrip("/") + (path if path.startswith("/") else "/" + path)
    # First hop (no follow) for Location inspection
    first = subprocess.run(
        [
            "curl",
            "-sS",
            "-A",
            UA,
            "--globoff",
            "-o",
            "/dev/null",
            "-w",
            "%{http_code}\t%{redirect_url}",
            "--max-redirs",
            "0",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    first_out = first.stdout.strip()
    parts = first_out.split("\t", 1)
    try:
        first_code = int(parts[0])
    except ValueError:
        first_code = 0
    location = parts[1] if len(parts) > 1 else ""

    if not follow or first_code < 300 or first_code >= 400:
        return first_code, 0, url, location

    followed = subprocess.run(
        [
            "curl",
            "-sS",
            "-A",
            UA,
            "--globoff",
            "-o",
            "/dev/null",
            "-L",
            "-w",
            "%{http_code}\t%{num_redirects}\t%{url_effective}",
            "--max-redirs",
            "5",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    fparts = followed.stdout.strip().split("\t")
    try:
        final_code = int(fparts[0])
    except (ValueError, IndexError):
        final_code = 0
    try:
        nredir = int(fparts[1])
    except (ValueError, IndexError):
        nredir = 0
    final_url = fparts[2] if len(fparts) > 2 else url
    return first_code, nredir, final_url, location


def classify(path: str, first_code: int, nredir: int, final_url: str, base: str) -> str:
    if path in DELIBERATE_404:
        return "ok-deliberate-404" if first_code == 404 else "bad-deliberate-404"

    if first_code == 200 and nredir == 0:
        return "ok-200"

    if first_code in (301, 302, 307, 308) and nredir == 1:
        # Final must be 200 on same host path — curl -L already followed
        # Re-check final is under base and landed 200: nredir==1 implies one hop;
        # verify final URL returns 200 by trusting curl -L's final http_code stored in first_code position...
        # Our curl_status returns first_code as the FIRST hop when follow=True was used...
        # Fix: when follow=True and redirects happened, we need the FINAL code.
        return "ok-single-redirect"

    if first_code in (301, 302, 307, 308) and nredir > 1:
        return "bad-redirect-chain"

    if first_code == 404:
        return "bad-404"

    return f"bad-status-{first_code}"


def check_one(base: str, path: str, require_no_redirect: bool) -> dict:
    if path in DELIBERATE_404:
        first_code, nredir, final_url, location = curl_status(base, path, follow=False)
        ok = first_code == 404
        return {
            "path": path,
            "first_code": first_code,
            "redirects": 0,
            "final_url": final_url,
            "location": location,
            "status": "ok-deliberate-404" if ok else "bad-deliberate-404",
            "ok": ok,
        }

    if require_no_redirect:
        first_code, nredir, final_url, location = curl_status(base, path, follow=False)
        ok = first_code == 200
        return {
            "path": path,
            "first_code": first_code,
            "redirects": 0,
            "final_url": final_url,
            "location": location,
            "status": "ok-200" if ok else f"bad-sitemap-{first_code}",
            "ok": ok,
        }

    # Historical: allow one redirect hop to a 200
    first_code, _n, _fu, location = curl_status(base, path, follow=False)
    if first_code == 200:
        return {
            "path": path,
            "first_code": first_code,
            "redirects": 0,
            "final_url": base.rstrip("/") + path,
            "location": "",
            "status": "ok-200",
            "ok": True,
        }

    if first_code in (301, 302, 307, 308):
        # Follow and ensure exactly one hop to 200
        followed = subprocess.run(
            [
                "curl",
                "-sS",
                "-A",
                UA,
                "--globoff",
                "-o",
                "/dev/null",
                "-L",
                "-w",
                "%{http_code}\t%{num_redirects}\t%{url_effective}",
                "--max-redirs",
                "5",
                base.rstrip("/") + path,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        fparts = followed.stdout.strip().split("\t")
        try:
            final_code = int(fparts[0])
        except (ValueError, IndexError):
            final_code = 0
        try:
            nredir = int(fparts[1])
        except (ValueError, IndexError):
            nredir = 0
        final_url = fparts[2] if len(fparts) > 2 else ""
        ok = final_code == 200 and nredir == 1
        status = (
            "ok-single-redirect"
            if ok
            else (
                "bad-redirect-chain"
                if nredir > 1
                else f"bad-redirect-final-{final_code}"
            )
        )
        return {
            "path": path,
            "first_code": first_code,
            "redirects": nredir,
            "final_url": final_url,
            "location": location,
            "status": status,
            "ok": ok,
        }

    return {
        "path": path,
        "first_code": first_code,
        "redirects": 0,
        "final_url": base.rstrip("/") + path,
        "location": location,
        "status": f"bad-status-{first_code}",
        "ok": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--base",
        default=DEFAULT_BASE,
        help=f"Site origin to probe (default {DEFAULT_BASE})",
    )
    ap.add_argument(
        "--fail-on-bad",
        action="store_true",
        help="Exit 1 if any non-deliberate URL is not 200 or single-hop 3xx→200",
    )
    ap.add_argument(
        "--workers",
        type=int,
        default=16,
        help="Parallel curl workers (default 16)",
    )
    ap.add_argument(
        "--sitemap-only",
        action="store_true",
        help="Only check sitemap.xml URLs",
    )
    args = ap.parse_args()
    base = args.base.rstrip("/")

    sitemap_paths = load_sitemap_paths()
    historical_paths = [] if args.sitemap_only else load_historical_paths()

    # De-dupe while preferring sitemap classification (no redirects allowed)
    sitemap_set = set(sitemap_paths)
    hist_only = [p for p in historical_paths if p not in sitemap_set]

    print(f"Base: {base}")
    print(f"Sitemap URLs: {len(sitemap_paths)}")
    print(f"Historical-only URLs: {len(hist_only)}")
    print()

    results = []

    def run_sitemap(path: str):
        return check_one(base, path, require_no_redirect=True)

    def run_hist(path: str):
        return check_one(base, path, require_no_redirect=False)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(run_sitemap, p) for p in sitemap_paths]
        futs += [ex.submit(run_hist, p) for p in hist_only]
        for fut in concurrent.futures.as_completed(futs):
            results.append(fut.result())

    results.sort(key=lambda r: r["path"])

    by_status: dict[str, list[dict]] = {}
    for r in results:
        by_status.setdefault(r["status"], []).append(r)

    ok_count = sum(1 for r in results if r["ok"])
    bad = [r for r in results if not r["ok"]]

    print("Summary:")
    for status in sorted(by_status):
        print(f"  {status}: {len(by_status[status])}")
    print(f"  TOTAL ok: {ok_count}/{len(results)}")
    print()

    if bad:
        print("Failures:")
        for r in bad:
            loc = f" -> {r['location']}" if r.get("location") else ""
            print(
                f"  {r['first_code']}  {r['path']}{loc}  [{r['status']}]"
                + (f"  redirects={r['redirects']} final={r['final_url']}" if r["redirects"] else "")
            )
        print()

    deliberate = by_status.get("ok-deliberate-404", [])
    if deliberate:
        print("Deliberate 404s (expected):")
        for r in deliberate:
            print(f"  {r['first_code']}  {r['path']}")
        print()

    redirects = by_status.get("ok-single-redirect", [])
    if redirects:
        print(f"Single-hop redirects ({len(redirects)}):")
        # Show leak-related and a short sample of the rest
        leakish = [
            r
            for r in redirects
            if "${" in r["path"]
            or r["path"] in {"/business", "/business/", "/category", "/category/"}
            or "undefined" in r["path"]
            or r["path"].endswith("/null")
            or "/null." in r["path"]
            or "hörmann" in r["path"]
            or "kräm" in r["path"]
            or "%C3%" in r["path"]
            or "%CC%" in r["path"]
        ]
        show = leakish or redirects[:20]
        for r in show:
            print(f"  {r['first_code']}  {r['path']} -> {r['location'] or r['final_url']}")
        if not leakish and len(redirects) > 20:
            print(f"  ... and {len(redirects) - 20} more")
        print()

    if args.fail_on_bad and bad:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
