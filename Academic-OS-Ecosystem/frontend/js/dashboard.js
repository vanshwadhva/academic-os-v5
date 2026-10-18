(() => {
  // Display-only gate. The backend is the enforcement point: /api/admin/dashboard/*
  // verifies the Firebase ID token and accepts only this verified email.
  const ADMIN_EMAIL = "2025em1300265@bitspilani-digital.edu.in";
  const API_BASE_URL = (window.APP_CONFIG?.API_URL || "https://academic-os-api.onrender.com")
    .replace(/\/predict\/?$/, "")
    .replace(/\/$/, "");

  const INPUT_LABELS = {
    preferred_study_hour: "Preferred study hour",
    weekly_study_hours: "Weekly study hours",
    consistency_score: "Consistency",
    attendance_pct: "Attendance %",
    backlogs_count: "Backlogs",
    aptitude_score: "Aptitude",
    avg_quiz_score: "Avg quiz score",
    quiz_score_std: "Quiz score spread",
    assignment_avg: "Graded-item average",
    trimester_gpa: "Trimester GPA",
    modules_completed_pct: "Modules completed %",
    communication_score: "Communication",
    projects_count: "Projects",
    internships_count: "Internships",
    mock_interviews_attended: "Mock interviews",
  };
  const SOURCE_LABELS = { lumen: "Lumen", self_reported: "Self-reported", imputed: "Default (no data)" };

  const state = {
    root: null,
    status: null,
    summary: null,
    table: null,
  };

  document.addEventListener("DOMContentLoaded", () => {
    state.root = document.getElementById("adminDashboard");
    if (!state.root) return;

    state.status = state.root.querySelector("[data-admin-status]");
    state.summary = state.root.querySelector("[data-admin-summary]");
    state.table = state.root.querySelector("[data-admin-table]");

    const refreshBtn = state.root.querySelector("[data-admin-refresh]");
    if (refreshBtn) refreshBtn.addEventListener("click", loadAdminDashboard);
    const fullscreenBtn = state.root.querySelector("[data-admin-fullscreen]");
    if (fullscreenBtn) fullscreenBtn.addEventListener("click", toggleFullscreenView);

    if (!window.firebase || !firebase.auth) {
      hideAdminDashboard();
      return;
    }

    firebase.auth().onAuthStateChanged((user) => {
      const email = (user?.email || "").toLowerCase();
      if (email === ADMIN_EMAIL) {
        showAdminDashboard();
        loadAdminDashboard();
      } else {
        hideAdminDashboard();
      }
    });
  });

  async function loadAdminDashboard() {
    const user = firebase.auth().currentUser;
    const email = (user?.email || "").toLowerCase();

    if (!user || email !== ADMIN_EMAIL) {
      hideAdminDashboard();
      return;
    }

    try {
      setStatus("Verifying Firebase session and loading cohort records...", "muted");
      const idToken = await user.getIdToken(true);
      const response = await fetch(`${API_BASE_URL}/api/admin/dashboard/progress`, {
        headers: {
          Authorization: `Bearer ${idToken}`,
          Accept: "application/json",
        },
      });

      if (response.status === 401 || response.status === 403) {
        hideAdminDashboard();
        return;
      }

      if (!response.ok) {
        throw new Error(`Admin dashboard request failed with HTTP ${response.status}`);
      }

      renderDashboard(await response.json());
    } catch (error) {
      console.error("Admin dashboard load failed", error);
      setStatus(error.message || "Admin dashboard failed to load.", "error");
    }
  }

  function showAdminDashboard() {
    state.root.classList.remove("hidden");
    state.root.setAttribute("aria-hidden", "false");
  }

  function hideAdminDashboard() {
    if (!state.root) return;
    state.root.classList.add("hidden");
    state.root.setAttribute("aria-hidden", "true");
    if (state.summary) state.summary.innerHTML = "";
    if (state.table) state.table.innerHTML = "";
  }

  function renderDashboard(data) {
    const users = data.users || [];
    const cohortSize = data.cohort_size || 250;
    const linked = users.filter(user => user.lumen).length;
    const predicted = users.filter(user => user.ml_prediction?.status === "ready").length;
    const atRisk = users.filter(user => user.ml_prediction?.risk_band === "High likelihood").length;

    setStatus(
      `Verified admin: ${data.viewer?.email || ADMIN_EMAIL}. ${users.length} student records · ${linked} with Lumen data · ${predicted} with a model prediction.`,
      "success"
    );

    state.summary.innerHTML = `
      ${summaryCard("Students", `${users.length}/${cohortSize}`, percent(users.length, cohortSize), "var(--done)")}
      ${summaryCard("Lumen linked", `${linked}`, percent(linked, users.length || 1), "var(--sm-color)")}
      ${summaryCard("Predictions ready", `${predicted}`, percent(predicted, users.length || 1), "var(--dv-color)")}
      ${summaryCard("High likelihood (model)", `${atRisk}`, percent(atRisk, predicted || 1), "var(--overdue)")}
    `;

    state.table.innerHTML = users.length
      ? users.map(renderUserRow).join("")
      : `<tr><td colspan="7" class="admin-dashboard__empty">No student records yet. Records appear after a student signs in and syncs Lumen or saves tracker progress.</td></tr>`;
  }

  function summaryCard(label, value, barValue, color) {
    return `
      <article class="summary-card">
        <div class="label">${escapeHtml(label)}</div>
        <div class="value">${escapeHtml(value)}</div>
        <div class="mini-bar">
          <div class="mini-bar-fill" style="width:${clamp(barValue)}%;background:${color};"></div>
        </div>
      </article>
    `;
  }

  function renderUserRow(user) {
    return `
      <tr>
        <td>
          <div class="admin-dashboard__student">${escapeHtml(user.email || user.student_id)}</div>
          <div class="admin-dashboard__subtext">${escapeHtml(user.student_id)}</div>
        </td>
        <td>${renderLumenStatus(user.lumen)}</td>
        <td>${renderCourses(user.lumen)}</td>
        <td>${renderPrediction(user.ml_prediction)}</td>
        <td>${renderProfile(user.profile)}</td>
        <td class="admin-dashboard__tracker-cell">${renderTrackerProgress(user.tracker_progress || [])}</td>
        <td>${formatDate(user.updated_at)}</td>
      </tr>
    `;
  }

  function renderLumenStatus(lumen) {
    if (!lumen) return `<span class="admin-dashboard__subtext">Lumen not connected</span>`;
    const errors = Object.keys(lumen.domain_errors || {}).length;
    return `
      <div>${escapeHtml(lumen.sync_status || "unknown")}</div>
      <div class="admin-dashboard__subtext">Synced ${formatDate(lumen.last_synced_at)}</div>
      <div class="admin-dashboard__subtext">${(lumen.courses || []).length} courses${errors ? ` · ${errors} fetch errors` : ""}</div>
    `;
  }

  function renderCourses(lumen) {
    const courses = lumen?.courses || [];
    if (!courses.length) return `<span class="admin-dashboard__subtext">No course data</span>`;
    return courses.map(course => {
      const quizzes = (course.quizzes || []).map(q => `<li>${escapeHtml(q.quiz_name || "Quiz")}: ${escapeHtml(q.status || "-")} · ${formatPct(q.percentage)}</li>`).join("");
      const grades = (course.grades || []).map(g => `<li>${escapeHtml(g.grade_item_id ?? "Item")}: ${formatPct(g.percentage)}</li>`).join("");
      const assignments = (course.assignments || []).map(a => `<li>${escapeHtml(a.name || a.assignment_id || "Assignment")}: ${escapeHtml(a.submission_status || "-")}</li>`).join("");
      const modules = (course.modules || []).map(m => `
        <li class="${m.visited || m.is_read || m.completed ? "is-complete" : "is-pending"}">
          <span aria-hidden="true">${m.visited || m.is_read || m.completed ? "✓" : "○"}</span>
          ${escapeHtml(m.title || "Lecture")}${m.module_path ? ` <span class="admin-dashboard__subtext">${escapeHtml(m.module_path)}</span>` : ""}
          ${m.last_visited ? `<span class="admin-dashboard__subtext">last ${formatDate(m.last_visited)}</span>` : ""}
        </li>`).join("");
      return `
        <div class="admin-dashboard__course">
          <div class="admin-dashboard__course-heading">
            <strong>${escapeHtml(course.course_name || course.course_code || `Course ${course.course_id}`)}</strong>
            <span>${formatPct(course.overall_progress_pct)}</span>
          </div>
          <div class="admin-dashboard__subtext">
            Lectures ${formatInteger(course.modules_completed)}/${formatInteger(course.modules_total)} ·
            Attendance ${formatPct(course.attendance?.attendance_pct)} ·
            Quizzes ${(course.quizzes || []).length} · Grades ${(course.grades || []).length} · Assignments ${(course.assignments || []).length}
          </div>
          <details class="admin-dashboard__module-details">
            <summary>View lectures, quizzes, grades and assignments</summary>
            <div class="admin-dashboard__subtext">Lectures</div>
            <ul class="admin-dashboard__week-list">${modules || "<li>No lectures returned.</li>"}</ul>
            <div class="admin-dashboard__subtext">Quizzes</div>
            <ul class="admin-dashboard__week-list">${quizzes || "<li>No quizzes returned.</li>"}</ul>
            <div class="admin-dashboard__subtext">Grades</div>
            <ul class="admin-dashboard__week-list">${grades || "<li>No grades returned.</li>"}</ul>
            <div class="admin-dashboard__subtext">Assignments</div>
            <ul class="admin-dashboard__week-list">${assignments || "<li>No assignments returned.</li>"}</ul>
          </details>
        </div>`;
    }).join("");
  }

  function renderPrediction(insights) {
    if (!insights || !insights.status) return `<span class="admin-dashboard__subtext">Not computed</span>`;
    if (insights.status !== "ready") {
      return `<span class="admin-dashboard__subtext">${escapeHtml(insights.message || insights.status)}</span>`;
    }
    const coverage = insights.coverage || {};
    const inputs = Object.entries(insights.inputs || {}).map(([key, input]) => `
      <li>${escapeHtml(INPUT_LABELS[key] || key)}: <strong>${escapeHtml(formatInputValue(input.value))}</strong>
        <span class="admin-dashboard__subtext">${escapeHtml(SOURCE_LABELS[input.source] || input.source)}</span></li>`).join("");
    const factors = (insights.top_factors || []).map(factor => `<li>${escapeHtml(factor.feature)}</li>`).join("");
    return `
      <div><strong>${formatPct(insights.placement_probability * 100)}</strong> · ${escapeHtml(insights.risk_band || "-")}</div>
      <div class="admin-dashboard__subtext">Inputs: ${coverage.lumen ?? 0} Lumen · ${coverage.self_reported ?? 0} self-reported · ${coverage.imputed ?? 0} default</div>
      <div class="admin-dashboard__subtext">Synthetic-data model, not validated</div>
      <details class="admin-dashboard__module-details">
        <summary>Model inputs and top factors</summary>
        <ul class="admin-dashboard__week-list">${inputs}</ul>
        <div class="admin-dashboard__subtext">Top factors</div>
        <ul class="admin-dashboard__week-list">${factors}</ul>
      </details>`;
  }

  function renderProfile(profile) {
    const entries = Object.entries(profile || {});
    if (!entries.length) return `<span class="admin-dashboard__subtext">Not provided</span>`;
    return `<ul class="admin-dashboard__week-list">${entries.map(([key, value]) =>
      `<li>${escapeHtml(INPUT_LABELS[key] || key)}: ${escapeHtml(value)}</li>`).join("")}</ul>`;
  }

  function renderTrackerProgress(terms) {
    if (!terms.length) return `<span class="admin-dashboard__subtext">No trimester data synced yet</span>`;

    return terms.map((term) => {
      const completion = clamp(term.completion_pct);
      const syncLabel = term.lumen_synced_at
        ? `Lumen synced ${formatDate(term.lumen_synced_at)}`
        : "No Lumen sync recorded";
      return `
        <section class="admin-dashboard__term">
          <div class="admin-dashboard__term-heading">
            <strong>${escapeHtml(term.trimester_name || `Trimester ${term.trimester_id}`)}</strong>
            <span>${formatPct(completion)}</span>
          </div>
          <div class="admin-dashboard__tracker-bar"><div style="width:${completion}%"></div></div>
          <div class="admin-dashboard__subtext">${formatInteger(term.completed_modules)} / ${formatInteger(term.total_modules)} modules · ${escapeHtml(syncLabel)}</div>
        </section>
      `;
    }).join("");
  }

  function setStatus(message, tone) {
    if (!state.status) return;
    state.status.textContent = message;
    state.status.dataset.tone = tone;
  }

  function toggleFullscreenView() {
    if (!state.root) return;
    const isFullscreen = state.root.classList.toggle("admin-dashboard--fullscreen");
    document.body.classList.toggle("admin-dashboard-lock", isFullscreen);
    const button = state.root.querySelector("[data-admin-fullscreen]");
    if (button) button.textContent = isFullscreen ? "Exit full screen" : "Full screen";
  }

  function percent(value, total) {
    if (!total) return 0;
    return (Number(value || 0) / Number(total)) * 100;
  }

  function clamp(value) {
    return Math.max(0, Math.min(100, Number(value || 0)));
  }

  function numeric(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return null;
    return Number(value);
  }

  function formatPct(value) {
    const number = numeric(value);
    if (number === null) return "-";
    return `${number.toFixed(1)}%`;
  }

  function formatInteger(value) {
    const number = numeric(value);
    if (number === null) return "-";
    return String(Math.round(number));
  }

  function formatInputValue(value) {
    const number = numeric(value);
    if (number === null) return "-";
    return Number.isInteger(number) ? String(number) : number.toFixed(2);
  }

  function formatDate(value) {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "-";
    return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  window.AdminDashboard = {
    load: loadAdminDashboard,
    allowedEmail: ADMIN_EMAIL,
  };
})();
