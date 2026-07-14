// active_fetcher.js — isolated-world content script on Lumen.
//
// Proactively pulls courses, grades, assignments, modules/progress,
// quizzes, discussions, and announcements via Brightspace's internal API.
//
// Auth model: cookie-based same-origin fetch is the real mechanism here
// (this runs IN the Lumen page's origin, so `credentials: "include"`
// carries the actual session). lumen_token_bridge.js's OAuth attempt is
// optional and opportunistic — if it produces a token, we attach it;
// if not (the likely case — see that file's header comment), cookies
// alone carry the whole load, same as if the bridge didn't exist.

const REQUEST_TIMEOUT_MS = 12_000;

function requestLumenAccessToken() {
  return new Promise((resolve) => {
    const handler = (event) => {
      if (event.source !== window) return;
      if (event.origin !== window.location.origin) return;
      if (event.data?.type !== "__ACADEMIC_OS_LUMEN_TOKEN_RESPONSE__") return;
      window.removeEventListener("message", handler);
      resolve(event.data.token || null);
    };
    window.addEventListener("message", handler);
    window.postMessage({ type: "__ACADEMIC_OS_REQUEST_LUMEN_TOKEN__" }, window.location.origin);

    setTimeout(() => {
      window.removeEventListener("message", handler);
      resolve(null); // no bridge response in time — proceed on cookies alone
    }, 3000);
  });
}

async function apiGet(path, token) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;

  try {
    const res = await fetch(path, { credentials: "include", headers, signal: controller.signal });

    if (res.status === 401 || res.status === 403) {
      throw new Error(`NOT_LOGGED_IN: got ${res.status} from ${path}. Sign in at ${location.origin}/d2l/home and retry.`);
    }
    if (!res.ok) throw new Error(`FETCH_${res.status}:${path}`);

    const contentType = res.headers.get("content-type") || "";
    if (contentType.includes("application/json") || contentType.includes("application/problem+json")) {
      return await res.json();
    }
    if (contentType.includes("text/plain")) {
      const text = await res.text();
      try {
        return JSON.parse(text); // some D2L endpoints mislabel JSON as text/plain
      } catch {
        throw new Error(`UNPARSEABLE_TEXT:${path}`);
      }
    }
    // Binary or unexpected content type (images, octet-stream, etc.) —
    // not something we can or should normalize. Treat as a soft failure.
    throw new Error(`UNSUPPORTED_CONTENT_TYPE:${contentType}:${path}`);
  } catch (err) {
    if (err.name === "AbortError") throw new Error(`TIMEOUT:${path}`);
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

async function detectApiVersions(token) {
  const versions = await apiGet("/d2l/api/versions/", token);
  const pick = (code, fallback) =>
    versions.find((v) => v.ProductCode === code)?.LatestVersion?.ProductVersion || fallback;
  return { lp: pick("lp", "1.43"), le: pick("le", "1.79") };
}

function summarizeModuleProgress(toc) {
  if (!toc?.Modules) return { completed: 0, total: 0 };
  let completed = 0;
  let total = 0;
  const walk = (modules) => {
    for (const m of modules) {
      for (const t of m.Topics || []) {
        total++;
        if (t.LastVisitedDate) completed++;
      }
      if (m.Modules) walk(m.Modules);
    }
  };
  walk(toc.Modules);
  return { completed, total };
}

function asList(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.Objects)) return payload.Objects;
  if (Array.isArray(payload?.Items)) return payload.Items;
  if (Array.isArray(payload?.value)) return payload.value;
  return [];
}

async function fetchCourseDetail(orgUnitId, le, token) {
  const results = await Promise.allSettled([
    apiGet(`/d2l/api/le/${le}/${orgUnitId}/grades/values/myGradeValues/`, token),
    apiGet(`/d2l/api/le/${le}/${orgUnitId}/content/toc`, token),
    apiGet(`/d2l/api/le/${le}/${orgUnitId}/dropbox/folders/`, token),
    apiGet(`/d2l/api/le/${le}/${orgUnitId}/quizzes/`, token),
    apiGet(`/d2l/api/le/${le}/${orgUnitId}/discussions/topics/`, token),
    apiGet(`/d2l/api/le/${le}/${orgUnitId}/news/`, token) // announcements
  ]);

  const [gradesR, tocR, dropboxR, quizzesR, discussionsR, announcementsR] = results;
  const errors = [];
  const value = (r, label) => {
    if (r.status === "fulfilled") return r.value;
    errors.push(`${label}: ${r.reason.message}`);
    return null;
  };

  const grades = asList(value(gradesR, "grades"));
  const dropbox = asList(value(dropboxR, "assignments"));
  const quizzes = asList(value(quizzesR, "quizzes"));
  const discussions = asList(value(discussionsR, "discussions"));
  const announcements = asList(value(announcementsR, "announcements"));
  const toc = tocR.status === "fulfilled" ? tocR.value : null;
  if (tocR.status === "rejected") errors.push(`modules: ${tocR.reason.message}`);

  return {
    grades: grades.map((g) => ({
      title: g.GradeObjectName ?? "Unknown",
      pointsNumerator: g.PointsNumerator ?? null,
      pointsDenominator: g.PointsDenominator ?? null,
      percentage:
        g.PointsNumerator != null && g.PointsDenominator
          ? Math.round((g.PointsNumerator / g.PointsDenominator) * 1000) / 10
          : null
    })),
    moduleProgress: summarizeModuleProgress(toc),
    assignments: dropbox.map((a) => ({
      title: a.Name ?? "Unknown",
      dueDate: a.DueDate ?? null,
      status: a.CompletionStatus ?? "unknown"
    })),
    quizzes: quizzes.map((q) => ({
      title: q.Name ?? "Unknown",
      isActive: q.IsActive ?? null
    })),
    discussions: discussions.map((d) => ({
      title: d.Name ?? "Unknown",
      postCount: d.PostCount ?? null
    })),
    announcements: announcements.map((n) => ({
      title: n.Title ?? "Unknown",
      postedDate: n.StartDate ?? null
    })),
    fetchErrors: errors
  };
}

async function fetchAllLumenProgress() {
  const errors = [];
  const token = await requestLumenAccessToken(); // may be null — that's fine, see header comment

  const { lp, le } = await detectApiVersions(token); // throws NOT_LOGGED_IN early if session is dead

  const whoami = await apiGet(`/d2l/api/lp/${lp}/users/whoami`, token).catch((e) => {
    errors.push(String(e.message));
    return null;
  });

  const enrollments = await apiGet(`/d2l/api/lp/${lp}/enrollments/myenrollments/?orgUnitTypeId=3`, token).catch((e) => {
    errors.push(String(e.message));
    return { Items: [] };
  });

  const courses = [];
  for (const enrollment of enrollments.Items || []) {
    const orgUnitId = enrollment.OrgUnit?.Id;
    if (!orgUnitId) continue;
    try {
      const detail = await fetchCourseDetail(orgUnitId, le, token);
      courses.push({
        orgUnitId,
        courseName: enrollment.OrgUnit?.Name ?? "Unknown course",
        courseCode: enrollment.OrgUnit?.Code ?? null,
        ...detail
      });
    } catch (e) {
      errors.push(`course ${orgUnitId}: ${e.message}`);
    }
  }

  return {
    student: whoami
      ? { name: `${whoami.FirstName ?? ""} ${whoami.LastName ?? ""}`.trim(), userId: whoami.Identifier ?? null }
      : null,
    courses,
    fetchedAt: new Date().toISOString(),
    errors
  };
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "FETCH_LUMEN_PROGRESS") return;
  fetchAllLumenProgress()
    .then((data) => sendResponse({ ok: true, data }))
    .catch((err) => sendResponse({ ok: false, error: err.message }));
  return true; // async response
});
