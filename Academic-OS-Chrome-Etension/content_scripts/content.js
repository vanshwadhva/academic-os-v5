// content.js — runs on the Academic OS frontend only. Relays Firebase ID
// tokens posted by the web app after sign-in via window.postMessage
// (content scripts can't read page localStorage directly — isolated world).

// Explicit allowlist check as defense-in-depth: even though the manifest
// match pattern already restricts where this script runs, don't trust
// that alone — re-verify against CONFIG before acting on anything.
if (window.location.origin !== CONFIG.ACADEMIC_OS_ORIGIN) {
  Logger.warn("content.js loaded on unexpected origin, refusing to activate:", window.location.origin);
} else {
  // Small ring buffer to dedupe identical auth messages fired twice by the
  // page (observed on some SPA re-renders / React StrictMode double effects).
  // Capped size — this is a content script that lives as long as the tab,
  // so an unbounded Set here would be a slow memory leak over a long session.
  const seenMessageHashes = [];
  const MAX_SEEN = 20;

  function alreadySeen(hash) {
    if (seenMessageHashes.includes(hash)) return true;
    seenMessageHashes.push(hash);
    if (seenMessageHashes.length > MAX_SEEN) seenMessageHashes.shift();
    return false;
  }

  window.addEventListener("message", (event) => {
    if (event.source !== window) return; // ignore all iframes, only trust the top-level page script
    if (event.origin !== window.location.origin) return;

    const msg = event.data;
    if (!msg || typeof msg.type !== "string") return;

    if (msg.type === "ACADEMIC_OS_AUTH") {
      handleAuthMessage(msg);
      return;
    }

    if (msg.type === "ACADEMIC_OS_REQUEST_PROGRESS") {
      // Your web app asking "what's the latest Lumen data you have?" —
      // answer from the local cache immediately (fast, works offline),
      // background pushes an updated one later if a fetch is in flight.
      Logger.debug("Dashboard requested cached progress");
      chrome.runtime
        .sendMessage({ type: "GET_PROGRESS_CACHE" })
        .then((res) => {
          Logger.debug("Returning cached progress to dashboard");
          window.postMessage(
            { type: "ACADEMIC_OS_PROGRESS_DATA", progress: res?.progress ?? null },
            window.location.origin
          );
        })
        .catch((err) => Logger.debug("Progress request failed:", err.message));
      return;
    }

    if (msg.type === "ACADEMIC_OS_REQUEST_REFRESH") {
      // Your web app asking "go fetch fresh data from Lumen right now."
      // This opens/uses a Lumen tab in the background — can take a few
      // seconds, so the page should show a loading state until the
      // ACADEMIC_OS_PROGRESS_DATA push arrives (see background.js).
      Logger.debug("Dashboard requested a fresh Lumen sync");
      chrome.runtime.sendMessage({ type: "FETCH_LUMEN_PROGRESS" }).catch((err) => {
        Logger.debug("Refresh request failed:", err.message);
      });
      return;
    }
  });

  function handleAuthMessage(msg) {
    if (typeof msg.token !== "string" || msg.token.length < 10) {
      Logger.warn("ACADEMIC_OS_AUTH message missing/invalid token, ignoring");
      return;
    }

    const hash = `${msg.token.slice(-16)}:${msg.expiresIn || ""}`;
    if (alreadySeen(hash)) {
      Logger.debug("Duplicate ACADEMIC_OS_AUTH message ignored");
      return;
    }

    chrome.runtime
      .sendMessage({
        type: "STORE_FIREBASE_TOKEN",
        token: msg.token,
        user: msg.user && typeof msg.user === "object" ? msg.user : null,
        expiresIn: typeof msg.expiresIn === "number" ? msg.expiresIn : 3600
      })
      .catch((err) => {
        // "Extension context invalidated" happens if the extension was
        // reloaded/updated while this tab stayed open — not actionable
        // from here, just don't let it throw an unhandled rejection.
        Logger.debug("Token relay failed (extension may have reloaded):", err.message);
      });
  }

  // Background pushes fresh data here (see PUSH_PROGRESS_TO_PAGE in
  // background.js) whenever a Lumen fetch completes, whether it was
  // triggered by the popup, the alarm, or this page's own refresh request.
  chrome.runtime.onMessage.addListener((message) => {
    if (message?.type !== "PUSH_PROGRESS_TO_PAGE") return;
    Logger.debug("Received fresh progress from background; forwarding to web app");
    window.postMessage({ type: "ACADEMIC_OS_PROGRESS_DATA", progress: message.progress }, window.location.origin);
  });

  Logger.debug("Academic OS extension bridge ready");
  window.postMessage({ type: "ACADEMIC_OS_EXTENSION_READY" }, window.location.origin);
}
