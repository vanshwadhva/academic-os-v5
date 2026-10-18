// Frontend configuration - can be overridden at build time or runtime
window.APP_CONFIG = {
  // Backend API URL - set at build time via environment variable
  // For local development, this will be overridden by the script in index.html
  API_URL: window.APP_CONFIG?.API_URL || "https://academic-os-api.onrender.com",

  // Firebase configuration (set in index.html from Firebase console)
  FIREBASE_CONFIG: window.APP_CONFIG?.FIREBASE_CONFIG || {},

  // Google OAuth client ID used only by the Chrome extension build (chrome.identity sign-in).
  // It is a public identifier, not a secret. Empty in the hosted web app.
  GOOGLE_OAUTH_CLIENT_ID: window.APP_CONFIG?.GOOGLE_OAUTH_CLIENT_ID || "",

  // Feature flags
  ENABLE_LUMEN_SYNC: true,
  ENABLE_PREDICTIONS: true,
  ENABLE_ADMIN_DASHBOARD: true
};

// Auto-detect local development
if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
  window.APP_CONFIG.API_URL = "http://localhost:8000";
}