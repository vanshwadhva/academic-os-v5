# Web App Integration — bits-dsai-tracker.web.app

The extension talks to your web app entirely through `window.postMessage`,
because content scripts run in an isolated JS world and can't touch your
page's variables, React state, or localStorage directly. This is the same
mechanism used for auth, just extended to progress data.

Everything below is the contract your frontend needs to implement. The
extension side (`content_scripts/content.js`, `background/background.js`)
is already built and listening.

## 1. Detect the extension is installed

```js
window.addEventListener("message", (event) => {
  if (event.source !== window) return;
  if (event.data?.type === "ACADEMIC_OS_EXTENSION_READY") {
    // show "Extension connected" UI, enable the refresh button, etc.
  }
});
```

Fires once per page load, right after the content script injects.

## 2. Send the Firebase ID token after sign-in (unchanged from before)

```js
window.postMessage({
  type: "ACADEMIC_OS_AUTH",
  token: await firebaseUser.getIdToken(),
  user: { name: firebaseUser.displayName, email: firebaseUser.email, photo: firebaseUser.photoURL },
  expiresIn: 3600
}, window.location.origin);
```

## 3. Ask for the current Lumen progress data

```js
window.postMessage({ type: "ACADEMIC_OS_REQUEST_PROGRESS" }, window.location.origin);

window.addEventListener("message", (event) => {
  if (event.source !== window) return;
  if (event.data?.type === "ACADEMIC_OS_PROGRESS_DATA") {
    renderDashboard(event.data.progress); // your own UI, your own component
  }
});
```

`progress` is `null` if nothing's been fetched yet, otherwise:

```ts
{
  student: { name: string, userId: string } | null,
  courses: [
    {
      orgUnitId: number,
      courseName: string,
      courseCode: string | null,
      grades: [{ title, pointsNumerator, pointsDenominator, percentage }],
      moduleProgress: { completed: number, total: number },
      assignments: [{ title, dueDate, status }],
      quizzes: [{ title, isActive }],
      discussions: [{ title, postCount }],
      announcements: [{ title, postedDate }],
      fetchErrors: string[]  // non-fatal per-endpoint failures for this course
    }
  ],
  fetchedAt: string, // ISO timestamp
  errors: string[]   // non-fatal top-level failures (e.g. whoami failed)
}
```

## 4. Trigger a fresh pull from Lumen (e.g. a "Refresh" button on your page)

```js
window.postMessage({ type: "ACADEMIC_OS_REQUEST_REFRESH" }, window.location.origin);
// Response arrives async as ACADEMIC_OS_PROGRESS_DATA (same listener as step 3),
// typically a few seconds later — show a loading state until then.
```

This opens (or reuses) a background Lumen tab, pulls fresh data via the
student's real session cookies, and pushes the result to every open
bits-dsai-tracker tab automatically — you don't need to re-request it.

## 5. Live updates without a page reload

Whenever the extension's 15-minute auto-refresh alarm fires (or the
student clicks "Refresh from Lumen" in the extension popup), your open
tab gets an unsolicited `ACADEMIC_OS_PROGRESS_DATA` push. Just keep the
step 3 listener registered for the life of the page and it'll stay current.

## What's still NOT wired to your web app

- The extension still queues data toward `CONFIG.API_BASE_URL` (currently
  a placeholder — `academic-os-api.onrender.com`) via `sync_manager.js`.
  If your web app has its own backend (Firestore, a Cloud Function,
  whatever's behind `bits-dsai-tracker.web.app`), decide whether you want
  the extension to also POST there directly, or whether the web app
  itself should persist what it receives via postMessage. Say which and
  I'll wire `api_client.js`/`config.js` accordingly — right now data
  reaches your page live, but nothing on the extension side is writing
  to whatever backend actually powers bits-dsai-tracker.
