// network_monitor.js — passive capture relay from injected_hook.js.
// Normalizes raw Brightspace payloads into the backend's expected schema.
// Unknown shapes are ignored rather than uploaded as raw payloads.

const Normalizer = {
  normalize(url, body) {
    if (url.includes("/d2l/api/le/") && url.includes("grades")) return this.normalizeGrades(body);
    if (url.includes("/d2l/api/le/") && url.includes("dropbox")) return this.normalizeAssignments(body);
    if (url.includes("/d2l/api/lp/") && url.includes("enrollments")) return this.normalizeCourses(body);
    if (url.includes("/d2l/api/le/") && url.includes("quizzes")) return this.normalizeQuizzes(body);
    if (url.includes("/d2l/api/le/") && url.includes("discussions")) return this.normalizeDiscussions(body);
    if (url.includes("/d2l/api/le/") && url.includes("news")) return this.normalizeAnnouncements(body);
    return null; // unrecognized shape — never forward raw payloads to the backend
  },

  _asList(body) {
    if (Array.isArray(body)) return body;
    if (Array.isArray(body?.Objects)) return body.Objects;
    if (Array.isArray(body?.Items)) return body.Items;
    return [];
  },

  normalizeGrades(body) {
    const items = this._asList(body)
      .map((g) => ({
        title: g.Name ?? g.GradeObjectName ?? null,
        score: g.PointsNumerator ?? g.score ?? null,
        percentage: g.WeightedDenominator ? (g.PointsNumerator / g.WeightedDenominator) * 100 : g.percentage ?? null,
        published_at: g.LastModified ?? g.publishedAt ?? null
      }))
      .filter((g) => g.title != null); // required field check

    if (items.length === 0) return null;
    return { type: "grades", data: items };
  },

  normalizeAssignments(body) {
    const items = this._asList(body)
      .map((a) => ({
        title: a.Name ?? null,
        due_date: a.DueDate ?? null,
        status: a.CompletionStatus ?? a.SubmissionStatus ?? "unknown",
        marks: a.Score ?? null
      }))
      .filter((a) => a.title != null);

    if (items.length === 0) return null;
    return { type: "assignments", data: items };
  },

  normalizeCourses(body) {
    const items = this._asList(body)
      .map((c) => ({
        course_name: c.OrgUnit?.Name ?? null,
        semester: c.OrgUnit?.Code ?? null,
        instructor: c.Instructor ?? null
      }))
      .filter((c) => c.course_name != null);

    if (items.length === 0) return null;
    return { type: "courses", data: items };
  },

  normalizeQuizzes(body) {
    const items = this._asList(body)
      .map((q) => ({
        title: q.Name ?? null,
        attempts: q.AttemptsAllowed ?? null,
        marks: q.Score ?? null,
        percentage: q.percentage ?? null
      }))
      .filter((q) => q.title != null);

    if (items.length === 0) return null;
    return { type: "quizzes", data: items };
  },

  normalizeDiscussions(body) {
    const items = this._asList(body)
      .map((d) => ({ title: d.Name ?? null, post_count: d.PostCount ?? null }))
      .filter((d) => d.title != null);

    if (items.length === 0) return null;
    return { type: "discussions", data: items };
  },

  normalizeAnnouncements(body) {
    const items = this._asList(body)
      .map((n) => ({ title: n.Title ?? null, posted_at: n.StartDate ?? null }))
      .filter((n) => n.title != null);

    if (items.length === 0) return null;
    return { type: "announcements", data: items };
  }
};

if (typeof globalThis !== "undefined") globalThis.Normalizer = Normalizer;

window.addEventListener("message", (event) => {
  if (event.source !== window) return;
  if (event.origin !== window.location.origin) return;

  const msg = event.data;
  if (!msg || msg.source !== "academic-os-injected-hook") return;
  if (msg.type !== "LUMEN_API_CAPTURED") return;

  const { url, body } = msg.payload;
  let normalized;
  try {
    normalized = Normalizer.normalize(url, body);
  } catch (err) {
    Logger.debug("Normalization threw, dropping payload:", err.message);
    return;
  }

  if (!normalized) {
    Logger.debug("Unrecognized or empty payload shape, ignored:", url);
    return;
  }

  chrome.runtime
    .sendMessage({ type: "LUMEN_DATA_CAPTURED", normalized, capturedAt: msg.payload.capturedAt })
    .catch((err) => Logger.debug("Capture relay failed (extension may have reloaded):", err.message));
});
