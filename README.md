# Grand Traverse Builders

Northwest Michigan builders directory — home builders, contractors, and trades across the Traverse City area (Grand Traverse, Leelanau, Benzie, and neighboring counties).

This is a **static site**, recovered from the live Cloudflare Pages direct-upload deployment (`buildnorthernmichigan`, production domain [grandtraversebuilders.com](https://grandtraversebuilders.com)). It was not previously on Git so the published files are the source of truth.

## Run locally

```bash
npx serve .
```

Then open the URL `serve` prints (usually http://localhost:3000).

## Layout

- `index.html` — homepage / directory
- `categories.html` — all trade categories
- `search.html` / `search-index.json` — site-wide directory search (`/search?q=`)
- `claim.html` — claim a listing
- `plan-my-build.html` — project planner
- `blog/` — guides
- `business/` — business listing pages (count from `const businesses` in `index.html`)
- `category/` — 119 category pages
- `project.js` — favorites / project planner (localStorage)
- `style.css` — shared styles
- `sitemap.xml`, `robots.txt`

## Cloudflare Pages

- **Project name:** `buildnorthernmichigan`
- **Production domain:** https://grandtraversebuilders.com
- **Pages.dev:** https://buildnorthernmichigan.pages.dev

Direct Upload originally (not Git-connected). Re-deploy from this repo after connecting the project to GitHub if you want Git-based deploys.

### Listing data audit / cleanup

Source of truth is `const businesses=[...]` in `index.html`. Audit (and optionally normalize) data quality:

```bash
python3 scripts/audit_listings.py              # report only
python3 scripts/audit_listings.py --apply      # fix + sync category arrays, counts, redirects, sitemap
```

After data changes, rebuild derived artifacts:

```bash
python3 scripts/build_search_index.py
python3 scripts/upgrade_business_pages.py
python3 scripts/inject-static-listings.py
python3 scripts/thin_category_noindex.py
python3 scripts/thin_category_noindex.py --verify-only
python3 scripts/update_sitemap_lastmod.py
```

### Regenerating the search index

```bash
python3 scripts/build_search_index.py
```

### Thin category noindex

Category pages with fewer than 3 listings are marked `noindex, follow` and omitted from `sitemap.xml` (25 SEO-upgraded trades always stay indexable). After listing data changes:

```bash
python3 scripts/thin_category_noindex.py
python3 scripts/thin_category_noindex.py --verify-only
```

### Sitemap lastmod dates

`sitemap.xml` `<lastmod>` values are derived from git history of each URL’s HTML source (skipping directory-wide listing-count chrome so audit-only count bumps don’t rewrite every date). Re-run after content or listing rebuilds:

```bash
python3 scripts/update_sitemap_lastmod.py
python3 scripts/update_sitemap_lastmod.py --dry-run
```

On shallow clones (e.g. Cloudflare Pages), the script deepens history when possible and keeps the existing `<lastmod>` when a file has no usable history — it never stamps today’s date as a fallback.

### IndexNow (search engine URL submission)

After each push to `main`, Cloudflare Pages deploys the static site, then the GitHub Actions workflow [`.github/workflows/indexnow.yml`](.github/workflows/indexnow.yml) waits until production is live and submits **new or changed** sitemap URLs to [IndexNow](https://www.indexnow.org/) (`https://api.indexnow.org/indexnow`).

- **Key file (public by design):** [`/07a8cebdaa07da33e0ad820b1a1ec2de.txt`](https://grandtraversebuilders.com/07a8cebdaa07da33e0ad820b1a1ec2de.txt) — body is only the key; served as `text/plain`.
- **Script:** `scripts/indexnow_submit.py` (Python standard library only). Diffs `sitemap.xml` `<loc>` / `<lastmod>` against the previous commit by default; supports `--all`, `--urls`, and `--dry-run`.
- **Weekly SEO articles:** new blog posts are added to `sitemap.xml` (and get a `<lastmod>` from `scripts/update_sitemap_lastmod.py`), so the post-deploy sitemap-diff step submits them automatically — no extra wiring.
- The workflow needs **no secrets**. A non-2xx IndexNow response is logged as a warning and never fails the deploy.

```bash
python3 scripts/indexnow_submit.py --dry-run
python3 scripts/indexnow_submit.py --dry-run HEAD~1
python3 scripts/indexnow_submit.py --all --dry-run
python3 scripts/indexnow_submit.py --urls https://grandtraversebuilders.com/about --dry-run
```

Rebuild chain reminder (listing/content changes → derived artifacts → sitemap dates → IndexNow on next `main` deploy):

```bash
python3 scripts/build_search_index.py
python3 scripts/upgrade_business_pages.py
python3 scripts/inject-static-listings.py
python3 scripts/thin_category_noindex.py
python3 scripts/update_sitemap_lastmod.py
# push to main → Cloudflare Pages deploy → IndexNow workflow submits sitemap diff
```

### URL status audit (sitemap + historical)

```bash
python3 scripts/check_urls.py --base https://grandtraversebuilders.com
python3 scripts/check_urls.py --base https://<preview>.buildnorthernmichigan.pages.dev --fail-on-bad
```

Uses `sitemap.xml` plus `scripts/historical-urls.txt` (past sitemap locs, `.html` variants, template-leak paths). Expect every sitemap URL → 200, historical URLs → 200 or one 301/308 hop; `/404` stays 404 by design.
