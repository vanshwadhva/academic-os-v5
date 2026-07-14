const el = (id) => document.getElementById(id);

function sendMessage(message) {
  return chrome.runtime.sendMessage(message);
}

function pctClass(pct) {
  if (pct == null) return "";
  if (pct >= 75) return "good";
  if (pct >= 50) return "mid";
  return "low";
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

function courseCardHtml(course) {
  const { total, completed } = course.moduleProgress || { total: 0, completed: 0 };
  const pctModules = total > 0 ? Math.round((completed / total) * 100) : 0;

  const gradesHtml = (course.grades || [])
    .map(
      (g) => `
      <div class="grade-row">
        <span>${escapeHtml(g.title)}</span>
        <span class="pct ${pctClass(g.percentage)}">${g.percentage != null ? g.percentage + "%" : "—"}</span>
      </div>`
    )
    .join("");

  const assignmentsHtml = (course.assignments || [])
    .map(
      (a) => `
      <div class="assignment-row">
        <span>${escapeHtml(a.title)}</span>
        <span class="status-badge">${escapeHtml(a.status || "unknown")}</span>
      </div>`
    )
    .join("");

  return `
    <div class="course-card">
      <div class="course-title">${escapeHtml(course.courseName)}</div>
      <div class="course-code">${escapeHtml(course.courseCode || "")}</div>

      <div class="progress-bar-track">
        <div class="progress-bar-fill" style="width:${pctModules}%"></div>
      </div>
      <div class="progress-label">${completed}/${total} topics visited</div>

      ${gradesHtml ? `<div class="section-label">Grades</div>${gradesHtml}` : ""}
      ${assignmentsHtml ? `<div class="section-label">Assignments</div>${assignmentsHtml}` : ""}
    </div>
  `;
}

function formatFetchedAt(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return `Last pulled ${d.toLocaleString()}`;
}

async function render() {
  const { progress } = await sendMessage({ type: "GET_PROGRESS_CACHE" });

  if (!progress || !progress.courses || progress.courses.length === 0) {
    el("empty-state").classList.remove("hidden");
    el("course-grid").innerHTML = "";
    el("student-name").textContent = "";
    el("fetched-at").textContent = "";
    return;
  }

  el("empty-state").classList.add("hidden");
  el("student-name").textContent = progress.student?.name || "";
  el("fetched-at").textContent = formatFetchedAt(progress.fetchedAt);

  if (progress.errors?.length) {
    el("errors-banner").textContent =
      `${progress.errors.length} item(s) failed to fetch — showing partial data. ` +
      `First error: ${progress.errors[0]}`;
    el("errors-banner").classList.remove("hidden");
  } else {
    el("errors-banner").classList.add("hidden");
  }

  el("course-grid").innerHTML = progress.courses.map(courseCardHtml).join("");
}

async function refresh(button) {
  button.disabled = true;
  const originalText = button.textContent;
  button.textContent = "Fetching from Lumen…";

  const result = await sendMessage({ type: "FETCH_LUMEN_PROGRESS" });

  button.disabled = false;
  button.textContent = originalText;

  if (!result.ok) {
    el("errors-banner").textContent = `Refresh failed: ${result.error}`;
    el("errors-banner").classList.remove("hidden");
    return;
  }

  await render();
}

el("refresh-btn").addEventListener("click", () => refresh(el("refresh-btn")));
el("empty-refresh-btn").addEventListener("click", () => refresh(el("empty-refresh-btn")));

render();
