# vnstratlab · PO dashboard (branch `po`)

Orphan branch: shares no history with the code. Served at `/po/` by `pages.yml` on `develop`.

- `index.html`, `styles.css`, `app.js` — static UI (Vietnamese), no framework, no build step.
- `data.json` is **not** stored here. It is generated on every Pages build by
  `tools/build_status.py` (on `develop`) from the plan, roadmap, task cards (front matter),
  progress log, ADRs, test/coverage results, benchmark history and the GitHub API.
- Login: the build publishes only `data.enc.json`, encrypted by `tools/encrypt_po.py` with a key
  derived (PBKDF2-SHA256) from the secrets `VNSTRATLAB_PO_USER` / `VNSTRATLAB_PO_PASSWORD`.
  The page decrypts it in the browser (WebCrypto); the derived key stays in `sessionStorage`
  for the tab only. Without the secrets the page says it is not configured.
- Same monochrome design system and buffalo mascot as the intro site (`site` branch).
- A push to this branch triggers `pages.yml` via `.github/workflows/trigger-pages.yml`.

Preview locally:

```bash
# from a develop checkout
python tools/build_status.py --repo . --out /tmp/vnsite
VNSTRATLAB_PO_USER=po VNSTRATLAB_PO_PASSWORD=<test value> \n  python tools/encrypt_po.py --in /tmp/vnsite/po/data.json --out /tmp/vnsite/po/data.enc.json
cp -r <po checkout>/* /tmp/vnsite/po/
python -m http.server -d /tmp/vnsite 8080   # open http://localhost:8080/po/
```

Changes go through a PR into `po` (G2 review for content and accessibility).
