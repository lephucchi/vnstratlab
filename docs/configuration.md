# Configuration

vnstratlab separates **parameters** (YAML, safe to share) from **secrets** (environment only).

## 1. App home

All user files live in one directory:

| OS | Default |
|---|---|
| Windows | `%LOCALAPPDATA%\vnstratlab` |
| macOS | `~/Library/Application Support/vnstratlab` |
| Linux | `~/.local/share/vnstratlab` |

Override with `VNSTRATLAB_HOME`. `vnstratlab doctor` prints the active paths.

```
<home>/
├── config.yaml        # your overrides (written by `vnstratlab init`)
├── .env               # your secrets (optional; env vars also work)
├── data/              # market.duckdb, lab.duckdb, journal.sqlite, raw/
├── strategies/        # your strategy plug-ins
├── logs/
└── backups/
```

## 2. Parameters (YAML)

Packaged defaults: [`src/vnstratlab/config/`](../src/vnstratlab/config/)

| File | Contents |
|---|---|
| `defaults.yaml` | Books, costs, risk limits, lab gates and weights, benchmarks, stress settings, news, notifications |
| `markets/hose.yaml` | HOSE rules (settlement offset, price limit, lots, ticks, sessions, tax) and holidays per year |
| `universes/vn30_banks.yaml` | Default universe seed (13 VN30 banks + known exits) |

Your `<home>/config.yaml` overrides any key. Example:

```yaml
books:
  short: {capital_vnd: 20000000}
costs:
  brokerage_fee_pct: 0.0
benchmarks:
  risk_free: {annual_rate: 0.05}
```

### Merge rules

`load_config()` ([`config/loader.py`](../src/vnstratlab/config/loader.py)) deep-merges your
`config.yaml` over the packaged defaults:

- dicts merge recursively, so overriding one nested key leaves its siblings intact;
- **lists and scalars replace** the default (a list in your file is not appended);
- `market:` and `universe:` in your file are merged over the packaged
  `markets/<project.market>.yaml` and `universes/<project.universe>.yaml`; you can override market
  rules or supply `holidays` for a year (a `days` list replaces the packaged list for that year;
  an empty `days: []` removes all holidays of that year). Year keys may be quoted; they are
  normalised to integers, and non-integer or duplicate years are errors.

Validation is strict: unknown keys are errors, percentages must be in [0, 1), capital > 0,
`max_positions` >= 1, horizons are `short|medium|long`, and holidays must be weekdays inside their
year. All problems are reported together as `dotted.path: reason`; `vnstratlab doctor` prints
`config: INVALID` with these lines and exits 1, otherwise `config: OK` plus holiday coverage
for the current and next year (`partial` or `missing` is a warning, not an error).

### `[VERIFY]` values

Market rules in `hose.yaml` carry `status: VERIFY` or `status: confirmed`. VERIFY values come
from secondary sources. Confirm them with official sources and your broker, then set
`status: confirmed` and a `source` in your override. Release readiness (G3) lists every VERIFY
value still in use.

### Frozen parameters

Strategy parameters, gate thresholds (`lab.gate1`, `lab.gate2`, `mcs_alpha`), weight settings
(λ, η, caps) and risk limits are **frozen** for contributors: changes go through the owner.
As a user you may change them for your own runs; the lab records every parameter set as a new
trial and counts it in the Deflated Sharpe Ratio, so changing parameters raises the bar.

## 3. Secrets (environment)

Read by [`settings.py`](../src/vnstratlab/settings.py) from environment variables or a `.env`
file. Template: [`.env.example`](../.env.example).

| Variable | Used for | Needed |
|---|---|---|
| `VNSTRATLAB_HOME` | App home override | Optional |
| `VNSTRATLAB_LOG_LEVEL` | Logging | Optional |
| `VNSTRATLAB_DATA_API_KEY` | Market data provider, if it needs a key | Depends on source |
| `VNSTRATLAB_TELEGRAM_BOT_TOKEN` | Telegram report | Optional |
| `VNSTRATLAB_TELEGRAM_CHAT_ID` | Telegram report | Optional |
| `VNSTRATLAB_LLM_API_KEY` | News scoring (Phase 2) | Optional |
| `VNSTRATLAB_PO_USER`, `VNSTRATLAB_PO_PASSWORD` | PO dashboard login; the Pages build encrypts the dashboard data with them (`tools/encrypt_po.py`) | Pages build only |

Rules: never commit `.env` (it is git-ignored); secrets are held as `SecretStr`, never logged,
printed or sent to the dashboard; `vnstratlab doctor` shows only *set / not set*.

CI needs **no** secrets: tests use synthetic fixtures. PyPI publishing uses Trusted Publishing
(OIDC), not a token.
