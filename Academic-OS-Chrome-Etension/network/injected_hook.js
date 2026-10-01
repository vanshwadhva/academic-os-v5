// injected_hook.js — MAIN world: intercepts page fetch/XHR for passive
// capture. Ignores OPTIONS/HEAD (no useful body), binary responses, and
// anything outside the known API path patterns.

(() => {
  const PATTERNS = [
    "/d2l/api/le/",
    "/d2l/api/lp/",
    "/d2l/api/quiz/",
    "/d2l/api/discussions/"
  ];
  const IGNORED_METHODS = new Set(["OPTIONS", "HEAD"]);
  const JSON_LIKE = ["application/json", "application/problem+json", "text/plain"];

  const matchesPattern = (url) => typeof url === "string" && PATTERNS.some((p) => url.includes(p));
  const isJsonLike = (contentType) => JSON_LIKE.some((t) => (contentType || "").includes(t));

  const emit = (url, method, status, body) => {
    window.postMessage(
      {
        source: "academic-os-injected-hook",
        type: "LUMEN_API_CAPTURED",
        payload: { url, method, status, body, capturedAt: Date.now() }
      },
      window.location.origin
    );
  };

  const originalFetch = window.fetch;
  window.fetch = async function (...args) {
    const response = await originalFetch.apply(this, args);

    try {
      const url = typeof args[0] === "string" ? args[0] : args[0]?.url;
      const method = (args[1]?.method || "GET").toUpperCase();

      if (url && matchesPattern(url) && !IGNORED_METHODS.has(method)) {
        const contentType = response.headers.get("content-type");
        if (isJsonLike(contentType)) {
          const clone = response.clone();
          clone
            .text()
            .then((text) => {
              try {
                emit(url, method, response.status, JSON.parse(text));
              } catch {
                /* malformed JSON — drop silently, don't forward garbage */
              }
            })
            .catch(() => {});
        }
        // else: binary or unrecognized content type, ignore per spec
      }
    } catch {
      /* never let interception break the page's real request */
    }

    return response;
  };

  const originalOpen = XMLHttpRequest.prototype.open;
  const originalSend = XMLHttpRequest.prototype.send;

  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.__academicOsUrl = url;
    this.__academicOsMethod = (method || "GET").toUpperCase();
    return originalOpen.call(this, method, url, ...rest);
  };

  XMLHttpRequest.prototype.send = function (...args) {
    if (
      this.__academicOsUrl &&
      matchesPattern(this.__academicOsUrl) &&
      !IGNORED_METHODS.has(this.__academicOsMethod)
    ) {
      this.addEventListener("load", function () {
        const contentType = this.getResponseHeader("content-type");
        if (!isJsonLike(contentType)) return; // binary/unknown — ignore
        try {
          const body = JSON.parse(this.responseText);
          emit(this.__academicOsUrl, this.__academicOsMethod, this.status, body);
        } catch {
          /* malformed JSON — drop silently */
        }
      });
    }
    return originalSend.apply(this, args);
  };
})();
