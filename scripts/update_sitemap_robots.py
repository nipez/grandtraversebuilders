#!/usr/bin/env python3
"""Normalize sitemap.xml and robots.txt.

  - sitemap: convert .html <loc> entries to clean URLs (matching what is served),
    drop the claim page (it is Disallowed), and refresh <lastmod>.
  - robots: also disallow the clean /claim path.
Idempotent."""
import datetime
import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
TODAY = datetime.date.today().isoformat()


def fix_sitemap():
    p = ROOT / "sitemap.xml"
    t = p.read_text(encoding="utf-8")
    t = re.sub(r"(https://grandtraversebuilders\.com/[^\s\"'<>]+?)\.html", r"\1", t)
    # Drop the claim URL entry (disallowed in robots.txt).
    t = re.sub(r"\s*<url><loc>https://grandtraversebuilders\.com/claim</loc>.*?</url>", "", t, flags=re.S)
    t = re.sub(r"<lastmod>\d{4}-\d{2}-\d{2}</lastmod>", f"<lastmod>{TODAY}</lastmod>", t)
    p.write_text(t, encoding="utf-8")
    print(f"sitemap.xml: {t.count('<loc>')} urls, lastmod {TODAY}")


def fix_robots():
    p = ROOT / "robots.txt"
    t = p.read_text(encoding="utf-8")
    if "Disallow: /claim\n" not in t:
        t = t.replace("Disallow: /claim.html\n", "Disallow: /claim.html\nDisallow: /claim\n")
        p.write_text(t, encoding="utf-8")
        print("robots.txt: added Disallow: /claim")
    else:
        print("robots.txt: already up to date")


if __name__ == "__main__":
    fix_sitemap()
    fix_robots()
