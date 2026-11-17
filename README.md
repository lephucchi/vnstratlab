# vnstratlab · intro site (branch `site`)

Orphan branch: shares no history with the code. Served at `/` by `pages.yml` on `develop`.

- `index.html`, `styles.css`, `app.js`, `buffalo.svg` — static, bilingual (VI/EN), no framework, no build step.
  Monochrome design (light/dark), animated dot-grid background, terminal demo with real
  commands and output, pipeline and git-flow diagrams. Mascot: the buffalo (`buffalo.svg`).
- The "Project status" block reads `data/status.json`, generated on every Pages build from CI
  measurements on `develop` (tests, coverage, last CI run, benchmarks). Only measured facts, each
  with commit and timestamp.
- No demo yet: it will show results of `vnstratlab demo` on synthetic data once P1-T32 lands.
  Never publish real prices or real recommendations here.
- A push to this branch triggers `pages.yml` via `.github/workflows/trigger-pages.yml`.
