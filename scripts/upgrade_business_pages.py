#!/usr/bin/env python3
"""Upgrade every business listing page template from directory data.

Idempotent. Reads `const businesses=[...]` from index.html and rewrites SEO,
JSON-LD, intro, CTAs, breadcrumbs, badges, and related-business sections on
each business/*.html page. Uses only fields that exist in the data — never
invents reviews, ratings, licenses, or towns.

Run:  python3 scripts/upgrade_business_pages.py
"""
from __future__ import annotations

import html as htmlmod
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote, urlparse

ROOT = Path(__file__).resolve().parents[1]
BIZ_DIR = ROOT / "business"
INDEX = ROOT / "index.html"
SITE = "https://grandtraversebuilders.com"

SKIP_WORDS = {"LLC", "Inc", "Inc.", "Co", "Co.", "of", "the", "and", "The", "LLP"}

# schema.org subtypes when the primary category clearly maps
SCHEMA_SPECIFIC = {
    "Roofing": "RoofingContractor",
    "Electrical Contractors": "Electrician",
    "Plumbing Contractors": "Plumber",
    "HVAC Contractors": "HVACBusiness",
    "Building Contractors": "GeneralContractor",
}

# Broader HomeAndConstructionBusiness for construction / trade categories
SCHEMA_HOME_CONSTRUCTION = {
    "Remodeling Contractors",
    "Siding Contractors",
    "Drywall Contractors",
    "Painting & Wallpaper Contractors",
    "Framing Contractors",
    "Decks",
    "Gutters",
    "Windows & Doors",
    "Insulation Contractors & Installers",
    "Concrete - Foundations, Poured Walls, & Precast",
    "Concrete Floors - Epoxy, Resurfacing, & Polishing",
    "Masonry Contractors",
    "Excavating",
    "Demolition Contractors",
    "Handyman Services",
    "Kitchen & Bath",
    "Floor Coverings & Hardwood Floors",
    "Tile",
    "Cabinetry - Whole House",
    "Countertops",
    "Trim & Finish Carpentry",
    "Glass Contractors & Installers",
    "Garage Doors",
    "Pole Buildings & Garages",
    "Log Home Builders",
    "Timber Frame Manufacturer",
    "Architectural  & Design Services",
    "Landscaping & Gardening Contractors",
    "Hardscape Installation & Suppliers",
    "Roofing",
    "Electrical Contractors",
    "Plumbing Contractors",
    "HVAC Contractors",
    "Building Contractors",
    "Sewer & Water Installation",
    "Well Drilling",
    "Irrigation",
    "Fencing",
    "Retaining Walls",
    "Seawalls",
    "Asphalt Paving & Repairs",
    "Restoration - Fire & Water",
    "Insurance Restoration & Mitigation",
    "Millwork Contractors",
    "Skylights",
    "Water Heaters",
    "Water Treatment",
    "Fireplaces",
    "Swimming Pools",
    "Hot Tubs / Spas",
    "Acoustic Ceilings",
    "Closet Systems, Organizers & Shelving",
    "Structural Wall Panels",
    "Trusses",
    "Welding & Fabrication",
    "Modular and Manufactured Homes",
}

PHONE_SVG = (
    '<svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.5">'
    '<path d="M2 3.5C2 8.5 3.5 10 8.5 10l1-2.2-2.3-1L6 8c-1.2-.5-2.5-1.8-3-3l1.2-1.2-1-2.3z"/>'
    "</svg>"
)

HUB_BLOCK = (
    "<!-- gtb-hub-link -->\n"
    '<p class="biz-hub-context" style="max-width:1340px;margin:0 auto;padding:0 40px 12px;'
    'font-size:.88rem;line-height:1.7;color:var(--text-light);">'
    "Exploring the local market? See our "
    '<a href="../traverse-city-home-builders" '
    'style="color:var(--copper-warm);font-weight:600;text-decoration:none;">'
    "Traverse City home builders</a> hub for an overview, then compare listings "
    "in the full directory."
    "</p>\n"
)


def esc(s: str) -> str:
    return htmlmod.escape(s or "", quote=True)


def esc_text(s: str) -> str:
    return htmlmod.escape(s or "", quote=False)


def extract_businesses() -> list[dict]:
    text = INDEX.read_text(encoding="utf-8")
    m = re.search(r"const businesses=(\[.*?\]);", text, re.S)
    if not m:
        raise SystemExit("Could not find businesses array in index.html")
    return json.loads(m.group(1))


def build_cat_slug_map() -> dict[str, str]:
    """Prefer live hrefs on existing pages so odd slugs stay correct."""
    mapping: dict[str, str] = {}
    for path in BIZ_DIR.glob("*.html"):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(
            r'href="\.\./category/([^"]+)"[^>]*>.*?service-card-name">([^<]+)',
            text,
            re.S,
        ):
            slug, name = m.group(1), m.group(2).replace("&amp;", "&")
            mapping[name] = slug
        for m in re.finditer(
            r'<a href="\.\./category/([^"]+)">([^<]+)</a>',
            text,
        ):
            slug, name = m.group(1), m.group(2).replace("&amp;", "&")
            if name not in ("Home",) and name not in mapping:
                mapping[name] = slug
    # Fallbacks for categories that may only appear in breadcrumbs
    if "Auto/Truck/Equipment Sales & Leasing" not in mapping:
        mapping["Auto/Truck/Equipment Sales & Leasing"] = (
            "autotruckequipment-sales-leasing"
        )
    return mapping


def build_icon_map() -> dict[str, str]:
    icons: dict[str, str] = {}
    for path in BIZ_DIR.glob("*.html"):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(
            r'service-card-icon">([^<]+)</div><div class="service-card-name">([^<]+)',
            text,
        ):
            icon, name = m.group(1), m.group(2).replace("&amp;", "&")
            icons[name] = icon
    return icons


def get_initials(n: str) -> str:
    parts = re.split(r"[\s&,]+", n)
    words = [w for w in parts if len(w) > 1 and w not in SKIP_WORDS]
    if not words:
        words = [w for w in parts if w]
    return "".join(w[0].upper() for w in words[:2]) or "?"


def get_city(address: str | None) -> str | None:
    if not address:
        return None
    parts = [p.strip() for p in address.split(",")]
    if len(parts) < 2:
        return None
    city = parts[-2].strip()
    if city.startswith("MI") or re.match(r"^\d+$", city):
        return parts[-3].strip() if len(parts) >= 3 else None
    # Normalize odd casing like "traverse City"
    if city:
        return city.title() if city.lower() != city else city
    return None


def parse_address(address: str) -> dict:
    """Split a freeform MI address into PostalAddress fields when possible."""
    parts = [p.strip() for p in address.split(",") if p.strip()]
    out: dict = {"addressCountry": "US"}
    if not parts:
        return out
    # Find MI / ZIP segment
    region_idx = None
    for i, p in enumerate(parts):
        if re.match(r"^MI\b", p, re.I) or re.search(r"\bMI\s+\d{5}", p, re.I):
            region_idx = i
            break
    if region_idx is None and len(parts) >= 2:
        # last looks like state
        region_idx = len(parts) - 1
    if region_idx is not None and region_idx >= 1:
        city = parts[region_idx - 1]
        street = ", ".join(parts[: region_idx - 1]) if region_idx >= 2 else ""
        region_part = parts[region_idx]
        out["addressLocality"] = city.title() if city.islower() else city
        out["addressRegion"] = "MI"
        zip_m = re.search(r"(\d{5}(?:-\d{4})?)", region_part)
        if zip_m:
            out["postalCode"] = zip_m.group(1)
        if street:
            out["streetAddress"] = street
        elif len(parts) == 2:
            # "Street, City MI ZIP" rare; keep full as street if needed
            pass
    else:
        out["streetAddress"] = address
    return out


def location_label(biz: dict) -> str:
    city = get_city(biz.get("a"))
    if city:
        return f"{city}, Michigan"
    return "Northwest Michigan"


def location_short(biz: dict) -> str:
    city = get_city(biz.get("a"))
    return city if city else "Northwest Michigan"


def primary_trade(biz: dict) -> str | None:
    cats = biz.get("c") or []
    return cats[0] if cats else None


def schema_type(biz: dict) -> str:
    """Map from primary category; only fall back across cats when primary is vague."""
    cats = biz.get("c") or []
    trade = primary_trade(biz)
    if trade and trade in SCHEMA_SPECIFIC:
        return SCHEMA_SPECIFIC[trade]
    if trade and trade in SCHEMA_HOME_CONSTRUCTION:
        return "HomeAndConstructionBusiness"
    for c in cats[1:]:
        if c in SCHEMA_SPECIFIC:
            return SCHEMA_SPECIFIC[c]
    if any(c in SCHEMA_HOME_CONSTRUCTION for c in cats):
        return "HomeAndConstructionBusiness"
    return "LocalBusiness"


def trade_for_prose(trade: str) -> str:
    """Readable trade phrase without forced a/an + plural category names."""
    special = {
        "Decks": "deck construction",
        "Gutters": "gutter installation",
        "Roofing": "roofing",
        "Excavating": "excavating",
        "Lighting": "lighting",
        "Tile": "tile work",
        "Trusses": "truss supply",
        "Skylights": "skylight installation",
        "Fencing": "fencing",
        "Fireplaces": "fireplace services",
        "Appliances": "appliance services",
        "Cleaning": "cleaning services",
        "Insurance": "insurance",
        "Utilities": "utilities",
        "Countertops": "countertops",
        "Furniture": "furniture",
        "Blueprints": "blueprint services",
        "Signs": "signage",
        "Printing": "printing",
        "Irrigation": "irrigation",
        "Seawalls": "seawall construction",
        "Retaining Walls": "retaining wall construction",
        "Water Heaters": "water heater services",
        "Water Treatment": "water treatment",
        "Well Drilling": "well drilling",
        "Construction Waste Removal": "construction waste removal",
        "Waste Disposal": "waste disposal",
        "Health Care": "health care",
        "HVAC Contractors": "HVAC contractor",
    }
    if trade in special:
        return special[trade]
    if trade.endswith(" Contractors"):
        base = trade[: -len(" Contractors")]
        return f"{base.lower()} contractor"
    if trade.endswith(" Services"):
        return trade.lower()
    return trade.lower()


def cat_slug(name: str, mapping: dict[str, str]) -> str:
    if name in mapping:
        return mapping[name]
    s = name.lower().replace("&", "")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")


def display_host(url: str) -> str:
    try:
        host = urlparse(url).netloc or url
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return url


def make_title(biz: dict) -> str:
    name = biz["n"]
    trade = primary_trade(biz)
    city = get_city(biz.get("a"))
    if trade and city:
        return f"{name} | {trade} in {city}, MI | Grand Traverse Builders"
    if trade:
        return f"{name} | {trade} in Northwest Michigan | Grand Traverse Builders"
    if city:
        return f"{name} | Contractor in {city}, MI | Grand Traverse Builders"
    return f"{name} | Northwest Michigan Directory | Grand Traverse Builders"


def make_description(biz: dict) -> str:
    name = biz["n"]
    trade = primary_trade(biz)
    loc = location_short(biz)
    bits = []
    if trade and loc != "Northwest Michigan":
        bits.append(
            f"{name} — {trade} in {loc}, Michigan, listed for "
            f"{trade_for_prose(trade)}."
        )
    elif trade:
        bits.append(
            f"{name} — {trade} in Northwest Michigan, listed for "
            f"{trade_for_prose(trade)}."
        )
    elif loc != "Northwest Michigan":
        bits.append(f"{name} — local professional in {loc}, Michigan.")
    else:
        bits.append(f"{name} — Northwest Michigan builders directory listing.")
    if biz.get("p"):
        bits.append(f"Call {biz['p']}.")
    cats = biz.get("c") or []
    if len(cats) > 1:
        extra = ", ".join(cats[1:3])
        bits.append(f"Also listed under {extra}.")
    bits.append("Contact info and related contractors on Grand Traverse Builders.")
    desc = " ".join(bits)
    if len(desc) > 165:
        desc = desc[:162].rsplit(" ", 1)[0] + "…"
    return desc


def make_intro(biz: dict) -> str:
    name = biz["n"]
    trade = primary_trade(biz)
    loc = location_label(biz)
    cats = biz.get("c") or []
    parts = []
    if trade:
        phrase = trade_for_prose(trade)
        if len(cats) > 1:
            others = ", ".join(cats[1:3])
            parts.append(
                f"{name} is listed under {trade} ({phrase}) serving {loc}, "
                f"and also under {others}."
            )
        else:
            parts.append(
                f"{name} is listed under {trade} ({phrase}) serving {loc}."
            )
    else:
        parts.append(
            f"{name} is listed in the Grand Traverse Builders directory serving {loc}."
        )
    if biz.get("p"):
        parts.append(f"Reach them at {biz['p']}.")
    if biz.get("a"):
        parts.append(f"Address on file: {biz['a']}.")
    elif biz.get("w"):
        parts.append("Visit their website from the contact options on this page.")
    return " ".join(parts)


def build_schema(biz: dict) -> tuple[dict, dict]:
    slug = biz["s"]
    name = biz["n"]
    trade = primary_trade(biz)
    city = get_city(biz.get("a"))
    page_url = f"{SITE}/business/{slug}"
    stype = schema_type(biz)

    crumbs = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "Home",
                "item": SITE,
            }
        ],
    }
    pos = 2
    if trade:
        crumbs["itemListElement"].append(
            {
                "@type": "ListItem",
                "position": pos,
                "name": trade,
                "item": f"{SITE}/category/{cat_slug(trade, CAT_SLUGS)}",
            }
        )
        pos += 1
    crumbs["itemListElement"].append(
        {
            "@type": "ListItem",
            "position": pos,
            "name": name,
            "item": page_url,
        }
    )

    lb: dict = {
        "@context": "https://schema.org",
        "@type": stype,
        "name": name,
        "url": page_url,
        "description": make_intro(biz),
    }
    if city:
        lb["areaServed"] = {
            "@type": "City",
            "name": city,
            "containedInPlace": {"@type": "State", "name": "Michigan"},
        }
    else:
        lb["areaServed"] = {
            "@type": "AdministrativeArea",
            "name": "Northwest Michigan",
            "containedInPlace": {"@type": "State", "name": "Michigan"},
        }
    if biz.get("p"):
        lb["telephone"] = biz["p"]
    if biz.get("w"):
        lb["sameAs"] = biz["w"]
    if biz.get("a"):
        addr = parse_address(biz["a"])
        # Only emit address if we have locality or street
        if addr.get("addressLocality") or addr.get("streetAddress"):
            lb["address"] = {"@type": "PostalAddress", **addr}
    cats = biz.get("c") or []
    if cats:
        lb["knowsAbout"] = cats
    return crumbs, lb


def breadcrumbs_html(biz: dict) -> str:
    name = biz["n"]
    trade = primary_trade(biz)
    parts = [
        '<div class="breadcrumbs">',
        '  <a href="../">Home</a><span class="sep">/</span>',
    ]
    if trade:
        slug = cat_slug(trade, CAT_SLUGS)
        parts.append(
            f'  <a href="../category/{esc(slug)}">{esc_text(trade)}</a>'
            f'<span class="sep">/</span>'
        )
    parts.append(f'  <span class="current">{esc_text(name)}</span>')
    parts.append("</div>")
    return "\n".join(parts) + "\n"


def services_html(biz: dict, icons: dict[str, str]) -> str:
    cats = biz.get("c") or []
    if not cats:
        return ""
    cards = []
    for c in cats:
        slug = cat_slug(c, CAT_SLUGS)
        icon = icons.get(c, "🔧")
        cards.append(
            f'<a href="../category/{esc(slug)}" class="service-card" '
            f'style="text-decoration:none;color:inherit;">'
            f'<div class="service-card-icon">{icon}</div>'
            f'<div class="service-card-name">{esc_text(c)}</div>'
            f'<div class="service-card-desc">View category</div></a>'
        )
    return (
        '<div class="section-label">Services &amp; Specialties</div>'
        f'<div class="services-grid">{"".join(cards)}</div>'
    )


def sidebar_actions_html(biz: dict) -> str:
    buttons = []
    if biz.get("p"):
        buttons.append(
            f'<a href="tel:{esc(biz["p"])}" class="sidebar-btn primary">'
            f'📞 Call {esc_text(biz["p"])}</a>'
        )
    if biz.get("w"):
        buttons.append(
            f'<a href="{esc(biz["w"])}" target="_blank" rel="noopener" '
            f'class="sidebar-btn secondary">🌐 Visit Website</a>'
        )
    if biz.get("a"):
        q = quote(biz["a"])
        buttons.append(
            f'<a href="https://www.google.com/maps/search/?api=1&amp;query={q}" '
            f'target="_blank" rel="noopener" class="sidebar-btn secondary">'
            f"📍 Get Directions</a>"
        )
    if not buttons:
        return ""
    return (
        '<div class="sidebar-card">\n'
        "      <h3>Contact</h3>\n"
        '      <div class="sidebar-actions">\n'
        f'        {" ".join(buttons)}\n'
        "      </div>\n"
        "    </div>"
    )


def sidebar_info_html(biz: dict) -> str:
    items = []
    if biz.get("a"):
        items.append(
            f'<li><span class="si-label">Address</span>'
            f'<span>{esc_text(biz["a"])}</span></li>'
        )
    if biz.get("p"):
        items.append(
            f'<li><span class="si-label">Phone</span>'
            f'<a href="tel:{esc(biz["p"])}">{esc_text(biz["p"])}</a></li>'
        )
    if biz.get("w"):
        items.append(
            f'<li><span class="si-label">Web</span>'
            f'<a href="{esc(biz["w"])}" target="_blank" rel="noopener">'
            f"{esc_text(display_host(biz['w']))}</a></li>"
        )
    cats = biz.get("c") or []
    if cats:
        linked = []
        for c in cats:
            slug = cat_slug(c, CAT_SLUGS)
            linked.append(
                f'<a href="../category/{esc(slug)}" '
                f'style="color:var(--copper-warm);text-decoration:none;">'
                f"{esc_text(c)}</a>"
            )
        items.append(
            f'<li><span class="si-label">Trades</span>'
            f'<span>{", ".join(linked)}</span></li>'
        )
    if not items:
        return ""
    return (
        '<div class="sidebar-card">\n'
        "      <h3>Business Info</h3>\n"
        f'      <ul class="sidebar-info">{"".join(items)}</ul>\n'
        '      <div class="sidebar-creds">\n'
        '        <span class="cred-badge">Directory Listing</span>\n'
        "      </div>\n"
        "    </div>"
    )


def location_card_html(biz: dict) -> str:
    if not biz.get("a"):
        return ""
    q = quote(biz["a"])
    addr = esc_text(biz["a"])
    return (
        '<div class="sidebar-card" style="padding:0;overflow:hidden;">'
        '<div style="width:100%;height:200px;">'
        f'<iframe src="https://www.google.com/maps?q={q}&amp;output=embed" '
        'width="100%" height="200" style="border:0;display:block;" '
        'allowfullscreen="" loading="lazy" '
        'referrerpolicy="no-referrer-when-downgrade"></iframe>'
        "</div>"
        '<div style="padding:16px 28px 20px;">'
        '<h3 style="margin-bottom:12px;">📍 Location</h3>'
        f'<div style="font-size:1rem;color:var(--text-light);margin-bottom:14px;'
        f'line-height:1.5;">{addr}</div>'
        f'<a href="https://www.google.com/maps/search/?api=1&amp;query={q}" '
        'target="_blank" rel="noopener" class="sidebar-btn secondary">'
        "Get Directions</a></div></div>"
    )


def avatar_color(html: str) -> str:
    m = re.search(
        r'page-hero[\s\S]*?card-avatar" style="background:(#[A-Fa-f0-9]+)',
        html,
    )
    return m.group(1) if m else "#1C2B36"


def related_businesses(biz: dict, all_biz: list[dict], limit: int = 4) -> list[dict]:
    trade = primary_trade(biz)
    city = get_city(biz.get("a"))
    others = [b for b in all_biz if b["s"] != biz["s"]]

    def score(b: dict) -> tuple:
        same_trade = 1 if trade and trade in (b.get("c") or []) else 0
        same_city = 1 if city and get_city(b.get("a")) == city else 0
        # Prefer same trade first, then same city
        return (same_trade, same_city)

    ranked = sorted(others, key=score, reverse=True)
    # Keep only those with at least one match when possible
    matched = [b for b in ranked if score(b) != (0, 0)]
    pool = matched if matched else ranked
    return pool[:limit]


def card_html(b: dict) -> str:
    initials = esc(get_initials(b["n"]))
    name = esc_text(b["n"])
    city = get_city(b.get("a"))
    loc = f'<div class="card-location">{esc_text(city)}, MI</div>' if city else ""
    cats = b.get("c") or []
    primary = ""
    if cats:
        primary = cats[0].replace(" Contractors", "").replace(" & Design Services", "")
    trade = f'<span class="card-trade">{esc_text(primary)}</span>' if primary else ""
    cat_tags = "".join(
        f'<span class="card-cat-tag">{esc_text(c)}</span>' for c in cats[:3]
    )
    phone = ""
    if b.get("p"):
        phone = f'<span class="card-phone">{PHONE_SVG}{esc_text(b["p"])}</span>'
    return (
        f'<a class="builder-card" href="../business/{esc(b["s"])}">'
        f'<div class="card-header">'
        f'<div class="card-avatar" style="background:#1C2B36">{initials}</div>'
        f'<div class="card-info">'
        f'<div class="card-name">{name}</div>'
        f"{loc}"
        f"</div></div>"
        f'<div class="card-body">{trade}'
        f'<div class="card-cats">{cat_tags}</div></div>'
        f'<div class="card-footer"><div class="card-footer-left">{phone}'
        f'<span class="card-link">View Details <span>&rarr;</span></span>'
        f"</div></div></a>"
    )


def similar_html(biz: dict, related: list[dict]) -> str:
    if not related:
        return ""
    trade = primary_trade(biz)
    if trade:
        heading = f"More {esc_text(trade)}"
        tag = "Related Listings"
    else:
        city = get_city(biz.get("a"))
        heading = f"More in {esc_text(city)}" if city else "Related Listings"
        tag = "Similar Businesses"
    cards = "".join(card_html(b) for b in related)
    return (
        '<section class="similar-section">\n'
        '<div class="similar-inner">\n'
        '  <div class="section-header">\n'
        f'    <div class="section-tag">{tag}</div>\n'
        f'    <h2 class="section-title">{heading}</h2>\n'
        "  </div>\n"
        f'  <div class="builder-grid">{cards}</div>\n'
        "</div>\n"
        "</section>\n"
    )


def hero_location_line(biz: dict) -> str:
    trade = primary_trade(biz)
    loc = location_label(biz)
    if trade:
        return f"{esc_text(trade)} · {esc_text(loc)}"
    return esc_text(loc)


def upgrade_page(
    path: Path,
    biz: dict,
    all_biz: list[dict],
    icons: dict[str, str],
) -> bool:
    html = path.read_text(encoding="utf-8")
    original = html
    name = biz["n"]
    slug = biz["s"]
    title = make_title(biz)
    desc = make_description(biz)
    intro = make_intro(biz)
    stype = schema_type(biz)
    crumbs, lb = build_schema(biz)
    color = avatar_color(html)
    initials = get_initials(name)
    claim_q = quote(name)

    # --- Head SEO ---
    html = re.sub(
        r"<title>.*?</title>",
        f"<title>{esc_text(title)}</title>",
        html,
        count=1,
        flags=re.S,
    )
    html = re.sub(
        r'<meta content="[^"]*" name="description"/>',
        f'<meta content="{esc(desc)}" name="description"/>',
        html,
        count=1,
    )
    html = re.sub(
        r'<meta property="og:title" content="[^"]*"/>',
        f'<meta property="og:title" content="{esc(title)}"/>',
        html,
        count=1,
    )
    html = re.sub(
        r'<meta property="og:description" content="[^"]*"/>',
        f'<meta property="og:description" content="{esc(desc)}"/>',
        html,
        count=1,
    )
    html = re.sub(
        r'<meta name="twitter:title" content="[^"]*"/>',
        f'<meta name="twitter:title" content="{esc(title)}"/>',
        html,
        count=1,
    )
    html = re.sub(
        r'<meta name="twitter:description" content="[^"]*"/>',
        f'<meta name="twitter:description" content="{esc(desc)}"/>',
        html,
        count=1,
    )
    # Geo placename from real town when known
    city = get_city(biz.get("a"))
    geo = f"{city}, Michigan" if city else "Northwest Michigan"
    html = re.sub(
        r'<meta name="geo.placename" content="[^"]*"/>',
        f'<meta name="geo.placename" content="{esc(geo)}"/>',
        html,
        count=1,
    )

    schema_html = (
        f'<script type="application/ld+json">{json.dumps(crumbs, ensure_ascii=False, separators=(",", ":"))}</script>'
        f'<script type="application/ld+json">{json.dumps(lb, ensure_ascii=False, separators=(",", ":"))}</script>'
    )
    html = re.sub(
        r"(<!-- Schema -->\s*)(?:<script type=\"application/ld\+json\">.*?</script>\s*)+",
        r"\1" + schema_html + "\n",
        html,
        count=1,
        flags=re.S,
    )

    # --- Breadcrumbs + hub ---
    html = re.sub(
        r'<div class="breadcrumbs">.*?</div>\s*(?:<!-- gtb-hub-link -->\s*'
        r'<p class="biz-hub-context"[^>]*>.*?</p>\s*)?',
        breadcrumbs_html(biz) + "\n" + HUB_BLOCK,
        html,
        count=1,
        flags=re.S,
    )

    # --- Hero: keep structure, refresh H1, location, trade chips ---
    cats = biz.get("c") or []
    chips = ""
    if cats:
        chip_bits = []
        for c in cats[:4]:
            chip_bits.append(
                '<span style="display:inline-flex;align-items:center;gap:5px;'
                "padding:4px 12px;border-radius:4px;font-size:.62rem;font-weight:600;"
                "letter-spacing:.08em;text-transform:uppercase;"
                "background:rgba(193,127,78,0.15);color:var(--copper-glow);"
                'border:1px solid rgba(193,127,78,0.2);">'
                f"{esc_text(c)}</span>"
            )
        chips = (
            '<div style="display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;">'
            + "".join(chip_bits)
            + "</div>"
        )
    hero_inner = (
        f'<div class="card-avatar" style="background:{color};width:68px;height:68px;'
        f'font-size:1.5rem;border-radius:12px;flex-shrink:0;">{esc_text(initials)}</div>\n'
        f"  <div>\n"
        f"    {chips}\n"
        f'    <h1 style="font-size:clamp(1.8rem,3.5vw,2.6rem);">{esc_text(name)}</h1>\n'
        f'    <p class="page-hero-desc" style="margin-top:6px;">{hero_location_line(biz)}</p>\n'
        f"  </div>"
    )
    html = re.sub(
        r'(<div class="page-hero-content"[^>]*>)\s*.*?(</div>\s*</section>)',
        r"\1\n  " + hero_inner + r"\n</div>\n</section>",
        html,
        count=1,
        flags=re.S,
    )

    # --- Article microdata type + props ---
    html = re.sub(
        r'<article itemscope itemtype="https://schema\.org/[^"]+">\s*'
        r'(?:<meta itemprop="[^"]+" content="[^"]*"/>\s*)*',
        f'<article itemscope itemtype="https://schema.org/{stype}">\n'
        f'<meta itemprop="name" content="{esc(name)}"/>\n'
        + (f'<meta itemprop="telephone" content="{esc(biz["p"])}"/>\n' if biz.get("p") else "")
        + (f'<meta itemprop="url" content="{esc(biz["w"])}"/>\n' if biz.get("w") else "")
        + "\n",
        html,
        count=1,
    )

    # --- About intro ---
    if cats:
        follow = (
            "Browse their trade categories below, or explore our "
            '<a href="../traverse-city-home-builders" '
            'style="color:var(--copper-warm);font-weight:600;text-decoration:none;">'
            "Traverse City home builders</a> hub for the wider Northwest Michigan market."
        )
    else:
        follow = (
            "Explore our "
            '<a href="../traverse-city-home-builders" '
            'style="color:var(--copper-warm);font-weight:600;text-decoration:none;">'
            "Traverse City home builders</a> hub or the "
            '<a href="../categories" '
            'style="color:var(--copper-warm);font-weight:600;text-decoration:none;">'
            "full category directory</a> for more Northwest Michigan contractors."
        )
    about = (
        f'      <div class="section-label">About</div>\n'
        f"      <h2>About {esc_text(name)}</h2>\n"
        f'      <div class="about-text">\n'
        f"        <p>{esc_text(intro)}</p>\n"
        f"        <p>{follow}</p>\n"
        f"      </div>"
    )
    html = re.sub(
        r'<div class="about-section">\s*.*?</div>\s*(?=<div class="section-label">|<div class="gallery-section">)',
        '<div class="about-section">\n' + about + "\n    </div>\n    \n    ",
        html,
        count=1,
        flags=re.S,
    )

    # --- Services grid ---
    services = services_html(biz, icons)
    if services:
        html = re.sub(
            r'<div class="section-label">Services &amp; Specialties</div>'
            r'<div class="services-grid">.*?</div>',
            services,
            html,
            count=1,
            flags=re.S,
        )
    else:
        html = re.sub(
            r'<div class="section-label">Services &amp; Specialties</div>'
            r'<div class="services-grid">.*?</div>\s*',
            "",
            html,
            count=1,
            flags=re.S,
        )

    # --- Sidebar: replace from first sidebar-card through end of detail-sidebar ---
    actions = sidebar_actions_html(biz)
    info = sidebar_info_html(biz)
    loc_card = location_card_html(biz)
    sidebar_parts = [p for p in (actions, info, loc_card) if p]
    sidebar_body = "\n    \n    ".join(sidebar_parts)
    html = re.sub(
        r'(<div class="detail-sidebar">)\s*.*?(\n  </div>\n</div>\n</article>)',
        r"\1\n    " + sidebar_body + r"\2",
        html,
        count=1,
        flags=re.S,
    )

    # --- Similar / related ---
    related = related_businesses(biz, all_biz)
    similar = similar_html(biz, related)
    if re.search(r'<section class="similar-section">.*?</section>', html, re.S):
        html = re.sub(
            r'<section class="similar-section">.*?</section>\s*',
            similar,
            html,
            count=1,
            flags=re.S,
        )
    elif similar:
        html = re.sub(
            r'(</main>\s*)',
            r"\1\n" + similar,
            html,
            count=1,
        )

    # Ensure claim links still use the business name (should already)
    # Normalize claim query encoding
    html = re.sub(
        r'href="\.\./claim\?business=[^"]+"',
        f'href="../claim?business={claim_q}"',
        html,
    )

    # Safety: no template leaks
    if "${" in html or "undefined" in html:
        raise RuntimeError(f"Template leak detected in {path.name}")

    if html != original:
        path.write_text(html, encoding="utf-8")
        return True
    return False


CAT_SLUGS: dict[str, str] = {}


def main() -> None:
    global CAT_SLUGS
    businesses = extract_businesses()
    by_slug = {b["s"]: b for b in businesses}
    CAT_SLUGS = build_cat_slug_map()
    icons = build_icon_map()

    changed = 0
    missing = []
    for path in sorted(BIZ_DIR.glob("*.html")):
        slug = path.stem
        biz = by_slug.get(slug)
        if not biz:
            missing.append(slug)
            continue
        if upgrade_page(path, biz, businesses, icons):
            changed += 1

    print(f"Upgraded {changed} business pages ({len(businesses)} in data)")
    if missing:
        print(f"WARNING: {len(missing)} HTML files with no data match: {missing[:10]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
