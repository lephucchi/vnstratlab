window.BENCHMARK_DATA = {
  "lastUpdate": 1795227507366,
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
      }
    ]
  }
}