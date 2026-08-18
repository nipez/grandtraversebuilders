#!/usr/bin/env python3
"""Audit the directory data for completeness, consistency, and data-quality issues.

This is a STATIC directory (no live data source), and the same business data is
duplicated across index.html, business/*.html, category/*.html, search-index.json,
and sitemap.xml. This script is how you "double-check it's up to date": it cross-
checks those copies and flags stale counts, orphans, category mismatches, and
suspicious data (e.g. one website copied onto many businesses).

Run:  python3 scripts/audit_directory.py
"""
import json
import re
import pathlib
import unicodedata
from collections import Counter, defaultdict


def nfc(s):
    return unicodedata.normalize("NFC", s)

ROOT = pathlib.Path(__file__).resolve().parent.parent
issues = {"FAIL": 0, "WARN": 0}


def log(level, msg):
    if level in issues:
        issues[level] += 1
    print(f"[{level}] {msg}")


def ok(msg):
    print(f"[OK]   {msg}")


def slugify(t):
    t = t.lower()
    t = re.sub(r"[^\w\s-]", "", t, flags=re.UNICODE)
    t = re.sub(r"[\s_]+", "-", t)
    t = re.sub(r"-+", "-", t)
    return t.strip("-")


def extract_array(text, var="businesses"):
    i = text.index(f"const {var}=")
    s = text.index("[", i)
    depth = 0
    for j in range(s, len(text)):
        if text[j] == "[":
            depth += 1
        elif text[j] == "]":
            depth -= 1
            if depth == 0:
                return json.loads(text[s : j + 1])
    raise ValueError("array not terminated")


def main():
    index_html = (ROOT / "index.html").read_text(encoding="utf-8")
    data = extract_array(index_html)
    dataset_slugs = [b["s"] for b in data]
    print(f"\n=== Directory audit: {len(data)} businesses in master dataset (index.html) ===\n")

    # 1) Cross-source count consistency ------------------------------------
    biz_pages = {nfc(p.stem) for p in (ROOT / "business").glob("*.html")}
    cat_pages = {nfc(p.stem) for p in (ROOT / "category").glob("*.html")}
    search_index = json.loads((ROOT / "search-index.json").read_text(encoding="utf-8"))

    print("-- Counts across sources --")
    print(f"   dataset={len(data)}  business_pages={len(biz_pages)}  search_index={len(search_index)}  category_pages={len(cat_pages)}")
    if len(data) == len(biz_pages) == len(search_index):
        ok("dataset, business pages, and search index counts match")
    else:
        log("FAIL", "dataset / business page / search-index counts differ (see above)")

    # 2) Orphans -----------------------------------------------------------
    ds = {nfc(s) for s in dataset_slugs}
    missing_pages = sorted(ds - biz_pages)
    orphan_pages = sorted(biz_pages - ds)
    if missing_pages:
        log("FAIL", f"{len(missing_pages)} dataset businesses have NO detail page: {missing_pages[:5]}")
    if orphan_pages:
        log("WARN", f"{len(orphan_pages)} business pages are NOT in the dataset: {orphan_pages[:5]}")
    if not missing_pages and not orphan_pages:
        ok("every dataset business has a page and vice versa")

    dup_slugs = [s for s, n in Counter(dataset_slugs).items() if n > 1]
    if dup_slugs:
        log("FAIL", f"duplicate slugs in dataset: {dup_slugs}")
    else:
        ok("all dataset slugs are unique")

    # 3) Hard-coded totals vs reality --------------------------------------
    print("\n-- Hard-coded totals --")
    n = len(data)
    stale = re.findall(r"\b(37\d|38\d)\b Builders & Contractors", index_html)
    for claim in re.findall(r">(\d{3}) (?:Builders & Contractors|Businesses)", index_html):
        pass
    for m in re.findall(r"(\d{3}) Builders &amp; Contractors|(\d{3}) Builders & Contractors", index_html):
        val = m[0] or m[1]
        if val and int(val) != n:
            log("WARN", f'home top-bar says "{val} Builders & Contractors" but dataset has {n}')
    # generic: any 3-digit "Businesses Listed" stat
    for val in re.findall(r'ph-stat-num[^>]*>(\d{3})</div><div class="ph-stat-label">Businesses', index_html):
        if int(val) != n:
            log("WARN", f'home stat says "{val} Businesses Listed" but dataset has {n}')

    # 4) Category integrity ------------------------------------------------
    print("\n-- Category integrity --")
    cat_counts = Counter(c for b in data for c in b.get("c", []))
    missing_cat_pages = []
    count_mismatch = []
    for cat, cnt in cat_counts.items():
        slug = slugify(cat)
        if slug not in cat_pages:
            missing_cat_pages.append((cat, slug))
            continue
        page = (ROOT / "category" / f"{slug}.html").read_text(encoding="utf-8")
        m = re.search(r'"numberOfItems":(\d+)', page)
        if m and int(m.group(1)) != cnt:
            count_mismatch.append((slug, int(m.group(1)), cnt))
    if missing_cat_pages:
        log("FAIL", f"{len(missing_cat_pages)} categories used in data have NO category page: {missing_cat_pages[:5]}")
    else:
        ok(f"all {len(cat_counts)} categories used in the data have a category page")
    if count_mismatch:
        log("WARN", f"{len(count_mismatch)} category pages have a count that doesn't match the data: {count_mismatch[:5]}")
    else:
        ok("category page counts match the dataset")

    # 5) Data-quality: shared website/phone (scrape artifacts) -------------
    print("\n-- Data quality --")
    by_site = defaultdict(list)
    by_phone = defaultdict(list)
    for b in data:
        if b.get("w"):
            by_site[b["w"]].append(b["n"])
        if b.get("p"):
            by_phone[b["p"]].append(b["n"])
    shared_sites = {w: names for w, names in by_site.items() if len(names) >= 3}
    shared_phones = {p: names for p, names in by_phone.items() if len(names) >= 3}
    if shared_sites:
        log("WARN", f"{len(shared_sites)} website(s) are shared by 3+ businesses (likely bad data):")
        for w, names in sorted(shared_sites.items(), key=lambda x: -len(x[1])):
            print(f"        {w}  ->  {len(names)} businesses: {', '.join(names[:6])}{'…' if len(names) > 6 else ''}")
    if shared_phones:
        log("WARN", f"{len(shared_phones)} phone number(s) are shared by 3+ businesses:")
        for p, names in sorted(shared_phones.items(), key=lambda x: -len(x[1])):
            print(f"        {p}  ->  {len(names)} businesses: {', '.join(names[:6])}{'…' if len(names) > 6 else ''}")
    if not shared_sites and not shared_phones:
        ok("no website/phone is shared across many businesses")

    # 6) Completeness ------------------------------------------------------
    no_site = sum(1 for b in data if not b.get("w"))
    no_phone = sum(1 for b in data if not b.get("p"))
    no_addr = sum(1 for b in data if not b.get("a"))
    print(f"   completeness: missing website={no_site}  missing phone={no_phone}  missing address={no_addr}")

    # 7) Sitemap coverage --------------------------------------------------
    print("\n-- Sitemap coverage --")
    sm = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    sm_missing = [s for s in dataset_slugs if f"/business/{s}<" not in sm]
    if sm_missing:
        log("WARN", f"{len(sm_missing)} businesses missing from sitemap.xml: {sm_missing[:5]}")
    else:
        ok("every business is present in sitemap.xml")

    print(f"\n=== Summary: {issues['FAIL']} FAIL, {issues['WARN']} WARN ===")


if __name__ == "__main__":
    main()
