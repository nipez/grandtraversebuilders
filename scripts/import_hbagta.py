#!/usr/bin/env python3
"""Cross-reference the HBAGTA member CSV against the current directory and add any
missing businesses.

Notes on the source data:
  - `categories` packs multiple categories with no delimiter (e.g. "Gutters
    Roofing"); we tokenize it by greedy longest-match against the directory's
    existing category names, so no new category pages are invented.
  - `website` is a generic Google Maps link for every row, so it is NOT imported
    as a business website (left blank).
  - Matching to existing entries is by slug and by a normalized name, to avoid
    duplicates.

Set DRY_RUN=True to preview. Run:  python3 scripts/import_hbagta.py
Then run scripts/audit_directory.py.
"""
import csv
import json
import re
import subprocess
import sys
import pathlib

import add_business as ab

ROOT = pathlib.Path(__file__).resolve().parent.parent
CSV_PATH = pathlib.Path("/home/ubuntu/.cursor/projects/workspace/uploads/hbagta_members_clean_07b2.csv")
DRY_RUN = False


def norm_name(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def norm_ws(s):
    return re.sub(r"\s+", " ", s).strip()


def clean_phone(p):
    p = norm_ws(p)
    return p if re.search(r"\d{3}.*\d{4}", p) else ""


def fix_city(c):
    return norm_ws(c).replace("Traveres City", "Traverse City")


def load_dataset():
    t = (ROOT / "index.html").read_text(encoding="utf-8")
    s, e = ab.find_array_span(t, "businesses")
    return json.loads(t[s:e])


def build_category_lookup(dataset):
    names = sorted({c for b in dataset for c in b.get("c", [])}, key=len, reverse=True)
    lookup = {norm_ws(n).lower(): n for n in names}
    return names, lookup


def parse_categories(raw, names, lookup):
    """Greedy longest-match tokenization of a space-joined category string."""
    s = norm_ws(raw)
    low = s.lower()
    matched, i, unmatched = [], 0, []
    ordered = sorted(lookup.keys(), key=len, reverse=True)
    while i < len(low):
        if low[i] == " ":
            i += 1
            continue
        hit = None
        for key in ordered:
            if low.startswith(key, i) and (i + len(key) == len(low) or low[i + len(key)] == " "):
                hit = key
                break
        if hit:
            matched.append(lookup[hit])
            i += len(hit)
        else:
            nxt = low.find(" ", i)
            nxt = len(low) if nxt == -1 else nxt
            unmatched.append(s[i:nxt])
            i = nxt
    # de-dupe, preserve order
    seen, out = set(), []
    for c in matched:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out, unmatched


def build_address(row):
    street = norm_ws(row.get("address_street", ""))
    city = norm_ws(row.get("address_city", ""))
    zip_ = norm_ws(row.get("address_zip", ""))
    if street and city:
        return f"{street}, {city}, MI {zip_}".strip()
    if city:
        return f"{city}, MI {zip_}".strip()
    return ""


def main():
    dataset = load_dataset()
    existing_slugs = {b["s"] for b in dataset}
    existing_names = {norm_name(b["n"]) for b in dataset}
    names, lookup = build_category_lookup(dataset)

    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
    new, skipped_existing, no_cat, unmatched_all = [], 0, [], set()

    for row in rows:
        name = norm_ws(row["company_name"])
        if not name:
            continue
        slug = ab.slugify(name)
        if slug in existing_slugs or norm_name(name) in existing_names:
            skipped_existing += 1
            continue
        cats, unmatched = parse_categories(row.get("categories", ""), names, lookup)
        unmatched_all.update(unmatched)
        if not cats:
            no_cat.append((name, row.get("categories", "")))
            continue
        row["address_city"] = fix_city(row.get("address_city", ""))
        city = row["address_city"] or "Northwest Michigan"
        new.append({
            "n": name,
            "p": clean_phone(row.get("phone_primary", "")),
            "a": build_address(row),
            "w": "",  # CSV website is a generic maps link; not a real site
            "c": cats,
            "s": slug,
            "city": city,
        })

    print(f"CSV rows: {len(rows)}")
    print(f"Already in directory (skipped): {skipped_existing}")
    print(f"New businesses to add: {len(new)}")
    print(f"Rows with no recognized category (skipped): {len(no_cat)}")
    if no_cat:
        for n, c in no_cat[:20]:
            print(f"    - {n}  [categories: {c!r}]")
    if unmatched_all:
        print(f"Unmatched category tokens seen: {sorted(unmatched_all)}")
    print("\nSample of new businesses:")
    for r in new[:15]:
        print(f"    + {r['n']}  ->  {r['c']}  ({r['city']})  {r['p']}")

    if DRY_RUN:
        print("\n[DRY RUN] No files changed. Set DRY_RUN=False to apply.")
        return new

    apply_new(dataset, new)
    return new


def recompute_category_page(cat, dataset):
    slug = ab.slugify(cat)
    p = ROOT / "category" / f"{slug}.html"
    if not p.exists():
        return
    members = [b for b in dataset if cat in b.get("c", [])]
    recs = [{k: b.get(k, "") for k in ("n", "p", "a", "w", "c", "s")} for b in members]
    t = p.read_text(encoding="utf-8")
    s, e = ab.find_array_span(t, "businesses")
    new_arr = "[" + ",".join(ab.rec_json(b) for b in recs) + "]"
    t = t[:s] + new_arr + t[e:]
    n = len(recs)
    t = re.sub(r'"numberOfItems":\d+', f'"numberOfItems":{n}', t, count=1)
    t = re.sub(r"Showing <strong>\d+</strong>", f"Showing <strong>{n}</strong>", t, count=1)
    t = re.sub(r'(<div class="ph-stat-num">)\d+(</div><div class="ph-stat-label">Businesses</div>)', rf"\g<1>{n}\g<2>", t, count=1)
    t = re.sub(r"(setCity\('all',this\)\">All<span class=\"count\"> \()\d+(\)</span>)", rf"\g<1>{n}\g<2>", t, count=1)
    p.write_text(t, encoding="utf-8")


def apply_new(dataset, new):
    if not new:
        print("Nothing to add.")
        return
    # 1) dataset
    idx = ROOT / "index.html"
    html = idx.read_text(encoding="utf-8")
    s, e = ab.find_array_span(html, "businesses")
    arr = json.loads(html[s:e])
    arr += [{k: r.get(k, "") for k in ("n", "p", "a", "w", "c", "s")} for r in new]
    html = html[:s] + "[" + ",".join(ab.rec_json(b) for b in arr) + "]" + html[e:]
    idx.write_text(html, encoding="utf-8")
    total = len(arr)
    print(f"  ✓ dataset now {total}")

    # 2) detail pages
    for r in new:
        (ROOT / "business" / f"{r['s']}.html").write_text(ab.build_business_page(r), encoding="utf-8")
    print(f"  ✓ wrote {len(new)} detail pages")

    # 3) recompute affected category pages from the full dataset
    affected_cats = {c for r in new for c in r["c"]}
    full = load_dataset()
    for cat in affected_cats:
        recompute_category_page(cat, full)
    print(f"  ✓ updated {len(affected_cats)} category pages")

    # 4) global counts
    ab.bump_global_counts(total)

    # 5) sitemap
    for r in new:
        ab.add_to_sitemap(r["s"])
    print("  ✓ sitemap updated")

    # 6) search index
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_search_index.py")], check=True)


if __name__ == "__main__":
    main()
