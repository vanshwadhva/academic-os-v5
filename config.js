// config.js — classic script (no ES modules). Loaded via importScripts
// in the service worker and as a content script on Lumen pages.

const CONFIG = {
  DEBUG: false, // flip true during development; Logger.info/debug go silent when false

  ACADEMIC_OS_ORIGIN: "https://bits-dsai-tracker.web.app",
  API_BASE_URL: "https://academic-os-api.onrender.com", // update once/if you have a real backend behind this

  LUMEN_BASE_URL: "https://lumen.bitspilani-digital.edu.in",
  LUMEN_HOME_URL: "https://lumen.bitspilani-digital.edu.in/d2l/home",
  LUMEN_MATCH_PATTERN: "https://lumen.bitspilani-digital.edu.in/*",

  ENDPOINTS: {
    SYNC: "/api/lumen/sync",
    SYNC_BATCH: "/api/lumen/sync/batch", // used if BACKEND_SUPPORTS_BATCH_SYNC is true
    STATUS: "/api/lumen/status",
    HISTORY: "/api/lumen/history",
    MANUAL: "/api/lumen/manual"
  },

  // Flip to true once the backend actually exposes a batch endpoint that
  // accepts { events: [...] }. Until then individual POSTs are used, same
  // as before — this flag exists so turning batching on is a one-line
  // change instead of a rewrite.
  BACKEND_SUPPORTS_BATCH_SYNC: false,
  SYNC_BATCH_MAX_SIZE: 25,

  SYNC_INTERVAL_MINUTES: 15,
  RETRY_MAX_ATTEMPTS: 5,
  RETRY_BASE_DELAY_MS: 1000,
  RETRY_MAX_DELAY_MS: 30_000,
  REQUEST_TIMEOUT_MS: 15_000,

  // Sync-queue items older than this are dropped on the next cleanup pass
  // rather than retried forever (e.g. a grade payload from 3 weeks ago that
  // never synced because auth was broken the whole time — not worth
  // uploading stale data as if it were current).
  SYNC_QUEUE_MAX_AGE_MS: 7 * 24 * 60 * 60 * 1000, // 7 days
  SYNC_QUEUE_MAX_SIZE: 500, // hard cap; oldest items dropped beyond this

  LUMEN_API_PATTERNS: ["/d2l/api/le/", "/d2l/api/lp/", "/d2l/api/quiz/", "/d2l/api/discussions/"],

  STORAGE_KEYS: {
    FIREBASE_TOKEN: "academicos_firebase_token",
    TOKEN_EXPIRY: "academicos_firebase_token_expiry",
    USER_INFO: "academicos_user_info",
    LAST_SYNC: "academicos_last_sync",
    SYNC_QUEUE: "academicos_sync_queue",
    AUTO_SYNC_ENABLED: "academicos_auto_sync_enabled",
    PROGRESS_CACHE: "academicos_progress_cache",
    LAST_SYNC_STATUS: "academicos_last_sync_status", // "ok" | "auth_expired" | "backend_offline" | "lumen_offline"
    SEEN_MESSAGE_IDS: "academicos_seen_message_ids" // dedup ring buffer, see content.js
  }
};

if (typeof globalThis !== "undefined") globalThis.CONFIG = CONFIG;
