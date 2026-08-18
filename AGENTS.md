# Grand Traverse Builders

Static SEO directory website (Northwest Michigan builders directory). See `README.md` for the project overview and layout.

## Cursor Cloud specific instructions

- Mostly a static site (plain HTML + vanilla JS) with one dynamic piece: a Cloudflare Pages Function at `functions/api/claim.js` (the claim form). No build step, no package manager, no lockfile. Nothing to compile; no dependencies to install.
- Two ways to run locally from the repo root:
  - Static only: `npx serve .` (http://localhost:3000) or `python3 -m http.server 3000`. Fine for HTML/CSS/JS work, but `/api/claim` will 404 and the `_headers` rules do not apply.
  - Full (with the claim backend + `_headers`): `npx wrangler pages dev . --port 8788`. Use this to test the claim form end-to-end. Both Node 22 and Python 3 are available.
- Clean URLs: the site is served at extensionless URLs (`/business/<slug>`). `npx serve` and Cloudflare Pages both 301-redirect `/x.html` → `/x`. Internal links still use `.html` (they redirect fine). Any code that reads the current URL must NOT assume a `.html` suffix (this caused the favorites Save-button bug).
- `project.js` is the SINGLE source of truth for planner/favorites/search JS. Every page loads `<script src="/project.js" defer>`; pages no longer inline it, so JS changes only need to happen in `project.js`. `style.css` is currently unused (no page links it) — edit the inline `<style>` blocks or `project.js`, not `style.css`.
- Directory data has no live source — it is a static snapshot, and the same business records are duplicated across `index.html` (the master `businesses` array), `business/*.html`, `category/*.html`, `search-index.json`, and `sitemap.xml`. To add/update/verify a business you must keep those copies in sync.
- Audit the directory with `python3 scripts/audit_directory.py`: it cross-checks all those copies and flags stale hard-coded counts, orphaned pages, category count mismatches, suspicious shared website/phone data, and completeness gaps. Run it after any data change.
- Generated file: `search-index.json` powers `/search`. Regenerate it after directory data changes with `python3 scripts/build_search_index.py` (it is derived from the `businesses` dataset embedded in `index.html`). The other `scripts/*.py` are idempotent transforms (SEO/URL cleanup, https upgrade, etc.) that have already been applied; re-running them is safe.
- Claim function env vars (all optional, set in the Pages dashboard): `RESEND_API_KEY` + `CLAIM_NOTIFY_TO` + `CLAIM_NOTIFY_FROM` (email via Resend), `CLAIM_WEBHOOK_URL` (forward JSON), `TURNSTILE_SECRET` (spam check). With none set, the function validates, logs, and returns success so the form works out of the box.
- There are no lint/test/build commands — no such tooling exists. Sanity-check by serving and exercising favorites, the "Plan My Build" planner (localStorage keys `nwmi_favorites` / `nwmi_project`), `/search`, and the claim form in a browser.
