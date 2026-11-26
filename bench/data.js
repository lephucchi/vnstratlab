window.BENCHMARK_DATA = {
  "lastUpdate": 1795689362352,
  "repoUrl": "https://github.com/lephucchi/vnstratlab",
  "entries": {
    "vnstratlab": [
      {
        "commit": {
          "author": {
            "email": "lephucchi@users.noreply.github.com",
            "name": "Le Phuc Chi",
            "username": "lephucchi"
          },
          "committer": {
            "email": "lephucchi@users.noreply.github.com",
            "name": "Le Phuc Chi",
            "username": "lephucchi"
          },
          "distinct": true,
          "id": "e045d983f5d63e1ae6a4b5cd66d216e819d1ea67",
          "message": "style(tools): ruff-clean build_status.py\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-17T16:50:23+07:00",
          "tree_id": "46673ad914d6c155c607b258ead811ae2d553ad2",
          "url": "https://github.com/lephucchi/vnstratlab/commit/e045d983f5d63e1ae6a4b5cd66d216e819d1ea67"
        },
        "date": 1794909111615,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 100.83712228819594,
            "unit": "iter/sec",
            "range": "stddev: 0.0002142698479808405",
            "extra": "mean: 9.916982727273453 msec\nrounds: 11"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "lephucchi@users.noreply.github.com",
            "name": "Le Phuc Chi",
            "username": "lephucchi"
          },
          "committer": {
            "email": "lephucchi@users.noreply.github.com",
            "name": "Le Phuc Chi",
            "username": "lephucchi"
          },
          "distinct": true,
          "id": "5de06e51ee784d011ce3c9302af1ce734fc052c5",
          "message": "feat(config): typed config loader and trading calendar (P1-T02)\n\n- load_config / load_config_with_info: packaged defaults + market + universe,\n  deep-merged user config.yaml, strict frozen pydantic models, ConfigError with\n  dotted.path messages; holiday year keys normalised to int\n- TradingCalendar (config holidays or observed sessions), decision_days for\n  short (weekly) and medium/long (monthly, ADR-005); truncated periods on\n  observed-session calendars yield no decision day\n- doctor reports config status, holiday coverage and user holiday overrides\n- HOSE holidays 2026 (complete, VERIFY) and 2027 (partial, provisional)\n\nG2: two review rounds, all findings fixed; final re-review skipped on owner\ninstruction to push to develop.\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-17T16:51:32+07:00",
          "tree_id": "a9c8120909b96b93695cad0cf78001fc242140e2",
          "url": "https://github.com/lephucchi/vnstratlab/commit/5de06e51ee784d011ce3c9302af1ce734fc052c5"
        },
        "date": 1794909175302,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 147.47414843406327,
            "unit": "iter/sec",
            "range": "stddev: 0.00012484866304584256",
            "extra": "mean: 6.780849461538725 msec\nrounds: 13"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "lephucchi@users.noreply.github.com",
            "name": "Le Phuc Chi",
            "username": "lephucchi"
          },
          "committer": {
            "email": "lephucchi@users.noreply.github.com",
            "name": "Le Phuc Chi",
            "username": "lephucchi"
          },
          "distinct": true,
          "id": "aa76fed0dee0b3e3c1cf6dd166a079840bb943b6",
          "message": "feat(config): typed config loader and trading calendar (P1-T02)\n\n- load_config / load_config_with_info: packaged defaults + market + universe,\n  deep-merged user config.yaml, strict frozen pydantic models, ConfigError with\n  dotted.path messages; holiday year keys normalised to int\n- TradingCalendar (config holidays or observed sessions), decision_days for\n  short (weekly) and medium/long (monthly, ADR-005); truncated periods on\n  observed-session calendars yield no decision day\n- doctor reports config status, holiday coverage and user holiday overrides\n- HOSE holidays 2026 (complete, VERIFY) and 2027 (partial, provisional)\n\nG2: two review rounds, all findings fixed; final re-review skipped on owner\ninstruction to push to develop.",
          "timestamp": "2026-11-17T16:51:32+07:00",
          "tree_id": "a9c8120909b96b93695cad0cf78001fc242140e2",
          "url": "https://github.com/lephucchi/vnstratlab/commit/aa76fed0dee0b3e3c1cf6dd166a079840bb943b6"
        },
        "date": 1794909616501,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 149.06099928494356,
            "unit": "iter/sec",
            "range": "stddev: 0.00012874895286751428",
            "extra": "mean: 6.708662928580062 msec\nrounds: 14"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "9f64e256754840c5a81ab503c3ae9143239b443d",
          "message": "feat(po)!: encrypted PO login; plain env var names (#1)\n\nPO dashboard data published only encrypted (AES-256-GCM, PBKDF2-SHA256 600k) by tools/build_status.py; env vars without prefix (APP_HOME, LOG_LEVEL, VNSTOCK_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, PO_USERNAME, PO_PASSWORD); LLM key removed; blank values unset; Pages deploy docs. G2 round 2 approve.",
          "timestamp": "2026-11-17T20:54:02+07:00",
          "tree_id": "793e0134e4a535c81b53bfb86cb91f57fbc8c530",
          "url": "https://github.com/lephucchi/vnstratlab/commit/9f64e256754840c5a81ab503c3ae9143239b443d"
        },
        "date": 1794923663438,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 105.42871629038517,
            "unit": "iter/sec",
            "range": "stddev: 0.0020788083482122855",
            "extra": "mean: 9.485081818180095 msec\nrounds: 11"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "aafea65817b31a11fe1d315b054b10d4178edb9e",
          "message": "docs(readme): website link, site preview and architecture diagram (#5)\n\nSame change as the docs PR into main, so develop stays in sync.\n\nCo-authored-by: Le Phuc Chi <lephucchi@users.noreply.github.com>",
          "timestamp": "2026-11-17T21:07:04+07:00",
          "tree_id": "21c068326c4efffb5a1e9d27ac8b82eba87309f8",
          "url": "https://github.com/lephucchi/vnstratlab/commit/aafea65817b31a11fe1d315b054b10d4178edb9e"
        },
        "date": 1794924446169,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 205.0282191158774,
            "unit": "iter/sec",
            "range": "stddev: 0.00006287081021327206",
            "extra": "mean: 4.8773773888891965 msec\nrounds: 18"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "8e79a362a26bba8f3dfbe32e58278ce33ad16fec",
          "message": "docs(readme): development workflow diagram (#10)\n\nTwin of the docs PR into main, keeps develop in sync.\n\nCo-authored-by: Le Phuc Chi <lephucchi@users.noreply.github.com>",
          "timestamp": "2026-11-17T21:29:53+07:00",
          "tree_id": "5fe2fe4a64e774b433e37be4f2086e4ed647c742",
          "url": "https://github.com/lephucchi/vnstratlab/commit/8e79a362a26bba8f3dfbe32e58278ce33ad16fec"
        },
        "date": 1794925815505,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 148.16762317510688,
            "unit": "iter/sec",
            "range": "stddev: 0.000216403986213601",
            "extra": "mean: 6.7491127857142175 msec\nrounds: 14"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "6f9351927aedbf124957e4c438a85700a91160c7",
          "message": "Merge pull request #11 from lephucchi/main\n\nchore: back-merge main into develop",
          "timestamp": "2026-11-17T21:46:09+07:00",
          "tree_id": "5fe2fe4a64e774b433e37be4f2086e4ed647c742",
          "url": "https://github.com/lephucchi/vnstratlab/commit/6f9351927aedbf124957e4c438a85700a91160c7"
        },
        "date": 1794926792377,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 148.31655414030925,
            "unit": "iter/sec",
            "range": "stddev: 0.0001700370459597214",
            "extra": "mean: 6.74233571428573 msec\nrounds: 14"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "be908208f707b0cc7f21cf0eced97b81b2f14fea",
          "message": "docs(adr): ADR-006 synthetic data first; vnstock review (#12)\n\n- D6 superseded: pre-v6 vnstock stopped working on 2026-11-10; v6 is proprietary and\n  rejected as a dependency; vnstock-oapi + SSI stays a deferred candidate\n- new card P1-T36 (DataSource protocol + synthetic market); P1-T11 depends on it;\n  real-data cards blocked on the owner's source decision\n- data-sources, plan, roadmap, .env.example, CHANGELOG, mkdocs nav updated\n\nCo-authored-by: Le Phuc Chi <lephucchi@users.noreply.github.com>",
          "timestamp": "2026-11-17T21:47:52+07:00",
          "tree_id": "739c85e613254e371c898a98e118235ab68b9fe5",
          "url": "https://github.com/lephucchi/vnstratlab/commit/be908208f707b0cc7f21cf0eced97b81b2f14fea"
        },
        "date": 1794926897130,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 100.2053334817058,
            "unit": "iter/sec",
            "range": "stddev: 0.0002274183976824281",
            "extra": "mean: 9.979508727273156 msec\nrounds: 11"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "0e776f3d502c9ead68fb6855650abf839ca88b56",
          "message": "docs(adr): ADR-007 Yahoo interim source, data pipeline, gap register (#13)\n\nOwner decision 2026-11-18. ADR-007, Yahoo source review, gap register (14 gaps), data-pipeline design, cards P1-T36..T38, M1.1 schedule.\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-18T11:04:51+07:00",
          "tree_id": "246d5b0e0f1ffae5bb2659a6bf225be7a542860a",
          "url": "https://github.com/lephucchi/vnstratlab/commit/0e776f3d502c9ead68fb6855650abf839ca88b56"
        },
        "date": 1794974711038,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 205.21465767845848,
            "unit": "iter/sec",
            "range": "stddev: 0.00012637853410002778",
            "extra": "mean: 4.872946266668994 msec\nrounds: 15"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "0666c7923b7eba7b4e1371d8c04588ffb665f6c5",
          "message": "feat(data): DataSource protocol, market store and synthetic market (P1-T36) (#15)\n\nDataSource protocol and registry; DuckDB market store with raw Parquet snapshots, revisions, one kind rule (synthetic vs real stores), atomic ingest with error run rows and run-id refusal; deterministic synthetic market (HOSE ticks/limits, corporate actions, suspensions); vnstratlab ingest with --dry-run; import-boundary test. G2 approved in round 3.\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-18T11:43:32+07:00",
          "tree_id": "d694f9729eb56b0204e8b2e6e247d446e7be60f3",
          "url": "https://github.com/lephucchi/vnstratlab/commit/0666c7923b7eba7b4e1371d8c04588ffb665f6c5"
        },
        "date": 1794977037742,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 141.19820514486963,
            "unit": "iter/sec",
            "range": "stddev: 0.00911812504572895",
            "extra": "mean: 7.082243000001297 msec\nrounds: 21"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "dbae0f66db950864eaa98387568b1a758f6dc9b7",
          "message": "feat(tools): gap register and card due dates in PO data (#16)\n\nG2 round 3 point (dead fallback) verified removed; CI green.\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-18T12:27:40+07:00",
          "tree_id": "5187117f911adb23b1d159e2963d957d53d0fcd6",
          "url": "https://github.com/lephucchi/vnstratlab/commit/dbae0f66db950864eaa98387568b1a758f6dc9b7"
        },
        "date": 1794979689770,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 115.9942839237701,
            "unit": "iter/sec",
            "range": "stddev: 0.012424594210522581",
            "extra": "mean: 8.621114473685504 msec\nrounds: 19"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "d604d5aa145baefd9715e6ee9e28f207a3780dc3",
          "message": "feat(data): YahooSource adapter, interim Phase 1 price source (P1-T37) (#19)\n\nOwner asked to merge without further review (2026-11-18). CI green.\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-18T13:04:48+07:00",
          "tree_id": "a541a6a22af12f4a28c2e3b409d6dc165f93e41c",
          "url": "https://github.com/lephucchi/vnstratlab/commit/d604d5aa145baefd9715e6ee9e28f207a3780dc3"
        },
        "date": 1794981930569,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 128.53913298312395,
            "unit": "iter/sec",
            "range": "stddev: 0.005650608501238898",
            "extra": "mean: 7.7797319523797555 msec\nrounds: 21"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "e7c53163af9f3b772fb54fdc134bd14e574edc11",
          "message": "feat(data): quality checks v0, gap register and data status (P1-T38) (#20)\n\nMerged on owner request without final G2 approval (2026-11-18); known follow-up: trailing synthetic suspension gap fails DQ on some days.\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-18T13:09:16+07:00",
          "tree_id": "c2bf649fa753f55574a4ffeb1187ca013b0981b6",
          "url": "https://github.com/lephucchi/vnstratlab/commit/e7c53163af9f3b772fb54fdc134bd14e574edc11"
        },
        "date": 1794982189737,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 121.00031443942741,
            "unit": "iter/sec",
            "range": "stddev: 0.00016746140356442292",
            "extra": "mean: 8.264441333337183 msec\nrounds: 12"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "27afb0e843a2ba532113522be439f059a79be6b4",
          "message": "docs(engine): HTML architecture diagrams and Phase 1 data constraints (#18)\n\nNine engine figures in docs/diagrams/engine-architecture.html, embedded in engine.md; Phase 1 data constraints (P1-T06 reconstructs raw-like prices and limits from stock events, late actions applied once); GAP-01 wording; CLAUDE.md rule: no AI attribution watermarks. Merged on owner request.",
          "timestamp": "2026-11-18T13:16:42+07:00",
          "tree_id": "334038960c2e181502bbaa3122214b2819cd3716",
          "url": "https://github.com/lephucchi/vnstratlab/commit/27afb0e843a2ba532113522be439f059a79be6b4"
        },
        "date": 1794982632637,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 102.00991669009014,
            "unit": "iter/sec",
            "range": "stddev: 0.00025017188435831134",
            "extra": "mean: 9.802968499994336 msec\nrounds: 10"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "c3d67b7c5c84e7bf7481596b52ab5b315dd63323",
          "message": "docs(adr): accept ADR-003 in part; card P1-T11 simulator core (#21)\n\nOwner decision 2026-11-18: ADR-003 proposals 1, 3, 4, 6-12 accepted, 2 and 5 deferred; cash_proceeds_offset = 3 and stock_dividend_listing_lag_sessions = 20 confirmed. Card P1-T11 with settled engine details. Merged on owner request.",
          "timestamp": "2026-11-18T13:20:33+07:00",
          "tree_id": "8a06edb4db1391590df533ff82c3bbf4db2da106",
          "url": "https://github.com/lephucchi/vnstratlab/commit/c3d67b7c5c84e7bf7481596b52ab5b315dd63323"
        },
        "date": 1794982860522,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 170.6101132812954,
            "unit": "iter/sec",
            "range": "stddev: 0.0001853204092245707",
            "extra": "mean: 5.86131724999935 msec\nrounds: 12"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "f8a2986547aa61d07bd0fea77777186858aee38f",
          "message": "feat(engine): simulator core with HOSE rules (P1-T11) (#23)\n\nPure event loop and SimExecutor: settlement T+3, price limits, round and odd lots, ticks, fees, sales tax, slippage, cash ledger with proceeds offset 3, cash and stock dividends, order lifecycle with order_events, ideal and executable modes, turnover. Merged on owner request; G2 follow-ups open (late-action entitlement, turnover denominator, pre-ex pending rescale).",
          "timestamp": "2026-11-18T13:25:43+07:00",
          "tree_id": "c45ea45e8873b6b5c58f2c69863d54eaf05182c3",
          "url": "https://github.com/lephucchi/vnstratlab/commit/f8a2986547aa61d07bd0fea77777186858aee38f"
        },
        "date": 1794983177414,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 95.84388220053283,
            "unit": "iter/sec",
            "range": "stddev: 0.0002764022411666604",
            "extra": "mean: 10.433634125000424 msec\nrounds: 8"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "039bc059f327972e91818cd641ff09c45d40e6f5",
          "message": "fix(engine): P1-T11b review findings, declared suspensions, CLI import time (#25)\n\nCloses #24. Late-action entitlement from ex-date holdings (bonus credit list), turnover over previous-close equity, only pre-ex pending orders rescale on stock events, synthetic declared suspensions downgrade trailing DQ gaps to warnings, lazy heavy imports in the CLI. G2 approve (round 3).",
          "timestamp": "2026-11-19T19:44:26+07:00",
          "tree_id": "9464af6cd59e7686ecdac6725cfeeee2dc6cdbf8",
          "url": "https://github.com/lephucchi/vnstratlab/commit/039bc059f327972e91818cd641ff09c45d40e6f5"
        },
        "date": 1795092308642,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 138.68815704379662,
            "unit": "iter/sec",
            "range": "stddev: 0.00011570698250826308",
            "extra": "mean: 7.2104210000007996 msec\nrounds: 16"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "51a62401e224db2995a5faa2a5f368110d7c60e7",
          "message": "feat(data): corporate actions, adjusted and execution prices (P1-T06) (#29)\n\nCloses #27. prices_adjusted for scale-invariant signals, prices_exec (exec_reconstructed) for the engine, exec_exclusions; rebuild recomputes error-level row checks over the full history; scale-discontinuity check (wrong-but-consistent ratios undetected, GAP-06); freshness flag; data rebuild --dry-run; corporate_actions pay_date/listing_date. G2 approve (round 2).",
          "timestamp": "2026-11-19T20:31:29+07:00",
          "tree_id": "6143cdb978e5e7a8745b7017dbc0117df83fdfad",
          "url": "https://github.com/lephucchi/vnstratlab/commit/51a62401e224db2995a5faa2a5f368110d7c60e7"
        },
        "date": 1795095123762,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 76.77494101660827,
            "unit": "iter/sec",
            "range": "stddev: 0.00024476164038845485",
            "extra": "mean: 13.025083272726658 msec\nrounds: 11"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "ee775d0f5e9b56c8d3c501a4261cd945b55ca410",
          "message": "feat(risk): risk layer, stops, circuit breaker (P1-T12) (#28)\n\nCloses #26. Pure risk layer (ATR sizing at 1 % equity risk, max weight per ticker, max positions, vol scaling, circuit breaker with alert flag), lot-based ATR stops with stop_pending_settlement, cooldown from stop exit (risk.stop_cooldown_sessions, null = one decision period, owner to confirm), ex-date factor in ATR, rebalance threshold. Opt-in: without a risk layer the simulator is unchanged. G2 approve (round 2).",
          "timestamp": "2026-11-19T20:38:49+07:00",
          "tree_id": "dfaf3e4fd3b92e06e4e65c90aa9646bb68f9ef81",
          "url": "https://github.com/lephucchi/vnstratlab/commit/ee775d0f5e9b56c8d3c501a4261cd945b55ca410"
        },
        "date": 1795095564273,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 73.04210971850193,
            "unit": "iter/sec",
            "range": "stddev: 0.000248236329407642",
            "extra": "mean: 13.690732699998875 msec\nrounds: 10"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "1e4da7f3d823f4e908628716ce44189e34173e81",
          "message": "fix(risk): ATR for late actions and exact lot tracking (P1-T12b) (#32)\n\nCloses #30. ATR series recomputed on late add_actions (no rewrite of used values), exact lot/ledger sync, lots for bonus shares without entry, ex-date-open lot ATR in post-event basis, residual lots keep their ATR read session, relative sync tolerance. G2 approve (round 1); round-2 fixes merged by owner decision without re-review.",
          "timestamp": "2026-11-19T21:11:15+07:00",
          "tree_id": "53cd2ef29c361afaee2237ca55a0fd42a27a3c3d",
          "url": "https://github.com/lephucchi/vnstratlab/commit/1e4da7f3d823f4e908628716ce44189e34173e81"
        },
        "date": 1795097516781,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 133.17106660817092,
            "unit": "iter/sec",
            "range": "stddev: 0.00013481050564384252",
            "extra": "mean: 7.509138625001022 msec\nrounds: 16"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "a523123015fa71049f25ed9acb4150dca5f235b0",
          "message": "fix(data): Yahoo event-scale repair and split-adjusted dividends (P1-T06b) (#33)\n\nCloses #31. Owner override: merged with G2 request changes open, tracked in #34. Outlier rows / suspect step events / pre-HOSE history classification, split-adjusted Yahoo dividends, owner decisions 2026-11-19, next-session handoff (docs/reports/next-session.md), P1-T10 card.",
          "timestamp": "2026-11-19T21:19:37+07:00",
          "tree_id": "1fa87ceac71c0cbcf73b4d281d26b9df3a465364",
          "url": "https://github.com/lephucchi/vnstratlab/commit/a523123015fa71049f25ed9acb4150dca5f235b0"
        },
        "date": 1795098011897,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 115.16604454264464,
            "unit": "iter/sec",
            "range": "stddev: 0.00017145282877721268",
            "extra": "mean: 8.683114923077103 msec\nrounds: 13"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "cf89688723ed408aa9007cc36311af7104e8175c",
          "message": "docs(workflow): tiered G2 review, delta rounds, no duplicate test runs (#35)\n\nOwner decision 2026-11-21: light tier (manager) for docs/tools/CI PRs, full tier (QA Reviewer) for finance and engine logic; round 2+ is a delta review, max 2 rounds, minor findings go to a follow-up issue; reviewer and manager rely on green CI on the head SHA instead of re-running the full suite.",
          "timestamp": "2026-11-21T08:57:21+07:00",
          "tree_id": "b8ee9324e1d7acd4e662d376168cfc7fe26d96cf",
          "url": "https://github.com/lephucchi/vnstratlab/commit/cf89688723ed408aa9007cc36311af7104e8175c"
        },
        "date": 1795226277283,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 78.58345127817508,
            "unit": "iter/sec",
            "range": "stddev: 0.00019234669818567917",
            "extra": "mean: 12.725325545452714 msec\nrounds: 11"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "0c18200254ebe28275ae54a8c1b64808c4714943",
          "message": "fix(data): P1-T06c adjust review findings (#36)\n\nCloses #34. Persistent step vs outlier classification (nearer-old-level + continuity break; AC1(c) dropped, see #37), pre-HOSE cut at the last out-of-band session followed by >= 60 in-band sessions (bad rows neutral), cash ex-dates exempt from the band test, split-adjusted dividend end-to-end test, exec_exclusions.rows, prices_adjusted.signal_ok. Minor follow-ups in #37.",
          "timestamp": "2026-11-21T09:05:09+07:00",
          "tree_id": "f1bdf47a68e52c53b3fc15914989b3a998619546",
          "url": "https://github.com/lephucchi/vnstratlab/commit/0c18200254ebe28275ae54a8c1b64808c4714943"
        },
        "date": 1795226747252,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 134.76266847342112,
            "unit": "iter/sec",
            "range": "stddev: 0.00017625375027294484",
            "extra": "mean: 7.420452647071376 msec\nrounds: 17"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "8b85a3fdc4b1b281abb94fbfa8562c0779bac9fc",
          "message": "docs(qa): real-data dry run before merging data-cleaning PRs (#38)\n\nManager runs data rebuild --dry-run with branch code on the local store before merging data-cleaning PRs; progress log for #35 and #36.",
          "timestamp": "2026-11-21T09:13:37+07:00",
          "tree_id": "280ef0a812eac3db5dadbdfac11e8185d959c230",
          "url": "https://github.com/lephucchi/vnstratlab/commit/8b85a3fdc4b1b281abb94fbfa8562c0779bac9fc"
        },
        "date": 1795227256654,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 72.9131955428528,
            "unit": "iter/sec",
            "range": "stddev: 0.00021143946974489005",
            "extra": "mean: 13.714938599999726 msec\nrounds: 10"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "7803c9a4134687d01fc65c735d42ed24d455bb6b",
          "message": "fix(data): P1-T06d density guard for the non-HOSE cut (#39)\n\nNon-HOSE cut only at clustered out-of-band sessions (>= 10 in the trailing 250 good sessions; owner-approved). Real-data dry run: prices_exec 6,223 -> 24,483; non-HOSE cut on SHB only. Minor follow-ups in #37.",
          "timestamp": "2026-11-21T09:17:58+07:00",
          "tree_id": "00017018b009ff742da728faae18f401e4400f35",
          "url": "https://github.com/lephucchi/vnstratlab/commit/7803c9a4134687d01fc65c735d42ed24d455bb6b"
        },
        "date": 1795227506884,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 166.56115884757077,
            "unit": "iter/sec",
            "range": "stddev: 0.0002845678861419515",
            "extra": "mean: 6.003800687500949 msec\nrounds: 16"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "4780535636c8823741e369252239e30122bd37c0",
          "message": "fix(data): P1-T06e adjust follow-ups (#40)\n\nCloses #37. Spike counted once and run reset only on clustered sessions in the non-HOSE cut; near-tolerance stock events handled at row/step level (LPB, SHB, VIB kept); duplicate_session exclusion (GAP-07); adjusted_is_rebuilt + ADJ_METHOD ratio-v2; owner-approved wording. Real-data dry run: prices_exec 24,483 -> 27,541, no excluded tickers.",
          "timestamp": "2026-11-21T09:33:43+07:00",
          "tree_id": "b75ba0a726eb64aa52bd0e94a8eb05dbc7dada56",
          "url": "https://github.com/lephucchi/vnstratlab/commit/4780535636c8823741e369252239e30122bd37c0"
        },
        "date": 1795228468354,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 76.54145301395344,
            "unit": "iter/sec",
            "range": "stddev: 0.0003763958531205202",
            "extra": "mean: 13.06481600000069 msec\nrounds: 10"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "81ca997bd8b07cb616a0cbb1cbb1b216b44aab49",
          "message": "docs(data): GAP-07 Tuesday duplicate pattern; progress log (#42)\n\nGAP-07 medium: Yahoo repeats Monday's bar on Tuesday since 2025-05 (442 rows). Progress log for #38-#40.",
          "timestamp": "2026-11-21T09:53:37+07:00",
          "tree_id": "ddf7cbf6db803228dfdc36f687def102917d3ab1",
          "url": "https://github.com/lephucchi/vnstratlab/commit/81ca997bd8b07cb616a0cbb1cbb1b216b44aab49"
        },
        "date": 1795229654920,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 77.4021348112535,
            "unit": "iter/sec",
            "range": "stddev: 0.0002743983647079421",
            "extra": "mean: 12.91954029999971 msec\nrounds: 10"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "bb6a3fe7e3647324c21d19b83bd3e06f17d1651c",
          "message": "feat(features): feature store v1 (P1-T10) (#43)\n\nPure point-in-time features (trend/momentum, relative strength, mean reversion, volatility, volume/liquidity, equal-weight market context); signal_ok=false treated as missing; refuses non-rebuilt stores; feature_version from code, windows and adj_version; features_daily + features build [--dry-run]; load_features with asof guard. Membership by date follow-up: #44.",
          "timestamp": "2026-11-21T10:10:07+07:00",
          "tree_id": "4249078679e311fab77dcf375fdda6ab5d9dd45e",
          "url": "https://github.com/lephucchi/vnstratlab/commit/bb6a3fe7e3647324c21d19b83bd3e06f17d1651c"
        },
        "date": 1795230645645,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_features.py::test_bench_compute_features_15_tickers_3000_sessions",
            "value": 3.097949709966878,
            "unit": "iter/sec",
            "range": "stddev: 0.0153097691924778",
            "extra": "mean: 322.7941359999325 msec\nrounds: 3"
          },
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 126.21989955179838,
            "unit": "iter/sec",
            "range": "stddev: 0.0001616187235462767",
            "extra": "mean: 7.92268099999254 msec\nrounds: 14"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "1ab258b2a2ecfc66d55adf406d110a2db12baf2c",
          "message": "feat(strategies): strategy base, registry and trial log (P1-T13) (#45)\n\nStrategy protocol and BaseStrategy (asof guard, weight validation; registry requires BaseStrategy), config-driven registry, append-only trial_registry in lab.duckdb with trial_id = hash(strategy, params, horizon, code hash, feature_version, ENGINE_VERSION), monotonic trial count, lab trials / lab register [--dry-run].",
          "timestamp": "2026-11-21T10:50:13+07:00",
          "tree_id": "0c23b9a501c6db56d17a0fe656ec8e0565c63fc4",
          "url": "https://github.com/lephucchi/vnstratlab/commit/1ab258b2a2ecfc66d55adf406d110a2db12baf2c"
        },
        "date": 1795233050406,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_features.py::test_bench_compute_features_15_tickers_3000_sessions",
            "value": 2.3825444273932908,
            "unit": "iter/sec",
            "range": "stddev: 0.014488820582857121",
            "extra": "mean: 419.7193506666679 msec\nrounds: 3"
          },
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 87.12634993565261,
            "unit": "iter/sec",
            "range": "stddev: 0.0002300468215216067",
            "extra": "mean: 11.477584000001752 msec\nrounds: 11"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "da77987bf717be514f9d5c1571ebbff54c4df14f",
          "message": "feat(strategies): S00 composite score and S17 equal weight (P1-T14) (#47)\n\nS00 v1 (4 blocks, valuation omitted per owner 2026-11-21; weight sets equal / trend_heavy, top_n 3, trigger breakout or oversold-in-uptrend) and S17 equal weight (all horizons); both in the packaged config (5 trials).",
          "timestamp": "2026-11-21T11:48:48+07:00",
          "tree_id": "3ff7189be721b733bfb04fec04acee22eefc0ea4",
          "url": "https://github.com/lephucchi/vnstratlab/commit/da77987bf717be514f9d5c1571ebbff54c4df14f"
        },
        "date": 1795236566333,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_features.py::test_bench_compute_features_15_tickers_3000_sessions",
            "value": 1.9782118389684047,
            "unit": "iter/sec",
            "range": "stddev: 0.01187851480179798",
            "extra": "mean: 505.50703433332933 msec\nrounds: 3"
          },
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 66.83068054268556,
            "unit": "iter/sec",
            "range": "stddev: 0.00021384041809738877",
            "extra": "mean: 14.963187444444593 msec\nrounds: 9"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "421469d45f0a1f80269baee501d06bc5e308cea7",
          "message": "docs(progress): P1-T10, P1-T13, P1-T14 (#48)\n\nProgress log for #42, #43, #45, #47.",
          "timestamp": "2026-11-21T12:02:56+07:00",
          "tree_id": "e80125ffc26b5e969120679dd48f7e4b48387c5a",
          "url": "https://github.com/lephucchi/vnstratlab/commit/421469d45f0a1f80269baee501d06bc5e308cea7"
        },
        "date": 1795237406486,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_features.py::test_bench_compute_features_15_tickers_3000_sessions",
            "value": 2.7276142642529955,
            "unit": "iter/sec",
            "range": "stddev: 0.01681807050846805",
            "extra": "mean: 366.6207546666674 msec\nrounds: 3"
          },
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 101.58524205593143,
            "unit": "iter/sec",
            "range": "stddev: 0.0002552569055556451",
            "extra": "mean: 9.843949571429025 msec\nrounds: 7"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "70fefd785a42a296143b50580c9ba17d1e3ddf94",
          "message": "feat(strategies): S01 weekly reversal, S02 breakout, S03 oversold in uptrend (P1-T15) (#49)\n\nS01 (n 2/3), S02 (close_20d_break + volume > 1.5x, max 3; new feature close_20d_break, features-v2), S03 (RSI2<10 / RSI14<30 above MA50, max 3). Packaged config now 10 trials.",
          "timestamp": "2026-11-21T12:12:14+07:00",
          "tree_id": "ae10a1616bed9d7995b435b9b6fb70d7ea414df0",
          "url": "https://github.com/lephucchi/vnstratlab/commit/70fefd785a42a296143b50580c9ba17d1e3ddf94"
        },
        "date": 1795237963350,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_features.py::test_bench_compute_features_15_tickers_3000_sessions",
            "value": 3.1879541918186547,
            "unit": "iter/sec",
            "range": "stddev: 0.023305011465387864",
            "extra": "mean: 313.680793333333 msec\nrounds: 3"
          },
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 132.69973779303896,
            "unit": "iter/sec",
            "range": "stddev: 0.0006712282628244554",
            "extra": "mean: 7.535809916667802 msec\nrounds: 12"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "0263763c4b238fe43b8e150f81cc8f927a307418",
          "message": "feat(strategies): S04 long-only bank pairs, S05 residual mean reversion (P1-T16) (#50)\n\nS04 (top-5 correlated pairs over 250 sessions, laggard on |z| > 2, onset-based max_hold 10, zero-cross exit), S05 (OLS residual s-score over 60 sessions, n 2 below -1.5); feature ret_1d (features-v3); BaseStrategy.lookback_sessions. Packaged config 12 trials. Merged by owner request with CI green; G2 review still running at merge time.",
          "timestamp": "2026-11-21T12:42:34+07:00",
          "tree_id": "0f7ee96b8c12ef760ce3beafadadc86c2b73aca2",
          "url": "https://github.com/lephucchi/vnstratlab/commit/0263763c4b238fe43b8e150f81cc8f927a307418"
        },
        "date": 1795239796621,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_features.py::test_bench_compute_features_15_tickers_3000_sessions",
            "value": 3.107368927887352,
            "unit": "iter/sec",
            "range": "stddev: 0.012363707068588428",
            "extra": "mean: 321.8156656666717 msec\nrounds: 3"
          },
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 117.92242572275576,
            "unit": "iter/sec",
            "range": "stddev: 0.0001310362961745057",
            "extra": "mean: 8.480151200002222 msec\nrounds: 15"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "030de98e6deb705258b396cd55e5fab6afbd0703",
          "message": "docs: close out cards P1-T06b..P1-T16, roadmap, progress log (#51)\n\nCards marked done, roadmap status, progress log for #49 and #50.",
          "timestamp": "2026-11-21T12:48:17+07:00",
          "tree_id": "e5a008551611ddb7de62e1e98e8cf7ebcbbd2026",
          "url": "https://github.com/lephucchi/vnstratlab/commit/030de98e6deb705258b396cd55e5fab6afbd0703"
        },
        "date": 1795240143558,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_features.py::test_bench_compute_features_15_tickers_3000_sessions",
            "value": 2.278611623253335,
            "unit": "iter/sec",
            "range": "stddev: 0.01693467585800115",
            "extra": "mean: 438.863731666667 msec\nrounds: 3"
          },
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 87.15404104368241,
            "unit": "iter/sec",
            "range": "stddev: 0.0002585724845993718",
            "extra": "mean: 11.473937272728303 msec\nrounds: 11"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "4c3ffdc29c70c04e3a7f1c5d03faa308f4470324",
          "message": "fix(strategies): S04 no re-entry across missing sessions (P1-T16b) (#52)\n\nopen_side compares with the last observed z across sessions without a spread; only the window start counts as no z. G2 round 2 (delta) approve.",
          "timestamp": "2026-11-21T12:50:22+07:00",
          "tree_id": "3812b4129f36ed7c145b4020dae19c0e5c063cf1",
          "url": "https://github.com/lephucchi/vnstratlab/commit/4c3ffdc29c70c04e3a7f1c5d03faa308f4470324"
        },
        "date": 1795240260485,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_features.py::test_bench_compute_features_15_tickers_3000_sessions",
            "value": 3.072174220296495,
            "unit": "iter/sec",
            "range": "stddev: 0.005772539758760874",
            "extra": "mean: 325.502373333336 msec\nrounds: 3"
          },
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 117.34896779218941,
            "unit": "iter/sec",
            "range": "stddev: 0.00017426241332582474",
            "extra": "mean: 8.521591785714529 msec\nrounds: 14"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "4b2fa32efe878aa24cd96b0320be241c9510e6fa",
          "message": "docs: close P1-T16b, progress log (#53)\n\nCard P1-T16b done; progress log for #52.",
          "timestamp": "2026-11-21T12:56:14+07:00",
          "tree_id": "3f29df426097cbf00ca5aaebc70fd2f5afea22ba",
          "url": "https://github.com/lephucchi/vnstratlab/commit/4b2fa32efe878aa24cd96b0320be241c9510e6fa"
        },
        "date": 1795240606719,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_features.py::test_bench_compute_features_15_tickers_3000_sessions",
            "value": 1.9669268811054146,
            "unit": "iter/sec",
            "range": "stddev: 0.023138780389366877",
            "extra": "mean: 508.40730766666786 msec\nrounds: 3"
          },
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 67.91362511534068,
            "unit": "iter/sec",
            "range": "stddev: 0.00018628731950404934",
            "extra": "mean: 14.724585800001933 msec\nrounds: 10"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "785fb9036a6c4e660f465d2aa959e4838ed3ab1c",
          "message": "feat(strategies): S08 momentum and S09 medium-term reversal (P1-T17) (#54)\n\nS08 (6m/12m skip-1m momentum, top 4), S09 (6m reversal, bottom 4); feature ret_6m_skip1m (features-v4); S13 blocked on P1-T07. Packaged config 15 trials.",
          "timestamp": "2026-11-21T13:08:45+07:00",
          "tree_id": "0bd0ac94c5294a9a24d6a5340817466c4d07417b",
          "url": "https://github.com/lephucchi/vnstratlab/commit/785fb9036a6c4e660f465d2aa959e4838ed3ab1c"
        },
        "date": 1795241359068,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_features.py::test_bench_compute_features_15_tickers_3000_sessions",
            "value": 1.887290375819157,
            "unit": "iter/sec",
            "range": "stddev: 0.01479668989622117",
            "extra": "mean: 529.8601703333337 msec\nrounds: 3"
          },
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 66.25572705302127,
            "unit": "iter/sec",
            "range": "stddev: 0.00021796577916218627",
            "extra": "mean: 15.093034888889653 msec\nrounds: 9"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "bd08b5979afdb52ffb85fb606fcbe40ff2502a7f",
          "message": "docs: close P1-T17, progress log, roadmap (#55)\n\nCard P1-T17 done; progress log for #54.",
          "timestamp": "2026-11-21T13:14:02+07:00",
          "tree_id": "ef6f805d2463190bc78da23c8452dc33529af13f",
          "url": "https://github.com/lephucchi/vnstratlab/commit/bd08b5979afdb52ffb85fb606fcbe40ff2502a7f"
        },
        "date": 1795241675574,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_features.py::test_bench_compute_features_15_tickers_3000_sessions",
            "value": 1.9852086904678372,
            "unit": "iter/sec",
            "range": "stddev: 0.011089049202296329",
            "extra": "mean: 503.7253789999975 msec\nrounds: 3"
          },
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 66.97638466926779,
            "unit": "iter/sec",
            "range": "stddev: 0.00017602419553517518",
            "extra": "mean: 14.93063570000146 msec\nrounds: 10"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "a94e92b2574cd1924445f505869a9e21c80fd75b",
          "message": "feat(strategies): S14 low volatility, S15 sector trend, S18 HRP (P1-T19) (#57)\n\nS14 low volatility (std_60d, bottom 4), S15 sector trend filter (group_ret_12m / group_ret_6m, 1/N or cash), S18 Hierarchical Risk Parity (250-session ret_1d, single linkage, cash fallback on non-PSD pairwise covariance); feature group_ret_6m (features-v5); scipy runtime dependency. Packaged config 19 trials, 12 strategy ids. Closes #56.",
          "timestamp": "2026-11-22T20:22:16+07:00",
          "tree_id": "187cb3736011978beff52e8fc13a1b1765a1b7ee",
          "url": "https://github.com/lephucchi/vnstratlab/commit/a94e92b2574cd1924445f505869a9e21c80fd75b"
        },
        "date": 1795353773535,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_features.py::test_bench_compute_features_15_tickers_3000_sessions",
            "value": 1.9467860365260932,
            "unit": "iter/sec",
            "range": "stddev: 0.029594747959098968",
            "extra": "mean: 513.6671319999972 msec\nrounds: 3"
          },
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 66.79346783128625,
            "unit": "iter/sec",
            "range": "stddev: 0.0001919927352424068",
            "extra": "mean: 14.97152390000025 msec\nrounds: 10"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "fd51588c6b61c992edf12727f38f72425b4327e9",
          "message": "docs: close P1-T19, progress log, roadmap (#58)\n\nCo-authored-by: Le Phuc Chi <lephucchi@users.noreply.github.com>",
          "timestamp": "2026-11-22T20:27:50+07:00",
          "tree_id": "5bd40bc499077a45ac98dc4865e8812a2cadd9ab",
          "url": "https://github.com/lephucchi/vnstratlab/commit/fd51588c6b61c992edf12727f38f72425b4327e9"
        },
        "date": 1795354103832,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_features.py::test_bench_compute_features_15_tickers_3000_sessions",
            "value": 2.6403904003087733,
            "unit": "iter/sec",
            "range": "stddev: 0.01565195418227754",
            "extra": "mean: 378.73187233337075 msec\nrounds: 3"
          },
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 102.11032341402749,
            "unit": "iter/sec",
            "range": "stddev: 0.0002778593344295973",
            "extra": "mean: 9.793329083341481 msec\nrounds: 12"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "cd2c2ec7440a018e69b0baacda9f8333753f9792",
          "message": "docs: v0.1.0 scope — defer P1-T05/P1-T18/S13, backtest in v0.2, add init (#60)\n\nScope decisions for v0.1.0 (owner-delegated, 2026-11-26).",
          "timestamp": "2026-11-26T15:13:47+07:00",
          "tree_id": "ad6fd0397fac7ec6f6cb206b4e2ccaa5fb94c7b5",
          "url": "https://github.com/lephucchi/vnstratlab/commit/cd2c2ec7440a018e69b0baacda9f8333753f9792"
        },
        "date": 1795680870822,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_features.py::test_bench_compute_features_15_tickers_3000_sessions",
            "value": 3.0078905632198363,
            "unit": "iter/sec",
            "range": "stddev: 0.009774941932288785",
            "extra": "mean: 332.45890399999683 msec\nrounds: 3"
          },
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 116.86247948958973,
            "unit": "iter/sec",
            "range": "stddev: 0.0001673708742032977",
            "extra": "mean: 8.557066428571554 msec\nrounds: 14"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "0d33c4ec2cc83e27dbd8803ff42a268863d6e221",
          "message": "tools(po): normalise card status, hide superseded and covered ranges; cards for blocked items (#62)\n\nPO board: status normalisation, superseded and covered ranges hidden, cards for blocked items; progress line for #60.",
          "timestamp": "2026-11-26T15:30:45+07:00",
          "tree_id": "5c81b8f2f3dd07c29088e2c38e0033194cebd1f4",
          "url": "https://github.com/lephucchi/vnstratlab/commit/0d33c4ec2cc83e27dbd8803ff42a268863d6e221"
        },
        "date": 1795681881469,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_features.py::test_bench_compute_features_15_tickers_3000_sessions",
            "value": 2.606302436491924,
            "unit": "iter/sec",
            "range": "stddev: 0.01558363908233824",
            "extra": "mean: 383.68532600000077 msec\nrounds: 3"
          },
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 102.2116514553595,
            "unit": "iter/sec",
            "range": "stddev: 0.0001995515183769415",
            "extra": "mean: 9.783620416667915 msec\nrounds: 12"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "30541a54b1819407c08ee3ed719027eeb4323623",
          "message": "feat(demo): vnstratlab demo, offline end-to-end run on synthetic data (P1-T32) (#63)\n\nP1-T32: synthetic ingest, rebuild, features, 19 packaged trials through the simulator with the risk layer (executable mode); lab/metrics.py; demo --quiet in the CI smoke step. G2 approve round 1; minor findings in a follow-up issue.",
          "timestamp": "2026-11-26T15:36:51+07:00",
          "tree_id": "e457d5ec7739753ab590233007b55e6746688647",
          "url": "https://github.com/lephucchi/vnstratlab/commit/30541a54b1819407c08ee3ed719027eeb4323623"
        },
        "date": 1795682248515,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_features.py::test_bench_compute_features_15_tickers_3000_sessions",
            "value": 2.2784757946602485,
            "unit": "iter/sec",
            "range": "stddev: 0.016213633559338567",
            "extra": "mean: 438.889893999999 msec\nrounds: 3"
          },
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 82.9961081992048,
            "unit": "iter/sec",
            "range": "stddev: 0.0002593017119385446",
            "extra": "mean: 12.048757727288002 msec\nrounds: 11"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "ac0cbd4f14cfe719d861d2cecf1ed1d2f6dbcd2c",
          "message": "feat(init): vnstratlab init, interactive user config wizard (P1-T35) (#66)\n\nP1-T35: init wizard writes a minimal validated config.yaml (capital per book, data source, brokerage fee), atomic, --force keeps a .bak copy; never handles secrets. Closes #61. Replaces #64. G2 light (manager).",
          "timestamp": "2026-11-26T15:53:22+07:00",
          "tree_id": "5acb6a1e35d8e80e03c2fa51fad5845ffe82ba0c",
          "url": "https://github.com/lephucchi/vnstratlab/commit/ac0cbd4f14cfe719d861d2cecf1ed1d2f6dbcd2c"
        },
        "date": 1795683237605,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_features.py::test_bench_compute_features_15_tickers_3000_sessions",
            "value": 3.1811480989986824,
            "unit": "iter/sec",
            "range": "stddev: 0.01778464247438967",
            "extra": "mean: 314.35191600000206 msec\nrounds: 3"
          },
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 109.37976640976977,
            "unit": "iter/sec",
            "range": "stddev: 0.00033154781782424037",
            "extra": "mean: 9.142458727272253 msec\nrounds: 11"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "fa5edfbe269740d409867d4f150f98ec6a2c0fac",
          "message": "docs: close P1-T32 and P1-T35, progress log, roadmap (#67)\n\nDocs only.",
          "timestamp": "2026-11-26T16:00:53+07:00",
          "tree_id": "11f2147e685b290928057ced230543e1fe71be60",
          "url": "https://github.com/lephucchi/vnstratlab/commit/fa5edfbe269740d409867d4f150f98ec6a2c0fac"
        },
        "date": 1795683697878,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_features.py::test_bench_compute_features_15_tickers_3000_sessions",
            "value": 3.085417100454967,
            "unit": "iter/sec",
            "range": "stddev: 0.01079901051099737",
            "extra": "mean: 324.105288666658 msec\nrounds: 3"
          },
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 101.55179852588246,
            "unit": "iter/sec",
            "range": "stddev: 0.00017261665191005245",
            "extra": "mean: 9.847191428570616 msec\nrounds: 14"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "f0bff57f5690aaf3a253af184dfc4bbf7f71576a",
          "message": "feat(runs): run registry with DAG runner and per-task logs, vnstratlab serve API (P1-T27a) (#70)\n\nP1-T27a: runs package (demo/refresh/ingest/rebuild/features pipelines, per-task logs, retention 50), serve on loopback with runs/logs/SSE/data/results API, Yahoo terms confirmation. G2 light (manager): loopback Host/Origin guard, X-Vnstratlab header on POST, run_id regex before path use, no secrets.",
          "timestamp": "2026-11-26T17:07:26+07:00",
          "tree_id": "65eb64b34f84b9ebae84ee038a101ad292080bc7",
          "url": "https://github.com/lephucchi/vnstratlab/commit/f0bff57f5690aaf3a253af184dfc4bbf7f71576a"
        },
        "date": 1795687695914,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_features.py::test_bench_compute_features_15_tickers_3000_sessions",
            "value": 1.962735740002567,
            "unit": "iter/sec",
            "range": "stddev: 0.0120095885576511",
            "extra": "mean: 509.49293866666545 msec\nrounds: 3"
          },
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 51.5674522480502,
            "unit": "iter/sec",
            "range": "stddev: 0.0007816844488008132",
            "extra": "mean: 19.392076909089695 msec\nrounds: 11"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "36ca54c824055626f4c92e9d66a0586dd48761d5",
          "message": "feat(app): Console UI with guide, runs, data and results pages (P1-T28a) (#74)\n\nP1-T28a: static Console (Vietnamese, offline, no build step): animated 6-step guide, Airflow-like runs grid and live DAG with SSE logs, data and results pages. G2 light (manager): no innerHTML/eval, X-Vnstratlab header on POST, no external URLs. Not verified in a browser: mid-run live view, 390 px layout, terms dialog.",
          "timestamp": "2026-11-26T17:30:25+07:00",
          "tree_id": "0a29453921c576a2b3eee2a4d44410854b89e9ab",
          "url": "https://github.com/lephucchi/vnstratlab/commit/36ca54c824055626f4c92e9d66a0586dd48761d5"
        },
        "date": 1795689063756,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_features.py::test_bench_compute_features_15_tickers_3000_sessions",
            "value": 1.9641044255766624,
            "unit": "iter/sec",
            "range": "stddev: 0.017768200210744788",
            "extra": "mean: 509.1378986666655 msec\nrounds: 3"
          },
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 53.609266270048494,
            "unit": "iter/sec",
            "range": "stddev: 0.00029091823880515115",
            "extra": "mean: 18.65349163636474 msec\nrounds: 11"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "phucchi12112004@gmail.com",
            "name": "Lê Phúc Chí",
            "username": "lephucchi"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "c6a15c0495f24693dd7b49e6b960aa231746fa88",
          "message": "chore: lean tests, smaller PR CI, one-round reviews (X-trim) (#73)\n\nOwner decision 2026-11-26: full G2 only for engine/finance/cost/statistics math, 1 round; lean test policy; PR CI ubuntu+windows py3.12, full matrix on push/nightly/dispatch; 28 redundant tests removed (pytest 227 s -> 135 s, coverage 97.3%); autouse temp APP_HOME in conftest so tests never write run records to the real home. G2 light (manager).",
          "timestamp": "2026-11-26T17:35:20+07:00",
          "tree_id": "180585798e56549760e3c95b1b5b82b449c7eeb9",
          "url": "https://github.com/lephucchi/vnstratlab/commit/c6a15c0495f24693dd7b49e6b960aa231746fa88"
        },
        "date": 1795689361506,
        "tool": "pytest",
        "benches": [
          {
            "name": "benchmarks/test_bench_features.py::test_bench_compute_features_15_tickers_3000_sessions",
            "value": 2.6044293523049484,
            "unit": "iter/sec",
            "range": "stddev: 0.011474914765019344",
            "extra": "mean: 383.96126933333363 msec\nrounds: 3"
          },
          {
            "name": "benchmarks/test_bench_smoke.py::test_bench_cli_help",
            "value": 81.28896497625315,
            "unit": "iter/sec",
            "range": "stddev: 0.00022357398339305015",
            "extra": "mean: 12.301792750001539 msec\nrounds: 16"
          }
        ]
      }
    ]
  }
}