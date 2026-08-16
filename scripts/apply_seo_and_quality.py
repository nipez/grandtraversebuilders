#!/usr/bin/env python3
"""Idempotent SEO + data-quality pass over all static HTML pages.

Transforms applied to every page:
  1. Canonical/OG/JSON-LD absolute URLs: strip the ".html" so they match the
     clean/extensionless URLs actually served (Cloudflare Pages + `serve` both
     301-redirect /path.html -> /path). Internal *relative* links are left alone.
  2. Upgrade outbound http:// links (business sites, socials) to https://,
     leaving XML namespaces (w3.org/schema.org) untouched.
  3. Inject favicon, theme-color, og:image/twitter:image, and upgrade the
     Twitter card to summary_large_image.
  4. Fix the BreadcrumbList "Home" item (was null) to point at the homepage.
  5. Relabel Facebook links mislabeled as "Visit Website".
  6. Add noindex to claim.html (it is Disallowed in robots.txt).

Safe to run repeatedly.
"""
import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOMAIN = "https://grandtraversebuilders.com"

FAVI_MARK = "favicon.svg"
OG_MARK = "og-image.png"

CLEAN_RE = re.compile(r"(https://grandtraversebuilders\.com/[^\s\"'<>]+?)\.html")
CONTENT_HTTP_RE = re.compile(r'content="http://([^"]+)"')
FAVICON_BLOCK = (
    '<link rel="icon" href="/favicon.svg" type="image/svg+xml"/>'
    '<meta name="theme-color" content="#1C2B36"/>'
)
OG_BLOCK = (
    f'<meta property="og:image" content="{DOMAIN}/og-image.png"/>'
    '<meta property="og:image:width" content="1200"/>'
    '<meta property="og:image:height" content="630"/>'
    f'<meta name="twitter:image" content="{DOMAIN}/og-image.png"/>'
)


def clean_urls(t):
    t = t.replace("grandtraversebuilders.com/index.html", "grandtraversebuilders.com/")
    return CLEAN_RE.sub(r"\1", t)


def upgrade_https(t):
    t = t.replace('href="http://', 'href="https://')
    t = t.replace('"sameAs":"http://', '"sameAs":"https://')
    t = t.replace('"w":"http://', '"w":"https://')  # embedded businesses dataset

    def repl(m):
        rest = m.group(1)
        host = rest.split("/")[0]
        if host.endswith("w3.org") or host.endswith("schema.org"):
            return m.group(0)
        return 'content="https://' + rest + '"'

    return CONTENT_HTTP_RE.sub(repl, t)


def inject_head(t):
    if FAVI_MARK not in t:
        t = re.sub(r'(<meta content="width=device-width[^>]*/>)', r"\1" + FAVICON_BLOCK, t, count=1)
    if OG_MARK not in t:
        t = re.sub(r'(<link rel="canonical"[^>]*/>)', r"\1" + OG_BLOCK, t, count=1)
    t = t.replace('name="twitter:card" content="summary"', 'name="twitter:card" content="summary_large_image"')
    return t


def fix_breadcrumb(t):
    return t.replace('"name":"Home","item":null', f'"name":"Home","item":"{DOMAIN}/"')


def relabel_facebook(t):
    t = re.sub(
        r'(<a href="https://[^"]*facebook\.com[^"]*"[^>]*class="sidebar-btn secondary">)\U0001F310 Visit Website(</a>)',
        lambda m: m.group(1) + "\U0001F4D8 Facebook" + m.group(2),
        t,
    )
    t = re.sub(
        r'(<span class="si-label">)Web(</span><a href="https://[^"]*facebook\.com)',
        r"\1Facebook\2",
        t,
    )
    return t


def add_noindex(t):
    if "noindex" in t:
        return t
    return re.sub(
        r'(<meta content="width=device-width[^>]*/>)',
        r'\1<meta name="robots" content="noindex,follow"/>',
        t,
        count=1,
    )


def iter_files():
    for name in ("index.html", "categories.html", "claim.html", "plan-my-build.html"):
        p = ROOT / name
        if p.exists():
            yield p
    for sub in ("business", "category", "blog"):
        yield from sorted((ROOT / sub).glob("*.html"))


def main():
    changed = 0
    for p in iter_files():
        orig = p.read_text(encoding="utf-8")
        t = orig
        t = clean_urls(t)
        t = upgrade_https(t)
        t = inject_head(t)
        t = fix_breadcrumb(t)
        t = relabel_facebook(t)
        if p.name == "claim.html":
            t = add_noindex(t)
        if t != orig:
            p.write_text(t, encoding="utf-8")
            changed += 1
    print(f"Updated {changed} HTML files")


if __name__ == "__main__":
    main()
