#!/usr/bin/env python3
"""Trust & site-basics: About / Contact / Privacy pages + Verified/count cleanup.

Idempotent. Creates about.html, contact.html, privacy.html from the favorites
chrome; rewrites footer Company links; replaces hardcoded 379 with the real
listing count from index.html; strips non-data-backed Verified labels/claims.

Run:  python3 scripts/trust_site_basics.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = "https://grandtraversebuilders.com"
TODAY = date.today().isoformat()


def extract_businesses(html: str) -> list:
    start = html.index("const businesses=")
    i = html.index("[", start)
    depth = 0
    for j in range(i, len(html)):
        if html[j] == "[":
            depth += 1
        elif html[j] == "]":
            depth -= 1
            if depth == 0:
                return json.loads(html[i : j + 1])
    raise ValueError("unterminated businesses array")


def listing_count() -> int:
    return len(extract_businesses((ROOT / "index.html").read_text(encoding="utf-8")))


def chrome_from_favorites() -> tuple[str, str]:
    """Return (head_through_nav_open, footer_through_end) from favorites.html."""
    fav = (ROOT / "favorites.html").read_text(encoding="utf-8")
    # Split after nav closes, before breadcrumbs — we'll inject page body.
    m = re.search(
        r"(.*?</div></nav>\n)\s*<div class=\"breadcrumbs\">.*?</div>\s*"
        r"(.*?)(<footer>.*)</body></html>\s*$",
        fav,
        re.S,
    )
    if not m:
        raise SystemExit("favorites.html structure unexpected — aborting")
    head_nav = m.group(1)
    footer = m.group(3)
    return head_nav, footer


def patch_head(
    head_nav: str,
    *,
    title: str,
    description: str,
    path: str,
    page_name: str,
    body_class: str,
) -> str:
    out = head_nav
    out = re.sub(
        r"<title>.*?</title>",
        f"<title>{title}</title>",
        out,
        count=1,
    )
    out = re.sub(
        r'<meta content="[^"]*" name="description"/>',
        f'<meta content="{description}" name="description"/>',
        out,
        count=1,
    )
    # Canonical + OG/Twitter blocks (favorites uses both name= and property=)
    out = re.sub(
        r'<link rel="canonical" href="[^"]*"/>',
        f'<link rel="canonical" href="{SITE}/{path}"/>',
        out,
        count=1,
    )
    out = re.sub(
        r'<meta property="og:title" content="[^"]*"/>',
        f'<meta property="og:title" content="{title}"/>',
        out,
        count=1,
    )
    out = re.sub(
        r'<meta property="og:description" content="[^"]*"/>',
        f'<meta property="og:description" content="{description}"/>',
        out,
        count=1,
    )
    out = re.sub(
        r'<meta property="og:url" content="[^"]*"/>',
        f'<meta property="og:url" content="{SITE}/{path}"/>',
        out,
        count=1,
    )
    out = re.sub(
        r'<meta name="twitter:title" content="[^"]*"/>',
        f'<meta name="twitter:title" content="{title}"/>',
        out,
        count=1,
    )
    out = re.sub(
        r'<meta name="twitter:description" content="[^"]*"/>',
        f'<meta name="twitter:description" content="{description}"/>',
        out,
        count=1,
    )
    crumb = (
        '{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":['
        f'{{"@type":"ListItem","position":1,"name":"Home","item":"{SITE}"}},'
        f'{{"@type":"ListItem","position":2,"name":"{page_name}","item":"{SITE}/{path}"}}'
        "]}"
    )
    out = re.sub(
        r'<script type="application/ld\+json">\{"@context":"https://schema\.org","@type":"BreadcrumbList".*?</script>',
        f'<script type="application/ld+json">{crumb}</script>',
        out,
        count=1,
    )
    out = re.sub(
        r'<body[^>]*>',
        f'<body data-root="" class="{body_class}">',
        out,
        count=1,
    )
    # Favorites is noindex; trust pages must be indexable
    out = re.sub(r'\s*<meta name="robots" content="noindex"/>\s*', "\n", out, count=1)
    # Drop favorites-only active nav state
    out = out.replace('href="/favorites" class="active"', 'href="/favorites"')
    return out


CONTENT_CSS = """
.static-page{padding:50px 40px 70px;background:var(--white);}
.static-page-inner{max-width:760px;margin:0 auto;}
.static-page-inner h2{font-family:'DM Serif Display',serif;font-size:1.35rem;font-weight:400;color:var(--slate);margin:32px 0 12px;line-height:1.3;}
.static-page-inner h2:first-child{margin-top:0;}
.static-page-inner p,.static-page-inner li{font-size:.95rem;line-height:1.8;color:var(--text);margin-bottom:14px;}
.static-page-inner ul{margin:0 0 18px 1.2em;}
.static-page-inner a{color:var(--copper-warm);font-weight:600;text-decoration:underline;text-underline-offset:2px;}
.static-page-inner .note{font-size:.88rem;color:var(--text-light);border-left:3px solid var(--stone-dark);padding-left:14px;margin:20px 0;}
@media(max-width:700px){.static-page{padding:36px 20px 50px;}}
"""


def inject_content_css(head_nav: str) -> str:
    if ".static-page{" in head_nav:
        return head_nav
    return head_nav.replace("</style>", CONTENT_CSS + "\n</style>", 1)


def page_shell(
    *,
    title: str,
    description: str,
    path: str,
    page_name: str,
    body_class: str,
    tag: str,
    h1: str,
    hero_desc: str,
    body_html: str,
    head_nav: str,
    footer: str,
) -> str:
    head = inject_content_css(
        patch_head(
            head_nav,
            title=title,
            description=description,
            path=path,
            page_name=page_name,
            body_class=body_class,
        )
    )
    crumbs = f"""<div class="breadcrumbs">
  <a href="./">Home</a><span class="sep">/</span>
  <span class="current">{page_name}</span>
</div>

<section class="page-hero">
<div class="page-hero-bg"></div>
<div class="page-hero-content">
  <div class="page-hero-tag">{tag}</div>
  <h1>{h1}</h1>
  <p class="page-hero-desc">{hero_desc}</p>
</div>
</section>

<section class="static-page"><div class="static-page-inner">
{body_html}
</div></section>

"""
    return head + crumbs + footer + "\n</body></html>\n"


def about_body(count: int) -> str:
    return f"""<h2>What this site is</h2>
<p>Grand Traverse Builders is an independent local directory of home builders, contractors, and building trades serving Traverse City and Northwest Michigan — including Grand Traverse, Leelanau, Benzie, Antrim, Kalkaska, Manistee, Missaukee, and Wexford counties.</p>
<p>We list <strong>{count}</strong> businesses across 119 trade categories so homeowners and project owners can browse by trade, compare contact details, and assemble a build team. Listings are drawn from publicly available business information and owner submissions through our <a href="/claim">claim / list your business</a> flow.</p>

<h2>What we are not</h2>
<p>We are not a contractor, builder association, licensing board, or referral brokerage. We do not rank, rate, or endorse the businesses listed here. A listing means a business appears in the directory — not that we have inspected their work, confirmed licenses, or confirmed insurance.</p>

<h2>How to use the directory</h2>
<ul>
  <li>Browse by trade on <a href="/categories">All Categories</a> or search by name and city on <a href="/search">Search</a>.</li>
  <li>Save shortlists in your browser with favorites, or use <a href="/plan-my-build">Plan My Build</a> to organize trades by project phase.</li>
  <li>Read local guides on the <a href="/blog/">blog</a>, including permits and seasonal planning.</li>
</ul>

<h2>Business owners</h2>
<p>If your company should be listed — or you need to update an existing listing — use <a href="/claim">Claim Your Listing</a>. There is no fee required to submit a free listing request.</p>
"""


def contact_body() -> str:
    return """<h2>Business owners</h2>
<p>To claim an existing listing, update your information, or request a new listing, use the <a href="/claim">Claim Your Listing</a> form. Submissions go to the site operators through that form — that is the primary contact path for directory businesses today.</p>

<h2>Everyone else</h2>
<p>Grand Traverse Builders does not publish a public phone number or street address. For general questions about the directory itself, use the claim form and note that your message is not a listing request, or wait for a public contact email once one is published on this page.</p>
<p class="note">TODO for Nick: supply a public contact email (e.g. hello@grandtraversebuilders.com) to add a mailto link here. No invented phone or address.</p>

<h2>What we cannot do</h2>
<ul>
  <li>We do not mediate disputes between homeowners and contractors.</li>
  <li>We do not confirm licensing, insurance, or project availability for listed businesses.</li>
  <li>We do not send outbound marketing emails from this contact page.</li>
</ul>
"""


def privacy_body() -> str:
    return f"""<p>Last updated: {TODAY}. This policy describes what Grand Traverse Builders (grandtraversebuilders.com) actually collects and stores. It does not claim practices the site code does not implement.</p>

<h2>Analytics</h2>
<p>Pages load Google Analytics (gtag.js measurement ID <code>G-J2WCDRKR73</code>). Google may set cookies and collect usage data such as pages viewed, approximate location, device/browser information, and referral source under Google's terms. We use this to understand aggregate traffic, not to sell personal profiles.</p>

<h2>Favorites and build planner (localStorage)</h2>
<p>The site's favorites and Plan My Build features store data in your browser via <code>localStorage</code> keys <code>nwmi_favorites</code> and <code>nwmi_project</code>. That data stays on your device unless you clear site data or share a list yourself. It is not uploaded to our servers by those features.</p>

<h2>Claim / list-your-business form</h2>
<p>When you submit the form on <a href="/claim">/claim</a>, the browser posts to <code>/api/claim</code>. The submission includes the fields you enter (such as name, email, business name, trade, and description). The Pages Function validates the request, may check Cloudflare Turnstile if that secret is configured, logs the submission, and — when environment secrets are set — may email the operators (via Resend) and/or forward JSON to a configured webhook. We use that information to process listing requests, not to run an outbound newsletter from this form.</p>

<h2>Cookies</h2>
<p>Beyond cookies that Google Analytics may set, the static directory pages do not implement a separate first-party cookie consent or tracking system. Clearing cookies and site data in your browser removes analytics cookies and localStorage favorites/planner data for this site.</p>

<h2>What we do not do</h2>
<ul>
  <li>We do not sell your personal information.</li>
  <li>We do not require an account or login to browse the directory.</li>
  <li>We do not publish visitor emails from claim submissions on the public site.</li>
</ul>

<h2>Third-party links</h2>
<p>Business listings may link to external websites, phone numbers, or map searches. Those destinations have their own privacy practices.</p>

<h2>Contact about privacy</h2>
<p>Questions about this policy can be sent through the <a href="/claim">claim form</a> (note that it is a privacy inquiry) or via the public contact email once published on the <a href="/contact">Contact</a> page.</p>
"""


def write_static_pages(count: int, head_nav: str, footer: str) -> None:
    pages = [
        dict(
            filename="about.html",
            title="About — Grand Traverse Builders",
            description="Grand Traverse Builders is an independent local directory of Traverse City–area home builders, contractors, and trades across Northwest Michigan.",
            path="about",
            page_name="About",
            body_class="page-about",
            tag="About the Directory",
            h1="An independent builder directory for Northwest Michigan",
            hero_desc="Local listings for Traverse City–area home builders, contractors, and trades — not a contractor, not a ratings board.",
            body=about_body(count),
        ),
        dict(
            filename="contact.html",
            title="Contact — Grand Traverse Builders",
            description="Contact Grand Traverse Builders. Business owners: claim or update your listing. No public phone or street address is published.",
            path="contact",
            page_name="Contact",
            body_class="page-contact",
            tag="Contact",
            h1="Get in touch",
            hero_desc="Business owners use Claim Your Listing. A public contact email will be added when one is available.",
            body=contact_body(),
        ),
        dict(
            filename="privacy.html",
            title="Privacy Policy — Grand Traverse Builders",
            description="Privacy policy for Grand Traverse Builders: Google Analytics, localStorage favorites, and the /api/claim form — what the site actually does.",
            path="privacy",
            page_name="Privacy Policy",
            body_class="page-privacy",
            tag="Privacy",
            h1="Privacy Policy",
            hero_desc="A plain summary of analytics, browser storage, and claim-form data on this directory.",
            body=privacy_body(),
        ),
    ]
    for p in pages:
        html = page_shell(
            title=p["title"],
            description=p["description"],
            path=p["path"],
            page_name=p["page_name"],
            body_class=p["body_class"],
            tag=p["tag"],
            h1=p["h1"],
            hero_desc=p["hero_desc"],
            body_html=p["body"],
            head_nav=head_nav,
            footer=footer,
        )
        # New pages should already have correct Company footer links
        html = rewrite_company_footer(html)
        html = html.replace(
            "379 Builders & Contractors",
            f"{count} Builders & Contractors",
        )
        (ROOT / p["filename"]).write_text(html, encoding="utf-8")
        print(f"wrote {p['filename']}")


COMPANY_FOOTER_RE = re.compile(
    r'(<div class="footer-col"><h4>Company</h4><ul>\s*)'
    r'<li><a href="[^"]*">About Us</a></li>\s*'
    r'<li><a href="[^"]*">Contact</a></li>\s*'
    r'(?:<li><a href="[^"]*">Advertise</a></li>\s*)?'
    r'<li><a href="[^"]*">Privacy Policy</a></li>\s*'
    r"(</ul></div>)",
    re.S,
)

COMPANY_FOOTER_REPL = (
    r"\1"
    '<li><a href="/about">About</a></li>\n'
    '    <li><a href="/contact">Contact</a></li>\n'
    '    <li><a href="/claim">Advertise</a></li>\n'
    '    <li><a href="/privacy">Privacy Policy</a></li>\n'
    "  "
    r"\2"
)


def rewrite_company_footer(text: str) -> str:
    return COMPANY_FOOTER_RE.sub(COMPANY_FOOTER_REPL, text, count=1)


def strip_verified_claims(text: str) -> str:
    # Business service cards (legacy badge copy)
    text = text.replace(
        '<div class="service-card-desc">Verified Professional</div>',
        '<div class="service-card-desc">View category</div>',
    )
    text = text.replace(
        "This business has a verified premium listing with enhanced visibility across the directory.",
        "This business has a premium listing with enhanced visibility across the directory.",
    )

    # Stock category about paragraph
    text = re.sub(
        r"<p>Each listed business has been verified as a local building professional "
        r"serving the Northern Michigan region\.\s*",
        "<p>",
        text,
    )

    # Common adjective uses — order matters (longer / more specific first)
    replacements = [
        (r"\bA verified directory\b", "A directory"),
        (r"\ba verified directory\b", "a directory"),
        (r"\bCompare verified local\b", "Compare local"),
        (r"\bcompare verified local\b", "compare local"),
        (r"\bBrowse verified contractors\b", "Browse local contractors"),
        (r"\bbrowse verified contractors\b", "browse local contractors"),
        (r"\bBrowse verified listings\b", "Browse listings"),
        (r"\bbrowse verified listings\b", "browse listings"),
        (r"\bBrowse (\d+) verified\b", r"Browse \1"),
        (r"\bbrowse (\d+) verified\b", r"browse \1"),
        (r"\blists (\d+) verified\b", r"lists \1"),
        (r"\bdirectory of (\d+)\+ verified\b", r"directory of \1+"),
        (r"\bwith verified\b", "with local"),
        (r"\bverified local\b", "local"),
        (r"\bverified builders\b", "builders"),
        (r"\bverified building contractors\b", "building contractors"),
        (r"\bverified listings\b", "listings"),
        (r"\bverified contractors\b", "contractors"),
        (r"\bverified professionals\b", "professionals"),
        (r"\bverified plumbers\b", "plumbers"),
        (r"\bverified roofers\b", "roofers"),
        (r"\bverified electricians\b", "electricians"),
        (r"\bverified painters\b", "painters"),
        (r"\bverified landscape pros\b", "landscape pros"),
        (r"\bverified heating and cooling pros\b", "heating and cooling pros"),
        (r"\bverified excavation pros\b", "excavation pros"),
        (r"\bverified foundation pros\b", "foundation pros"),
        (r"\bverified pros\b", "pros"),
        (r"\bverified directory\b", "directory"),
    ]
    for pat, repl in replacements:
        text = re.sub(pat, repl, text)
    return text


def update_sitemap(count: int) -> None:
    path = ROOT / "sitemap.xml"
    text = path.read_text(encoding="utf-8")
    entries = [
        ("about", "0.6"),
        ("contact", "0.5"),
        ("privacy", "0.4"),
    ]
    inserts = []
    for slug, pri in entries:
        loc = f"{SITE}/{slug}"
        if loc in text:
            continue
        inserts.append(
            f"<url><loc>{loc}</loc><lastmod>{TODAY}</lastmod>"
            f"<changefreq>monthly</changefreq><priority>{pri}</priority></url>"
        )
    if inserts:
        # Place after homepage / core pages — insert after plan-my-build block if present
        anchor = f"<url><loc>{SITE}/plan-my-build</loc>"
        idx = text.find(anchor)
        if idx == -1:
            text = text.replace(
                "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n",
                "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n"
                + "\n".join(inserts)
                + "\n",
                1,
            )
        else:
            end = text.find("</url>", idx) + len("</url>")
            text = text[:end] + "\n" + "\n".join(inserts) + text[end:]
        path.write_text(text, encoding="utf-8")
        print(f"sitemap: added {len(inserts)} URL(s)")
    else:
        print("sitemap: already has about/contact/privacy")


def iter_html() -> list[Path]:
    files = []
    for p in ROOT.rglob("*.html"):
        if any(part.startswith(".") for part in p.parts):
            continue
        files.append(p)
    return sorted(files)


def main() -> None:
    count = listing_count()
    print(f"listing count from index.html: {count}")
    biz_files = len(list((ROOT / "business").glob("*.html")))
    if biz_files != count:
        print(
            f"WARNING: business/*.html count ({biz_files}) != index businesses ({count})",
            file=sys.stderr,
        )

    head_nav, footer = chrome_from_favorites()
    write_static_pages(count, head_nav, footer)
    update_sitemap(count)

    changed = 0
    for path in iter_html():
        original = path.read_text(encoding="utf-8")
        text = original
        text = text.replace(
            "379 Builders & Contractors",
            f"{count} Builders & Contractors",
        )
        text = rewrite_company_footer(text)
        text = strip_verified_claims(text)
        if text != original:
            path.write_text(text, encoding="utf-8")
            changed += 1
    print(f"updated {changed} HTML files")

    # Sanity greps
    remaining_verified_badge = 0
    remaining_379 = 0
    remaining_hash_about = 0
    for path in iter_html():
        t = path.read_text(encoding="utf-8")
        remaining_verified_badge += t.count("Verified Professional")
        remaining_379 += t.count("379 Builders & Contractors")
        if 'href="#">About' in t or 'href="#">About Us' in t:
            remaining_hash_about += 1
    print(f"remaining Verified Professional: {remaining_verified_badge}")
    print(f"remaining 379 Builders: {remaining_379}")
    print(f"pages with hash About link: {remaining_hash_about}")

    # leftover verified word (informational)
    verif_files = 0
    for path in iter_html():
        if re.search(r"\b[Vv]erified\b", path.read_text(encoding="utf-8")):
            verif_files += 1
    print(f"files still containing word Verified/verified: {verif_files}")


if __name__ == "__main__":
    main()
