window.BENCHMARK_DATA = {
  "lastUpdate": 1794909176007,
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
      }
    ]
  }
}