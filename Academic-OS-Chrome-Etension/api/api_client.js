// api_client.js — talks to the Render FastAPI backend with Firebase auth.
// Adds: request timeout via AbortController, request IDs, idempotency
// keys on writes, jittered exponential backoff, and error classification
// that the rest of the extension (popup, sync manager) can act on.

const ApiClient = {
  async request(path, { method = "GET", body = null, retry = true, idempotencyKey = null } = {}) {
    const authHeader = await Auth.authHeader();
    if (!authHeader) {
      throw new Error("NOT_AUTHENTICATED");
    }

    const url = `${CONFIG.API_BASE_URL}${path}`;
    const requestId = (self.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`);

    const headers = {
      "Content-Type": "application/json",
      "X-Request-Id": requestId,
      ...authHeader
    };
    if (idempotencyKey) headers["X-Idempotency-Key"] = idempotencyKey;

    const maxAttempts = retry ? CONFIG.RETRY_MAX_ATTEMPTS : 1;
    let lastErr;

    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), CONFIG.REQUEST_TIMEOUT_MS);

      try {
        const response = await fetch(url, {
          method,
          headers,
          body: body ? JSON.stringify(body) : undefined,
          signal: controller.signal
        });
        clearTimeout(timeoutId);

        if (response.status === 401) {
          await Auth.clearToken(); // keep user info; this is "expired", not "signed out"
          throw new Error("AUTH_EXPIRED");
        }

        if (response.status === 429 || response.status >= 500) {
          throw new Error(`RETRYABLE_${response.status}`);
        }

        if (!response.ok) {
          const text = await response.text().catch(() => "");
          throw new Error(`REQUEST_FAILED_${response.status}: ${text}`);
        }

        return response.status === 204 ? null : response.json();
      } catch (err) {
        clearTimeout(timeoutId);

        const isAbort = err.name === "AbortError";
        const isNetworkFailure = err.name === "TypeError"; // fetch throws TypeError for DNS/connection failures
        const isRetryableHttp = err.message?.startsWith("RETRYABLE_");
        const isRetryable = isAbort || isNetworkFailure || isRetryableHttp;

        lastErr = isAbort
          ? new Error("REQUEST_TIMEOUT")
          : isNetworkFailure
          ? new Error("BACKEND_UNREACHABLE")
          : err;

        const isLastAttempt = attempt === maxAttempts;
        if (!isRetryable || isLastAttempt) {
          Logger.error(`Request failed [${method} ${path}] attempt ${attempt}/${maxAttempts}:`, lastErr.message);
          throw lastErr;
        }

        const backoff = Math.min(CONFIG.RETRY_BASE_DELAY_MS * 2 ** (attempt - 1), CONFIG.RETRY_MAX_DELAY_MS);
        const jitter = backoff * (0.5 + Math.random() * 0.5); // 50-100% of backoff, avoids thundering herd
        Logger.warn(`Retrying [${method} ${path}] in ${Math.round(jitter)}ms (attempt ${attempt}/${maxAttempts})`);
        await new Promise((r) => setTimeout(r, jitter));
      }
    }

    throw lastErr;
  },

  syncPayload(payload, idempotencyKey) {
    return this.request(CONFIG.ENDPOINTS.SYNC, { method: "POST", body: payload, idempotencyKey });
  },

  syncBatch(events, idempotencyKey) {
    return this.request(CONFIG.ENDPOINTS.SYNC_BATCH, { method: "POST", body: { events }, idempotencyKey });
  },

  getStatus() {
    return this.request(CONFIG.ENDPOINTS.STATUS, { method: "GET" });
  },

  getHistory() {
    return this.request(CONFIG.ENDPOINTS.HISTORY, { method: "GET" });
  },

  manualSync(payload) {
    return this.request(CONFIG.ENDPOINTS.MANUAL, { method: "POST", body: payload });
  }
};

if (typeof globalThis !== "undefined") globalThis.ApiClient = ApiClient;
