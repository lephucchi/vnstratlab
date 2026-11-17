window.BENCHMARK_DATA = {
  "lastUpdate": 1794926897727,
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
      }
    ]
  }
}