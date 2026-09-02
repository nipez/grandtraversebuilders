#!/usr/bin/env python3
"""Pre-render business listing cards into category pages and the homepage.

Category/home grids ship empty in static HTML and are filled from a trailing
`const businesses=[...]` script. This injects the same cards into the HTML so
crawlers see real `/business/{slug}` links without JavaScript. Client-side
filter/search keep working by replacing grid contents after load.
"""
from __future__ import annotations

import html as htmlmod
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PHONE_SVG = (
    '<svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.5">'
    '<path d="M2 3.5C2 8.5 3.5 10 8.5 10l1-2.2-2.3-1L6 8c-1.2-.5-2.5-1.8-3-3l1.2-1.2-1-2.3z"/>'
    "</svg>"
)
SKIP_WORDS = {"LLC", "Inc", "Inc.", "Co", "Co.", "of", "the", "and", "The"}


def esc(s: str) -> str:
    return htmlmod.escape(s or "", quote=True)


def get_initials(n: str) -> str:
    parts = re.split(r"[\s&,]+", n)
    words = [w for w in parts if len(w) > 1 and w not in SKIP_WORDS]
    return "".join(w[0].upper() for w in words[:2])


def get_city_from_address(a: str | None) -> str | None:
    if not a:
        return None
    p = a.split(",")
    if len(p) >= 2:
        c = p[-2].strip()
        if c.startswith("MI") or re.match(r"^\d+$", c):
            return p[-3].strip() if len(p) >= 3 else None
        return c
    return None


def card_html(b: dict, href_prefix: str, *, use_city_field: bool) -> str:
    initials = esc(get_initials(b["n"]))
    name = esc(b["n"])
    if use_city_field:
        city = b.get("city") or ""
    else:
        city = get_city_from_address(b.get("a")) or ""
    primary = ""
    if b.get("c"):
        primary = b["c"][0].replace(" Contractors", "").replace(" & Design Services", "")
    cats = b.get("c") or []
    cat_tags = "".join(f'<span class="card-cat-tag">{esc(c)}</span>' for c in cats[:3])
    phone = ""
    if b.get("p"):
        phone = f'<span class="card-phone">{PHONE_SVG}{esc(b["p"])}</span>'
    loc = f'<div class="card-location">{esc(city)}, MI</div>' if city else ""
    trade = f'<span class="card-trade">{esc(primary)}</span>' if primary else ""
    return (
        f'<a class="builder-card" href="{href_prefix}{esc(b["s"])}">'
        f'<div class="card-header">'
        f'<div class="card-avatar" style="background:#1C2B36">{initials}</div>'
        f'<div class="card-info">'
        f'<div class="card-name">{name}</div>'
        f"{loc}"
        f"</div></div>"
        f'<div class="card-body">{trade}<div class="card-cats">{cat_tags}</div></div>'
        f'<div class="card-footer"><div class="card-footer-left">{phone}'
        f'<span class="card-link">View Details <span>→</span></span></div></div>'
        f"</a>"
    )


def extract_businesses(page: str) -> list[dict]:
    m = re.search(r"const businesses=(\[.*?\]);", page, re.S)
    if not m:
        raise ValueError("no businesses array")
    return json.loads(m.group(1))


def find_ld_json_scripts(page: str) -> list[tuple[int, int, dict]]:
    """Return (start, end, data) for each application/ld+json script with object JSON."""
    out = []
    for m in re.finditer(
        r'<script type="application/ld\+json">(.*?)</script>', page, re.S
    ):
        raw = m.group(1).strip()
        if not raw.startswith("{"):
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        out.append((m.start(), m.end(), data))
    return out


def replace_itemlist(page: str, businesses: list[dict]) -> str:
    scripts = find_ld_json_scripts(page)
    target = None
    for start, end, data in scripts:
        if data.get("@type") == "ItemList":
            target = (start, end, data)
            break
    if not target:
        print("  WARN: no ItemList found", file=sys.stderr)
        return page
    start, end, old = target
    elements = [
        {
            "@type": "ListItem",
            "position": i,
            "name": b["n"],
            "url": f"https://grandtraversebuilders.com/business/{b['s']}",
        }
        for i, b in enumerate(businesses, 1)
    ]
    new_data = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": old.get("name", "Business directory"),
        "description": old.get(
            "description",
            f"Directory of {len(businesses)} businesses serving Northwest Michigan",
        ),
        "numberOfItems": len(businesses),
        "itemListElement": elements,
    }
    # Escape </ to avoid breaking out of the script element if a name ever contains it
    payload = json.dumps(new_data, separators=(",", ":"), ensure_ascii=False).replace(
        "<", "\\u003c"
    )
    new_script = f'<script type="application/ld+json">{payload}</script>'
    return page[:start] + new_script + page[end:]


def inject_grid(page: str, grid_id: str, cards_html: str) -> str:
    # Prefer replacing an empty grid; otherwise replace existing children up to
    # the known sibling markers used on category/home pages.
    empty = re.search(
        rf'(<div class="builder-grid" id="{re.escape(grid_id)}">)\s*(</div>)', page
    )
    if empty:
        return (
            page[: empty.start()]
            + empty.group(1)
            + cards_html
            + empty.group(2)
            + page[empty.end() :]
        )

    filled = re.search(
        rf'(<div class="builder-grid" id="{re.escape(grid_id)}">)(.*?)'
        rf'(</div>\s*<div[^>]*id="(?:noResults|viewMoreWrap)")',
        page,
        re.S,
    )
    if not filled:
        raise ValueError(f'grid id="{grid_id}" not found')
    return page[: filled.start(2)] + cards_html + page[filled.start(3) :]


def process_category(path: Path) -> int:
    page = path.read_text(encoding="utf-8")
    businesses = extract_businesses(page)
    cards = "".join(
        card_html(b, "../business/", use_city_field=True) for b in businesses
    )
    page = inject_grid(page, "catGrid", cards)
    page = replace_itemlist(page, businesses)
    if "<body" not in page or "const businesses=" not in page:
        raise RuntimeError(f"{path.name}: injection corrupted page structure")
    path.write_text(page, encoding="utf-8")
    return len(businesses)


def process_homepage(path: Path) -> int:
    page = path.read_text(encoding="utf-8")
    businesses = extract_businesses(page)
    cards = "".join(
        card_html(b, "business/", use_city_field=False) for b in businesses
    )
    page = inject_grid(page, "builderGrid", cards)

    # Align default client filter with the full static directory so first paint
    # matches crawler HTML (All / 377) instead of flashing then filtering.
    page = page.replace(
        "let currentFilter='Building Contractors',currentSearch='';",
        "let currentFilter='all',currentSearch='';",
        1,
    )
    page = page.replace("let showAll=false;", "let showAll=true;", 1)
    old_filters = (
        '<button class="filter-btn" onclick="setFilter(\'all\',this)">All'
        '<span class="count"> (377)</span></button>\n'
        '<button class="filter-btn active" onclick="setFilter(\'Building Contractors\',this)">'
        'Home Builders<span class="count"> (112)</span></button>'
    )
    new_filters = (
        '<button class="filter-btn active" onclick="setFilter(\'all\',this)">All'
        '<span class="count"> (377)</span></button>\n'
        '<button class="filter-btn" onclick="setFilter(\'Building Contractors\',this)">'
        'Home Builders<span class="count"> (112)</span></button>'
    )
    if old_filters not in page:
        raise RuntimeError("index.html: could not find default filter buttons to update")
    page = page.replace(old_filters, new_filters, 1)

    if "<body" not in page or "const businesses=" not in page:
        raise RuntimeError("index.html: injection corrupted page structure")
    if page.count('href="business/') < len(businesses):
        raise RuntimeError("index.html: missing static business links")
    path.write_text(page, encoding="utf-8")
    return len(businesses)


def verify() -> None:
    samples = [
        ("category/building-contractors.html", 112),
        ("category/roofing.html", 13),
        ("category/kitchen-bath.html", 15),
    ]
    for rel, expected in samples:
        page = (ROOT / rel).read_text(encoding="utf-8")
        body = page[page.find("<body") :]
        body_noscript = re.sub(r"<script\b[\s\S]*?</script>", "", body)
        hrefs = len(re.findall(r'href="[^"]*business/', body_noscript))
        names_ok = "No businesses found" in body_noscript  # still present for filters
        itemlists = [
            d for _, _, d in find_ld_json_scripts(page) if d.get("@type") == "ItemList"
        ]
        n_items = len(itemlists[0]["itemListElement"]) if itemlists else 0
        print(
            f"VERIFY {rel}: static hrefs={hrefs} (expect {expected}), "
            f"ItemList={n_items}, empty-state markup present={names_ok}"
        )
        if hrefs < expected or n_items != expected:
            raise SystemExit(f"verification failed for {rel}")

    page = (ROOT / "index.html").read_text(encoding="utf-8")
    body = page[page.find("<body") :]
    body_noscript = re.sub(r"<script\b[\s\S]*?</script>", "", body)
    hrefs = len(re.findall(r'href="[^"]*business/', body_noscript))
    has_all_filter = "let currentFilter='all'" in page
    has_show_all = "let showAll=true;" in page
    print(
        f"VERIFY index.html: static hrefs={hrefs}, "
        f"currentFilter all={has_all_filter}, showAll={has_show_all}"
    )
    if hrefs < 377:
        raise SystemExit("verification failed for index.html")


def main() -> None:
    cat_files = sorted((ROOT / "category").glob("*.html"))
    print(f"Processing {len(cat_files)} category pages...")
    for path in cat_files:
        n = process_category(path)
        print(f"  {path.name}: {n} cards")

    print("Processing index.html...")
    n = process_homepage(ROOT / "index.html")
    print(f"  index.html: {n} cards")
    verify()
    print("Done.")


if __name__ == "__main__":
    main()
