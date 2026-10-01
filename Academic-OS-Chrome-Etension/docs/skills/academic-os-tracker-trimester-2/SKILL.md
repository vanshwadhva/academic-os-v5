---
name: academic-os-tracker-trimester-2
description: Understand, debug, extend, and operate the Academic OS Trimester 2 Chrome extension that bridges the BITS DSAI tracker, Brightspace/Lumen progress, and a Firebase-authenticated sync backend.
---

# Academic OS Tracker Trimerster 2

Use this skill for repository work involving the Academic OS Lumen Sync extension in this workspace. Treat the current source as authoritative: it is a Manifest V3, classic-script Chrome extension with no build step.

## Operating rules

- Preserve the extension's classic-script loading model. `config.js` and `utils/logger.js` must precede dependent scripts; the background worker loads its dependencies with `importScripts`.
- Treat `chrome.storage.local` as the durable source of truth for authentication metadata, progress cache, sync queue, and sync status. Persist a new sync item before making a network request.
- Keep Lumen authentication cookie-first. The MAIN-world token bridge is optional, time-boxed, and allowed to return `null`; do not make active fetching depend on it.
- Never forward unrecognized, malformed, binary, or non-JSON Lumen responses. Normalize known payloads and drop unknown shapes.
- Preserve idempotency, queue age/size limits, retry ceilings, and the single-flight guards in `SyncManager` and `refreshLumenProgress`.
- Do not assume the Render backend, batch endpoint, OAuth flow, or Brightspace field mappings are production-verified. Validate those external contracts before changing defaults.
- Keep user-facing data partial and useful: per-course endpoint failures belong in `fetchErrors`; top-level failures belong in `errors`.

## Reference routing

- Read [architecture.md](references/architecture.md) for the component graph, file responsibilities, lifecycle, and trust boundaries.
- Read [algorithms.md](references/algorithms.md) for normalization, progress aggregation, queueing, retries, and concurrency invariants.
- Read [contracts.md](references/contracts.md) for message schemas, progress shape, backend routes, and storage keys.
- Read [setup.md](references/setup.md) for installation, testing, configuration, and known production gaps.

## Verification

Run `node tests/run_tests.js` after changes to production logic. For manifest or UI changes, load the repository unpacked at `chrome://extensions` and exercise auth, Lumen refresh, cached dashboard rendering, auto-refresh, offline queueing, and sign-out. Avoid adding a build system unless explicitly requested.
