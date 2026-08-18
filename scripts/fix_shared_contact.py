#!/usr/bin/env python3
"""Clean scrape artifacts where @Home Cabinetry & Interiors' website/phone/address
were wrongly copied onto ~14 unrelated businesses (e.g. West Shore Bank, MI Roof
Pro all listing a cabinetry company's website).

For every business EXCEPT the legitimate owner, blank only the fields that exactly
match the bad shared values — leaving any correct, different data untouched. The
change is propagated to the master dataset, each affected category page, the
regenerated detail pages, and the search index.

Run:  python3 scripts/fix_shared_contact.py   (then run scripts/audit_directory.py)
"""
import json
import re
import subprocess
import sys
import pathlib

import add_business as ab  # reuse helpers (find_array_span, rec_json, build_business_page, slugify)

ROOT = pathlib.Path(__file__).resolve().parent.parent

BAD_WEB = "https://www.homecabinetryandinteriors.com/"
BAD_PHONE = "231-947-7040"
BAD_ADDR = "808 S. Garfield Ave., Ste. B, Traverse City, MI 49686"
OWNER_SLUG = "home-cabinetry-interiors-inc"

CITY_RE = re.compile(r",\s*([A-Za-z .'\-]+),\s*MI")


def city_of(addr):
    m = CITY_RE.search(addr or "")
    return m.group(1).strip() if m else "Northwest Michigan"


def clean_record(b):
    """Return (record, changed) with wrongly-copied fields blanked."""
    changed = False
    r = dict(b)
    if r.get("s") == OWNER_SLUG:
        return r, False
    if r.get("w") == BAD_WEB:
        r["w"] = ""; changed = True
    if r.get("p") == BAD_PHONE:
        r["p"] = ""; changed = True
    if r.get("a") == BAD_ADDR:
        r["a"] = ""; changed = True
    return r, changed


def map_array_in_file(path, affected):
    """Blank fields for affected slugs inside a file's `const businesses=[...]`."""
    t = path.read_text(encoding="utf-8")
    try:
        s, e = ab.find_array_span(t, "businesses")
    except ValueError:
        return False
    arr = json.loads(t[s:e])
    if not any(b.get("s") in affected for b in arr):
        return False
    new = []
    for b in arr:
        if b.get("s") in affected:
            b, _ = clean_record(b)
        new.append(b)
    new_arr = "[" + ",".join(ab.rec_json(b) for b in new) + "]"
    path.write_text(t[:s] + new_arr + t[e:], encoding="utf-8")
    return True


def main():
    idx = ROOT / "index.html"
    data = json.loads((lambda t: t[slice(*ab.find_array_span(t, "businesses"))])(idx.read_text(encoding="utf-8")))

    affected = {}
    for b in data:
        r, changed = clean_record(b)
        if changed:
            affected[b["s"]] = r
    if not affected:
        print("Nothing to clean.")
        return
    print(f"Cleaning {len(affected)} businesses with wrongly-copied contact data:")
    for slug in sorted(affected):
        print(f"  - {slug}")

    # 1) master dataset
    map_array_in_file(idx, set(affected))

    # 2) category pages that contain any affected business
    for p in sorted((ROOT / "category").glob("*.html")):
        map_array_in_file(p, set(affected))

    # 3) regenerate affected detail pages with cleaned data
    for slug, r in affected.items():
        r = dict(r)
        r["city"] = city_of(r.get("a", ""))
        (ROOT / "business" / f"{slug}.html").write_text(ab.build_business_page(r), encoding="utf-8")
    print(f"  ✓ regenerated {len(affected)} detail pages")

    # 4) search index
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_search_index.py")], check=True)
    print("Done.")


if __name__ == "__main__":
    main()
