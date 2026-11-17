# Data source review: vnstock

Status: **reviewed** · owner decision: [ADR-006](../adr/ADR-006-synthetic-first.md) (synthetic data first; source decision deferred)
Card: P1-T03. Reviewed: 2026-11-17. Reviewer: research agent (no data endpoint was called,
no key was used, no package was imported).

This is a technical reading of public licences and package code, not legal advice. Where this
review summarises a licence, the vendor's own text is the binding version.

## 1. Summary

The `vnstock` that plan decision D6 assumed (a free library wrapping public VCI / TCBS / KBS / MSN
web endpoints) no longer exists in a usable form:

- PyPI quarantined `vnstock` and its required dependency `vnai` (search results report
  2026-09-24); both are absent from the PyPI JSON and simple APIs.
- The vendor moved distribution to its own index (`https://vnstocks.com/api/packages`) and
  released **generation 6**. Every release before generation 6 (`vnstock` 4.x / 5.x) "stopped
  authenticating" on **2026-11-10**.
- Generation 6 no longer scrapes public endpoints. It connects to **official broker Open APIs
  with the user's own brokerage account and keys** (BYOK): SSI FastConnect, TCBS iFlash, DNSE
  Lightspeed, FHSC, plus FMP and Binance.
- Generation 6 is two packages: `vnstock` 6.0.1 (proprietary, Rust core shipped as a binary,
  client-policy gate, optional telemetry) and `vnstock-oapi` 0.1.2 (source-available pure
  Python, no vendor phone-home, explicit permission to build free "extension packages").

The "free Community tier, no account needed, public endpoints" assumption behind D6 is no longer
true. Changing D6 is an owner decision (plan §2).

## 2. Current releases (verified)

| Package | Version | Date | Where | Licence |
|---|---|---|---|---|
| `vnstock` | 6.0.1 | not exposed (reproducible build timestamps); listed on the vendor index on 2026-11-17 | `https://vnstocks.com/api/packages/vnstock` | `LicenseRef-Vnstock-Proprietary`, classifier "Other/Proprietary"; no licence file in the wheel; governed by `https://vnstocks.com/onboard/giay-phep-su-dung` |
| `vnstock-oapi` | 0.1.2 | tag `v0.1.2` committed 2026-11-15 | vendor index, or `git+https://github.com/vnstock-hq/vnstock-open-api` | `vnstock-oapi-license-2026.11.1` (custom, not open source), full text in the wheel `dist-info/licenses/LICENSE` |
| `vnstock` (legacy) | 4.0.9 | GitHub release 2026-09-27 | `github.com/thinh-vu/vnstock` (repo now a landing page) | "Custom (Personal Use)"; LICENSE.md "license-2026.09"; **no longer works** |

Evidence:

- `https://pypi.org/pypi/vnstock/json`, `/pypi/vnai/json`, `/simple/vnstock/` return 404
  (checked 2026-11-17). Quarantine reason: not stated by PyPI. GitHub issue
  `thinh-vu/vnstock#237` (2026-10-06): maintainer says the project left PyPI "after a PyPI
  incident" and now distributes through vnstocks.com.
- `https://vnstocks.com/api/simple/vnstock` returns: "this library version has stopped
  authenticating since 10/11/2026", with a link to the generation 6 migration page.
- `github.com/thinh-vu/vnstock` README (commit 2026-11-07): versions older than generation 6
  "stop working on 10 November 2026"; generation 5+ is a Rust core with a Python wrapper,
  shipped as prebuilt packages; the repo grants no rights to the generation 5 or 6 code.
- Install command from `https://vnstocks.com/download`:
  `pip install -U --extra-index-url https://vnstocks.com/api/packages "vnstock==6.0.1" "vnstock-oapi==0.1.2"`.
- Wheels inspected (SHA-256 matched the index):
  `vnstock-6.0.1-cp310-abi3-win_amd64.whl` (7fd5bf75…2513),
  `vnstock_oapi-0.1.2-py3-none-any.whl` (e292eada…eaf8).

## 3. Licence terms

### 3.1 `vnstock` software licence (website, applies to `vnstock` 6 and Community edition)

Verified from `https://vnstocks.com/onboard/giay-phep-su-dung` (published 2026-11-10, effective
2026-11-30) and the earlier "license-2026.09" summary in the legacy `LICENSE.md`:

- Community edition: personal, study and research use only ("chỉ dành cho mục đích cá nhân,
  học tập và nghiên cứu"). Not an OSI licence.
- Paid tiers (Bronze / Silver / Golden / Diamond): single user except Diamond; scope counted by
  users and registered devices; income-generating own work allowed inside that scope.
- Separate written agreement needed to redistribute the software or activation keys, or to run a
  product whose main value is giving third parties access to market data.
- Prohibited: reverse engineering, copying or redistributing source, forging device identity,
  circumventing limits.
- **Release lifetime**: by default 365 days for an official release and 30 days for a test
  release; after expiry data calls are refused until the user updates. Applies to the
  Community edition too. The vendor may remotely switch off a release, a source or a host.
- Attribution for published research is encouraged, not required.
- The vendor processes account, licence, device and technical-measurement data per its privacy
  policy.
- Not addressed: use inside other open-source projects, declaring `vnstock` as a dependency,
  scheduled use, datacenter IPs, governing law.

### 3.2 `vnstock-oapi` licence (in the wheel, effective 2026-11-01)

Verified from `vnstock_oapi-0.1.2.dist-info/licenses/LICENSE` (Vietnamese text prevails):

- §1 grants each individual: read, install, run and modify for personal, educational or research
  use. Rights are per individual; an organisation paying does not extend them.
- **§1.1 Extension packages.** You may publish and share, free of charge, your own software that
  uses `vnstock-oapi` through its public API (`vnstock_oapi`, `vnstock_oapi.ext`), **including
  declaring it as a dependency**, without separate permission, if:
  1. you do not bundle or redistribute `vnstock-oapi` code; users install it themselves from the
     original repo or the Vnstock index;
  2. you do not charge for the extension or for the right to use it;
  3. each user connects with their own account and keys; no intermediary service, and no
     providing retrieved data to others;
  4. you do not use it to send trading orders or read users' account information;
  5. you do not modify, disable or bypass its controls (host and method allowlist, source
     registration checks, key redaction);
  6. you state that you use `vnstock-oapi`, link to the original repo and to the licence, do not
     imply Vnstock endorsement, and do not name `vnstock-oapi` as the producer of the data.
- §2: commercial or revenue-generating use, or anything outside §1.1, needs written permission.
- §3: no rights to third-party data; the user must follow each source's terms.
- §6: termination after an uncured breach (14 days' notice).

### 3.3 Upstream data terms (as summarised inside `vnstock_oapi/spec/sources/*/terms.toml`)

Every domestic source is a broker API that limits data to the account holder's own purpose and
forbids passing it to third parties:

| Source | Credentials (env var names) | Notes from the vendor's terms summary | Client rate cap in code |
|---|---|---|---|
| SSI FastConnect | `SSI_API_KEY`, `SSI_API_SECRET` (key/secret, token auto-refresh) | data for the customer's own purpose; no third parties; SSI may stop service at will; suspended after 90 days without connection; 1-year term, renewed online | 10 req/s |
| TCBS iFlash | `TCBS_API_KEY` + **manual Smart OTP** to open a session | own account only; no third parties even for processed data; TCBS may inspect the client system | 2 req/s |
| FHSC | `FHSC_API_KEY` (key rotates every 30 days) | website content is for information; no copying, redistribution or derived products without consent | 0.6 req/s |
| DNSE Lightspeed | `DNSE_API_KEY`, `DNSE_API_SECRET` | trading API; respect DNSE rate limits | n/a |
| FMP | `FMP_API_KEY` | Personal plan: non-commercial, no display to others, delete data on termination | 2 req/s |

SSI's own page (`https://developers.ssi.com.vn/term-condition`) confirms: own securities trading
purpose only, no sharing with third parties, keep secrets private, suspension after 90 days of
no activity, SSI may stop the service without notice. It says nothing about fees, rate limits,
storage, automated access or IP restrictions.

## 4. Package behaviour (verified from installed code, not imported)

Installed with `pip install --no-deps --no-index` from the downloaded wheels into a throwaway venv
(`…/scratchpad/vnstock-probe/venv`). Nothing was imported or executed.

### 4.1 `vnstock-oapi` 0.1.2 (pure Python)

- Package docstring (`vnstock_oapi/__init__.py`): "Importing this package sends nothing, reads
  no key and writes no file." No vnstocks.com URL appears in any `.py` file; network goes only to
  the source `hosts` allowlist over HTTPS, GET only, no redirects
  (`core/registry.py`, `core/transport.py`).
- Entry points (`vnstock_oapi/__init__.py`):
  `source(name: str, profile: str = "default") -> Source`, `sources() -> list[str]`,
  `status(profile="default") -> list[dict]` (no network), `terms(name) -> Terms`.
- Daily OHLC (`vnstock_oapi/core/source.py:485`):
  `Source.ohlc(self, symbol: str, *, start: str|date|datetime|None = None, end=None,
  interval: str = "1D", limit: int|None = None, asset: str = "equity") -> Envelopes`.
  Returns the source body verbatim in `Envelope`s with query context and SHA-256 (fits our
  "raw kept" rule).
- Symbols: `Source.symbols(*args, **filters) -> Envelopes` (`core/source.py:563`);
  calendar: `Source.calendar()`.
- SSI extras (`vnstock_oapi/sources/ssi.py:378`): `summary`, `index_summary`, `index_flows`,
  `index_list`, `index_members(index)` (data-securitiesByBoard, current constituents only),
  `security`, `price_limits(start, end, date)` (reference / ceiling / floor per day,
  data-masterdata), `corporate_actions(symbol, start, end, language)` (5-day chunks),
  `foreign(symbol, start, end, limit)`.
- SSI OHLC request (`sources/ssi.py:175`): `GET /api/v3/data/ohlc` with `symbol, from, to,
  timeFrame, pageIndex, pageSize`. No adjustment parameter exists.
- Keys (`core/credentials.py`): read from environment → `.env` in the current directory →
  OS keyring (service `vnstock-oapi`). Names are `<SOURCE>[_<PROFILE>]_<FIELD>`, e.g.
  `SSI_API_KEY`. The README states keys are never accepted as function arguments. Sessions are
  stored in the keyring or, with `VNSTOCK_OAPI_SESSION_BACKEND=file`, under
  `VNSTOCK_OAPI_STATE_DIR`.
- Dependencies: `httpx`, `truststore`, `certifi`, `platformdirs`, `keyring`, `tzdata` (Windows).

### 4.2 `vnstock` 6.0.1 (proprietary, Rust core)

- `vnstock/__init__.py`: imports `account, compat, errors, provenance, sources, telemetry` and
  `vnstock._core` (binary `_core.pyd`); calls `sources._load_env()` (reads a `VNSTOCK_SOURCES`
  rules file). No network call is visible in the Python layer at import; the Rust core was not
  inspected (the licence forbids reverse engineering).
- Daily OHLCV (`vnstock/market.py:264`):
  `Market(source: str|None = None, *, profile: str = "default")`, then
  `Market("ssi").equity("FPT").ohlcv(start=None, end=None, interval="1D", limit=None,
  floating=2, *, source=None, count_back=None, length=None, compat=None,
  columns="standard", **legacy) -> pd.DataFrame`. Prices are in **thousands of VND**, indices in
  points. Fetching is delegated to `vnstock-oapi`.
- **Client-policy gate** (`vnstock/_policy.py`): before every request `_core.gate(source)` can
  refuse with `VNSTOCK_RELEASE_EXPIRED` / `VNSTOCK_RELEASE_DISABLED` or a `PolicyError` when the
  vendor switched off the release, a source or a host. This is the remote switch described in
  the licence.
- **Telemetry** (`vnstock/telemetry.py`, `_policy.py`): usage counting in the Rust core, sent only
  if the "signed client policy" allows it and the account consented on vnstocks.com; off with
  `DO_NOT_TRACK=1` or `VNSTOCK_TELEMETRY=0`, or `vnstock.telemetry.disable()`. Counts flushed at
  exit (`atexit.register(_core.usage_flush)`). Documented as never containing symbols, dates or
  values.
- Vendor account: `vnstock.account.login(api_key)` (vnstocks.com key, distinct from broker
  keys). Whether the Community edition works without login was not verified.
- No legacy-style public-endpoint sources remain; `vnstock.sources` routes only to
  `vnstock-oapi` sources.

### 4.3 Legacy `vnstock` 4.0.9 (for the record; it no longer works)

Read from the GitHub tag tarball, not installed (its `vnai` dependency is unavailable):
`Quote(source="kbs"|"vci"|"msn"|…, symbol).history(symbol=None, start, end, interval="1D")`
(`vnstock/api/quote.py:89`); `Listing.symbols_by_group(group="VN30")`; key via
`register_user()` / `VNSTOCK_API_KEY`; guest 20 req/min, community 60, sponsor 180–600. Import
ran `vnai.setup()` lazily, a version check against PyPI and vnstocks.com
(`core/utils/upgrade.py:239`), and earlier versions wrote AI-assistant instruction files on
import (removed in 4.0.9 per its own comment). It also shipped DNSE order placement code
(`vnstock/connector/dnse/trade.py: Trade.place_order`) loaded by `from . import connector` at
import. None of this is usable now.

## 5. Fit with vnstratlab rules

| Rule | `vnstock` 6 | `vnstock-oapi` 0.1.2 directly |
|---|---|---|
| Recommend-only | read-only market calls | licence §1.1 forbids orders; README says read-only, no account data. Our guardrail bans the string `dnse` in `src/`, so the adapter must not name that source |
| No redistribution | user-local | user-local; licence and upstream terms both forbid passing data on |
| Optional install extra in an Apache-2.0 package | not covered by the licence; Community is personal/research only | explicitly allowed as a free extension package (§1.1), with attribution |
| Install path | vendor index only | vendor index or git tag; **neither is on PyPI** |
| Phone-home / remote switch | yes: policy gate, release lifetime, optional telemetry | none found in code |
| Secrets via `vnstratlab.settings.Settings` | broker keys go through `vnstock-oapi` | keys read by `vnstock-oapi` itself from `SSI_API_KEY` etc.; passing keys as arguments is not supported and bypassing key handling is forbidden (§1.1 item 5) |
| Raw prices (P1-T06) | not stated | body verbatim; adjustment state of SSI `data-ohlc` not documented in code |
| Nightly unattended loop | subject to release expiry | SSI: yes (key/secret, token refresh). TCBS: no (manual Smart OTP). FHSC: key rotates every 30 days |
| Datacenter IPs | unknown | unknown; SSI terms silent |

## 6. Recommendation to owner

1. **Do not adopt `vnstock` 6 as a dependency.** Its Community licence is personal / research
   only, it does not cover use inside another published project, and it carries a remote kill
   switch and release expiry that can stop the nightly loop without notice.
2. **If a Vnstock-family package is used at all, use `vnstock-oapi` directly**, as an optional
   adapter under its §1.1 extension-package terms:
   - do not list it in `pyproject.toml` extras that PyPI must resolve (it is not on PyPI; a
     direct URL dependency is rejected by PyPI). Document a manual install pinned to a tag or a
     hash instead, e.g.
     `pip install "vnstock-oapi @ git+https://github.com/vnstock-hq/vnstock-open-api@v0.1.2"`;
     avoid bare `--extra-index-url` (dependency-confusion risk while the name is unclaimed on
     PyPI);
   - import it lazily inside `VnstockSource`; the core install must work without it;
   - add the attribution and licence link required by §1.1 to `docs/data-sources.md` and the
     adapter docstring; do not imply endorsement;
   - support SSI only at first; never reference DNSE (guardrail) and skip TCBS (manual OTP).
3. **Revisit D6 (owner decision).** BYOK means every user needs an SSI securities account and a
   FastConnect registration. This conflicts with plan policy 1 "free first, so anyone can run
   the lab". Options: (a) accept BYOK SSI as the Phase 1 source; (b) look for another free,
   licence-clean source for daily OHLCV and keep `vnstock-oapi` as an optional adapter; (c) build
   on public exchange or index publications where terms allow. The `DataSource` protocol keeps
   all three open.
4. **Settings exception.** Decide whether the adapter may let `vnstock-oapi` read `SSI_API_KEY` /
   `SSI_API_SECRET` itself (our `Settings` would only check presence and never read the value),
   or whether this breaks the "secrets only via `vnstratlab.settings.Settings`" rule. This needs
   an ADR.
5. **Keep P1-T06 blocked on raw-price proof.** Before computing `prices_adjusted`, confirm with
   synthetic-free evidence (a manual check by the owner on his own account) whether SSI
   `data-ohlc` is raw or adjusted, and compare with `price_limits` reference prices.
6. **Update `docs/data-sources.md`** candidates table: `vnstock` → "Generation 6 BYOK; legacy
   public-endpoint versions dead since 2026-11-10; see this review".

## 7. Open questions

1. Does SSI FastConnect Data require fees, a funded account, or a separate registration from the
   trading API? Is there a published rate limit and an IP allowlist / datacenter IP policy?
2. Is SSI `data-ohlc` raw or adjusted for corporate actions? How far back does daily history go?
3. Does SSI's "own securities trading purpose" clause cover running a personal research and
   backtest tool? (Interpretation for the owner, possibly with the broker.)
4. Does the `vnstock-oapi` §1.1 condition "you do not charge" interact with Apache-2.0's
   permission for others to sell vnstratlab? Our licence cannot restrict that; a NOTICE that the
   optional adapter is subject to the `vnstock-oapi` licence is probably needed.
5. Does `vnstock` 6 Community need a vnstocks.com login, and does the policy gate call the network
   on every request? (Only relevant if option 1 is reversed.)
6. Why were `vnstock` and `vnai` quarantined on PyPI? No official reason is published; community
   reports about telemetry in `vnai` are unverified.
7. `index_members` returns current constituents only. VN30 membership history still needs
   P1-T05 (HOSE announcements).

## 8. Sources

- PyPI JSON API: `https://pypi.org/pypi/vnstock/json`, `https://pypi.org/pypi/vnai/json`,
  `https://pypi.org/pypi/vnstock-oapi/json` (all 404 on 2026-11-17)
- `https://github.com/thinh-vu/vnstock` (README, tag v4.0.9, issue #237)
- `https://github.com/vnstock-hq/vnstock-open-api` (README, tag v0.1.2)
- `https://vnstocks.com/download`, `https://vnstocks.com/the-he-6`,
  `https://vnstocks.com/onboard-member/migration`, `https://vnstocks.com/onboard/giay-phep-su-dung`
- `https://vnstocks.com/api/simple/vnstock`, `https://vnstocks.com/api/packages/vnstock`,
  `https://vnstocks.com/api/packages/vnstock-oapi`
- `https://developers.ssi.com.vn/term-condition`
- Installed files: `vnstock_oapi/__init__.py`, `vnstock_oapi/core/source.py`,
  `vnstock_oapi/core/credentials.py`, `vnstock_oapi/sources/ssi.py`,
  `vnstock_oapi/spec/sources/*/terms.toml`, `vnstock_oapi-0.1.2.dist-info/licenses/LICENSE`,
  `vnstock/__init__.py`, `vnstock/market.py`, `vnstock/_policy.py`, `vnstock/telemetry.py`,
  `vnstock/account.py`, `vnstock-6.0.1.dist-info/METADATA`
