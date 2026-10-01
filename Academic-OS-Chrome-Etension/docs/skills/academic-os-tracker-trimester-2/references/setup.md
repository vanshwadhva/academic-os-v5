# Setup and operations

## Install

1. Open `chrome://extensions`.
2. Enable Developer mode.
3. Choose Load unpacked and select the repository root containing `manifest.json`.
4. Sign in to the Academic OS page so its Firebase ID token is relayed to the extension.
5. Sign in to the BITS Lumen home page. Use the popup's “Refresh from Lumen” or open the dashboard.

## Test

Run:

```sh
node tests/run_tests.js
```

The tests load the real classic scripts in a VM and cover queue idempotency, age/size limits, normalizer filtering, unknown-route dropping, and backoff math. There is no build, install, or dependency step.

## Development switches

- Set `CONFIG.DEBUG = true` for info/debug logs; warnings and errors always print.
- Set `CONFIG.BACKEND_SUPPORTS_BATCH_SYNC = true` only after the backend accepts `POST /api/lumen/sync/batch` with `{ events: [...] }`.
- Change `API_BASE_URL` only when the real authenticated backend is known.

## Known external gaps

- `lumen_token_bridge.js` is unverified and likely unnecessary; cookie-authenticated same-origin fetch is the primary path.
- Brightspace API field names and endpoint behavior are best-effort until tested against a live BITS tenant.
- Attendance is not fetched; it may be exposed through a separate LTI.
- The web app receives live `postMessage` data, but the extension's queued backend is the Render API, not automatically the Firebase/web-app backend.
- No browser notifications or queue encryption are implemented.

## Debugging sequence

When a refresh fails, inspect: (1) extension service-worker console, (2) Lumen tab console, (3) `GET_STATUS` state and queue, (4) Lumen network response content type/shape, (5) backend status and auth expiry. Preserve partial progress and error fields while diagnosing. Do not bypass normalizers by uploading raw payloads.
