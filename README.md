# Academic OS — Chrome Extension (`academic-os-v5`)

Manifest V3 extension that pulls BITS Lumen (Brightspace) progress using the student’s browser session, then:

1. Pushes live progress into the Academic OS web app via `window.postMessage`  
2. Syncs snapshots to the FastAPI backend (`POST /api/lumen/sync`) with a Firebase ID token relayed from the web app  

Companion web app / API: **`placement-ml`** (Firebase Hosting + FastAPI).

Current version: see `manifest.json` (`2.2.4+`).

---

## Load unpacked (local / QA)

1. Open Chrome → `chrome://extensions`  
2. Enable **Developer mode**  
3. **Load unpacked** → select this repo folder (`academic-os-v5`)  
4. Keep the extension **Enabled**

### Local end-to-end

1. Start API + frontend from `placement-ml` (see that repo’s README)  
   - API: `http://127.0.0.1:8000`  
   - Tracker: `http://127.0.0.1:5500/index.html`  
2. Confirm `config.js`:

```js
ACADEMIC_OS_ORIGINS: [
  "https://bits-dsai-tracker.web.app",
  "http://127.0.0.1:5500",
  "http://localhost:5500"
],
ACADEMIC_OS_SIGNIN_URL: "http://127.0.0.1:5500/index.html",
API_BASE_URL: "http://127.0.0.1:8000",
```

3. Sign in on the tracker (BITS email) — UI should show **Ext: connected**  
4. Sign in to Lumen in Chrome: https://lumen.bitspilani-digital.edu.in  
5. Extension popup → **Refresh from Lumen**  
6. Tracker updates; backend `/api/lumen/status` shows a snapshot with non-zero `moduleProgress.completed` when Lumen has visits

After every code change: **Reload** the extension on `chrome://extensions`, then hard-refresh the tracker tab.

---

## Production deploy (extension)

Chrome Web Store packaging is optional. For cohort distribution you can:

### A. Internal / unpacked zip (fastest)

```bash
# From academic-os-v5 — exclude junk if any
zip -r academic-os-extension.zip . \
  -x "*.git*" -x "*node_modules*" -x "*.DS_Store*" -x "tests/*"
```

Share the zip. Students: unzip → Load unpacked (or follow your IT packaging).

### B. Chrome Web Store

1. Set production URLs in `config.js` and `manifest.json` `host_permissions`  
2. Set `CONFIG.DEBUG = false`  
3. Bump `manifest.json` `version`  
4. Zip the extension directory  
5. Upload in [Chrome Developer Dashboard](https://chrome.google.com/webstore/devconsole)  
6. Fill store listing, privacy (Lumen + Academic OS origins), submit for review  

### Production config checklist

| Setting | Value |
|---------|--------|
| `ACADEMIC_OS_ORIGIN` | `https://bits-dsai-tracker.web.app` |
| `ACADEMIC_OS_ORIGINS` | Include production (+ local only if you still need it) |
| `ACADEMIC_OS_SIGNIN_URL` | `https://bits-dsai-tracker.web.app/` (or `/index.html`) |
| `API_BASE_URL` | Your deployed FastAPI base (no trailing slash) |
| `host_permissions` | Tracker origin, API origin, `https://lumen.bitspilani-digital.edu.in/*` |
| Content script `matches` | Same tracker origins as `ACADEMIC_OS_ORIGINS` |

Deploy the **web app + API first** (`placement-ml` README), then ship the extension pointed at those URLs.

---

## How auth works (no token in localStorage)

1. Student signs in on the Academic OS **web app** (Firebase Auth)  
2. Page `postMessage`s `{ type: "ACADEMIC_OS_AUTH", token, user, expiresIn }`  
3. Content script relays into `chrome.storage.local`  
4. Sync manager sends `Authorization: Bearer <Firebase ID token>` to the API  

See [`WEBAPP_INTEGRATION.md`](WEBAPP_INTEGRATION.md) for the full postMessage contract.

---

## Lumen progress

- Cookie session on `lumen.bitspilani-digital.edu.in` (primary)  
- Completion counts from Brightspace `content/completions` + `userprogress` (not TOC visit fields alone)  
- Optional `lumen_token_bridge.js` OAuth is fail-soft and unused when cookies work  

---

## Tests

```bash
node tests/run_tests.js
```

---

## Layout

```
manifest.json              # MV3 entry
config.js                  # Origins, API, storage keys
background/background.js   # Alarms, Lumen refresh, sync drain
content_scripts/content.js # Webapp bridge
network/active_fetcher.js  # Lumen Valence pulls
sync/sync_manager.js       # Durable queue → API
authentication/auth.js     # Cached Firebase ID token
popup/                     # Toolbar UI
```
