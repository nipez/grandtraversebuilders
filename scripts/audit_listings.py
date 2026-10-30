#!/usr/bin/env python3
"""Audit (and optionally normalize) directory listing data quality.

Source of truth: `const businesses=[...]` in index.html.

  python3 scripts/audit_listings.py              # report only
  python3 scripts/audit_listings.py --json        # machine-readable report
  python3 scripts/audit_listings.py --apply       # write fixes, sync derived data

`--apply` updates index.html, syncs category embedded arrays, removes dropped
business pages, adds _redirects 301s, updates listing-count chrome, and prunes
sitemap business URLs. After apply, re-run the usual rebuild chain:

  python3 scripts/build_search_index.py
  python3 scripts/upgrade_business_pages.py
  python3 scripts/inject-static-listings.py
  python3 scripts/thin_category_noindex.py
  python3 scripts/thin_category_noindex.py --verify-only
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
CAT_DIR = ROOT / "category"
BIZ_DIR = ROOT / "business"
SITEMAP = ROOT / "sitemap.xml"
REDIRECTS = ROOT / "_redirects"
SITE = "https://grandtraversebuilders.com"
TODAY = date.today().isoformat()

# Slug special-cases that don't fall out of the generic slugify.
SPECIAL_CAT_SLUGS = {
    "Auto/Truck/Equipment Sales & Leasing": "autotruckequipment-sales-leasing",
}

# Contact triple stolen from @Home Cabinetry (copy-paste corruption).
STOLEN_PHONE = "231-947-7040"
STOLEN_ADDR = "808 S. Garfield Ave., Ste. B, Traverse City, MI 49686"
STOLEN_WEB_HOST = "homecabinetryandinteriors.com"
STOLEN_CANONICAL_SLUG = "home-cabinetry-interiors-inc"

# Person-level duplicate of a company listing (same phone+address, empty cats).
MERGE_INTO: dict[str, str] = {
    "jeff-kuhlman": "floor-coverings-international-of-northwest-michigan",
}

# Clearly outside Northwest Michigan service area (non-MI address).
REMOVE_OUT_OF_AREA: dict[str, str] = {
    # Redirect to the trade category they were listed under.
    "wausau-supply-co": "/category/building-materials-wholesale",
}

PLACEHOLDER_VALUES = frozenset(
    {
        "",
        "n/a",
        "na",
        "none",
        "null",
        "undefined",
        "tbd",
        "tba",
        "lorem",
        "test",
        "example",
        "placeholder",
        "-",
        "--",
        ".",
    }
)
JUNK_RE = re.compile(
    r"\b(undefined|null|lorem ipsum|placeholder|\$\{|TODO|FIXME)\b",
    re.I,
)
PHONE_DISPLAY_RE = re.compile(r"^(\d{3})-(\d{3})-(\d{4})$")
SMALL_WORDS = frozenset(
    {"and", "or", "of", "the", "a", "an", "at", "by", "for", "in", "to"}
)


@dataclass
class Finding:
    kind: str
    slug: str
    detail: str
    auto_fixable: bool = True


@dataclass
class Report:
    total: int = 0
    findings: list[Finding] = field(default_factory=list)
    borderline: list[Finding] = field(default_factory=list)

    def add(self, kind: str, slug: str, detail: str, *, fixable: bool = True) -> None:
        self.findings.append(Finding(kind, slug, detail, fixable))

    def add_borderline(self, kind: str, slug: str, detail: str) -> None:
        self.borderline.append(Finding(kind, slug, detail, False))

    def counts(self) -> dict[str, int]:
        return dict(Counter(f.kind for f in self.findings))


def extract_array_span(text: str, var: str = "businesses") -> tuple[int, int, list[dict]]:
    start = text.index(f"const {var}=")
    i = text.index("[", start)
    depth = 0
    for j in range(i, len(text)):
        ch = text[j]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return i, j + 1, json.loads(text[i : j + 1])
    raise ValueError(f"unterminated {var} array")


def extract_businesses(html: str) -> list[dict]:
    _, _, data = extract_array_span(html)
    return data


def replace_businesses_array(html: str, businesses: list[dict]) -> str:
    i, j, _ = extract_array_span(html)
    payload = json.dumps(businesses, ensure_ascii=False, separators=(",", ":"))
    return html[:i] + payload + html[j:]


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in PLACEHOLDER_VALUES
    if isinstance(value, list):
        return len(value) == 0
    return False


def present(value: Any) -> bool:
    return not is_missing(value)


def slugify_category(name: str) -> str:
    if name in SPECIAL_CAT_SLUGS:
        return SPECIAL_CAT_SLUGS[name]
    s = name.lower().replace("&", "")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")


def norm_website_host(url: str) -> str:
    if not url:
        return ""
    raw = url.strip()
    if not re.match(r"^https?://", raw, re.I):
        raw = "http://" + raw
    try:
        host = urlparse(raw).netloc.lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def digits_phone(p: str) -> str:
    return re.sub(r"\D", "", p or "")


def format_phone(p: str) -> str | None:
    d = digits_phone(p)
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    if len(d) == 10:
        return f"{d[:3]}-{d[3:6]}-{d[6:]}"
    if len(d) == 7:
        # Local 7-digit — keep only if already dashed oddly; don't invent area code.
        return None
    return None


def tel_href(p: str) -> str:
    """RFC-friendly tel: target for US numbers; falls back to cleaned digits."""
    d = digits_phone(p)
    if len(d) == 10:
        return f"+1{d}"
    if len(d) == 11 and d.startswith("1"):
        return f"+{d}"
    return d or p


def title_case_name(name: str) -> str:
    """Title-case an ALL-CAPS name without wrecking intentional short tokens."""
    parts = re.split(r"(\s+)", name.strip())
    out: list[str] = []
    for i, part in enumerate(parts):
        if part.isspace():
            out.append(part)
            continue
        # Keep punctuation glued; split on hyphens
        chunks = part.split("-")
        fixed = []
        for j, chunk in enumerate(chunks):
            lower = chunk.lower()
            if i > 0 and j == 0 and lower in SMALL_WORDS:
                fixed.append(lower)
            elif lower in {"llc", "inc", "llp", "plc", "pc", "co", "ltd"}:
                fixed.append(lower.upper() if lower != "co" else "Co")
            elif re.fullmatch(r"\d+[a-z]*", lower):
                fixed.append(chunk.upper() if chunk.isupper() else chunk)
            else:
                fixed.append(chunk[:1].upper() + chunk[1:].lower() if chunk else chunk)
        out.append("-".join(fixed))
    return "".join(out)


def normalize_address(addr: str) -> str:
    a = re.sub(r"\s+", " ", addr.strip())
    # Glued ZIP+4: MI 496848025 → MI 49684-8025
    a = re.sub(r"\b(MI)\s+(\d{5})(\d{4})\b", r"\1 \2-\3", a, flags=re.I)
    # Ensure state token is MI
    a = re.sub(r",\s*Michigan\s+", ", MI ", a, flags=re.I)
    a = re.sub(r",\s*mi\s+", ", MI ", a)
    a = re.sub(r",\s*Mi\s+", ", MI ", a)

    parts = [p.strip() for p in a.split(",") if p.strip()]
    for i, p in enumerate(parts):
        # Normalize "MI ZIP" segment casing; title-case an ALL-CAPS city before it.
        if re.fullmatch(r"MI\s+\d{5}(?:-\d{4})?", p, re.I):
            m = re.match(r"MI\s+(\d{5}(?:-\d{4})?)", p, re.I)
            parts[i] = f"MI {m.group(1)}" if m else p
            if i >= 1:
                city = parts[i - 1]
                letters = re.sub(r"[^A-Za-z]", "", city)
                if letters and letters.isupper() and len(letters) >= 3:
                    parts[i - 1] = title_case_name(city)
            continue
        # Title-case ALL-CAPS streets, but never touch highway codes (US-31, M-72).
        letters = re.sub(r"[^A-Za-z]", "", p)
        words = p.split()
        if (
            letters
            and letters.isupper()
            and len(letters) >= 4
            and len(words) >= 2
            and not re.search(r"\b(?:US|MI|M)[-\s]?\d+", p, re.I)
        ):
            parts[i] = title_case_name(p)
    return ", ".join(parts)


def normalize_website(url: str) -> str | None:
    if is_missing(url):
        return None
    w = url.strip()
    if JUNK_RE.search(w):
        return None
    if w.lower() in {"http://", "https://", "http://www.", "https://www."}:
        return None
    if not re.match(r"^https?://", w, re.I):
        if re.match(r"^[\w.-]+\.[a-z]{2,}", w, re.I):
            w = "https://" + w
        else:
            return None
    try:
        parsed = urlparse(w)
    except Exception:
        return None
    if not parsed.netloc:
        return None
    # Drop common tracking params; keep other query keys.
    if parsed.query:
        qs = parse_qs(parsed.query, keep_blank_values=True)
        cleaned = {
            k: v
            for k, v in qs.items()
            if not k.lower().startswith(("utm_", "fbclid", "gclid", "mc_"))
        }
        if cleaned != qs:
            from urllib.parse import urlencode

            pairs = [(k, item) for k, vals in cleaned.items() for item in vals]
            new_q = urlencode(pairs)
            w = urlunparse(parsed._replace(query=new_q))
    return w


def city_of(address: str) -> str:
    if not address:
        return ""
    m = re.search(r",\s*([A-Za-z .'\-]+),\s*MI\b", address, re.I)
    if not m:
        return ""
    return m.group(1).strip()


def audit(businesses: list[dict]) -> Report:
    report = Report(total=len(businesses))
    by_slug = {b["s"]: b for b in businesses}
    by_phone: dict[str, list[dict]] = defaultdict(list)
    by_web: dict[str, list[dict]] = defaultdict(list)
    by_addr: dict[str, list[dict]] = defaultdict(list)

    for b in businesses:
        slug = b.get("s") or ""
        name = b.get("n") or ""

        # Placeholders / junk in any field
        for key in ("n", "p", "a", "w", "s"):
            val = b.get(key)
            if val is None:
                continue
            if isinstance(val, str) and val != "" and is_missing(val):
                report.add("placeholder_field", slug, f"{key}={val!r}")
            elif isinstance(val, str) and JUNK_RE.search(val):
                report.add("junk_token", slug, f"{key} contains junk: {val!r}")

        if isinstance(name, str):
            if name != name.strip() or re.search(r"\s{2,}", name):
                report.add("name_whitespace", slug, repr(name))
            if name.isupper() and len(re.sub(r"[^A-Za-z]", "", name)) > 4:
                report.add("name_all_caps", slug, name)

        phone = b.get("p") or ""
        if present(phone):
            formatted = format_phone(phone)
            if formatted is None:
                report.add("phone_invalid", slug, repr(phone))
            elif phone != formatted:
                report.add("phone_format", slug, f"{phone!r} → {formatted}")
            by_phone[digits_phone(phone)].append(b)

        addr = b.get("a") or ""
        if present(addr):
            norm = normalize_address(addr)
            if addr != norm:
                report.add("address_normalize", slug, f"{addr!r} → {norm!r}")
            if re.search(r",\s*(WI|IL|IN|OH|FL|CA|NY|TX|AZ|WA|OR|MN|IA)\b", addr):
                report.add("out_of_state", slug, addr)
            by_addr[re.sub(r"\s+", " ", addr.strip().lower())].append(b)

        web = b.get("w") or ""
        if present(web):
            nw = normalize_website(web)
            if nw is None:
                report.add("website_invalid", slug, repr(web))
            elif nw != web:
                report.add("website_normalize", slug, f"{web!r} → {nw!r}")
            host = norm_website_host(web)
            if host:
                by_web[host].append(b)

        cats = b.get("c") or []
        if not cats:
            report.add("empty_categories", slug, name, fixable=False)

        # Stolen @Home contact cluster
        if (
            slug != STOLEN_CANONICAL_SLUG
            and phone == STOLEN_PHONE
            and (addr == STOLEN_ADDR or norm_website_host(web) == STOLEN_WEB_HOST)
        ):
            report.add(
                "stolen_contact",
                slug,
                f"shares @Home Cabinetry phone/address/website; clear contact fields",
            )

        if slug in MERGE_INTO:
            report.add(
                "duplicate_merge",
                slug,
                f"merge into {MERGE_INTO[slug]}",
            )
        if slug in REMOVE_OUT_OF_AREA:
            report.add(
                "remove_out_of_area",
                slug,
                f"redirect → {REMOVE_OUT_OF_AREA[slug]}",
            )

    # Shared contact clusters (borderline vs auto)
    for digits, items in by_phone.items():
        if len(items) < 2 or not digits:
            continue
        slugs = [b["s"] for b in items]
        # Skip the known stolen cluster and planned merges (already reported)
        if digits == digits_phone(STOLEN_PHONE):
            continue
        if any(s in MERGE_INTO for s in slugs):
            # Still note remaining co-phone after merge consideration
            survivors = [s for s in slugs if s not in MERGE_INTO]
            if len(survivors) >= 2:
                report.add_borderline(
                    "shared_phone",
                    ",".join(survivors),
                    f"phone {items[0]['p']}: {[b['n'] for b in items if b['s'] in survivors]}",
                )
            continue
        report.add_borderline(
            "shared_phone",
            ",".join(slugs),
            f"phone {items[0]['p']}: {[b['n'] for b in items]}",
        )

    for host, items in by_web.items():
        if len(items) < 2 or not host or host == STOLEN_WEB_HOST:
            continue
        slugs = [b["s"] for b in items]
        report.add_borderline(
            "shared_website",
            ",".join(slugs),
            f"{host}: {[b['n'] for b in items]}",
        )

    # Known borderline co-located related businesses
    report.add_borderline(
        "related_co_located",
        "david-webster-construction,dovetail-custom-cabinetry",
        "Same phone+address, different websites/names — likely related shops; keep both",
    )
    report.add_borderline(
        "related_sister_company",
        "elya-construction-co,elya-development-co",
        "Same phone+website+address; Construction vs Land Developers — keep both",
    )
    report.add_borderline(
        "shared_phone_person",
        "krista-esckilsen,wm",
        "Same phone; Krista may be a WM contact person — review before merging",
    )
    report.add_borderline(
        "shared_phone_only",
        "bac-design-group,bay-area-contracting-inc",
        "Same phone, different websites/addresses — review",
    )
    report.add_borderline(
        "co_located_address_only",
        "a-better-sound,mac-custom-homes",
        "Same address, different phones — co-located; keep both",
    )

    # Ensure referenced merge/remove targets exist
    for src, dest in MERGE_INTO.items():
        if src in by_slug and dest not in by_slug:
            report.add("merge_target_missing", src, dest, fixable=False)
    return report


def apply_fixes(businesses: list[dict], report: Report) -> tuple[list[dict], dict[str, str]]:
    """Return (cleaned businesses, redirects map of /business/old → target)."""
    redirects: dict[str, str] = {}
    drop: set[str] = set()

    for src, dest in MERGE_INTO.items():
        drop.add(src)
        redirects[f"/business/{src}"] = f"/business/{dest}"

    for src, dest in REMOVE_OUT_OF_AREA.items():
        drop.add(src)
        redirects[f"/business/{src}"] = dest

    cleaned: list[dict] = []
    for raw in businesses:
        b = deepcopy(raw)
        slug = b["s"]
        if slug in drop:
            continue

        # Strip stolen contacts
        if slug != STOLEN_CANONICAL_SLUG:
            phone = b.get("p") or ""
            addr = b.get("a") or ""
            web = b.get("w") or ""
            if phone == STOLEN_PHONE and (
                addr == STOLEN_ADDR or norm_website_host(web) == STOLEN_WEB_HOST
            ):
                b["p"] = ""
                b["a"] = ""
                b["w"] = ""

        # Name casing / whitespace
        name = (b.get("n") or "").strip()
        name = re.sub(r"\s+", " ", name)
        if name.isupper() and len(re.sub(r"[^A-Za-z]", "", name)) > 4:
            name = title_case_name(name)
        b["n"] = name

        # Phone
        if present(b.get("p")):
            formatted = format_phone(b["p"])
            b["p"] = formatted or ""
        else:
            b["p"] = ""

        # Address
        if present(b.get("a")):
            b["a"] = normalize_address(b["a"])
        else:
            b["a"] = ""

        # Website
        if present(b.get("w")):
            nw = normalize_website(b["w"])
            b["w"] = nw or ""
        else:
            b["w"] = ""

        # Categories: drop blank/junk entries; keep list (possibly empty)
        cats = []
        for c in b.get("c") or []:
            if isinstance(c, str) and present(c) and not JUNK_RE.search(c):
                cats.append(c.strip())
        b["c"] = cats

        cleaned.append(b)

    # Preserve existing directory order; only drop removed slugs.
    return cleaned, redirects


def sync_category_pages(businesses: list[dict]) -> int:
    """Rebuild each category page's embedded businesses array from master data."""
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for b in businesses:
        for c in b.get("c") or []:
            by_cat[c].append(b)

    updated = 0
    for path in sorted(CAT_DIR.glob("*.html")):
        slug = path.stem
        # Find category display name whose slug matches this file
        cat_name = None
        for name in by_cat:
            if slugify_category(name) == slug:
                cat_name = name
                break
        if cat_name is None:
            # Keep empty array if category has no remaining members
            members: list[dict] = []
        else:
            members = by_cat[cat_name]

        records = []
        for b in members:
            rec = {
                "n": b.get("n", ""),
                "p": b.get("p", "") or "",
                "a": b.get("a", "") or "",
                "w": b.get("w", "") or "",
                "c": b.get("c", []) or [],
                "s": b["s"],
                "city": city_of(b.get("a", "") or ""),
            }
            records.append(rec)
        records.sort(key=lambda x: x["n"].lower())

        page = path.read_text(encoding="utf-8")
        try:
            new_page = replace_businesses_array(page, records)
        except ValueError:
            print(f"WARNING: no businesses array in {path.name}", file=sys.stderr)
            continue
        if new_page != page:
            path.write_text(new_page, encoding="utf-8")
            updated += 1
    return updated


def update_listing_count_chrome(old_count: int, new_count: int) -> int:
    """Replace hardcoded listing counts across HTML/txt with the live total."""
    if old_count == new_count:
        # Still normalize any stray prior counts to new_count via digit-agnostic patterns
        pass
    changed_files = 0
    patterns: list[tuple[re.Pattern[str], str]] = [
        (
            re.compile(r"\d+ Builders & Contractors"),
            f"{new_count} Builders & Contractors",
        ),
        (
            re.compile(r"directory of \d+ businesses"),
            f"directory of {new_count} businesses",
        ),
        (
            re.compile(r"with \d+ listings"),
            f"with {new_count} listings",
        ),
        (
            re.compile(r"with \d+ local professionals"),
            f"with {new_count} local professionals",
        ),
        (
            re.compile(r"\(\d+ businesses across"),
            f"({new_count} businesses across",
        ),
        (
            re.compile(r"(We list <strong>)\d+(</strong> businesses)"),
            rf"\g<1>{new_count}\2",
        ),
        (
            re.compile(r"(business/` — )\d+( business listing pages)"),
            rf"\g<1>{new_count}\2",
        ),
        (
            re.compile(r'(id="topBarBizCount">)\d+'),
            rf"\g<1>{new_count}",
        ),
        (
            re.compile(
                r'(id="statBusinessCount"[^>]*>)\d+'
            ),
            rf"\g<1>{new_count}",
        ),
        (
            re.compile(r'(id="allFilterCount">\s*)\(\d+\)'),
            rf"\g<1>({new_count})",
        ),
        (
            re.compile(r"(Showing <strong>)\d+(</strong> businesses)"),
            rf"\g<1>{new_count}\2",
        ),
        (
            re.compile(
                r'(class="ph-stat-num">)\d+(</div><div class="ph-stat-label">Total Businesses)'
            ),
            rf"\g<1>{new_count}\2",
        ),
        (
            re.compile(
                r'(<span class="count">\s*)\(\d+\)(</span></button>\s*'
                r'<button class="filter-btn[^"]*" onclick="setFilter\(\'Building Contractors\')'
            ),
            rf"\g<1>({new_count})\2",
        ),
    ]

    targets = list(ROOT.rglob("*.html")) + [ROOT / "robots.txt", ROOT / "README.md"]
    for path in targets:
        if not path.is_file():
            continue
        if any(part.startswith(".") for part in path.parts):
            continue
        original = path.read_text(encoding="utf-8")
        text = original
        for cre, repl in patterns:
            text = cre.sub(repl, text)
        # inject-static-listings leftover plain All (N) without id
        text = re.sub(
            r'(onclick="setFilter\(\'all\',this\)">All<span class="count">)\s*\(\d+\)',
            rf"\g<1>({new_count})",
            text,
        )
        if text != original:
            path.write_text(text, encoding="utf-8")
            changed_files += 1
    return changed_files


def upsert_redirects(redirects: dict[str, str]) -> int:
    if not redirects:
        return 0
    text = REDIRECTS.read_text(encoding="utf-8")
    block_lines = [
        "",
        "# Dropped / merged listing slugs (data cleanup) — keep extensionless + .html",
    ]
    added = 0
    for src, dest in sorted(redirects.items()):
        for variant in (src, src + ".html", src + "/"):
            rule = f"{variant} {dest} 301"
            if rule in text or f"{variant} " in text:
                continue
            block_lines.append(rule)
            added += 1
    if added:
        # Insert before the final /*.html splat rules so specifics win.
        anchor = "\n/*.html/ /:splat 308\n"
        if anchor in text:
            text = text.replace(anchor, "\n".join(block_lines) + "\n" + anchor, 1)
        else:
            text = text.rstrip() + "\n" + "\n".join(block_lines) + "\n"
        REDIRECTS.write_text(text, encoding="utf-8")
    return added


def prune_sitemap_businesses(keep_slugs: set[str]) -> int:
    text = SITEMAP.read_text(encoding="utf-8")
    original = text

    def keep_url(match: re.Match[str]) -> str:
        block = match.group(0)
        m = re.search(rf"{re.escape(SITE)}/business/([^<]+)", block)
        if not m:
            return block
        slug = m.group(1).strip()
        return block if slug in keep_slugs else ""

    text = re.sub(
        rf"<url><loc>{re.escape(SITE)}/business/[^<]+</loc>.*?</url>\n?",
        keep_url,
        text,
        flags=re.S,
    )
    text = re.sub(r"\n{3,}", "\n\n", text)
    if text != original:
        SITEMAP.write_text(text, encoding="utf-8")
    removed = original.count("/business/") - text.count("/business/")
    return max(0, removed)


def delete_business_pages(slugs: set[str]) -> int:
    n = 0
    for slug in slugs:
        path = BIZ_DIR / f"{slug}.html"
        if path.exists():
            path.unlink()
            n += 1
    return n


def print_report(report: Report, *, as_json: bool = False) -> None:
    if as_json:
        payload = {
            "total": report.total,
            "issue_counts": report.counts(),
            "findings": [
                {
                    "kind": f.kind,
                    "slug": f.slug,
                    "detail": f.detail,
                    "auto_fixable": f.auto_fixable,
                }
                for f in report.findings
            ],
            "borderline": [
                {"kind": f.kind, "slug": f.slug, "detail": f.detail}
                for f in report.borderline
            ],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    print(f"Listings: {report.total}")
    counts = report.counts()
    if not counts:
        print("No issues found.")
    else:
        print("Issue counts:")
        for kind, n in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
            print(f"  {kind}: {n}")
        print("\nDetails:")
        for f in report.findings:
            flag = "" if f.auto_fixable else " [manual]"
            print(f"  [{f.kind}] {f.slug}: {f.detail}{flag}")
    if report.borderline:
        print("\nBorderline (left for human review):")
        for f in report.borderline:
            print(f"  [{f.kind}] {f.slug}: {f.detail}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Apply auto-fixes to index.html and sync derived files",
    )
    ap.add_argument("--json", action="store_true", help="Emit JSON report")
    args = ap.parse_args()

    html = INDEX.read_text(encoding="utf-8")
    businesses = extract_businesses(html)
    before = audit(businesses)
    print("=== BEFORE ===")
    print_report(before, as_json=args.json)

    if not args.apply:
        return

    cleaned, redirects = apply_fixes(businesses, before)
    old_count = len(businesses)
    new_count = len(cleaned)
    dropped = {b["s"] for b in businesses} - {b["s"] for b in cleaned}

    INDEX.write_text(replace_businesses_array(html, cleaned), encoding="utf-8")
    cat_updated = sync_category_pages(cleaned)
    pages_deleted = delete_business_pages(dropped)
    redir_added = upsert_redirects(redirects)
    count_files = update_listing_count_chrome(old_count, new_count)
    sitemap_removed = prune_sitemap_businesses({b["s"] for b in cleaned})

    after = audit(cleaned)
    print("\n=== APPLY SUMMARY ===")
    print(f"listings: {old_count} → {new_count}")
    print(f"dropped slugs: {sorted(dropped)}")
    print(f"redirects added: {redir_added}")
    print(f"business pages deleted: {pages_deleted}")
    print(f"category arrays updated: {cat_updated}")
    print(f"files with count chrome updated: {count_files}")
    print(f"sitemap business URLs removed: {sitemap_removed}")
    print("\n=== AFTER ===")
    print_report(after, as_json=args.json)

    # Persist a small summary artifact for the PR description
    summary_path = ROOT / "scripts" / "listing-cleanup-summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "date": TODAY,
                "before_count": old_count,
                "after_count": new_count,
                "before_issues": before.counts(),
                "after_issues": after.counts(),
                "dropped": sorted(dropped),
                "redirects": redirects,
                "borderline": [
                    {"kind": f.kind, "slug": f.slug, "detail": f.detail}
                    for f in after.borderline
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nWrote {summary_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
