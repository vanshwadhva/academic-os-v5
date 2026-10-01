// auth.js — caches Firebase ID token relayed from the Academic OS web app.
// No Firebase SDK here by design (see PRD) — the frontend does real auth,
// this just caches and validates the token it's handed.

const Auth = {
  async storeToken(idToken, expiresInSeconds = 3600) {
    const { STORAGE_KEYS } = CONFIG;
    const expiry = Date.now() + expiresInSeconds * 1000;
    await Storage.set(STORAGE_KEYS.FIREBASE_TOKEN, idToken);
    await Storage.set(STORAGE_KEYS.TOKEN_EXPIRY, expiry);
    Logger.info("Firebase token stored, expires", new Date(expiry).toISOString());
  },

  async storeUserInfo(userInfo) {
    await Storage.set(CONFIG.STORAGE_KEYS.USER_INFO, userInfo);
  },

  async getToken() {
    return Storage.get(CONFIG.STORAGE_KEYS.FIREBASE_TOKEN);
  },

  async getUserInfo() {
    return Storage.get(CONFIG.STORAGE_KEYS.USER_INFO);
  },

  // Full status object so callers (popup, background) can distinguish
  // "never signed in" from "was signed in, token expired" — those need
  // different UI/recovery behavior.
  async getStatus() {
    const { STORAGE_KEYS } = CONFIG;
    const [token, expiry, userInfo] = await Promise.all([
      Storage.get(STORAGE_KEYS.FIREBASE_TOKEN),
      Storage.get(STORAGE_KEYS.TOKEN_EXPIRY),
      Storage.get(STORAGE_KEYS.USER_INFO)
    ]);

    if (!token) {
      return { signedIn: false, expired: false, expiringSoon: false, user: userInfo };
    }

    const msRemaining = (expiry ?? 0) - Date.now();
    return {
      signedIn: msRemaining > 120_000, // 2-min safety margin before real expiry
      expired: msRemaining <= 0,
      expiringSoon: msRemaining > 0 && msRemaining <= 5 * 60_000, // under 5 min left
      user: userInfo
    };
  },

  async isTokenValid() {
    const status = await this.getStatus();
    return status.signedIn;
  },

  async isSignedIn() {
    return this.isTokenValid();
  },

  async authHeader() {
    const valid = await this.isTokenValid();
    if (!valid) return null;
    const token = await this.getToken();
    return { Authorization: `Bearer ${token}` };
  },

  // Called on AUTH_EXPIRED (401 from backend) or natural expiry detection.
  // Keeps user info so the popup can still say "Hi <name>, session expired"
  // instead of falling back to a generic signed-out state.
  async clearToken() {
    const { STORAGE_KEYS } = CONFIG;
    await Storage.remove(STORAGE_KEYS.FIREBASE_TOKEN);
    await Storage.remove(STORAGE_KEYS.TOKEN_EXPIRY);
    await Storage.set(STORAGE_KEYS.LAST_SYNC_STATUS, "auth_expired");
    Logger.warn("Firebase token cleared (expired or rejected by backend)");
  },

  // Explicit sign-out — clears everything, including cached user info.
  async clear() {
    await Storage.clearAuth();
    Logger.info("Signed out, all auth state cleared");
  }
};

if (typeof globalThis !== "undefined") globalThis.Auth = Auth;
