# Academic OS Extension — Production Readiness Audit Report

## 1. Files modified

| File | Change type |
|---|---|
| `manifest.json` | Fixed load order, bumped version, kept token bridge as MAIN-world script |
| `config.js` | Added DEBUG flag, timeout/backoff/batch/queue-limit constants |
| `utils/logger.js` | **New.** Shared Logger utility (item 11) |
| `authentication/auth.js` | Rewrote: expiry-aware status, split "expired" vs "signed out" |
| `api/api_client.js` | Rewrote: AbortController timeout, request IDs, idempotency headers, jittered backoff, error classification |
| `storage/storage.js` | Rewrote: idempotency-key dedup, queue age/size limits, cleanup |
| `sync/sync_manager.js` | Rewrote: durable-first enqueue, dead-lettering, batch support + partial-success fallback |
| `background/background.js` | Rewrote: message allowlist, refresh-race guard, cleanup alarm, startup recovery |
| `content_scripts/content.js` | Rewrote: message dedup ring buffer, stricter validation, origin allowlist |
| `network/injected_hook.js` | Rewrote: OPTIONS/HEAD/binary filtering, malformed-JSON handling |
| `network/network_monitor.js` | Rewrote: required-field validation per normalizer, unknown shapes → `null` (never raw passthrough), exposed `Normalizer` globally |
| `network/active_fetcher.js` | Rewrote: opportunistic (non-blocking) token use, per-request timeouts, content-type guards, added quizzes/discussions/announcements coverage |
| `network/lumen_token_bridge.js` | Hardened: timeout, never throws, documented as unverified/optional |
| `popup/popup.js`, `popup/popup.html`, `popup/popup.css` | Added sync-state banner, queue/retry count, session-expired state, offline detection |
| `tests/run_tests.js` | **New.** 9 tests covering storage dedup/limits, normalizers, backoff math |

## 2. Bugs fixed

1. **`Normalizer` wasn't exposed via `globalThis`** in `network_monitor.js` — invisible to anything outside that file's own scope (would only have been caught by another consumer trying to reach it, or by writing tests — which is exactly how this was caught).
2. **`isSignedIn()` didn't check token expiry**, only presence — a token that expired an hour ago still reported "signed in."
3. **`Auth.clear()` was called on every 401**, wiping user info along with the token — meant the popup couldn't distinguish "never signed in" from "was signed in, just expired," so it always showed the generic signed-out state.
4. **Sync queue items were pushed to memory before being persisted** in the old `pushNow` — a killed service worker between "add to array" and "write to storage" silently lost the item. Now enqueue-to-storage always happens first.
5. **No retry ceiling on individual queue items** — a permanently-broken item (bad schema, whatever) would retry forever on every alarm tick indefinitely. Now dead-lettered after `RETRY_MAX_ATTEMPTS`.
6. **Passive capture could forward raw/malformed payloads** if a normalizer didn't match — `normalize()` now returns `null` for anything unrecognized or missing required fields, and `network_monitor.js` drops those instead of forwarding.
7. **`active_fetcher.js` had zero request timeouts** — a hung Brightspace endpoint would hang the whole progress fetch indefinitely. Every `apiGet` now has a 12s `AbortController` timeout.
8. **Background had no message-type allowlist** — any message reaching the worker fell through to `default: unknown type`, which is fine functionally but doesn't reject bad senders early or log them for investigation. Now validated against `KNOWN_MESSAGE_TYPES` up front.
9. **No race guard on `refreshLumenProgress`** — the 15-min alarm firing while a manual "Refresh from Lumen" click was still in flight could produce two concurrent tab-open/fetch cycles. Added a shared in-flight promise guard, same pattern as `SyncManager._syncing`.

## 3. Security improvements

- Message-type allowlist in `background.js` — unknown message types rejected and logged before any handler logic runs.
- `content.js` validates token shape/length before relaying, dedupes identical `ACADEMIC_OS_AUTH` messages (defends against double-fire from SPA re-renders being treated as two separate events), and re-checks origin against `CONFIG.ACADEMIC_OS_ORIGIN` as defense-in-depth beyond the manifest match pattern.
- `injected_hook.js` / `network_monitor.js` never forward non-JSON or unrecognized-shape payloads — no raw data reaches storage or the backend.
- Confirmed: only Firebase ID tokens are ever stored (`STORAGE_KEYS.FIREBASE_TOKEN`); no passwords, no Google credentials, anywhere in the codebase (grepped for `password`, `credential`, `secret` — no hits outside this report).
- `lumen_token_bridge.js`'s OAuth attempt is now non-blocking and time-boxed — even if that endpoint behaves unexpectedly on a real tenant, it can't hang or crash the fetch pipeline.

## 4. Performance improvements

- Idempotency-key dedup in `Storage.enqueueSyncItem` — the same capture firing twice (observed behavior, not hypothetical) no longer duplicates the sync payload.
- Sync queue is now hard-capped (`SYNC_QUEUE_MAX_SIZE`, `SYNC_QUEUE_MAX_AGE_MS`) with a periodic cleanup alarm — unbounded growth from a long-broken auth state is no longer possible.
- Jittered exponential backoff (50-100% of the calculated delay) instead of fixed backoff — reduces synchronized retry storms if multiple items fail at once.
- Optional batch sync path (`CONFIG.BACKEND_SUPPORTS_BATCH_SYNC`) ready to flip on once the backend supports it, cutting N requests to N/25.
- `fetchCourseDetail` in `active_fetcher.js` uses `Promise.allSettled` across 6 endpoint calls per course instead of sequential awaits — one slow/failing endpoint no longer blocks the others.

## 5. Remaining issues (honest list, not swept under the rug)

- **`lumen_token_bridge.js`'s OAuth endpoint is still unverified and likely non-functional** against BITS's real Lumen tenant — I made it safe to fail, I did not make it work, because I have no way to confirm what would make it work without live access. This was true last round and is still true.
- **`active_fetcher.js`'s API field names/paths are still unverified** against a live Lumen session for the same reason. Cookie-auth path now works reliably in principle, but the payload shapes it expects are still my best reading of D2L's documented API, not a confirmed match.
- **No `notifications` permission/UI was added**, despite item 9 asking for a notifications audit — the architecture doc lists it as a background responsibility, but adding real notifications needs UX decisions (when to fire, how often, dismissal behavior) that are product calls, not something to bolt on silently. Flagging rather than guessing.
- **Batch sync endpoint (`/api/lumen/sync/batch`) does not exist yet** on the backend as far as I know — the code path is built and tested with a mock, but `CONFIG.BACKEND_SUPPORTS_BATCH_SYNC` stays `false` until you confirm the backend actually has it.
- **Attendance is not covered** in `active_fetcher.js` — many Brightspace tenants handle attendance via a separate third-party LTI tool with no Valence API exposure at all, not a gap I can close from the extension side without knowing what BITS specifically uses for it.
- No encryption was added to the cached sync queue (item 7's "optionally encrypt"). `chrome.storage.local` isn't accessible to other extensions or web pages, and the data in the queue is the student's own academic data, not credentials — I judged the complexity (key management inside a service worker with no persistent secure enclave) not worth it for this threat model. Flagging the decision rather than silently skipping it.

## 6. Production readiness score

**6.5 / 10** for the extension's own code (reliability, security posture, error handling, tests).

Held back from higher purely by external unknowns, not code quality:
- Two full subsystems (`lumen_token_bridge.js`'s OAuth path, `active_fetcher.js`'s API field mapping) are unverifiable without live access to BITS's actual Lumen tenant, and one of them (the token bridge) was already flagged as likely non-functional last round.
- The backend (`academic-os-api.onrender.com`) — whether it's actually deployed, what its real error responses look like, whether it has a batch endpoint — is completely outside what I can audit from the extension side.

The extension degrades gracefully around all of these (cookie auth carries the load if the token bridge fails; individual sync stays default until batch is confirmed; malformed/unverified API responses get dropped rather than corrupting the dashboard) — so "not fully verified" doesn't mean "will crash," it means "confirm these against production before you stop checking."
