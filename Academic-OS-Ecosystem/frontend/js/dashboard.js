(() => {
  const ADMIN_EMAIL = "2025em1300265@bitspilani-digital.edu.in";
  const API_BASE_URL = (window.API_URL || "https://academic-os-api.onrender.com")
    .replace(/\/predict\/?$/, "")
    .replace(/\/$/, "");

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
    const trackedStudents = Number(data.tracker_students || 0);
    const completedModules = Number(data.tracker_completed_modules || 0);
    const totalModules = Number(data.tracker_total_modules || 0);
    const atRisk = Number(data.at_risk_count || 0);

    setStatus(
      `Verified admin: ${data.viewer?.email || ADMIN_EMAIL}. Showing ${trackedStudents} students with tracker snapshots across ${Number(data.tracker_snapshot_count || 0)} trimester records.`,
      "success"
    );

    state.summary.innerHTML = `
      ${summaryCard("Students Tracking", `${trackedStudents}/${cohortSize}`, percent(trackedStudents, cohortSize), "var(--done)")}
      ${summaryCard("Average Progress", formatPct(data.average_modules_completed_pct), data.average_modules_completed_pct || 0, "var(--sm-color)")}
      ${summaryCard("Modules Completed", `${completedModules}/${totalModules}`, percent(completedModules, totalModules), "var(--dv-color)")}
      ${summaryCard("At Risk", atRisk, percent(atRisk, trackedStudents || 1), "var(--overdue)")}
    `;

    state.table.innerHTML = users.length
      ? users.map(renderUserRow).join("")
      : `<tr><td colspan="18" class="admin-dashboard__empty">No student tracker snapshots are available yet. Student data appears after sign-in and the first trimester sync.</td></tr>`;
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
    const progress = user.progress || {};
    const prediction = user.prediction || {};
    const completion = numeric(progress.modules_completed_pct);

    return `
      <tr>
        <td>
          <div class="admin-dashboard__student">${escapeHtml(user.email || user.student_id)}</div>
          <div class="admin-dashboard__subtext">${escapeHtml(user.email ? user.student_id : "BITS signup record")}</div>
        </td>
        <td>${progressBarCell(completion)}</td>
        <td>${formatPct(progress.attendance_pct)}</td>
        <td>${formatPct(progress.avg_quiz_score)}</td>
        <td>${formatPct(progress.assignment_avg)}</td>
        <td>${formatNumber(progress.weekly_study_hours, 1)}</td>
        <td>${formatDecimalScore(progress.consistency_score)}</td>
        <td>${formatNumber(progress.aptitude_score, 1)}</td>
        <td>${formatNumber(progress.trimester_gpa, 2)}</td>
        <td>${formatNumber(progress.communication_score, 1)}</td>
        <td>${formatInteger(progress.projects_count)}</td>
        <td>${formatInteger(progress.internships_count)}</td>
        <td>${formatInteger(progress.mock_interviews_attended)}</td>
        <td>${formatInteger(progress.backlogs_count)}</td>
        <td>${escapeHtml(prediction.risk_band || "Not predicted")}</td>
        <td>${renderTrackerPrediction(user.tracker_progress || [])}</td>
        <td class="admin-dashboard__tracker-cell">${renderTrackerProgress(user.tracker_progress || [])}</td>
        <td>${formatDate(user.updated_at)}</td>
      </tr>
    `;
  }

  function renderTrackerPrediction(terms) {
    const predictions = terms.filter(term => term.prediction?.expected_performance);
    if (!predictions.length) {
      return `<span class="admin-dashboard__subtext">No tracker prediction yet</span>`;
    }

    return predictions.map(term => {
      const prediction = term.prediction;
      const topFactors = (prediction.top_factors || []).map(factor => `<li>${escapeHtml(factor)}</li>`).join("");
      return `
        <div class="admin-dashboard__tracker-prediction">
          <strong>${escapeHtml(term.trimester_name || `Trimester ${term.trimester_id}`)} · ${escapeHtml(prediction.expected_performance)}</strong>
          <span>Probability: ${formatPct(prediction.probability_pct)}</span>
          <span>Risk: ${escapeHtml(prediction.risk || "-")}</span>
          <span>Consistency: ${escapeHtml(prediction.consistency || "-")}</span>
          <span>Study time: ${escapeHtml(prediction.recommended_study_time || "-")}</span>
          <span class="admin-dashboard__subtext">${escapeHtml(prediction.type || "")}</span>
          ${topFactors ? `<details><summary>Factors</summary><ul>${topFactors}</ul></details>` : ""}
        </div>
      `;
    }).join("");
  }

  function renderTrackerProgress(terms) {
    if (!terms.length) return `<span class="admin-dashboard__subtext">No trimester data synced yet</span>`;

    return terms.map((term) => {
      const completion = clamp(term.completion_pct);
      const courses = (term.courses || []).map(renderTrackerCourse).join("");
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
          <div class="admin-dashboard__tracker-courses">${courses}</div>
        </section>
      `;
    }).join("");
  }

  function renderTrackerCourse(course) {
    const weeks = course.weeks || [];
    const lumen = course.lumen_progress;
    const modules = weeks.flatMap(week => week.modules || []);
    const total = modules.length;
    const completed = modules.filter(module => module.completed).length;
    const completion = total ? (completed / total) * 100 : 0;
    const moduleDetails = weeks.map(week => `
      <li class="admin-dashboard__week">
        <strong>Week ${escapeHtml(week.week_label || "-")}${week.topic ? ` · ${escapeHtml(week.topic)}` : ""}</strong>
        <ul>${(week.modules || []).map(module => `
          <li class="${module.completed ? "is-complete" : "is-pending"}">
            <span aria-hidden="true">${module.completed ? "✓" : "○"}</span> ${escapeHtml(module.title)}
          </li>
        `).join("")}</ul>
      </li>
    `).join("");
    const lumenActivities = lumen?.activities || [];
    const lumenDetails = lumenActivities.map(activity => `
      <li class="${activity.completed ? "is-complete" : "is-pending"}">
        <span aria-hidden="true">${activity.completed ? "✓" : "○"}</span>
        ${escapeHtml(activity.kind)}: ${escapeHtml(activity.title)}
        <span>${escapeHtml(activity.status)}${activity.score_pct === null || activity.score_pct === undefined ? "" : ` · ${formatPct(activity.score_pct)}`}</span>
      </li>
    `).join("");
    const lumenHtml = lumen ? `
      <div class="admin-dashboard__lumen-progress">
        <div class="admin-dashboard__course-heading">
          <strong>Lumen activity</strong>
          <span>${formatPct(lumen.completion_pct)}</span>
        </div>
        <div class="admin-dashboard__tracker-bar is-course"><div style="width:${clamp(lumen.completion_pct)}%"></div></div>
        <div class="admin-dashboard__subtext">${lumen.lecture_status_available === false ? "Lumen content complete" : "Lectures viewed"} ${formatInteger(lumen.lectures_viewed)}/${formatInteger(lumen.lectures_total)} · Quizzes ${formatInteger(lumen.quizzes_completed)}/${formatInteger(lumen.quizzes_total)} · Assignments ${formatInteger(lumen.assignments_submitted)}/${formatInteger(lumen.assignments_total)}</div>
        <details class="admin-dashboard__module-details">
          <summary>${formatInteger(lumenActivities.filter(activity => activity.completed).length)}/${formatInteger(lumenActivities.length)} Lumen activities complete · View statuses</summary>
          <ul class="admin-dashboard__week-list">${lumenDetails || "<li>No Lumen activities returned.</li>"}</ul>
        </details>
      </div>
    ` : `<div class="admin-dashboard__subtext">Lumen activity not synced</div>`;

    return `
      <div class="admin-dashboard__course">
        <div class="admin-dashboard__course-heading">
          <strong>${escapeHtml(course.course_name || course.course_id)}</strong>
          <span>${formatPct(completion)}</span>
        </div>
        <div class="admin-dashboard__tracker-bar is-course"><div style="width:${clamp(completion)}%"></div></div>
        ${lumenHtml}
        <details class="admin-dashboard__module-details">
          <summary>${completed}/${total} modules complete · View module statuses</summary>
          <ul class="admin-dashboard__week-list">${moduleDetails}</ul>
        </details>
      </div>
    `;
  }

  function progressBarCell(value) {
    return `
      <div class="admin-dashboard__progress">
        <span>${formatPct(value)}</span>
        <div class="mini-bar">
          <div class="mini-bar-fill" style="width:${clamp(value)}%;background:var(--done);"></div>
        </div>
      </div>
    `;
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

  function formatNumber(value, digits) {
    const number = numeric(value);
    if (number === null) return "-";
    return number.toFixed(digits);
  }

  function formatDecimalScore(value) {
    const number = numeric(value);
    if (number === null) return "-";
    return number <= 1 ? number.toFixed(2) : number.toFixed(1);
  }

  function formatInteger(value) {
    const number = numeric(value);
    if (number === null) return "-";
    return String(Math.round(number));
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
