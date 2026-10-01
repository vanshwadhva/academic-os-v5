# Architecture

## System shape

The repository is a Manifest V3 Chrome extension named `Academic OS – Lumen Sync` (`manifest.json`, version 2.1.0). It has no package manager or build tooling. The runtime consists of:

1. An Academic OS web-app content script that bridges page `window.postMessage` events to the extension.
2. A background service worker that owns alarms, durable state, refresh orchestration, backend sync, and broadcasts.
3. A Lumen isolated-world content script that actively fetches Brightspace endpoints using the user's same-origin cookies.
4. A Lumen MAIN-world hook that passively observes fetch/XHR JSON responses and relays only recognized data.
5. Popup and dashboard pages that read state through background messages.

```text
Academic OS page
  ⇄ window.postMessage ⇄ content_scripts/content.js
                              ⇄ chrome.runtime messages
                         background/background.js
              ┌───────────────┼────────────────┐
              │               │                │
       chrome.storage    active Lumen tab   Render API
        queue/cache       active_fetcher    api_client
                              │
                 Lumen MAIN world hook
                 injected_hook + token bridge
```

## Runtime loading

- Background: `config.js`, `utils/logger.js`, `storage/storage.js`, `authentication/auth.js`, `api/api_client.js`, `sync/sync_manager.js`, then `background/background.js`.
- Academic OS pages: `config.js`, `utils/logger.js`, `content_scripts/content.js`.
- Lumen isolated world: `config.js`, `utils/logger.js`, `network/network_monitor.js`, `network/active_fetcher.js`.
- Lumen MAIN world: `network/lumen_token_bridge.js`, `network/injected_hook.js`.

## Responsibilities

- `config.js`: origins, endpoints, retry/queue constants, storage keys, and feature flags.
- `authentication/auth.js`: stores Firebase ID token and expiry; distinguishes signed out from expired; never stores passwords.
- `api/api_client.js`: authenticated fetch with request IDs, idempotency headers, timeout, error classification, and jittered exponential retry.
- `storage/storage.js`: async `chrome.storage.local` wrapper plus queue deduplication, age expiration, size cap, and FNV-1a fingerprinting.
- `sync/sync_manager.js`: durable-first queue drain, individual or optional batch delivery, auth/backend deferral, partial-success fallback, dead-letter behavior.
- `background/background.js`: single message router, alarms, Lumen tab discovery, single-flight refresh, cache write, web-app broadcast, and sync trigger.
- `active_fetcher.js`: discovers Brightspace API versions, fetches identity/enrollments, then gathers six course endpoints in parallel.
- `network_monitor.js`: converts passive payloads into backend event shapes; unknown payloads become `null` and are dropped.
- `injected_hook.js`: wraps page `fetch` and XHR without changing their result; captures only allowlisted API paths and JSON-like responses.
- `content_scripts/content.js`: validates origin/token shape, deduplicates auth messages, serves cached progress, requests refresh, and forwards background pushes.
- `popup/*`: status, refresh, auto-sync toggle, queue/session banners, sign-out.
- `dashboard/*`: iframe-hosted web app plus local cached progress view; escapes rendered strings.

## Trust boundaries

The page can post messages only from the same window and origin. The extension rechecks the Academic OS origin and token shape. The background worker allowlists message types. Lumen passive capture crosses MAIN-world to isolated-world via same-origin `window.postMessage`; it must remain normalized and non-raw. Firebase tokens are the only auth secret stored; Lumen data is cached and queued locally.
