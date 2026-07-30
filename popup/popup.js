const ACADEMIC_OS_SIGNIN_URL =
  (typeof CONFIG !== "undefined" && CONFIG.ACADEMIC_OS_SIGNIN_URL) ||
  "http://127.0.0.1:5500/index.html";

const el = (id) => document.getElementById(id);

function sendMessage(message) {
  return chrome.runtime.sendMessage(message);
}

function formatLastSync(ts) {
  if (!ts) return "Never";
  const mins = Math.floor((Date.now() - ts) / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return new Date(ts).toLocaleDateString();
}

function renderSyncBanner(status) {
  const banner = el("sync-state-banner");

  if (navigator.onLine === false) {
    banner.textContent = "You're offline — will retry once connected.";
    banner.className = "sync-banner warn";
    banner.classList.remove("hidden");
    return;
  }

  if (status.sessionExpired) {
    banner.textContent = "Your Academic OS session expired — reopen it to sign in again.";
    banner.className = "sync-banner warn";
    banner.classList.remove("hidden");
    return;
  }

  if (status.lastSyncStatus === "backend_offline") {
    banner.textContent = "Backend unreachable — data is queued locally and will sync once it's back.";
    banner.className = "sync-banner error";
    banner.classList.remove("hidden");
    return;
  }

  if (status.lastSyncStatus === "auth_expired") {
    banner.textContent = "Backend rejected your session — reopen Academic OS to refresh it.";
    banner.className = "sync-banner warn";
    banner.classList.remove("hidden");
    return;
  }

  banner.classList.add("hidden");
}

function renderQueueRow(status) {
  const row = el("queue-row");
  if (status.queueSize === 0) {
    row.classList.add("hidden");
    return;
  }
  row.classList.remove("hidden");
  const retryPart = status.queueFailingCount > 0 ? `, ${status.queueFailingCount} retrying` : "";
  row.textContent = `${status.queueSize} item(s) queued for sync${retryPart}`;
}

async function render() {
  const status = await sendMessage({ type: "GET_STATUS" });

  const lumenEl = el("lumen-status");
  if (status.lumenConnected || status.courseCount > 0) {
    lumenEl.textContent = "Lumen session connected";
    lumenEl.className = "lumen-status connected small";
  } else {
    lumenEl.textContent = "Open Lumen home and sign in to pull progress";
    lumenEl.className = "lumen-status muted small";
  }

  el("status-dot").className = "status-dot " + (status.signedIn ? "online" : "offline");
  el("course-count").textContent = status.courseCount ?? 0;
  el("last-sync").textContent = formatLastSync(status.lastSync);
  el("auto-sync-toggle").checked = !!status.autoSyncEnabled;

  renderSyncBanner(status);
  renderQueueRow(status);

  const authRow = el("academic-os-auth");
  authRow.classList.remove("hidden");

  if (status.signedIn) {
    el("user-info").textContent = status.user?.email || "Signed in";
    el("sign-out-btn").classList.remove("hidden");
  } else if (status.sessionExpired && status.user) {
    // Was signed in, token expired — different message than "never signed in".
    el("user-info").innerHTML =
      `Session expired for ${status.user.email || "your account"}. <a href="#" id="open-academic-os-link">Reopen Academic OS</a> to refresh.`;
    el("open-academic-os-link").addEventListener("click", (e) => {
      e.preventDefault();
      chrome.tabs.create({ url: ACADEMIC_OS_SIGNIN_URL });
    });
    el("sign-out-btn").classList.remove("hidden");
  } else {
    el("user-info").innerHTML =
      'Not signed in to Academic OS. <a href="#" id="open-academic-os-link">Sign in</a> to sync to cloud.';
    el("open-academic-os-link").addEventListener("click", (e) => {
      e.preventDefault();
      chrome.tabs.create({ url: ACADEMIC_OS_SIGNIN_URL });
    });
    el("sign-out-btn").classList.add("hidden");
  }
}

el("refresh-btn").addEventListener("click", async () => {
  const btn = el("refresh-btn");
  const msgEl = el("popup-message");
  const originalLabel = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Syncing…";
  msgEl.textContent = "Pulling from Lumen… (uses your Lumen login session)";

  const result = await sendMessage({ type: "FETCH_LUMEN_PROGRESS" });

  btn.disabled = false;
  btn.textContent = originalLabel;

  if (!result.ok) {
    msgEl.textContent = `Failed: ${result.error}`;
  } else {
    msgEl.textContent = `Pulled ${result.data.courses.length} course(s).`;
    await render();
  }
  setTimeout(() => (msgEl.textContent = ""), 6000);
});

el("dashboard-btn").addEventListener("click", () => {
  chrome.tabs.create({ url: chrome.runtime.getURL("dashboard/dashboard.html") });
});

el("auto-sync-toggle").addEventListener("change", async (e) => {
  await sendMessage({ type: "SET_AUTO_SYNC", enabled: e.target.checked });
});

el("sign-out-btn").addEventListener("click", async () => {
  await sendMessage({ type: "SIGN_OUT" });
  await render();
});

window.addEventListener("online", render);
window.addEventListener("offline", render);

render();
