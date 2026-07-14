# Academic OS — v4 (production hardening pass)

Run tests: `node tests/run_tests.js` (plain Node, no build tooling needed).

See PRODUCTION_AUDIT_REPORT.md for the full report requested (files
changed, bugs fixed, security/performance notes, remaining issues, score).

## Quick orientation

- `config.js` / `utils/logger.js` — load these first everywhere (manifest
  and importScripts already do this in the right order).
- `network/lumen_token_bridge.js` — kept per your file list, but now
  strictly optional/non-blocking. Read the header comment: this OAuth
  flow is unverified against real Brightspace and almost certainly
  doesn't work. `active_fetcher.js` no longer depends on it succeeding.
- `CONFIG.BACKEND_SUPPORTS_BATCH_SYNC` — flip to `true` once your FastAPI
  backend actually exposes `POST /api/lumen/sync/batch` accepting
  `{ events: [...] }`. Individual-item sync is the default and matches
  current behavior.
- `CONFIG.DEBUG` — `false` by default; flip `true` during development to
  see `Logger.info`/`Logger.debug` output. `warn`/`error` always print.

Load: `chrome://extensions` → Developer mode → Load unpacked.
