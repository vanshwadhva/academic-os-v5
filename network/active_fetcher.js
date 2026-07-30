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

function asList(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.Objects)) return payload.Objects;
  if (Array.isArray(payload?.Items)) return payload.Items;
  if (Array.isArray(payload?.value)) return payload.value;
  return [];
}

function countTocTopics(toc) {
  if (!toc?.Modules) return 0;
  let total = 0;
  const walk = (modules) => {
    for (const m of modules || []) {
      total += (m.Topics || []).length;
      if (m.Modules) walk(m.Modules);
    }
  };
  walk(toc.Modules);
  return total;
}

function topicLooksVisited(topic) {
  return !!(
    topic?.LastVisitedDate ||
    topic?.LastViewedDate ||
    topic?.DateLastVisited ||
    topic?.IsVisited ||
    topic?.Visited ||
    topic?.IsCompleted ||
    topic?.IsComplete ||
    topic?.CompletionDate ||
    topic?.CompletedDate
  );
}

function summarizeFromToc(toc) {
  if (!toc?.Modules) return { completed: 0, total: 0 };
  let completed = 0;
  let total = 0;
  const walk = (modules) => {
    for (const m of modules || []) {
      for (const t of m.Topics || []) {
        total++;
        if (topicLooksVisited(t)) completed++;
      }
      if (m.Modules) walk(m.Modules);
    }
  };
  walk(toc.Modules);
  return { completed, total };
}

function summarizeFromUserProgress(rows, tocTotal) {
  const list = asList(rows);
  let visited = 0;
  let completed = 0;
  let visits = 0;
  let timeSpentSeconds = 0;
  for (const row of list) {
    if (row.Visited || row.IsRead || row.LastVisited || Number(row.NumVisits) > 0) visited++;
    if (row.Completed || row.CompletedDate) completed++;
    visits += Number(row.NumVisits) || 0;
    timeSpentSeconds += Number(row.TotalTime) || 0;
  }
  // Lumen "Topics Visited" ≈ Visited; "Completed" ≈ Completed. Prefer completed for checklist %.
  const done = Math.max(completed, visited);
  return {
    completed: done,
    total: Math.max(tocTotal || 0, list.length, done),
    visited,
    completedStrict: completed,
    visits,
    timeSpentSeconds
  };
}

function summarizeFromMyCount(payload) {
  const rows = asList(payload);
  if (!rows.length) return null;

  // Org-unit aggregate when present (ObjectId === 0).
  const orgLevel = rows.find((r) => Number(r.ObjectId) === 0);
  if (orgLevel) {
    const total = Number(orgLevel.RequiredItems);
    const completed = Number(orgLevel.CompletedItems);
    if (Number.isFinite(total) && total > 0) {
      return {
        completed: Number.isFinite(completed) ? completed : 0,
        total,
        source: "completions/mycount"
      };
    }
  }

  // Module-level rows: sum required/completed across modules.
  let total = 0;
  let completed = 0;
  for (const row of rows) {
    const req = Number(row.RequiredItems);
    const done = Number(row.CompletedItems);
    if (Number.isFinite(req)) total += req;
    if (Number.isFinite(done)) completed += done;
  }
  if (total <= 0) return null;
  return { completed, total, source: "completions/mycount-sum" };
}

async function apiGetOptional(path, token) {
  try {
    return { ok: true, data: await apiGet(path, token) };
  } catch (err) {
    return { ok: false, error: String(err.message || err) };
  }
}

async function fetchMyCount(le, orgUnitId, token) {
  // Brightspace requires a completion aggregation level on some tenants.
  const candidates = [
    `/d2l/api/le/${le}/${orgUnitId}/content/completions/mycount/?level=1`,
    `/d2l/api/le/${le}/${orgUnitId}/content/completions/mycount/?level=OrgUnit`,
    `/d2l/api/le/${le}/${orgUnitId}/content/completions/mycount/`,
    `/d2l/api/le/${le}/${orgUnitId}/content/completions/mycount/?level=2`,
    `/d2l/api/le/${le}/${orgUnitId}/content/completions/mycount/?level=3`
  ];
  const errors = [];
  for (const path of candidates) {
    const res = await apiGetOptional(path, token);
    if (!res.ok) {
      errors.push(res.error);
      continue;
    }
    const summary = summarizeFromMyCount(res.data);
    if (summary) return { summary, errors };
  }
  return { summary: null, errors };
}

async function fetchAllUserProgress(le, orgUnitId, userId, token) {
  const collected = [];
  const errors = [];
  const starts = [];
  if (userId) {
    starts.push(`/d2l/api/le/${le}/${orgUnitId}/content/userprogress/?userId=${encodeURIComponent(userId)}&pageSize=200`);
  }
  // Calling-user context (no userId) — works when the session user is the learner.
  starts.push(`/d2l/api/le/${le}/${orgUnitId}/content/userprogress/?pageSize=200`);

  for (const start of starts) {
    let path = start;
    let gotAny = false;
    for (let page = 0; page < 25 && path; page++) {
      const res = await apiGetOptional(path, token);
      if (!res.ok) {
        errors.push(res.error);
        break;
      }
      const batch = asList(res.data);
      if (batch.length) gotAny = true;
      collected.push(...batch);
      const next = res.data?.Next || res.data?.PagingInfo?.Next || null;
      if (!next) break;
      path = String(next).startsWith("http")
        ? new URL(next).pathname + new URL(next).search
        : next;
    }
    if (gotAny) break;
  }
  return { rows: collected, errors };
}

/** One call covering all org units: CompletedItems / RequiredItems per course. */
async function fetchLearnerCompletionsByOrgUnit(le, userId, token) {
  if (!userId) return { map: new Map(), errors: ["no userId for completions"] };
  const paths = [
    `/d2l/api/le/${le}/content/completions/${encodeURIComponent(userId)}/`,
    `/d2l/api/le/${le}/content/completions/${encodeURIComponent(userId)}/?pageSize=100`
  ];
  const errors = [];
  for (const path of paths) {
    const res = await apiGetOptional(path, token);
    if (!res.ok) {
      errors.push(res.error);
      continue;
    }
    const map = new Map();
    for (const row of asList(res.data)) {
      const orgId = Number(row.OrgUnitId);
      const total = Number(row.RequiredItems);
      const completed = Number(row.CompletedItems);
      if (!Number.isFinite(orgId)) continue;
      if (!Number.isFinite(total) || total <= 0) continue;
      map.set(orgId, {
        completed: Number.isFinite(completed) ? completed : 0,
        total,
        source: "content/completions/userId"
      });
    }
    if (map.size) return { map, errors };
  }
  return { map: new Map(), errors };
}

function buildModuleProgress({ toc, myCountSummary, userProgressRows, learnerCompletion }) {
  const tocSummary = summarizeFromToc(toc);
  const tocTotal = tocSummary.total || learnerCompletion?.total || 0;
  const progressSummary = summarizeFromUserProgress(userProgressRows, tocTotal);

  // 1) Official per-user completion rollup (best match to Lumen UI).
  if (learnerCompletion && learnerCompletion.total > 0) {
    return {
      completed: learnerCompletion.completed,
      total: learnerCompletion.total,
      visited: progressSummary.visited || learnerCompletion.completed,
      visits: progressSummary.visits || 0,
      timeSpentSeconds: progressSummary.timeSpentSeconds || 0,
      source: learnerCompletion.source
    };
  }
  // 2) mycount for this org unit
  if (myCountSummary && myCountSummary.total > 0) {
    return {
      completed: myCountSummary.completed,
      total: myCountSummary.total,
      visited: progressSummary.visited || myCountSummary.completed,
      visits: progressSummary.visits || 0,
      timeSpentSeconds: progressSummary.timeSpentSeconds || 0,
      source: myCountSummary.source
    };
  }
  // 3) userprogress rows (Visited / NumVisits)
  if (progressSummary.completed > 0 || progressSummary.visited > 0) {
    return {
      completed: progressSummary.completed,
      total: Math.max(tocTotal, progressSummary.total, progressSummary.completed),
      visited: progressSummary.visited,
      visits: progressSummary.visits,
      timeSpentSeconds: progressSummary.timeSpentSeconds,
      source: "userprogress"
    };
  }
  // 4) TOC only — totals may be right, completed usually 0 without visit fields
  return {
    completed: tocSummary.completed,
    total: tocSummary.total,
    visited: tocSummary.completed,
    visits: 0,
    timeSpentSeconds: 0,
    source: "toc-fallback"
  };
}

async function fetchCourseDetail(orgUnitId, le, token, userId, learnerCompletion) {
  const results = await Promise.allSettled([
    apiGet(`/d2l/api/le/${le}/${orgUnitId}/grades/values/myGradeValues/`, token),
    apiGet(`/d2l/api/le/${le}/${orgUnitId}/content/toc`, token),
    apiGet(`/d2l/api/le/${le}/${orgUnitId}/dropbox/folders/`, token),
    apiGet(`/d2l/api/le/${le}/${orgUnitId}/quizzes/`, token),
    apiGet(`/d2l/api/le/${le}/${orgUnitId}/discussions/topics/`, token),
    apiGet(`/d2l/api/le/${le}/${orgUnitId}/news/`, token),
    fetchMyCount(le, orgUnitId, token),
    fetchAllUserProgress(le, orgUnitId, userId, token)
  ]);

  const [gradesR, tocR, dropboxR, quizzesR, discussionsR, announcementsR, myCountR, userProgressR] = results;
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

  const myCountPack = myCountR.status === "fulfilled" ? myCountR.value : { summary: null, errors: [myCountR.reason?.message] };
  const userProgressPack =
    userProgressR.status === "fulfilled" ? userProgressR.value : { rows: [], errors: [userProgressR.reason?.message] };
  (myCountPack.errors || []).forEach((e) => errors.push(`completions: ${e}`));
  (userProgressPack.errors || []).forEach((e) => errors.push(`userprogress: ${e}`));

  const moduleProgress = buildModuleProgress({
    toc,
    myCountSummary: myCountPack.summary,
    userProgressRows: userProgressPack.rows || [],
    learnerCompletion: learnerCompletion || null
  });

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
    moduleProgress,
    tocTopicCount: countTocTopics(toc),
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

  const lumenUserId = whoami?.Identifier ?? whoami?.UniqueName ?? null;

  const learnerCompletions = await fetchLearnerCompletionsByOrgUnit(le, lumenUserId, token);
  (learnerCompletions.errors || []).forEach((e) => errors.push(`learnerCompletions: ${e}`));

  const courses = [];
  for (const enrollment of enrollments.Items || []) {
    const orgUnitId = enrollment.OrgUnit?.Id;
    if (!orgUnitId) continue;
    try {
      const detail = await fetchCourseDetail(
        orgUnitId,
        le,
        token,
        lumenUserId,
        learnerCompletions.map.get(Number(orgUnitId)) || null
      );
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
