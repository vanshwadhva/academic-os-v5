# Algorithms and invariants

## Active progress fetch

1. Ask the optional MAIN-world bridge for a token for up to 3 seconds.
2. Call `/d2l/api/versions/`; select the latest `lp` and `le` versions, falling back to `1.43` and `1.79`.
3. Fetch `whoami` and course enrollments (`orgUnitTypeId=3`). Identity/enrollment failures become top-level errors.
4. For each enrollment with an `OrgUnit.Id`, call six endpoints concurrently with `Promise.allSettled`: grades, content TOC, Dropbox folders, quizzes, discussion topics, and news.
5. Convert fulfilled values into the stable progress shape. Rejected endpoints append a course-level error and do not erase other data.
6. Count module topics recursively; a topic is completed when `LastVisitedDate` is present. Grade percentage is rounded to one decimal place.

Every Lumen request has a 12-second abort timeout, includes cookies, accepts JSON or mislabelled `text/plain` JSON, and rejects unauthorized, unsupported, binary, or malformed results.

## Passive capture normalization

`injected_hook.js` observes only `/d2l/api/le/`, `/d2l/api/lp/`, `/d2l/api/quiz/`, and `/d2l/api/discussions/`. It ignores `OPTIONS`/`HEAD`, non-JSON content types, and invalid JSON. `network_monitor.js` routes recognized URL families to normalizers for grades, assignments, courses, quizzes, discussions, and announcements. Each normalizer accepts arrays or `Objects`/`Items` containers and filters entries missing their required title/course name. An unknown route or empty valid set returns `null` and is never uploaded.

## Durable queue and deduplication

`Storage.enqueueSyncItem` computes an idempotency key from `type` plus a 300-character JSON fingerprint using non-cryptographic FNV-1a. Existing keys are ignored. New items are written with `queued_at` and `attempts: 0`, then age and size limits are enforced. Items older than 7 days are removed; if over 500 items, oldest entries are removed first.

## Sync and retry behavior

- `SyncManager.pushNow(item)` enqueues first, then drains unless another drain is active.
- Default mode POSTs each item to `/api/lumen/sync` with its idempotency key.
- Optional batch mode sends up to 25 items to `/api/lumen/sync/batch`; a failed batch falls back to individual sends.
- API retries timeouts, network failures, 429, and 5xx responses up to 5 attempts. Delay is `min(base * 2^(attempt-1), max)` with a random 50–100% jitter; defaults are 1s base and 30s cap.
- Auth failures preserve the queue and set `auth_expired`; backend reachability failures preserve it and set `backend_offline`.
- Item-specific failures increment `attempts` and retain `lastError`. Items reaching the retry ceiling are dropped rather than retried forever.

## Concurrency and recovery

`_syncing` prevents overlapping queue drains. `_refreshing` shares one active Lumen refresh among popup clicks and the 15-minute alarm. Startup schedules alarms and attempts a best-effort drain of storage-backed items. Correctness does not depend on `onSuspend` completing.
