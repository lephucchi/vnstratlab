# vnstratlab · PO dashboard (branch `po`)

**Live dashboard:** https://lephucchi.github.io/vnstratlab/po/ (login required; credentials are the
`PO_USERNAME` / `PO_PASSWORD` repository secrets). Intro site: https://lephucchi.github.io/vnstratlab/

Orphan branch: shares no history with the code. Served at `/po/` by `pages.yml` on `develop`.

- `index.html`, `styles.css`, `app.js` — static UI (Vietnamese), no framework, no build step.
- `data.json` is **not** stored here. It is generated on every Pages build by
  `tools/build_status.py` (on `develop`) from the plan, roadmap, task cards (front matter),
  progress log, ADRs, test/coverage results, benchmark history and the GitHub API.
- Login: the build publishes only `data.enc.json`, encrypted by `tools/encrypt_po.py` with a key
  derived (PBKDF2-SHA256) from the secrets `PO_USERNAME` / `PO_PASSWORD`.
  The page decrypts it in the browser (WebCrypto); the derived key stays in `sessionStorage`
  for the tab only. Every Pages build rotates the salt, so users log in again after each build.
  Without the secrets the page says it is not configured. A CSP meta tag allows only same-origin
  scripts/data and Google Fonts.
- Same monochrome design system and buffalo mascot as the intro site (`site` branch).
- A push to this branch triggers `pages.yml` via `.github/workflows/trigger-pages.yml`.

Preview locally:

```bash
# from a develop checkout; put test values in .env (PO_USERNAME=..., PO_PASSWORD=...)
# rather than on the command line, so they stay out of shell history
python tools/build_status.py --repo . --out /tmp/vnsite      # writes po/data.enc.json
cp -r <po checkout>/* /tmp/vnsite/po/
python -m http.server -d /tmp/vnsite 8080                    # open http://localhost:8080/po/
```

Changes go through a PR into `po` (G2 review for content and accessibility).
