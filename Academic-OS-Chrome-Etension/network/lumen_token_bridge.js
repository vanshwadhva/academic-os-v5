// lumen_token_bridge.js — MAIN-world script on Lumen pages.
//
// STATUS: unverified / best-effort only. This attempts to read an
// "XSRF.Token" from localStorage and exchange it for an OAuth bearer
// token via /d2l/lp/auth/oauth2/token. That endpoint/flow does not match
// Brightspace's documented third-party OAuth2 (which requires a
// registered app with client_id/secret and a consent screen) — this was
// almost certainly never going to succeed against a real Lumen tenant.
//
// It is kept in the codebase (per architecture spec) but is now strictly
// optional and non-blocking: every failure path resolves to `null`
// instead of throwing, and active_fetcher.js treats a null token as
// "fine, use cookies" rather than "fatal". If this endpoint DOES turn out
// to work on BITS's tenant, active_fetcher.js will opportunistically
// attach the bearer token; if not, cookie-based same-origin auth (which
// is what actually works) carries the whole load, same as if this file
// didn't exist.

(() => {
  let cachedToken = null;
  let cachedExpiry = 0;

  async function fetchAccessToken() {
    if (cachedToken && Date.now() < cachedExpiry) return cachedToken;

    const xsrf = localStorage.getItem("XSRF.Token");
    if (!xsrf) return null;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);

    try {
      const res = await fetch("/d2l/lp/auth/oauth2/token", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded", "X-Csrf-Token": xsrf },
        credentials: "include",
        signal: controller.signal
      });

      if (!res.ok) return null;

      const data = await res.json().catch(() => null);
      if (!data?.access_token) return null;

      cachedToken = data.access_token;
      cachedExpiry = Date.now() + (data.expires_in || 3600) * 1000 - 60_000;
      return cachedToken;
    } catch {
      // Network error, timeout, non-JSON response, whatever — this path
      // is optional, so swallow and report "no token available."
      return null;
    } finally {
      clearTimeout(timeoutId);
    }
  }

  window.addEventListener("message", async (event) => {
    if (event.source !== window) return;
    if (event.origin !== window.location.origin) return;
    if (event.data?.type !== "__ACADEMIC_OS_REQUEST_LUMEN_TOKEN__") return;

    const token = await fetchAccessToken();
    window.postMessage(
      { type: "__ACADEMIC_OS_LUMEN_TOKEN_RESPONSE__", token, expiresIn: 3600 },
      window.location.origin
    );
  });

  // Opportunistic pre-fetch, also best-effort — never blocks page load,
  // never throws into the page's own error handling.
  if (window.location.pathname.includes("/d2l/home")) {
    fetchAccessToken().catch(() => {});
  }
})();
