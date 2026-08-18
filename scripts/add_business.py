#!/usr/bin/env python3
"""Add (or update) a single business across every place the directory stores data.

Because this is a static directory with the same records duplicated in many files,
adding one business by hand is error-prone. This helper keeps them in sync:
  1. master dataset (the `businesses` array in index.html)
  2. business/<slug>.html detail page (generated from the shared template)
  3. each relevant category/<cat>.html page (embedded array + visible counts)
  4. sitemap.xml
  5. search-index.json (regenerated)
  6. global "N Builders & Contractors" / "N Businesses Listed" counts

Edit the RECORD near the bottom and run:  python3 scripts/add_business.py
Re-running is safe: an existing slug is updated in place, not duplicated.
Always run scripts/audit_directory.py afterward to verify.
"""
import json
import re
import subprocess
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOMAIN = "https://grandtraversebuilders.com"
TEMPLATE_BIZ = ROOT / "business" / "a-better-sound.html"


def slugify(t):
    t = t.lower()
    t = re.sub(r"[^\w\s-]", "", t)
    t = re.sub(r"[\s_]+", "-", t)
    t = re.sub(r"-+", "-", t)
    return t.strip("-")


def find_array_span(text, var):
    i = text.index(f"const {var}=")
    s = text.index("[", i)
    depth = 0
    for j in range(s, len(text)):
        if text[j] == "[":
            depth += 1
        elif text[j] == "]":
            depth -= 1
            if depth == 0:
                return s, j + 1
    raise ValueError("array not terminated")


def load_dataset():
    t = (ROOT / "index.html").read_text(encoding="utf-8")
    s, e = find_array_span(t, "businesses")
    return json.loads(t[s:e])


def rec_json(r):
    return json.dumps(
        {"n": r["n"], "p": r["p"], "a": r["a"], "w": r["w"], "c": r["c"], "s": r["s"]},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def upsert_in_array(html, var, record):
    """Insert record into `const var=[...]`, or replace an existing entry with the
    same slug. Returns (new_html, array_len)."""
    s, e = find_array_span(html, var)
    arr = json.loads(html[s:e])
    arr = [b for b in arr if b.get("s") != record["s"]]
    arr.append(record)
    new_arr = "[" + ",".join(rec_json(b) for b in arr) + "]"
    return html[:s] + new_arr + html[e:], len(arr)


SHARED_STYLE = re.search(r"<style>.*?</style>", TEMPLATE_BIZ.read_text(encoding="utf-8"), re.S).group(0)

TAG_SPAN = ('<span style="display:inline-flex;align-items:center;gap:5px;padding:4px 12px;border-radius:4px;'
            'font-size:.62rem;font-weight:600;letter-spacing:.08em;text-transform:uppercase;'
            'background:rgba(193,127,78,0.15);color:var(--copper-glow);border:1px solid rgba(193,127,78,0.2);">{c}</span>')


def initials(name):
    words = [w for w in re.sub(r"[^A-Za-z ]", "", name).split() if w]
    return (words[0][0] + (words[1][0] if len(words) > 1 else "")).upper() if words else "?"


def web_display(url):
    return re.sub(r"^https?://", "", url).rstrip("/")


def build_business_page(r):
    name, phone, addr, web, cats, slug = r["n"], r["p"], r["a"], r["w"], r["c"], r["s"]
    city = r.get("city") or "Northwest Michigan"
    first_cat = cats[0]
    first_slug = slugify(first_cat)
    cats_lower = ", ".join(c.lower() for c in cats)
    trades = ", ".join(cats)
    esc_name = name.replace('"', "&quot;")
    biz_q = name.replace(" ", "%20").replace("&", "%26")

    title = f"{esc_name} — {first_cat} in {city} | Grand Traverse Builders"
    desc = f"{esc_name} is a verified {cats_lower} in {city}. Contact info, services, and more."

    breadcrumb_ld = {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{DOMAIN}/"},
            {"@type": "ListItem", "position": 2, "name": first_cat, "item": f"{DOMAIN}/category/{first_slug}"},
            {"@type": "ListItem", "position": 3, "name": name, "item": f"{DOMAIN}/business/{slug}"},
        ],
    }
    local_ld = {
        "@context": "https://schema.org", "@type": "LocalBusiness", "name": name,
        "url": f"{DOMAIN}/business/{slug}",
        "description": f"{name} is a verified building professional serving {city} and surrounding areas.",
        "areaServed": {"@type": "City", "name": city, "containedInPlace": {"@type": "State", "name": "Michigan"}},
        "telephone": phone,
    }
    if web:
        local_ld["sameAs"] = web
    if addr:
        local_ld["address"] = {"@type": "PostalAddress", "streetAddress": addr.split(",")[0], "addressLocality": city, "addressRegion": "MI", "addressCountry": "US"}
    local_ld["knowsAbout"] = cats

    tag_spans = "".join(TAG_SPAN.format(c=c) for c in cats)
    service_cards = "".join(
        f'<a href="../category/{slugify(c)}.html" class="service-card" style="text-decoration:none;color:inherit;">'
        f'<div class="service-card-icon">🔧</div><div class="service-card-name">{c}</div>'
        f'<div class="service-card-desc">Verified Professional</div></a>'
        for c in cats
    )

    contact_actions = f'<a href="tel:{phone}" class="sidebar-btn primary">📞 Call {phone}</a>' if phone else ""
    if web:
        contact_actions += f'<a href="{web}" target="_blank" rel="noopener" class="sidebar-btn secondary">🌐 Visit Website</a>'

    info_items = ""
    if addr:
        info_items += f'<li><span class="si-label">Address</span><span>{addr}</span></li>'
    if phone:
        info_items += f'<li><span class="si-label">Phone</span><a href="tel:{phone}">{phone}</a></li>'
    if web:
        info_items += f'<li><span class="si-label">Web</span><a href="{web}" target="_blank" rel="noopener">{web_display(web)}</a></li>'
    info_items += f'<li><span class="si-label">Trades</span><span>{trades}</span></li>'

    map_card = ""
    if addr:
        aq = addr.replace(" ", "%20").replace(",", "%2C")
        map_card = (f'<div class="sidebar-card" style="padding:0;overflow:hidden;"><div style="width:100%;height:200px;">'
                    f'<iframe src="https://www.google.com/maps?q={aq}&output=embed" width="100%" height="200" '
                    f'style="border:0;display:block;" allowfullscreen="" loading="lazy" referrerpolicy="no-referrer-when-downgrade"></iframe></div>'
                    f'<div style="padding:16px 28px 20px;"><h3 style="margin-bottom:12px;">📍 Location</h3>'
                    f'<div style="font-size:1rem;color:var(--text-light);margin-bottom:14px;line-height:1.5;">{addr}</div>'
                    f'<a href="https://www.google.com/maps/search/?api=1&query={aq}" target="_blank" rel="noopener" class="sidebar-btn secondary">Get Directions</a></div></div>')

    bc_ld = json.dumps(breadcrumb_ld, ensure_ascii=False, separators=(",", ":"))
    lb_ld = json.dumps(local_ld, ensure_ascii=False, separators=(",", ":"))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-J2WCDRKR73"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-J2WCDRKR73');</script>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/><link rel="icon" href="/favicon.svg" type="image/svg+xml"/><meta name="theme-color" content="#1C2B36"/>
<title>{title}</title>
<meta content="{desc}" name="description"/>
<link rel="canonical" href="{DOMAIN}/business/{slug}"/><meta property="og:image" content="{DOMAIN}/og-image.png"/><meta property="og:image:width" content="1200"/><meta property="og:image:height" content="630"/><meta name="twitter:image" content="{DOMAIN}/og-image.png"/>
<meta property="og:title" content="{title}"/>
<meta property="og:description" content="{desc}"/>
<meta property="og:type" content="business.business"/>
<meta property="og:url" content="{DOMAIN}/business/{slug}"/>
<meta property="og:site_name" content="Grand Traverse Builders"/>
<meta property="og:locale" content="en_US"/>
<meta name="twitter:card" content="summary_large_image"/>
<meta name="twitter:title" content="{title}"/>
<meta name="twitter:description" content="{desc}"/>
<meta name="geo.region" content="US-MI"/>
<meta name="geo.placename" content="Traverse City, Michigan"/>
<script type="application/ld+json">{bc_ld}</script><script type="application/ld+json">{lb_ld}</script>
<link href="https://fonts.googleapis.com" rel="preconnect"/>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=Source+Serif+4:ital,opsz,wght@0,8..60,300;0,8..60,400;0,8..60,500;0,8..60,600;1,8..60,400&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&display=swap" rel="stylesheet"/>
{SHARED_STYLE}
</head>
<body data-root="../">

<div class="top-bar"><span>8 Counties</span> · 377 Builders & Contractors · <span>119 Trade Categories</span> · Serving Northwest Michigan</div>
<nav id="mainNav"><div class="nav-inner">
<a class="logo" href="../">
  <div class="logo-mark"><svg width="18" height="18" viewBox="0 0 18 18" fill="none" style="position:relative;z-index:1;"><path d="M9 2L2 8h2v7h4v-4h2v4h4V8h2L9 2z" stroke="var(--copper-light)" stroke-width="1.4" fill="none"/></svg></div>
  <div class="logo-text"><span class="logo-main">Grand Traverse Builders</span><span class="logo-sub">Home Building Directory</span></div>
</a>
<ul class="nav-links">
  <li><a href="../#trades">Trades</a></li>
  <li><a href="../#directory">Directory</a></li>
  <li><a href="../categories.html">All Categories</a></li>
  <li><a href="../blog/">Blog</a></li>
  <li><a href="../plan-my-build.html">Plan My Build</a></li>
  <li><a href="/search">Search</a></li><li><a class="nav-cta" href="../claim.html">List Your Business</a></li>
</ul>
<button class="nav-toggle" onclick="document.querySelector('.nav-links').classList.toggle('show')" aria-label="Menu">
  <svg width="24" height="24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12h18M3 6h18M3 18h18"/></svg>
</button>
</div></nav>

<div class="breadcrumbs">
  <a href="../">Home</a><span class="sep">/</span>
  <a href="../category/{first_slug}.html">{first_cat}</a><span class="sep">/</span>
  <span class="current">{name}</span>
</div>

<section class="page-hero" style="padding:50px 40px 45px;">
<div class="page-hero-bg"></div>
<div class="page-hero-content" style="display:flex;align-items:center;gap:24px;flex-wrap:wrap;">
  <div class="card-avatar" style="background:#4A5A6A;width:68px;height:68px;font-size:1.5rem;border-radius:12px;flex-shrink:0;">{initials(name)}</div>
  <div>
    <div style="display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;">{tag_spans}</div>
    <h1 style="font-size:clamp(1.8rem,3.5vw,2.6rem);">{name}</h1>
    <p class="page-hero-desc" style="margin-top:6px;">{city}, Michigan</p>
  </div>
</div>
</section>

<main>
<article itemscope itemtype="https://schema.org/LocalBusiness">
<meta itemprop="name" content="{esc_name}"/>
<meta itemprop="telephone" content="{phone}"/>
{f'<meta itemprop="url" content="{web}"/>' if web else ''}

<div class="detail-wrap">
  <div class="detail-main">
    <div class="about-section">
      <div class="section-label">About</div>
      <h2>About {name}</h2>
      <div class="about-text">
        <p>{name} is a verified building professional serving {city} and surrounding areas in Northwest Michigan. Specializing in {cats_lower}, they bring professional expertise and local knowledge to every project.</p>
        <p>As a listed contractor in the Northwest Michigan builder directory, {name} is part of a network of trusted professionals committed to quality construction standards across the region's 8 counties.</p>
      </div>
    </div>

    <div class="section-label">Services &amp; Specialties</div><div class="services-grid">{service_cards}</div>

    <div class="claim-banner">
      <h3>Is This Your Business?</h3>
      <p>Claim your free listing to add photos, a detailed description, and showcase your best work. Premium listings get priority placement and lead generation.</p>
      <a href="../claim.html?business={biz_q}" class="btn-primary">Claim This Listing</a>
    </div>
  </div>

  <div class="detail-sidebar">
    <div class="sidebar-card">
      <h3>Contact</h3>
      <div class="sidebar-actions">
        {contact_actions}
      </div>
    </div>

    <div class="sidebar-card">
      <h3>Business Info</h3>
      <ul class="sidebar-info">{info_items}</ul>
      <div class="sidebar-creds">
        <span class="cred-badge">✓ Verified Listing</span>
        <span class="cred-badge">✓ Licensed</span>
        <span class="cred-badge">✓ Insured</span>
      </div>
    </div>
    {map_card}
  </div>
</div>
</article>
</main>

<section class="cta-banner" id="cta">
<div class="cta-inner">
  <h2>Are You a Builder or Contractor?</h2>
  <p>Get listed in Northwest Michigan's most comprehensive building directory. Reach homeowners actively planning new builds and renovations.</p>
  <a href="../claim.html" class="btn-primary">Get Listed</a>
</div>
</section>
<footer><div class="footer-inner">
<div class="footer-grid">
  <div class="footer-brand">
    <div class="logo-text"><span class="logo-main">Grand Traverse Builders</span><span class="logo-sub">Home Building Directory</span></div>
    <p>Your comprehensive guide to home builders, contractors, and skilled trades across Northwest Michigan's 8 counties.</p>
  </div>
  <div class="footer-col"><h4>Top Trades</h4><ul><li><a href="../category/building-contractors.html">Home Builders</a></li><li><a href="../category/remodeling-contractors.html">Remodeling</a></li><li><a href="../category/building-materials-retail.html">Materials (Retail)</a></li><li><a href="../category/kitchen-bath.html">Kitchen & Bath</a></li><li><a href="../category/windows-doors.html">Windows & Doors</a></li><li><a href="../category/roofing.html">Roofing</a></li></ul></div>
  <div class="footer-col"><h4>Resources</h4><ul>
    <li><a href="../categories.html">All Categories</a></li>
    <li><a href="../plan-my-build.html">Plan My Build</a></li>
    <li><a href="../blog/">Building Guides</a></li>
    <li><a href="../blog/building-permits-grand-traverse-county-guide.html">Permit Info</a></li>
  </ul></div>
  <div class="footer-col"><h4>Company</h4><ul>
    <li><a href="#">About Us</a></li>
    <li><a href="#">Contact</a></li>
    <li><a href="#">Advertise</a></li>
    <li><a href="#">Privacy Policy</a></li>
  </ul></div>
</div>
<div class="footer-bottom">
  <span>&copy; 2026 Grand Traverse Builders. All rights reserved.</span><span>Built by <a href="https://solutionstud.io/" target="_blank" rel="noopener">Solution Studio</a></span>
  <span>Covering Antrim &middot; Benzie &middot; Grand Traverse &middot; Kalkaska &middot; Leelanau &middot; Manistee &middot; Missaukee &middot; Wexford</span>
</div>
</div></footer>

<script src="/project.js" defer></script>
<script>window.addEventListener('scroll',()=>{{document.getElementById('mainNav').classList.toggle('scrolled',window.scrollY>10);}});</script>
</body></html>
"""


def update_category_page(cat, record):
    slug = slugify(cat)
    p = ROOT / "category" / f"{slug}.html"
    if not p.exists():
        print(f"  ! category page missing: {slug}.html (skipped)")
        return
    t = p.read_text(encoding="utf-8")
    t, new_len = upsert_in_array(t, "businesses", record)
    old = new_len - 1
    t = t.replace(f'"numberOfItems":{old}', f'"numberOfItems":{new_len}', 1)
    t = t.replace(f"Showing <strong>{old}</strong>", f"Showing <strong>{new_len}</strong>", 1)
    t = t.replace(f'<div class="ph-stat-num">{old}</div><div class="ph-stat-label">Businesses</div>',
                  f'<div class="ph-stat-num">{new_len}</div><div class="ph-stat-label">Businesses</div>', 1)
    t = t.replace(f'setCity(\'all\',this)">All<span class="count"> ({old})</span>',
                  f'setCity(\'all\',this)">All<span class="count"> ({new_len})</span>', 1)
    p.write_text(t, encoding="utf-8")
    print(f"  ✓ category {slug}: {old} -> {new_len}")


def bump_global_counts(total):
    old = total - 1
    changed = 0
    files = [ROOT / n for n in ("index.html", "categories.html", "claim.html", "plan-my-build.html", "search.html", "traverse-city-home-builders.html")]
    files += list((ROOT / "business").glob("*.html")) + list((ROOT / "category").glob("*.html")) + list((ROOT / "blog").glob("*.html"))
    for p in files:
        if not p.exists():
            continue
        t = p.read_text(encoding="utf-8")
        n = t
        n = n.replace(f"{old} Builders & Contractors", f"{total} Builders & Contractors")
        n = n.replace(f'<div class="ph-stat-num" style="font-size:2.2rem;">{old}</div><div class="ph-stat-label">Businesses Listed</div>',
                      f'<div class="ph-stat-num" style="font-size:2.2rem;">{total}</div><div class="ph-stat-label">Businesses Listed</div>')
        if n != t:
            p.write_text(n, encoding="utf-8")
            changed += 1
    print(f"  ✓ bumped global count {old} -> {total} in {changed} files")


def add_to_sitemap(slug):
    p = ROOT / "sitemap.xml"
    t = p.read_text(encoding="utf-8")
    if f"/business/{slug}<" in t:
        return
    import datetime
    entry = f'  <url><loc>{DOMAIN}/business/{slug}</loc><lastmod>{datetime.date.today().isoformat()}</lastmod><changefreq>monthly</changefreq><priority>0.6</priority></url>\n'
    t = t.replace("</urlset>", entry + "</urlset>", 1)
    p.write_text(t, encoding="utf-8")
    print(f"  ✓ added to sitemap: /business/{slug}")


def add_business(record):
    record["s"] = record.get("s") or slugify(record["n"])
    slug = record["s"]
    ds_record = {k: record.get(k, "") for k in ("n", "p", "a", "w", "c", "s")}
    print(f"Adding: {record['n']} ({slug})  categories={record['c']}")

    # 1) master dataset
    idx = ROOT / "index.html"
    html, total = upsert_in_array(idx.read_text(encoding="utf-8"), "businesses", ds_record)
    idx.write_text(html, encoding="utf-8")
    print(f"  ✓ dataset now {total} businesses")

    # 2) detail page
    (ROOT / "business" / f"{slug}.html").write_text(build_business_page(record), encoding="utf-8")
    print(f"  ✓ wrote business/{slug}.html")

    # 3) category pages
    for cat in record["c"]:
        update_category_page(cat, ds_record)

    # 4) global counts
    bump_global_counts(total)

    # 5) sitemap
    add_to_sitemap(slug)

    # 6) search index
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_search_index.py")], check=True)


# ---- Edit this record, then run the script -----------------------------------
RECORD = {
    "n": "Midwest Exteriors LLC",
    "p": "231-620-5061",
    "a": "4144 M-72, Williamsburg, MI 49690",
    "w": "https://www.midwestexteriorsllc.com/",
    "c": ["Windows & Doors", "Siding Contractors", "Roofing"],
    "city": "Williamsburg",
}

if __name__ == "__main__":
    add_business(RECORD)
