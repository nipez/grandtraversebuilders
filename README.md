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
- `business/` — 377 business listing pages
- `category/` — 119 category pages
- `project.js` — favorites / project planner (localStorage)
- `style.css` — shared styles
- `sitemap.xml`, `robots.txt`

## Cloudflare Pages

- **Project name:** `buildnorthernmichigan`
- **Production domain:** https://grandtraversebuilders.com
- **Pages.dev:** https://buildnorthernmichigan.pages.dev

Direct Upload originally (not Git-connected). Re-deploy from this repo after connecting the project to GitHub if you want Git-based deploys.

### Regenerating the search index

After changing the businesses list in `index.html`:

```bash
python3 scripts/build_search_index.py
```

### Thin category noindex

Category pages with fewer than 3 listings are marked `noindex, follow` and omitted from `sitemap.xml` (15 SEO-upgraded trades always stay indexable). After listing data changes:

```bash
python3 scripts/thin_category_noindex.py
python3 scripts/thin_category_noindex.py --verify-only
```

### URL status audit (sitemap + historical)

```bash
python3 scripts/check_urls.py --base https://grandtraversebuilders.com
python3 scripts/check_urls.py --base https://<preview>.buildnorthernmichigan.pages.dev --fail-on-bad
```

Uses `sitemap.xml` plus `scripts/historical-urls.txt` (past sitemap locs, `.html` variants, template-leak paths). Expect every sitemap URL → 200, historical URLs → 200 or one 301/308 hop; `/404` stays 404 by design.
