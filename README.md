# vnstratlab · PO dashboard (branch `po`)

Orphan branch: shares no history with the code. Served at `/po/` by `pages.yml` on `develop`.

- `index.html`, `styles.css`, `app.js` — static UI (Vietnamese), no framework, no build step.
- `data.json` is **not** stored here. It is generated on every Pages build by
  `tools/build_status.py` (on `develop`) from the plan, roadmap, task cards (front matter),
  progress log, ADRs, test/coverage results, benchmark history and the GitHub API.
- A push to this branch triggers `pages.yml` via `.github/workflows/trigger-pages.yml`.

Preview locally:

```bash
# from a develop checkout
python tools/build_status.py --repo . --out /tmp/vnsite
cp -r <po checkout>/* /tmp/vnsite/po/
python -m http.server -d /tmp/vnsite 8080   # open http://localhost:8080/po/
```

Changes go through a PR into `po` (G2 review for content and accessibility).
