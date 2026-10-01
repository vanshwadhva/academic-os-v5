# Academic OS — v4 (production hardening pass)

This repository now also contains the complete Academic OS placement-ML stack
adapted for the `Data Stores & Pipeline` course in `DSP-BITS- Handbook.pdf`.
The original Manifest V3 Lumen extension remains intact; the full-stack app is
under `frontend/`, `backend/`, `integrations/`, `ml/`, `services/`,
`repositories/`, `scheduler/`, `workers/`, and `monitoring/`.

The frontend keeps the original placement-ML UI and algorithms, but its live
course dataset is now the handbook's 3-credit, 15-week curriculum. Weeks 1-13
contain the handbook topics and Week 14-15 is the comprehensive examination.

Run the full stack using [README_PLACEMENT_ML.md](../README_PLACEMENT_ML.md).

Run tests: `node tests/run_tests.js` (plain Node, no build tooling needed).

See [PRODUCTION_AUDIT_REPORT.md](../../Academic-OS-Chrome-Etension/docs/PRODUCTION_AUDIT_REPORT.md) for the full report requested (files
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
