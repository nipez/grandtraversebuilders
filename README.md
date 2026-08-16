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
