# Security policy

## Supported versions

Only the latest release on `main` receives fixes while the project is pre-1.0.

## Reporting a vulnerability

Please use GitHub's **private vulnerability reporting**
(Security tab → "Report a vulnerability"). Do not open a public issue.

Include what you found, how to reproduce it and the impact. Expect a first reply within 7 days.

## Scope notes

- vnstratlab stores secrets only in environment variables or a local `.env` file and never sends
  them to the browser. Any path that logs, prints, commits or exposes a secret is a vulnerability.
- The dashboard binds to `127.0.0.1` by default. Exposing it publicly is unsupported.
- vnstratlab places no orders; there is no trading credential to protect.
