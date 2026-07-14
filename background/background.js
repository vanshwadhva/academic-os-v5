// background.js — service worker orchestrating Lumen progress fetch + sync.
// Single message router (one onMessage listener, one switch) — avoids the
// "multiple listeners silently racing" class of bug entirely.

importScripts(
  "../config.js",
  "../utils/logger.js",
  "../storage/storage.js",
  "../authentication/auth.js",
  "../api/api_client.js",
  "../sync/sync_manager.js"
);

const ALARM_SYNC = "academic_os_auto_sync";
const ALARM_CLEANUP = "academic_os_cleanup";

// Every message type this worker understands. Anything else is rejected
// outright rather than falling through to a default case after partial
// processing — defense in depth against a compromised/rogue sender.
const KNOWN_MESSAGE_TYPES = new Set([
  "STORE_FIREBASE_TOKEN",
  "FETCH_LUMEN_PROGRESS",
  "LUMEN_DATA_CAPTURED",
  "MANUAL_SYNC_REQUEST",
  "GET_STATUS",
  "GET_PROGRESS_CACHE",
  "SET_AUTO_SYNC",
  "SIGN_OUT"
]);

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(ALARM_SYNC, { periodInMinutes: CONFIG.SYNC_INTERVAL_MINUTES });
  chrome.alarms.create(ALARM_CLEANUP, { periodInMinutes: 60 });
  Logger.info("Installed, alarms scheduled");
});

chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create(ALARM_SYNC, { periodInMinutes: CONFIG.SYNC_INTERVAL_MINUTES });
  chrome.alarms.create(ALARM_CLEANUP, { periodInMinutes: 60 });
  // Browser restart recovery: drain whatever survived in storage from the
  // last session, best-effort, without blocking startup on it.
  SyncManager.pushNow(null).catch((e) => Logger.debug("Startup recovery sync skipped:", e.message));
});

// MV3 service workers don't get a reliable onSuspend hook for async work
// (there's no guarantee it finishes before teardown), so we don't rely on
// it for correctness — durability comes from Storage being the source of
// truth for the queue (see sync_manager.js), not from a shutdown flush.
// This listener is best-effort logging only.
chrome.runtime.onSuspend?.addListener(() => {
  Logger.debug("Service worker suspending");
});

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === ALARM_CLEANUP) {
    const remaining = await Storage.cleanupSyncQueue();
    Logger.debug("Queue cleanup ran, remaining items:", remaining);
    return;
  }

  if (alarm.name !== ALARM_SYNC) return;
  const enabled = await SyncManager.isAutoSyncEnabled();
  if (!enabled) return;
  await refreshLumenProgress().catch((err) => Logger.warn("Auto-refresh failed:", err.message));
});

async function findOrOpenLumenTab() {
  const existing = await chrome.tabs.query({ url: CONFIG.LUMEN_MATCH_PATTERN });
  if (existing.length) return existing[0];

  const tab = await chrome.tabs.create({ url: CONFIG.LUMEN_HOME_URL, active: false });
  await new Promise((resolve) => {
    const listener = (tabId, info) => {
      if (tabId === tab.id && info.status === "complete") {
        chrome.tabs.onUpdated.removeListener(listener);
        resolve();
      }
    };
    chrome.tabs.onUpdated.addListener(listener);
  });
  await new Promise((r) => setTimeout(r, 2000));
  return tab;
}

// Guards against overlapping refresh runs (e.g. alarm fires while a
// manual "Refresh from Lumen" click is still in flight) — same class of
// race the sync manager guards against with `_syncing`.
let _refreshing = null;

async function refreshLumenProgress() {
  if (_refreshing) return _refreshing;

  _refreshing = (async () => {
    const tab = await findOrOpenLumenTab();

    const response = await new Promise((resolve, reject) => {
      chrome.tabs.sendMessage(tab.id, { type: "FETCH_LUMEN_PROGRESS" }, (res) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
          return;
        }
        resolve(res);
      });
    });

    if (!response?.ok) {
      throw new Error(response?.error || "FETCH_LUMEN_PROGRESS_FAILED");
    }

    await Storage.set(CONFIG.STORAGE_KEYS.PROGRESS_CACHE, response.data);
    await Storage.setLastSync();

    broadcastProgressToWebApp(response.data).catch((e) =>
      Logger.debug("Web app broadcast failed (page may not be open):", e.message)
    );

    const signedIn = await Auth.isSignedIn();
    if (signedIn) {
      SyncManager.pushNow({ type: "progress_snapshot", data: response.data }).catch((e) =>
        Logger.debug("Backend push deferred:", e.message)
      );
    }

    return response.data;
  })();

  try {
    return await _refreshing;
  } finally {
    _refreshing = null;
  }
}

// Pushes to every open bits-dsai-tracker.web.app tab so the page updates
// live without the student needing to reload it. Best-effort — if no tab
// is open, this is a no-op; the page picks up the cache next time it
// loads and asks via ACADEMIC_OS_REQUEST_PROGRESS.
async function broadcastProgressToWebApp(progress) {
  const tabs = await chrome.tabs.query({ url: `${CONFIG.ACADEMIC_OS_ORIGIN}/*` });
  await Promise.allSettled(
    tabs.map(
      (tab) =>
        new Promise((resolve) => {
          chrome.tabs.sendMessage(tab.id, { type: "PUSH_PROGRESS_TO_PAGE", progress }, () => {
            if (chrome.runtime.lastError) Logger.debug("Tab push failed:", chrome.runtime.lastError.message);
            resolve();
          });
        })
    )
  );
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || typeof message.type !== "string" || !KNOWN_MESSAGE_TYPES.has(message.type)) {
    Logger.warn("Rejected unknown message type", message?.type, "from", sender.id);
    sendResponse({ ok: false, error: "UNKNOWN_MESSAGE_TYPE" });
    return false;
  }

  handleMessage(message, sender)
    .then(sendResponse)
    .catch((err) => {
      Logger.error(`Handler error for ${message.type}:`, err.message);
      sendResponse({ ok: false, error: err.message });
    });
  return true;
});

async function handleMessage(message, sender) {
  switch (message.type) {
    case "STORE_FIREBASE_TOKEN": {
      if (typeof message.token !== "string" || message.token.length < 10) {
        return { ok: false, error: "INVALID_TOKEN" };
      }
      await Auth.storeToken(message.token, message.expiresIn);
      if (message.user && typeof message.user === "object") await Auth.storeUserInfo(message.user);
      return { ok: true };
    }

    case "FETCH_LUMEN_PROGRESS": {
      try {
        const data = await refreshLumenProgress();
        return { ok: true, data };
      } catch (err) {
        return { ok: false, error: err.message };
      }
    }

    case "LUMEN_DATA_CAPTURED": {
      if (!message.normalized || typeof message.normalized !== "object" || !message.normalized.type) {
        Logger.debug("Ignored malformed LUMEN_DATA_CAPTURED payload");
        return { ok: false, error: "INVALID_PAYLOAD" };
      }
      const queueSize = await Storage.enqueueSyncItem(message.normalized);
      const signedIn = await Auth.isSignedIn();
      if (signedIn) SyncManager.pushNow(null).catch(() => {});
      return { ok: true, queueSize };
    }

    case "MANUAL_SYNC_REQUEST": {
      const signedIn = await Auth.isSignedIn();
      if (!signedIn) return { ok: false, error: "NOT_AUTHENTICATED" };
      const result = await SyncManager.pushNow(null);
      return { ok: true, ...result };
    }

    case "GET_STATUS": {
      const [authStatus, lastSync, queue, autoSync, progress, lastSyncStatus] = await Promise.all([
        Auth.getStatus(),
        Storage.get(CONFIG.STORAGE_KEYS.LAST_SYNC),
        Storage.getSyncQueue(),
        SyncManager.isAutoSyncEnabled(),
        Storage.get(CONFIG.STORAGE_KEYS.PROGRESS_CACHE),
        Storage.get(CONFIG.STORAGE_KEYS.LAST_SYNC_STATUS)
      ]);
      return {
        ok: true,
        signedIn: authStatus.signedIn,
        sessionExpired: authStatus.expired,
        user: authStatus.user,
        lastSync,
        lastSyncStatus: lastSyncStatus || "ok",
        queueSize: queue.length,
        queueFailingCount: queue.filter((q) => (q.attempts || 0) > 0).length,
        autoSyncEnabled: autoSync,
        courseCount: progress?.courses?.length ?? 0,
        lumenConnected: !!progress
      };
    }

    case "GET_PROGRESS_CACHE": {
      const progress = await Storage.get(CONFIG.STORAGE_KEYS.PROGRESS_CACHE);
      return { ok: true, progress };
    }

    case "SET_AUTO_SYNC": {
      await SyncManager.setAutoSyncEnabled(!!message.enabled);
      return { ok: true };
    }

    case "SIGN_OUT": {
      await Auth.clear();
      return { ok: true };
    }
  }
}
