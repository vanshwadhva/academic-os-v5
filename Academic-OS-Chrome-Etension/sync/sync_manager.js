// sync_manager.js — pushes queued progress snapshots to the backend.
// Storage.getSyncQueue() is the single source of truth; nothing is held
// only in memory, so a killed service worker or browser restart never
// loses a queued item (item 5: "browser restart recovery").

const SyncManager = {
  _syncing: false,

  async pushNow(newItem) {
    // Persist first, always — even if we're about to defer or fail, the
    // item is durable in storage before we ever touch the network.
    if (newItem) {
      await Storage.enqueueSyncItem(newItem);
      Logger.debug("Queued progress snapshot", newItem.type || "unknown");
    }

    if (this._syncing) {
      Logger.debug("Sync already in progress, item enqueued for the active run to pick up");
      return { synced: 0, failed: 0, deferred: true };
    }

    return this._drainQueue();
  },

  async _drainQueue() {
    this._syncing = true;
    try {
      const queue = await Storage.getSyncQueue();
      Logger.debug(`Sync queue contains ${queue.length} item(s)`);
      if (queue.length === 0) return { synced: 0, failed: 0 };

      if (CONFIG.BACKEND_SUPPORTS_BATCH_SYNC) {
        return await this._drainBatched(queue);
      }
      return await this._drainIndividually(queue);
    } finally {
      this._syncing = false;
    }
  },

  async _drainIndividually(queue) {
    let synced = 0;
    let failed = 0;
    const stillFailing = [];

    for (let i = 0; i < queue.length; i++) {
      const item = queue[i];

      if (item.attempts >= CONFIG.RETRY_MAX_ATTEMPTS) {
        Logger.warn("Dropping sync item after max retry attempts", item.idempotencyKey);
        continue; // dead-lettered: drop rather than retry forever
      }

      try {
        await ApiClient.syncPayload(item, item.idempotencyKey);
        Logger.debug("Synced progress snapshot", item.idempotencyKey);
        synced++;
      } catch (err) {
        if (err.message === "NOT_AUTHENTICATED" || err.message === "AUTH_EXPIRED") {
          // No point burning through the rest unauthenticated — keep them
          // queued as-is (don't increment attempts for an auth problem
          // that has nothing to do with the item itself).
          stillFailing.push(...queue.slice(i));
          await Storage.setLastSyncStatus("auth_expired");
          break;
        }
        if (err.message === "BACKEND_UNREACHABLE" || err.message === "REQUEST_TIMEOUT") {
          stillFailing.push(...queue.slice(i));
          await Storage.setLastSyncStatus("backend_offline");
          break;
        }
        item.attempts = (item.attempts || 0) + 1;
        item.lastError = err.message;
        stillFailing.push(item);
        failed++;
      }
    }

    await Storage.setSyncQueue(stillFailing);
    if (synced > 0) {
      await Storage.setLastSync();
      await Storage.setLastSyncStatus("ok");
    }
    return { synced, failed };
  },

  async _drainBatched(queue) {
    let synced = 0;
    let failed = 0;
    const stillFailing = [];

    for (let i = 0; i < queue.length; i += CONFIG.SYNC_BATCH_MAX_SIZE) {
      const batch = queue.slice(i, i + CONFIG.SYNC_BATCH_MAX_SIZE).filter((item) => item.attempts < CONFIG.RETRY_MAX_ATTEMPTS);
      if (batch.length === 0) continue;

      const batchKey = `batch:${batch.map((b) => b.idempotencyKey).join(",").slice(0, 200)}`;

      try {
        await ApiClient.syncBatch(batch, batchKey);
        Logger.debug(`Successfully synced batch of ${batch.length} item(s)`);
        synced += batch.length;
      } catch (err) {
        if (err.message === "NOT_AUTHENTICATED" || err.message === "AUTH_EXPIRED") {
          stillFailing.push(...queue.slice(i));
          await Storage.setLastSyncStatus("auth_expired");
          break;
        }
        if (err.message === "BACKEND_UNREACHABLE" || err.message === "REQUEST_TIMEOUT") {
          stillFailing.push(...queue.slice(i));
          await Storage.setLastSyncStatus("backend_offline");
          break;
        }
        // Batch itself failed for a non-retryable reason (e.g. one bad
        // item causing a 400) — fall back to per-item so one bad record
        // doesn't block the rest of the batch (partial success handling).
        Logger.warn("Batch sync failed, falling back to per-item for this batch:", err.message);
        for (const item of batch) {
          try {
            await ApiClient.syncPayload(item, item.idempotencyKey);
            Logger.debug("Synced progress snapshot", item.idempotencyKey);
            synced++;
          } catch (itemErr) {
            item.attempts = (item.attempts || 0) + 1;
            item.lastError = itemErr.message;
            stillFailing.push(item);
            failed++;
          }
        }
      }
    }

    await Storage.setSyncQueue(stillFailing);
    if (synced > 0) {
      await Storage.setLastSync();
      await Storage.setLastSyncStatus("ok");
    }
    return { synced, failed };
  },

  async syncLatestProgress(progress) {
    return this.pushNow({
      type: "progress_snapshot",
      timestamp: Date.now(),
      data: progress
    });
  },

  async isAutoSyncEnabled() {
    const val = await Storage.get(CONFIG.STORAGE_KEYS.AUTO_SYNC_ENABLED);
    return val !== false;
  },

  async setAutoSyncEnabled(enabled) {
    await Storage.set(CONFIG.STORAGE_KEYS.AUTO_SYNC_ENABLED, enabled);
  }
};

if (typeof globalThis !== "undefined") globalThis.SyncManager = SyncManager;
