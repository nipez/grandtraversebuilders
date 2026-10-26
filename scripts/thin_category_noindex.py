#!/usr/bin/env python3
"""Mark thin trade category pages noindex and keep sitemap in sync.

Category listing counts come from each page's embedded `const businesses=[...]`
array (same source as inject-static-listings.py). Categories with fewer than
THIN_THRESHOLD listings get `<meta name="robots" content="noindex, follow">`
and are removed from sitemap.xml. Pages stay live with self-referencing
canonicals and internal links intact.

ALWAYS_INDEXABLE trades (SEO-upgraded category pages) stay indexable even if
counts drop later. Re-run after listing data changes so the rule stays current.
"""
from __future__ import annotations

import argparse
import html as htmlmod
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = "https://grandtraversebuilders.com"
CAT_DIR = ROOT / "category"
SITEMAP = ROOT / "sitemap.xml"

# Fewer than this many listings → thin (noindex). Justified by inventory:
# 47 categories have 1–2 listings; 72 have 3+. Three is the minimum useful
# shortlist for a directory page.
THIN_THRESHOLD = 3

# SEO-upgraded trade pages (PRs #19–#21) — always keep indexable.
ALWAYS_INDEXABLE = frozenset(
    {
        "roofing",
        "kitchen-bath",
        "windows-doors",
        "siding-contractors",
        "excavating",
        "cabinetry-whole-house",
        "painting-wallpaper-contractors",
        "electrical-contractors",
        "decks",
        "hvac-contractors",
        "landscaping-gardening-contractors",
        "concrete-foundations-poured-walls-precast",
        "insulation-contractors-installers",
        "plumbing-contractors",
        "pole-buildings-garages",
    }
)

# Closest related indexable category (slug → label) for thin-page UX.
# Targets must themselves be indexable at current counts; hub used when none fit.
RELATED: dict[str, tuple[str, str]] = {
    "acoustic-ceilings": ("drywall-contractors", "Drywall Contractors"),
    "appliances": ("kitchen-bath", "Kitchen & Bath"),
    "asphalt-paving-repairs": ("excavating", "Excavating"),
    "attorneys": ("categories", "All Categories"),
    "autotruckequipment-sales-leasing": ("categories", "All Categories"),
    "blueprints": ("architectural-design-services", "Architectural & Design Services"),
    "civil-engineering": ("architectural-design-services", "Architectural & Design Services"),
    "closet-systems-organizers-shelving": ("cabinetry-whole-house", "Cabinetry"),
    "computer-products-and-services": ("categories", "All Categories"),
    "construction-waste-removal": ("waste-disposal", "Waste Disposal"),
    "crane-service-rental": ("building-contractors", "Building Contractors"),
    "electrical-suppliers": ("electrical-contractors", "Electrical Contractors"),
    "energy-consulting": ("insulation-contractors-installers", "Insulation"),
    "environmental-testing-consulting": ("categories", "All Categories"),
    "fencing": ("landscaping-gardening-contractors", "Landscaping"),
    "glass-contractors-installers": ("windows-doors", "Windows & Doors"),
    "health-care": ("categories", "All Categories"),
    "home-inspection-services": ("building-contractors", "Building Contractors"),
    "hot-tubs-spas": ("swimming-pools", "Swimming Pools"),
    "insurance-restoration-mitigation": ("restoration-fire-water", "Restoration"),
    "lawn-turf-care": ("landscaping-gardening-contractors", "Landscaping"),
    "legal-services": ("categories", "All Categories"),
    "log-home-builders": ("building-contractors", "Building Contractors"),
    "masonry-contractors": ("concrete-foundations-poured-walls-precast", "Concrete & Foundations"),
    "mirrors-glass": ("windows-doors", "Windows & Doors"),
    "modular-and-manufactured-homes": ("building-contractors", "Building Contractors"),
    "painting-wallpaper-suppliers": ("painting-wallpaper-contractors", "Painting Contractors"),
    "plumbing-suppliers": ("plumbing-contractors", "Plumbing Contractors"),
    "propane-home-heating-oil": ("hvac-contractors", "HVAC Contractors"),
    "recycling-services": ("waste-disposal", "Waste Disposal"),
    "rental-tools-equipment-supplies": ("building-materials-retail", "Building Materials"),
    "seawalls": ("excavating", "Excavating"),
    "security-systems": ("electrical-contractors", "Electrical Contractors"),
    "septic-pumping": ("plumbing-contractors", "Plumbing Contractors"),
    "sewer-water-installation": ("plumbing-contractors", "Plumbing Contractors"),
    "skilled-trade-staffing": ("building-contractors", "Building Contractors"),
    "skylights": ("roofing", "Roofing"),
    "storage-rental": ("moving-storage", "Moving & Storage"),
    "structural-wall-panels": ("framing-contractors", "Framing Contractors"),
    "survey-services": ("architectural-design-services", "Architectural & Design Services"),
    "temporary-staffing": ("building-contractors", "Building Contractors"),
    "title-insurance": ("insurance", "Insurance"),
    "tree-removal-service": ("landscaping-gardening-contractors", "Landscaping"),
    "water-heaters": ("plumbing-contractors", "Plumbing Contractors"),
    "welding-fabrication": ("building-contractors", "Building Contractors"),
    "well-drilling": ("plumbing-contractors", "Plumbing Contractors"),
    "windows-coverings-treatments-or-film-installation": (
        "windows-doors",
        "Windows & Doors",
    ),
}

ROBOTS_NOINDEX = '<meta name="robots" content="noindex, follow"/>'
ROBOTS_RE = re.compile(
    r'[ \t]*<meta\s+name=["\']robots["\']\s+content=["\'][^"\']*["\']\s*/?>\s*\n?',
    re.I,
)
NOTICE_BEGIN = "<!-- thin-category-notice:begin -->"
NOTICE_END = "<!-- thin-category-notice:end -->"
NOTICE_BLOCK_RE = re.compile(
    re.escape(NOTICE_BEGIN) + r".*?" + re.escape(NOTICE_END) + r"\s*",
    re.S,
)


@dataclass
class CategoryInfo:
    slug: str
    count: int
    path: Path
    display_name: str

    @property
    def indexable(self) -> bool:
        if self.slug in ALWAYS_INDEXABLE:
            return True
        return self.count >= THIN_THRESHOLD


def extract_businesses(page: str) -> list[dict]:
    m = re.search(r"const businesses=(\[.*?\]);", page, re.S)
    if not m:
        raise ValueError("no businesses array")
    return json.loads(m.group(1))


def display_name(page: str, slug: str) -> str:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
    if m:
        name = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        name = htmlmod.unescape(name)
        # Strip "Traverse City … Contractors" style SEO H1s to a short label
        name = re.sub(r"^Traverse City\s+", "", name)
        name = re.sub(r"\s+Contractors$", "", name)
        if name:
            return name
    return slug.replace("-", " ").title()


def inventory() -> list[CategoryInfo]:
    rows: list[CategoryInfo] = []
    for path in sorted(CAT_DIR.glob("*.html")):
        page = path.read_text(encoding="utf-8")
        businesses = extract_businesses(page)
        rows.append(
            CategoryInfo(
                slug=path.stem,
                count=len(businesses),
                path=path,
                display_name=display_name(page, path.stem),
            )
        )
    return rows


def set_robots_noindex(page: str, *, noindex: bool) -> str:
    page = ROBOTS_RE.sub("", page)
    if not noindex:
        return page
    # Insert after canonical when present; else after description / viewport.
    canon = re.search(r'<link\s+rel="canonical"[^>]*>\s*\n?', page, re.I)
    if canon:
        return page[: canon.end()] + ROBOTS_NOINDEX + "\n" + page[canon.end() :]
    desc = re.search(r'<meta\s+content="[^"]*"\s+name="description"\s*/?>\s*\n?', page, re.I)
    if desc:
        return page[: desc.end()] + ROBOTS_NOINDEX + "\n" + page[desc.end() :]
    head = page.find("<head>")
    if head == -1:
        raise ValueError("no <head>")
    insert_at = head + len("<head>")
    return page[:insert_at] + "\n" + ROBOTS_NOINDEX + page[insert_at:]


def related_href_and_label(slug: str) -> tuple[str, str]:
    if slug in RELATED:
        target, label = RELATED[slug]
        if target == "categories":
            return "../categories", label
        return target, label
    return "../traverse-city-home-builders", "Traverse City home builders"


def notice_html(info: CategoryInfo) -> str:
    href, label = related_href_and_label(info.slug)
    href_esc = htmlmod.escape(href, quote=True)
    label_esc = htmlmod.escape(label)
    noun = "listing" if info.count == 1 else "listings"
    return (
        f"{NOTICE_BEGIN}\n"
        f'<aside class="thin-category-notice" style="'
        f"max-width:1340px;margin:0 auto;padding:18px 40px 0;font-size:.95rem;"
        f'line-height:1.55;color:var(--text-light);">'
        f"This category currently has {info.count} {noun}. "
        f'Browse related options in <a href="{href_esc}" style="'
        f'color:var(--copper-warm);font-weight:600;text-decoration:none;">'
        f"{label_esc}</a>, see "
        f'<a href="../categories" style="color:var(--copper-warm);font-weight:600;'
        f'text-decoration:none;">all categories</a>, or the '
        f'<a href="../traverse-city-home-builders" style="color:var(--copper-warm);'
        f'font-weight:600;text-decoration:none;">Traverse City home builders</a> hub.'
        f"</aside>\n"
        f"{NOTICE_END}\n"
    )


def set_notice(page: str, info: CategoryInfo, *, thin: bool) -> str:
    page = NOTICE_BLOCK_RE.sub("", page)
    if not thin:
        return page
    # Place after the page-hero section closes (before toolbar / directory).
    m = re.search(
        r'(<section class="page-hero">.*?</section>)\s*',
        page,
        re.S,
    )
    if not m:
        raise ValueError(f"{info.slug}: page-hero section not found")
    return page[: m.end()] + notice_html(info) + page[m.end() :]


def apply_category(info: CategoryInfo) -> tuple[bool, bool]:
    """Returns (changed, is_thin/noindex)."""
    page = info.path.read_text(encoding="utf-8")
    thin = not info.indexable
    new_page = set_robots_noindex(page, noindex=thin)
    new_page = set_notice(new_page, info, thin=thin)
    changed = new_page != page
    if changed:
        info.path.write_text(new_page, encoding="utf-8")
    return changed, thin


def update_sitemap(noindex_slugs: set[str]) -> tuple[int, int]:
    """Remove noindexed category URLs from sitemap. Returns (removed, remaining cats)."""
    text = SITEMAP.read_text(encoding="utf-8")
    original = text
    removed = 0
    for slug in sorted(noindex_slugs):
        # Match full <url>...</url> block for this category
        pat = re.compile(
            rf"<url><loc>{re.escape(SITE)}/category/{re.escape(slug)}</loc>.*?</url>\n?",
            re.S,
        )
        text, n = pat.subn("", text, count=1)
        removed += n
    # Collapse accidental blank runs left by removals (keep single newlines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    if text != original:
        SITEMAP.write_text(text, encoding="utf-8")
    remaining = len(re.findall(rf"{re.escape(SITE)}/category/", text))
    return removed, remaining


def has_noindex(page: str) -> bool:
    m = re.search(
        r'<meta\s+name=["\']robots["\']\s+content=["\']([^"\']*)["\']',
        page,
        re.I,
    )
    if not m:
        return False
    return "noindex" in m.group(1).lower()


def verify(rows: list[CategoryInfo]) -> None:
    errors: list[str] = []
    sitemap = SITEMAP.read_text(encoding="utf-8")

    must_indexable = {
        "building-contractors",
        *ALWAYS_INDEXABLE,
    }
    for slug in must_indexable:
        path = CAT_DIR / f"{slug}.html"
        if not path.exists():
            errors.append(f"missing always-indexable page: {slug}")
            continue
        page = path.read_text(encoding="utf-8")
        if has_noindex(page):
            errors.append(f"{slug}: unexpectedly noindex")
        loc = f"{SITE}/category/{slug}"
        if loc not in sitemap:
            errors.append(f"{slug}: missing from sitemap but should be indexable")

    for core in (
        f"{SITE}",
        f"{SITE}/traverse-city-home-builders",
        f"{SITE}/about",
        f"{SITE}/contact",
        f"{SITE}/privacy",
        f"{SITE}/categories",
    ):
        # Homepage loc has no trailing path; match carefully
        if core == SITE:
            if f"<loc>{SITE}</loc>" not in sitemap and f"<loc>{SITE}/</loc>" not in sitemap:
                errors.append("homepage missing from sitemap")
        elif f"<loc>{core}</loc>" not in sitemap:
            errors.append(f"{core} missing from sitemap")

    for info in rows:
        page = info.path.read_text(encoding="utf-8")
        noidx = has_noindex(page)
        in_sm = f"{SITE}/category/{info.slug}" in sitemap
        expect_thin = not info.indexable
        if noidx != expect_thin:
            errors.append(
                f"{info.slug}: robots noindex={noidx} but expect thin={expect_thin} "
                f"(count={info.count})"
            )
        if noidx and in_sm:
            errors.append(f"{info.slug}: noindex but still in sitemap")
        if (not noidx) and (not in_sm):
            errors.append(f"{info.slug}: indexable but missing from sitemap")
        # Canonical must remain self-referencing extensionless
        m = re.search(r'rel="canonical"\s+href="([^"]+)"', page)
        if not m:
            errors.append(f"{info.slug}: missing canonical")
        else:
            expected = f"{SITE}/category/{info.slug}"
            if m.group(1) != expected:
                errors.append(f"{info.slug}: bad canonical {m.group(1)}")
        if expect_thin and NOTICE_BEGIN not in page:
            errors.append(f"{info.slug}: thin but missing related-link notice")
        if (not expect_thin) and NOTICE_BEGIN in page:
            errors.append(f"{info.slug}: indexable but still has thin notice")

    # No non-category noindex pages leaked into sitemap (prior GSC fix)
    for bad in ("/search", "/favorites", "/claim", "/404"):
        if f"{SITE}{bad}" in sitemap:
            errors.append(f"sitemap still contains {bad}")

    if errors:
        print("VERIFY FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"VERIFY OK: {len(rows)} categories; "
        f"threshold < {THIN_THRESHOLD}; "
        f"noindex/sitemap consistent"
    )


def print_table(rows: list[CategoryInfo]) -> None:
    print(f"{'slug':55} {'count':>5}  indexable")
    print("-" * 72)
    for info in rows:
        flag = "yes" if info.indexable else "no"
        always = " (always)" if info.slug in ALWAYS_INDEXABLE else ""
        print(f"{info.slug:55} {info.count:5}  {flag}{always}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inventory and report only; do not write files",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Run consistency checks against current files",
    )
    args = parser.parse_args()

    rows = inventory()
    thin = [r for r in rows if not r.indexable]
    indexable = [r for r in rows if r.indexable]

    print(
        f"Categories: {len(rows)} | indexable: {len(indexable)} | "
        f"thin (noindex, count < {THIN_THRESHOLD}): {len(thin)}"
    )
    print(
        f"Always-indexable whitelist: {len(ALWAYS_INDEXABLE)} "
        f"(all currently have count >= {THIN_THRESHOLD}: "
        f"{all(r.count >= THIN_THRESHOLD for r in rows if r.slug in ALWAYS_INDEXABLE)})"
    )
    print_table(rows)

    if args.verify_only:
        verify(rows)
        return

    if args.dry_run:
        print("\nDry run — no files written.")
        print("Would noindex:")
        for r in thin:
            print(f"  /category/{r.slug} ({r.count})")
        return

    changed = 0
    noindex_slugs: set[str] = set()
    for info in rows:
        did_change, is_thin = apply_category(info)
        if did_change:
            changed += 1
        if is_thin:
            noindex_slugs.add(info.slug)

    removed, remaining_cats = update_sitemap(noindex_slugs)
    print(
        f"\nUpdated {changed} category page(s); "
        f"removed {removed} URL(s) from sitemap; "
        f"{remaining_cats} category URLs remain in sitemap"
    )
    verify(inventory())


if __name__ == "__main__":
    main()
