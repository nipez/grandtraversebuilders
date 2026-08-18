#!/usr/bin/env python3
"""Recompute the visible per-category and total counts from the master dataset so
they never drift after data changes:
  - homepage trade-card counts ("N businesses")
  - the All Categories grid counts (ac-count) + total on categories.html
  - the top bar total on every page
Run after adding/removing businesses. Idempotent.
"""
import json
import re
import pathlib
from collections import Counter

import add_business as ab

ROOT = pathlib.Path(__file__).resolve().parent.parent


def dataset():
    t = (ROOT / "index.html").read_text(encoding="utf-8")
    s, e = ab.find_array_span(t, "businesses")
    return json.loads(t[s:e])


def main():
    data = dataset()
    total = len(data)
    counts = Counter(c for b in data for c in b.get("c", []))
    slug_count = {ab.slugify(name): n for name, n in counts.items()}

    # Homepage trade cards
    idx = ROOT / "index.html"
    t = idx.read_text(encoding="utf-8")

    def trade_card(m):
        slug = m.group(2)
        n = slug_count.get(slug)
        return m.group(0) if n is None else f"{m.group(1)}{n} businesses{m.group(3)}"

    t = re.sub(r'(<a class="trade-card" href="category/([^"]+)\.html">.*?<div class="trade-card-count">).*?(</div>)',
               trade_card, t, flags=re.S)
    idx.write_text(t, encoding="utf-8")

    # categories.html: all-cats grid counts + total
    cats_page = ROOT / "categories.html"
    if cats_page.exists():
        t = cats_page.read_text(encoding="utf-8")

        def ac(m):
            slug = m.group(1)
            n = slug_count.get(slug)
            return m.group(0) if n is None else f'{m.group(0)[:m.start(2)-m.start(0)]}{n}{m.group(0)[m.end(2)-m.start(0):]}'

        t = re.sub(r'href="category/([^"]+)\.html"[^>]*>.*?<span class="ac-count">(\d+)</span>',
                   lambda m: m.group(0).replace(f'>{m.group(2)}</span>', f'>{slug_count.get(m.group(1), m.group(2))}</span>'),
                   t, flags=re.S)
        t = re.sub(r"(\d+) Total Businesses", f"{total} Total Businesses", t)
        t = re.sub(r'(<div class="ph-stat-num">)\d+(</div><div class="ph-stat-label">Total Businesses</div>)', rf"\g<1>{total}\g<2>", t)
        cats_page.write_text(t, encoding="utf-8")

    # top bar everywhere
    files = [ROOT / n for n in ("index.html", "categories.html", "claim.html", "plan-my-build.html", "search.html", "traverse-city-home-builders.html")]
    files += list((ROOT / "business").glob("*.html")) + list((ROOT / "category").glob("*.html")) + list((ROOT / "blog").glob("*.html"))
    tb = 0
    for p in files:
        x = p.read_text(encoding="utf-8")
        n = re.sub(r"\d+ Builders & Contractors", f"{total} Builders & Contractors", x)
        if n != x:
            p.write_text(n, encoding="utf-8")
            tb += 1
    print(f"synced: total={total}; homepage trade cards + categories grid updated; top bar in {tb} files")


if __name__ == "__main__":
    main()
