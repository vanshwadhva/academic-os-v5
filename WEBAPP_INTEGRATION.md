# Web App Integration — bits-dsai-tracker.web.app
#
# Implemented on both sides (Full Bridge Stable).
# Extension: content_scripts/content.js + background/background.js
# Webapp: placement-ml/frontend/index.html (ACADEMIC_OS_* bridge)

The extension talks to the web app entirely through `window.postMessage`,
because content scripts run in an isolated JS world and can't touch your
page's variables, React state, or localStorage directly.

## 1. Extension ready

Webapp listens for `ACADEMIC_OS_EXTENSION_READY` and shows "Ext: connected".

## 2. Firebase ID token after sign-in

Webapp posts (never stores the ID token in localStorage):

```js
window.postMessage({
  type: "ACADEMIC_OS_AUTH",
  token: await firebaseUser.getIdToken(),
  user: { name: firebaseUser.displayName, email: firebaseUser.email, photo: firebaseUser.photoURL },
  expiresIn: 3600
}, window.location.origin);
```

Re-posted about every 50 minutes via `getIdToken(true)`.

## 3. Progress data

- Webapp may request: `ACADEMIC_OS_REQUEST_PROGRESS`
- Extension pushes: `ACADEMIC_OS_PROGRESS_DATA` with `{ progress }`
- Webapp maps extension course shapes (`courseName` / `moduleProgress`) into the tracker checklist and writes Firestore

## 4. Refresh from Lumen

`ACADEMIC_OS_REQUEST_REFRESH` → extension opens/reuses a Lumen tab, cookie-auth fetch, then pushes `ACADEMIC_OS_PROGRESS_DATA`.

## 5. Cloud sync (extension → backend)

When a Firebase token is cached in the extension, queue items POST to:

`POST {API_BASE_URL}/api/lumen/sync` with `Authorization: Bearer <Firebase ID token>`

Default `API_BASE_URL` is `http://127.0.0.1:8000` (same as webapp `BACKEND_API_URL`). Point both at your deployed FastAPI host in production.

Related: `GET /api/lumen/status`, `GET /api/lumen/history` (Bearer required).

## Firebase project

```js
projectId: "bits-dsai-tracker"
authDomain: "bits-dsai-tracker.firebaseapp.com"
appId: "1:530627005818:web:24ca6180f9ed9e2fcbdac3"
```
