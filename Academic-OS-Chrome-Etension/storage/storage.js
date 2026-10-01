// storage.js — thin async wrapper over chrome.storage.local, plus the
// sync-queue lifecycle (dedup, cleanup, idempotency keys).

const Storage = {
  async get(key) {
    const result = await chrome.storage.local.get(key);
    return result[key] ?? null;
  },

  async getMultiple(keys) {
    return chrome.storage.local.get(keys);
  },

  async set(key, value) {
    await chrome.storage.local.set({ [key]: value });
  },

  async remove(key) {
    await chrome.storage.local.remove(key);
  },

  // Full sign-out only. Token-expiry (still signed in, just needs a
  // fresh token) goes through Auth.clearToken() instead, which keeps
  // USER_INFO so the popup can show a meaningful "session expired" state
  // rather than falling back to a bare signed-out screen.
  async clearAuth() {
    const { STORAGE_KEYS } = CONFIG;
    await chrome.storage.local.remove([STORAGE_KEYS.FIREBASE_TOKEN, STORAGE_KEYS.TOKEN_EXPIRY, STORAGE_KEYS.USER_INFO]);
  },

  _idFor(item) {
    // Stable id from type + a shallow content fingerprint, so the exact
    // same capture queued twice (e.g. network_monitor firing on the same
    // API response twice) collapses to one entry instead of duplicating
    // the sync payload.
    const fingerprint = JSON.stringify(item.data ?? item).slice(0, 300);
    return `${item.type || "unknown"}:${fingerprint.length}:${simpleHash(fingerprint)}`;
  },

  async enqueueSyncItem(item) {
    const queue = (await this.getSyncQueue());
    const idempotencyKey = item.idempotencyKey || this._idFor(item);

    const alreadyQueued = queue.some((q) => q.idempotencyKey === idempotencyKey);
    if (alreadyQueued) {
      Logger.debug("Duplicate sync item ignored", idempotencyKey);
      return queue.length;
    }

    queue.push({ ...item, idempotencyKey, queued_at: Date.now(), attempts: 0 });

    const trimmed = this._enforceQueueLimits(queue);
    await this.setSyncQueue(trimmed);
    return trimmed.length;
  },

  _enforceQueueLimits(queue) {
    const now = Date.now();
    let result = queue.filter((item) => now - item.queued_at < CONFIG.SYNC_QUEUE_MAX_AGE_MS);

    if (result.length !== queue.length) {
      Logger.warn(`Dropped ${queue.length - result.length} stale sync item(s) older than max age`);
    }

    if (result.length > CONFIG.SYNC_QUEUE_MAX_SIZE) {
      const overflow = result.length - CONFIG.SYNC_QUEUE_MAX_SIZE;
      result = result.slice(overflow); // drop oldest first, keep most recent
      Logger.warn(`Sync queue over size limit, dropped ${overflow} oldest item(s)`);
    }

    return result;
  },

  async cleanupSyncQueue() {
    const queue = await this.getSyncQueue();
    const cleaned = this._enforceQueueLimits(queue);
    if (cleaned.length !== queue.length) await this.setSyncQueue(cleaned);
    return cleaned.length;
  },

  async getSyncQueue() {
    return (await this.get(CONFIG.STORAGE_KEYS.SYNC_QUEUE)) || [];
  },

  async setSyncQueue(queue) {
    await this.set(CONFIG.STORAGE_KEYS.SYNC_QUEUE, queue);
  },

  async setLastSync(timestamp = Date.now()) {
    await this.set(CONFIG.STORAGE_KEYS.LAST_SYNC, timestamp);
  },

  async setLastSyncStatus(status) {
    await this.set(CONFIG.STORAGE_KEYS.LAST_SYNC_STATUS, status);
  }
};

// Small non-cryptographic hash — this is for dedup fingerprinting, not
// security, so FNV-1a is plenty and has zero dependencies.
function simpleHash(str) {
  let hash = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    hash ^= str.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(36);
}

if (typeof globalThis !== "undefined") globalThis.Storage = Storage;
