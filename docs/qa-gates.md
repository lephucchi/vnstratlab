# QA gates

Four gates protect production (`main` and PyPI). G1 is automated; G2 and G3 are run by
independent reviewer agents (or human reviewers); G4 is the owner. See
[workflow.md](workflow.md) for who does what.

---

## G1 — CI (automated, every PR)

Defined in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) and
[`benchmark.yml`](../.github/workflows/benchmark.yml).

| Check | Command | Fails when |
|---|---|---|
| Lint | `ruff check .` | Any finding |
| Format | `ruff format --check .` | Any unformatted file |
| Types | `mypy` (strict) | Any error |
| Tests | `pytest` on Windows, macOS, Linux × Python 3.11, 3.12, 3.13 | Any failure, or coverage < 80% |
| Guardrails | `pytest tests/test_guardrails.py` | Order-placement code, invalid packaged config |
| Secret scan | gitleaks | Any secret in the diff or history |
| PR title | Conventional Commits check | Title does not match |
| Smoke | `vnstratlab --help`, `vnstratlab doctor` (later `vnstratlab demo`) | Non-zero exit |
| Benchmarks | `pytest benchmarks --benchmark-only` | > 20% slower than `develop` baseline (warning comment; blocking from v0.2) |

## G2 — Code review (QA Reviewer, every PR)

The reviewer works in a fresh context, reads the task card and the diff, then posts a review
with one verdict: **approve**, **request changes** or **block**.

### Review tiers (owner decision, 2026-11-21)

The manager picks the tier when it delegates the review and states it in the review request.

| Tier | Applies to | Who | Scope |
|---|---|---|---|
| **light** | Docs only, ADR text, PO/site/tools, CI config, tests-only changes, dependency bumps | Manager (no reviewer agent) | G1 green; the **Safety and scope** items below; no behaviour change outside the card |
| **full** | Anything under `src/` that touches prices, corporate actions, execution, costs, risk, features, strategies, lab statistics, or point-in-time logic | QA Reviewer (Opus, fresh context) | The whole checklist |

When unsure, use **full**. A light-tier PR that turns out to change behaviour is re-tiered.

### Review rounds

- **Round 1** reads the card and the whole diff.
- **Round 2 and later are delta reviews.** The reviewer gets the previous findings and the
  last reviewed SHA, reads only `git diff <last-reviewed-sha>..HEAD`, and checks that each
  finding is fixed and that the fix does not break anything nearby. It does not re-review the
  whole PR.
- **At most 2 rounds.** Only **blocker** and **major** findings cause another round. **minor**
  findings and nits are listed in the review and moved to a follow-up issue by the manager;
  they do not hold the merge. If a major finding is still open after round 2, the owner decides
  (fix in a follow-up card or hold the PR).

### Tests during review

CI (G1) already runs the full suite on 3 OS × 3 Python. When G1 is green on the head SHA under
review, the reviewer does **not** re-run the full suite. It runs only the tests for the changed
modules plus its own probes (`pytest tests/test_<module>.py -q --no-cov`). It runs the full
suite only when CI has not finished or is red. Reviewer probes that expose a bug go into the
findings with exact numbers, so the worker can add them as tests.

### Checklist

**Correctness and finance**
- [ ] No lookahead: every value used at `t` was knowable at the close of `t` (fundamentals by
      `published_at`, news cut-off 14:45, features computed on truncated data in tests).
- [ ] Market rules (settlement offset, ceiling/floor, lots, odd lots, ticks, fees, tax,
      slippage) come from config and have hand-computed tests.
- [ ] Survivorship: universe read by date from `universe_membership`, not a fixed list.
- [ ] Corporate actions: raw prices never overwritten; adjustment tested; no double adjustment.
- [ ] Costs applied on both sides; tax on sells even at a loss.

**Research integrity**
- [ ] No frozen parameter changed (strategy params, gate thresholds, λ, η, risk limits).
- [ ] Any new (strategy, params) is registered as a trial before it is backtested.
- [ ] Seeds come from config; results are reproducible.
- [ ] No claims in docs or reports beyond what the statistics show.

**Safety and scope**
- [ ] **No order placement, broker connection, or trading credential** of any kind. → otherwise **block**.
- [ ] No secrets in code, logs, fixtures or output; secrets read only via `Settings`.
- [ ] No real market data committed; fixtures with made-up numbers are `synthetic_*`.
- [ ] No network in unit tests.
- [ ] Changes stay inside the card's file list.

**Code quality**
- [ ] Type hints, small functions, clear names; no dead code or duplication.
- [ ] Errors are explicit; failures in optional parts (news, notifications) never stop the loop.
- [ ] `--dry-run` works for anything that writes.
- [ ] Docs and `CHANGELOG.md` updated when behaviour or config changes.

### Verdicts

| Verdict | Meaning | Next |
|---|---|---|
| approve | No blocker or major finding open (minor items go to a follow-up issue) | Manager merges |
| request changes | Open blocker or major findings | Worker fixes on the same branch; G1 + G2 delta round (max 2 rounds) |
| block | Violates a ground rule (order placement, lookahead by design, secret leak, frozen-param edit) | PR closed or rescoped by the manager; owner informed |

---

## G3 — Release readiness (Reality Analyst, every `release/*`)

Output: `docs/reports/release-vX.Y.Z-readiness.md` from the template below, committed to the
release branch. Uses the owner's local data for real-data checks; nothing real is uploaded.

### G3.1 Benchmarks (investment)

Every lab result is compared with the benchmarks in config (`benchmarks:`): VN-Index and VN30
buy-and-hold, equal weight of the universe, the sector index, the risk-free rate, and the naive
selectors (equal weight of all strategies, "pick last winner"). Reported per horizon on
**executable** returns after costs: annual return, volatility, Sharpe, max drawdown, turnover,
hit rate, number of independent decisions.

### G3.2 Cross-engine check (engine correctness)

Run the same simple strategies (e.g. S02 breakout, S17 equal weight) on the same data in
**vectorbt** and **backtrader** with HOSE rules switched off in vnstratlab (ideal returns), then
with rules on.

| Check | Pass when |
|---|---|
| Rules off: vnstratlab vs. vectorbt/backtrader daily returns | Correlation ≥ 0.999 and annual return within 0.2 pp |
| Rules on: difference explained | Each difference traced to a named rule (lot, settlement, ceiling/floor, tick, cost) |

### G3.3 Realism stress tests (`vnstratlab stress`)

| Test | Setting (config `stress:`) | Pass when |
|---|---|---|
| Higher costs | fees + slippage ×2 and ×3 | Selected portfolio still beats equal weight at ×2, or the report flags the edge as cost-fragile |
| Delayed fills | fill at t+2 instead of t+1 | Sharpe drops by less than half |
| Small capital | 11,000,000 VND executable vs. ideal | Gap reported; recommendations remain buyable in lots/odd lots |
| Liquidity | order value vs. 20-day average traded value | No recommended order above 1% |
| Parameter noise | each param ±20% | No collapse (sign of excess return unchanged for the majority) |
| Regimes | configured up / down / sideways windows | Results reported per regime; no regime hidden |
| Paper vs. backtest | paper book vs. backtest forecast band | Paper inside the band, or deviation explained |

### G3.4 Product comparison

A short, honest table of where vnstratlab stands against comparable tools, updated each minor
release.

| Tool | Type | Compared on |
|---|---|---|
| vectorbt | Open-source vectorised backtester | Speed, flexibility, market-rule realism |
| backtrader | Open-source event-driven backtester | Order modelling, ease of use |
| QuantConnect Lean | Open-source engine + cloud | Breadth, data, Vietnamese market support |
| FinRL | Open-source RL for trading | Approach, overfitting controls |
| Vietnamese signal tools and broker screeners | Commercial | Coverage, transparency, statistical evidence |

Criteria: HOSE rule realism, overfitting controls, transparency of evidence, install effort,
offline use, cost. The report states gaps as clearly as strengths.

### G3.5 Release hygiene

- [ ] All `[VERIFY]` items listed with their current status; none newly relied upon unverified.
- [ ] TestPyPI rc installs in a clean venv on Windows and one of macOS/Linux; `vnstratlab demo` runs.
- [ ] Docs build; README matches behaviour; CHANGELOG complete.
- [ ] No open G2 "request changes" on the release branch.

### Readiness report template

```markdown
# Release vX.Y.Z readiness
- Date / analyst / commit:
- Verdict: Ready | Not ready
- Summary (3 lines):

## G3.1 Benchmarks          (table per horizon)
## G3.2 Cross-engine check  (table + explained differences)
## G3.3 Stress tests        (table: test, result, pass/fail, note)
## G3.4 Product comparison  (table)
## G3.5 Hygiene             (checklist)
## Risks and known limitations
## Recommendation to owner
```

---

## G4 — Owner approval

The owner reads the readiness report and approves the `release/* → main` PR. Approval means:
"I have read the evidence and accept the stated limitations." A **Not ready** verdict can only
be overridden by the owner in writing in the PR, with the reason.
