# Grand Traverse Builders

Static SEO directory website (Northwest Michigan builders directory). See `README.md` for the project overview and layout.

## Cursor Cloud specific instructions

- This is a pure static site: plain HTML, `style.css`, and vanilla JS (`project.js`). There is no build step, no package manager, no lockfile, and no backend. There is nothing to compile and no dependencies to install.
- Run it with any static file server from the repo root. Canonical command (per `README.md`): `npx serve .` (serves on http://localhost:3000). `python3 -m http.server 3000` also works — both Node 22 and Python 3 are available.
- Internal links use `.html` paths (e.g. `/business/<slug>.html`), so both servers work. Note: `npx serve` additionally 301-redirects `.html` URLs to extensionless "clean" URLs; this is expected and transparent in a browser. `python3 -m http.server` serves the `.html` paths directly without redirects but does NOT serve clean/extensionless URLs.
- `npx serve` fetches the `serve` package from npm on first use (needs network). If offline, use `python3 -m http.server` instead, which needs no downloads.
- There are no lint, test, or build commands — this repo has no such tooling. "Running" the app just means serving the files and opening them in a browser.
- Core client-side functionality lives in `project.js`: favorites (localStorage key `nwmi_favorites`) and the "Plan My Build" planner (localStorage key `nwmi_project`) on `/plan-my-build.html`. To sanity-check changes, exercise the planner and favorites in the browser; there is no automated test harness.
