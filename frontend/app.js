const state = {
  repoId: localStorage.getItem("repoAnalyzer.repoId") || "",
  loaderTimer: null,
  loaderStartedAt: 0,
  loaderStep: 0,
  fullReviewIssues: [],
  fullReviewCards: new Map(),
};

const loaderFlows = {
  index: ["Cloning repository", "Reading code", "Splitting chunks", "Creating vectors", "Saving index"],
  zip: ["Uploading ZIP", "Extracting files", "Reading code", "Creating vectors", "Saving index"],
  ask: ["Opening vector DB", "Searching code", "Preparing context", "Asking model", "Rendering answer"],
  fullReview: ["Loading files", "Checking syntax", "Reviewing in parallel", "Collecting issues", "Rendering report"],
  syntax: ["Scanning files", "Detecting language", "Running checkers", "Collecting snippets", "Rendering findings"],
};

const elements = {
  activeRepo: document.querySelector("#activeRepo"),
  statusDot: document.querySelector("#statusDot"),
  indexForm: document.querySelector("#indexForm"),
  zipForm: document.querySelector("#zipForm"),
  fullReviewForm: document.querySelector("#fullReviewForm"),
  syntaxForm: document.querySelector("#syntaxForm"),
  navTabs: document.querySelectorAll("[data-route]"),
  pages: document.querySelectorAll("[data-page]"),
  repoLink: document.querySelector("#repoLink"),
  forceReindex: document.querySelector("#forceReindex"),
  zipFile: document.querySelector("#zipFile"),
  fullQuestion: document.querySelector("#fullQuestion"),
  indexButton: document.querySelector("#indexButton"),
  zipButton: document.querySelector("#zipButton"),
  fullReviewButton: document.querySelector("#fullReviewButton"),
  fullReviewInlineResults: document.querySelector("#fullReviewInlineResults"),
  syntaxButton: document.querySelector("#syntaxButton"),
  askButton: document.querySelector("#askButton"),
  askLauncher: document.querySelector("#askLauncher"),
  heroAskButton: document.querySelector("#heroAskButton"),
  chatWindow: document.querySelector("#chatWindow"),
  chatClose: document.querySelector("#chatClose"),
  chatForm: document.querySelector("#chatForm"),
  chatQuestion: document.querySelector("#chatQuestion"),
  chatMessages: document.querySelector("#chatMessages"),
  indexMeta: document.querySelector("#indexMeta"),
  zipMeta: document.querySelector("#zipMeta"),
  zipProjects: document.querySelector("#zipProjects"),
  loaderPanel: document.querySelector("#loaderPanel"),
  loaderStage: document.querySelector("#loaderStage"),
  loaderTitle: document.querySelector("#loaderTitle"),
  loaderDetail: document.querySelector("#loaderDetail"),
  loaderHint: document.querySelector("#loaderHint"),
  elapsedTime: document.querySelector("#elapsedTime"),
  progressBar: document.querySelector("#progressBar"),
  emptyState: document.querySelector("#emptyState"),
  summary: document.querySelector("#summary"),
  issues: document.querySelector("#issues"),
  improvements: document.querySelector("#improvements"),
  resultTotal: document.querySelector("#resultTotal"),
  resultHigh: document.querySelector("#resultHigh"),
  resultSyntax: document.querySelector("#resultSyntax"),
  resultFiles: document.querySelector("#resultFiles"),
  clearButton: document.querySelector("#clearButton"),
  toastStack: document.querySelector("#toastStack"),
};

function setActiveRepo(repoId) {
  state.repoId = repoId;

  if (repoId) {
    localStorage.setItem("repoAnalyzer.repoId", repoId);
    elements.activeRepo.textContent = repoId;
    elements.statusDot.classList.add("ready");
    return;
  }

  localStorage.removeItem("repoAnalyzer.repoId");
  elements.activeRepo.textContent = "None indexed";
  elements.statusDot.classList.remove("ready");
}

function showPage(route, updateHash = true) {
  const nextRoute = document.querySelector(`[data-page="${route}"]`) ? route : "dashboard";

  elements.pages.forEach((page) => {
    page.classList.toggle("active", page.dataset.page === nextRoute);
  });

  elements.navTabs.forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.route === nextRoute);
  });

  if (updateHash && window.location.hash !== `#${nextRoute}`) {
    history.replaceState(null, "", `#${nextRoute}`);
  }
}

function showToast(title, detail = "", type = "info") {
  const toast = document.createElement("article");
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <div>
      <strong>${escapeHtml(title)}</strong>
      ${detail ? `<span>${escapeHtml(detail)}</span>` : ""}
    </div>
    <button type="button" aria-label="Dismiss notification">x</button>
  `;

  const close = () => {
    toast.classList.add("leaving");
    window.setTimeout(() => toast.remove(), 180);
  };

  toast.querySelector("button").addEventListener("click", close);
  elements.toastStack.prepend(toast);
  window.setTimeout(close, type === "error" ? 8000 : 5200);
}

function setButtonLoading(button, isLoading, idleHtml, loadingText) {
  button.disabled = isLoading;
  button.classList.toggle("is-loading", isLoading);
  button.innerHTML = isLoading
    ? `<span class="button-icon"></span> ${escapeHtml(loadingText)}`
    : idleHtml;
}

function startLoader(type, title, hint) {
  const steps = loaderFlows[type] || loaderFlows.ask;
  state.loaderStartedAt = Date.now();
  state.loaderStep = 0;
  elements.loaderPanel.hidden = false;
  elements.loaderStage.textContent = type.replace(/([A-Z])/g, " $1").trim();
  elements.loaderTitle.textContent = title;
  elements.loaderHint.textContent = hint || "Large repositories can take a few minutes.";
  elements.loaderDetail.textContent = steps[0];
  elements.elapsedTime.textContent = "Elapsed: 0s";
  elements.progressBar.style.width = "8%";

  window.clearInterval(state.loaderTimer);
  state.loaderTimer = window.setInterval(() => {
    const elapsed = Math.floor((Date.now() - state.loaderStartedAt) / 1000);
    state.loaderStep = Math.min(Math.floor(elapsed / 4), steps.length - 1);
    const loopProgress = 10 + ((elapsed * 6) % 82);

    elements.elapsedTime.textContent = `Elapsed: ${elapsed}s`;
    elements.loaderDetail.textContent = steps[state.loaderStep];
    elements.progressBar.style.width = `${loopProgress}%`;
  }, 500);
}

function stopLoader(finalText = "Done") {
  window.clearInterval(state.loaderTimer);
  state.loaderTimer = null;
  elements.loaderDetail.textContent = finalText;
  elements.progressBar.style.width = "100%";
  window.setTimeout(() => {
    if (!state.loaderTimer) {
      elements.loaderPanel.hidden = true;
      elements.progressBar.style.width = "0%";
    }
  }, 800);
}

function hideLoader() {
  window.clearInterval(state.loaderTimer);
  state.loaderTimer = null;
  elements.loaderPanel.hidden = true;
  elements.progressBar.style.width = "0%";
}

function showResultsPage() {
  showPage("results", false);
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  return parseResponse(response);
}

async function postForm(url, formData) {
  const response = await fetch(url, {
    method: "POST",
    body: formData,
  });

  return parseResponse(response);
}

async function parseResponse(response) {
  const text = await response.text();
  let data;

  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { detail: text };
  }

  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : "Request failed";
    throw new Error(detail);
  }

  return data;
}

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function skippedFileCount(fileFilter = {}) {
  return (fileFilter.ignored || 0)
    + (fileFilter.style_skipped || 0)
    + (fileFilter.unsupported || 0)
    + (fileFilter.too_large || 0);
}

function renderZipIndexResult(result, options = {}) {
  setActiveRepo(result.repo_id);

  if (!options.keepProjectChoices) {
    elements.zipProjects.hidden = true;
    elements.zipProjects.innerHTML = "";
  }

  elements.zipMeta.innerHTML = `
    <span>Files: ${escapeHtml(result.files_loaded ?? "--")}</span>
    <span>Chunks: ${escapeHtml(result.chunks_created ?? "--")}</span>
    <span>${result.cached ? "Cached" : "Fresh"}</span>
    ${result.project ? `<span>Project: ${escapeHtml(result.project.name || result.project.path || "Root")}</span>` : ""}
    ${result.file_filter ? `<span>Skipped: ${escapeHtml(skippedFileCount(result.file_filter))}</span>` : ""}
  `;
}

function renderZipProjectChoices(result) {
  const projects = Array.isArray(result.projects) ? result.projects : [];
  setActiveRepo("");
  elements.zipMeta.innerHTML = `
    <span>${escapeHtml(projects.length)} projects detected</span>
    <span>Select one below</span>
  `;
  elements.zipProjects.hidden = false;
  elements.zipProjects.innerHTML = `
    <div class="zip-projects-header">
      <div>
        <strong>Select Repository From ZIP</strong>
        <span>Multiple repositories were detected. Index one project, run review, then return here and index the next one if needed.</span>
      </div>
      <span class="zip-project-count">${escapeHtml(projects.length)} detected</span>
    </div>
    <div class="zip-project-list">
      ${projects.map((project, index) => `
        <article class="zip-project-card">
          <div>
            <strong>${escapeHtml(project.name || `Project ${index + 1}`)}</strong>
            <span>${escapeHtml(project.path || "ZIP root")}</span>
          </div>
          <p>${escapeHtml((project.markers || []).join(", ") || "No framework marker found")}</p>
          <button type="button" data-zip-project="${escapeHtml(project.path)}">Index and use for review</button>
        </article>
      `).join("")}
    </div>
  `;

  elements.zipProjects.querySelectorAll("[data-zip-project]").forEach((button) => {
    button.addEventListener("click", () => {
      indexSelectedZipProject(result.zip_id, button.dataset.zipProject, button);
    });
  });
}

async function indexSelectedZipProject(zipId, projectPath, button) {
  const idleText = "Index and use for review";
  setButtonLoading(button, true, idleText, "Indexing");
  startLoader("zip", "Indexing selected ZIP project", "Reading, chunking, and vectorizing only the selected project.");

  try {
    const result = await postJson("/ai/index-zip-project", {
      zip_id: zipId,
      project_path: projectPath,
    });
    renderZipIndexResult(result, { keepProjectChoices: true });
    elements.zipProjects.querySelectorAll("[data-zip-project]").forEach((projectButton) => {
      projectButton.classList.remove("secondary");
      projectButton.textContent = projectButton.dataset.indexed ? "Indexed" : idleText;
    });
    button.textContent = "Active for review";
    button.classList.add("secondary");
    button.dataset.indexed = "true";
    showToast("ZIP project ready", "This project is now active for full review.", "success");
    stopLoader("ZIP project ready");
  } catch (error) {
    showToast("ZIP project failed", error.message, "error");
    stopLoader("ZIP project failed");
  } finally {
    setButtonLoading(button, false, button.dataset.indexed ? "Active for review" : idleText, "Indexing");
  }
}

function severityClass(severity = "") {
  const normalized = severity.toLowerCase();
  if (normalized.includes("high")) return "severity-high";
  if (normalized.includes("medium")) return "severity-medium";
  return "severity-low";
}

function iconSvg(name) {
  const icons = {
    alert: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 9v4" /><path d="M12 17h.01" /><path d="M10.3 3.9 2.6 18a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /></svg>',
    shield: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /><path d="m9 12 2 2 4-5" /></svg>',
    target: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3" /><path d="M12 2v3" /><path d="M12 19v3" /><path d="M2 12h3" /><path d="M19 12h3" /></svg>',
    bug: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 2l2 3" /><path d="M16 2l-2 3" /><rect x="7" y="5" width="10" height="14" rx="5" /><path d="M4 13h3" /><path d="M17 13h3" /><path d="M5 20l3-3" /><path d="M19 20l-3-3" /><path d="M12 9v6" /></svg>',
    code: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 18-6-6 6-6" /><path d="m15 6 6 6-6 6" /></svg>',
    module: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h6v6H4z" /><path d="M14 4h6v6h-6z" /><path d="M4 14h6v6H4z" /><path d="M14 14h6v6h-6z" /></svg>',
    file: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /></svg>',
    lightbulb: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 18h6" /><path d="M10 22h4" /><path d="M8.5 14a6 6 0 1 1 7 0c-.8.5-1.5 1.5-1.5 2.5h-4c0-1-.7-2-1.5-2.5z" /></svg>',
    search: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>',
  };

  return icons[name] || icons.code;
}

function createIconBadge(icon, label, className = "") {
  return `<span class="icon-badge ${className}">${iconSvg(icon)}<span>${escapeHtml(label)}</span></span>`;
}

function createDetailRow(icon, label, value) {
  if (!value) return "";

  return `
    <div class="issue-detail-row">
      <span class="detail-icon">${iconSvg(icon)}</span>
      <div>
        <strong>${escapeHtml(label)}</strong>
        <p>${escapeHtml(value)}</p>
      </div>
    </div>
  `;
}

function reportSectionIcon(title) {
  const normalized = title.toLowerCase();

  if (normalized.includes("tech stack")) return "code";
  if (normalized.includes("developed modules")) return "module";
  if (normalized.includes("major problems")) return "alert";
  if (normalized.includes("each file")) return "file";
  if (normalized.includes("severity")) return "shield";

  return "target";
}

function resetResults() {
  elements.emptyState.hidden = true;
  elements.summary.hidden = true;
  elements.improvements.hidden = true;
  elements.summary.textContent = "";
  elements.improvements.innerHTML = "";
  elements.issues.innerHTML = "";
}

function updateResultStats({ total = 0, high = 0, syntax = 0, files = 0 }) {
  elements.resultTotal.textContent = total;
  elements.resultHigh.textContent = high;
  elements.resultSyntax.textContent = syntax;
  elements.resultFiles.textContent = files;
}

function updateIssueStats(issues) {
  const files = new Set(issues.map((issue) => issue.file_path).filter(Boolean));
  updateResultStats({
    total: issues.length,
    high: issues.filter((issue) => String(issue.severity || "").toLowerCase().includes("high")).length,
    syntax: issues.filter((issue) => String(issue.issue_type || issue.rule || "").toLowerCase().includes("syntax")).length,
    files: files.size,
  });
}

function createIssueCard(issue) {
  const code = issue.improved_code?.code || issue.code;
  const language = issue.improved_code?.language || issue.language || "code";
  const severity = issue.severity || "low";
  const confidence = issue.confidence || "medium";
  const issueType = issue.issue_type || issue.rule || "finding";
  const vulnerabilityLabel = issue.vulnerability ? "vulnerability" : "no vulnerability";
  const node = document.createElement("article");
  node.className = "issue";
  node.innerHTML = `
    <div class="issue-top">
      <div class="issue-title">
        <span class="detail-icon">${iconSvg("file")}</span>
        <h4>${escapeHtml(issue.file_path || "Unknown file")}</h4>
      </div>
      ${createIconBadge("alert", severity, severityClass(severity))}
    </div>
    <div class="issue-chip-grid">
      ${createIconBadge("bug", issueType)}
      ${language ? createIconBadge("code", language) : ""}
      ${issue.module ? createIconBadge("module", issue.module) : ""}
      ${createIconBadge("target", `${confidence} confidence`)}
      ${createIconBadge("shield", vulnerabilityLabel, issue.vulnerability ? "severity-high" : "severity-low")}
    </div>
    <div class="issue-detail-grid">
      ${createDetailRow("bug", "Problem", issue.problem || "")}
      ${createDetailRow("search", "Evidence", issue.evidence || "")}
      ${createDetailRow("alert", "Impact", issue.why_it_is_problem || "")}
      ${createDetailRow("lightbulb", "Suggestion", issue.suggestion || "")}
    </div>
    ${code ? `<pre class="code-block"><code>${escapeHtml(code)}</code></pre>` : ""}
  `;
  return node;
}

function createReportSection(title, bodyHtml) {
  const node = document.createElement("article");
  node.className = "issue report-section";
  node.innerHTML = `
    <div class="report-section-header">
      <span class="report-section-icon">${iconSvg(reportSectionIcon(title))}</span>
      <div>
        <h4>${escapeHtml(title)}</h4>
        <span>Review section</span>
      </div>
    </div>
    ${bodyHtml}
  `;
  return node;
}

function renderMetricCards(items, valueKey = "files", labelKey = "name") {
  return `
    <div class="report-metric-grid">
      ${items.map((item) => `
        <div class="report-metric">
          <strong>${escapeHtml(item[valueKey] ?? 0)}</strong>
          <span>${escapeHtml(item[labelKey] || "item")}</span>
        </div>
      `).join("")}
    </div>
  `;
}

function renderTechStackSection(techStack, target = elements.issues) {
  if (!techStack || (!Array.isArray(techStack.languages) && !Array.isArray(techStack.frameworks_libraries))) {
    return;
  }

  const languages = Array.isArray(techStack.languages) ? techStack.languages : [];
  const configs = Array.isArray(techStack.configs) ? techStack.configs : [];
  const frameworks = Array.isArray(techStack.frameworks_libraries) ? techStack.frameworks_libraries : [];
  const languageTotal = languages.reduce((sum, item) => sum + Number(item.files || 0), 0);
  const configTotal = configs.reduce((sum, item) => sum + Number(item.files || 0), 0);
  const body = `
    <div class="report-overview">
      <div>
        <span>Primary stack</span>
        <strong>${escapeHtml(techStack.summary || "Not detected")}</strong>
      </div>
      <div>
        <span>Source files</span>
        <strong>${escapeHtml(languageTotal)}</strong>
      </div>
      <div>
        <span>Config files</span>
        <strong>${escapeHtml(configTotal)}</strong>
      </div>
    </div>
    ${languages.length ? renderMetricCards(languages) : ""}
    ${frameworks.length ? `
      <div class="report-subsection">
        <h5>Frameworks and libraries</h5>
        <div class="report-chip-row">${frameworks.map((item) => createIconBadge("code", item)).join("")}</div>
      </div>
    ` : ""}
    ${configs.length ? `
      <div class="report-subsection">
        <h5>Configuration footprint</h5>
        <div class="report-chip-row">${configs.map((item) => createIconBadge("file", `${item.name}: ${item.files}`)).join("")}</div>
      </div>
    ` : ""}
  `;
  target.appendChild(createReportSection("Tech Stack", body));
}

function renderModuleProblemsSection(moduleProblems, target = elements.issues) {
  if (!Array.isArray(moduleProblems) || !moduleProblems.length) return;

  const body = `
    <div class="report-card-list">
      ${moduleProblems.map((item) => `
        <article class="report-card">
          <div class="report-card-header">
            <strong>${escapeHtml(item.module)}</strong>
            <span>${escapeHtml(item.issue_count || 0)} issue(s)</span>
          </div>
          <p>${escapeHtml(item.major_problem || "")}</p>
          <div class="report-chip-row">
            ${createIconBadge("alert", `High ${item.high || 0}`, Number(item.high || 0) ? "severity-high" : "")}
            ${createIconBadge("target", `Medium ${item.medium || 0}`, Number(item.medium || 0) ? "severity-medium" : "")}
            ${createIconBadge("file", `${Array.isArray(item.files) ? item.files.length : 0} file(s)`)}
          </div>
        </article>
      `).join("")}
    </div>
  `;
  target.appendChild(createReportSection("Module By Module Major Problems", body));
}

function renderDevelopedModulesSection(modules, target = elements.issues) {
  if (!Array.isArray(modules) || !modules.length) return;

  const body = `
    <div class="report-card-list">
      ${modules.map((item) => `
        <article class="report-card">
          <div class="report-card-header">
            <strong>${escapeHtml(item.name)}</strong>
            <span>${escapeHtml(item.file_count || 0)} file(s)</span>
          </div>
          <div class="report-chip-row">
            ${(Array.isArray(item.languages) ? item.languages : []).map((language) => createIconBadge("code", language)).join("")}
          </div>
          ${Array.isArray(item.sample_files) && item.sample_files.length ? `
            <div class="report-file-list">
              ${item.sample_files.map((file) => `<span>${escapeHtml(file)}</span>`).join("")}
            </div>
          ` : ""}
        </article>
      `).join("")}
    </div>
  `;
  target.appendChild(createReportSection("Developed Modules", body));
}

function renderSeverityVulnerabilitySection(summary, target = elements.issues) {
  if (!summary || typeof summary !== "object") return;

  const body = `
    <div class="issue-meta">
      <span class="badge severity-high">High: ${escapeHtml(summary.high || 0)}</span>
      <span class="badge severity-medium">Medium: ${escapeHtml(summary.medium || 0)}</span>
      <span class="badge severity-low">Low: ${escapeHtml(summary.low || 0)}</span>
      <span class="badge">Vulnerabilities: ${escapeHtml(summary.vulnerabilities || 0)}</span>
    </div>
    ${summary.review_standard ? `<p>${escapeHtml(summary.review_standard)}</p>` : ""}
  `;
  target.appendChild(createReportSection("Severity And Vulnerability", body));
}

function renderReviewReportContent(result, targetIssues) {
  const issues = Array.isArray(result.issues) ? result.issues : [];
  const hasSections = Boolean(result.tech_stack)
    || (Array.isArray(result.developed_modules) && result.developed_modules.length)
    || (Array.isArray(result.module_problems) && result.module_problems.length)
    || Boolean(result.severity_vulnerability);

  renderTechStackSection(result.tech_stack, targetIssues);
  renderDevelopedModulesSection(result.developed_modules, targetIssues);
  renderModuleProblemsSection(result.module_problems, targetIssues);

  if (issues.length) {
    targetIssues.appendChild(createReportSection("Each File Defects And Suggestions", ""));
  }

  if (!issues.length && !hasSections) {
    targetIssues.innerHTML = '<div class="empty-state"><strong>No issues returned</strong><span>The analysis did not report structured findings.</span></div>';
  }

  issues.forEach((issue) => {
    targetIssues.appendChild(createIssueCard(issue));
  });

  renderSeverityVulnerabilitySection(result.severity_vulnerability, targetIssues);
}

function renderFullReviewInline(result) {
  const panel = elements.fullReviewInlineResults;

  if (!panel) {
    renderReviewResults(result);
    return;
  }

  const summary = panel.querySelector("[data-inline-summary]");
  const issues = panel.querySelector("[data-inline-issues]");
  const improvements = panel.querySelector("[data-inline-improvements]");

  panel.hidden = false;
  summary.hidden = !result.summary;
  summary.textContent = result.summary || "";
  issues.innerHTML = "";

  renderReviewReportContent(result, issues);

  const improvementItems = Array.isArray(result.overall_improvements) ? result.overall_improvements : [];
  improvements.hidden = !improvementItems.length;
  improvements.innerHTML = improvementItems.length
    ? `<strong>Overall improvements</strong><ul>${improvementItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
    : "";
}

function prepareFullReviewStream() {
  const panel = elements.fullReviewInlineResults;

  hideLoader();
  resetResults();
  state.fullReviewIssues = [];
  state.fullReviewCards = new Map();

  if (!panel) {
    showResultsPage();
    elements.summary.hidden = false;
    elements.summary.textContent = "Starting full review...";
    return {
      summary: elements.summary,
      issues: elements.issues,
      improvements: elements.improvements,
    };
  }

  const summary = panel.querySelector("[data-inline-summary]");
  const issues = panel.querySelector("[data-inline-issues]");
  const improvements = panel.querySelector("[data-inline-improvements]");

  panel.hidden = false;
  summary.hidden = false;
  summary.textContent = "Starting full review...";
  issues.innerHTML = "";
  improvements.hidden = true;
  improvements.innerHTML = "";
  updateIssueStats([]);

  return { summary, issues, improvements };
}

function ensureFileDefectsSection(targetIssues) {
  if (targetIssues.querySelector("[data-file-defects-section]")) return;

  const section = createReportSection("Each File Defects And Suggestions", "");
  section.dataset.fileDefectsSection = "true";
  targetIssues.appendChild(section);
}

function handleFullReviewStreamEvent(event, streamUi) {
  if (event.type === "status") {
    streamUi.summary.textContent = event.message || "Full review is running...";
    return null;
  }

  if (event.type === "section" && event.name === "tech_stack") {
    renderTechStackSection(event.data, streamUi.issues);
    return null;
  }

  if (event.type === "section" && event.name === "developed_modules") {
    renderDevelopedModulesSection(event.data, streamUi.issues);
    return null;
  }

  if (event.type === "issue" && event.issue) {
    ensureFileDefectsSection(streamUi.issues);
    state.fullReviewIssues.push(event.issue);
    updateIssueStats(state.fullReviewIssues);
    streamUi.issues.appendChild(createIssueCard(event.issue));
    streamUi.summary.textContent = `Reviewed ${event.reviewed_files || 0}/${event.total_files || "--"} files. Found ${event.total_issues || state.fullReviewIssues.length} issue(s).`;
    return null;
  }

  if (event.type === "file_done") {
    streamUi.summary.textContent = `Reviewed ${event.reviewed_files || 0}/${event.total_files || "--"} files. Found ${event.total_issues || state.fullReviewIssues.length} issue(s).`;
    return null;
  }

  if (event.type === "done") {
    const result = event.result || {};
    streamUi.summary.textContent = result.summary || "Full review complete.";

    if (!state.fullReviewIssues.length) {
      ensureFileDefectsSection(streamUi.issues);
      streamUi.issues.appendChild(createReportSection(
        "No File Defects Found",
        '<div class="empty-state"><strong>No issues returned</strong><span>The analysis did not report structured findings.</span></div>'
      ));
    }

    renderModuleProblemsSection(result.module_problems, streamUi.issues);
    renderSeverityVulnerabilitySection(result.severity_vulnerability, streamUi.issues);

    const improvementItems = Array.isArray(result.overall_improvements) ? result.overall_improvements : [];
    streamUi.improvements.hidden = !improvementItems.length;
    streamUi.improvements.innerHTML = improvementItems.length
      ? `<strong>Overall improvements</strong><ul>${improvementItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
      : "";

    updateIssueStats(Array.isArray(result.issues) ? result.issues : state.fullReviewIssues);
    return result;
  }

  return null;
}

async function streamFullReview(payload) {
  const streamUi = prepareFullReviewStream();
  const response = await fetch("/ai/full-review", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok || !response.body) {
    return parseResponse(response);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult = null;

  while (true) {
    const { value, done } = await reader.read();

    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line);
      finalResult = handleFullReviewStreamEvent(event, streamUi) || finalResult;
    }
  }

  if (buffer.trim()) {
    const event = JSON.parse(buffer);
    finalResult = handleFullReviewStreamEvent(event, streamUi) || finalResult;
  }

  return finalResult || { summary: "Full review stream completed." };
}

function renderReviewResults(result) {
  resetResults();
  showResultsPage();
  elements.summary.hidden = !result.summary;
  elements.summary.textContent = result.summary || "";

  const issues = Array.isArray(result.issues) ? result.issues : [];
  updateIssueStats(issues);
  renderReviewReportContent(result, elements.issues);

  const improvements = Array.isArray(result.overall_improvements) ? result.overall_improvements : [];
  elements.improvements.hidden = !improvements.length;
  elements.improvements.innerHTML = improvements.length
    ? `<strong>Overall improvements</strong><ul>${improvements.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
    : "";
}

function renderAskResults(result) {
  resetResults();
  showResultsPage();
  elements.summary.hidden = false;
  elements.summary.textContent = result.answer || "Answer returned.";

  const rows = Array.isArray(result.results) ? result.results : [];
  const files = new Set(rows.map((row) => row.file_path).filter(Boolean));
  updateResultStats({
    total: rows.length,
    high: 0,
    syntax: 0,
    files: files.size,
  });

  if (!rows.length) {
    elements.issues.innerHTML = '<div class="empty-state"><strong>No matching symbols</strong><span>The vector search did not return structured matches.</span></div>';
    return;
  }

  rows.forEach((row) => {
    const node = document.createElement("article");
    node.className = "issue";
    node.innerHTML = `
      <div class="issue-top">
        <h4>${escapeHtml(row.name || "Result")}</h4>
        <span class="badge">${escapeHtml(row.symbol_type || "symbol")}</span>
      </div>
      <div class="issue-meta">
        <span class="badge">${escapeHtml(row.file_path || "Unknown file")}</span>
        <span class="badge">Line: ${escapeHtml(row.line_number ?? "n/a")}</span>
      </div>
      <p>${escapeHtml(row.description || "")}</p>
    `;
    elements.issues.appendChild(node);
  });

  const suggestions = Array.isArray(result.suggestions) ? result.suggestions : [];
  elements.improvements.hidden = !suggestions.length;
  elements.improvements.innerHTML = suggestions.length
    ? `<strong>Suggestions</strong><ul>${suggestions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
    : "";
}

function renderSyntaxResults(result) {
  renderReviewResults({
    summary: result.summary,
    issues: (result.issues || []).map((issue) => ({
      ...issue,
      issue_type: issue.rule || "syntax_error",
      severity: "high",
      improved_code: {
        language: issue.language || "",
        code: issue.code || "",
      },
      why_it_is_problem: `${issue.language || "Code"} syntax errors can break builds or runtime execution.`,
      suggestion: `Fix the ${issue.rule || "syntax"} issue on line ${issue.line ?? "reported"}.`,
    })),
    overall_improvements: [
      `Checked files: ${result.checked_files ?? "--"}`,
      `Skipped files: ${result.skipped_files ?? "--"}`,
    ],
  });
}

function requireRepo() {
  if (state.repoId) return true;
  showToast("No active repo", "Index a Git repository or ZIP project first.", "error");
  return false;
}

function openChat() {
  elements.chatWindow.hidden = false;
  elements.chatQuestion.focus();
}

function closeChat() {
  elements.chatWindow.hidden = true;
}

function addChatMessage(role, text) {
  const node = document.createElement("div");
  node.className = `chat-message ${role}`;
  node.textContent = text;
  elements.chatMessages.appendChild(node);
  elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
}

function summarizeAskAnswer(result) {
  const count = Array.isArray(result.results) ? result.results.length : 0;
  const base = result.answer || "Answer returned.";
  return count ? `${base}\n\nStructured matches: ${count}` : base;
}

elements.indexForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setButtonLoading(elements.indexButton, true, '<span class="button-icon">+</span> Index', "Indexing");
  startLoader("index", "Indexing repository", "Cloning and vectorizing code can take time on larger repos.");

  try {
    const result = await postJson("/ai/index", {
      repo_link: elements.repoLink.value.trim(),
      force_reindex: elements.forceReindex.checked,
    });
    setActiveRepo(result.repo_id);
    elements.indexMeta.innerHTML = `
      <span>Files: ${escapeHtml(result.files_loaded ?? "--")}</span>
      <span>Chunks: ${escapeHtml(result.chunks_created ?? "--")}</span>
      <span>${result.cached ? "Cached" : "Fresh"}</span>
      ${result.file_filter ? `<span>Skipped: ${escapeHtml((result.file_filter.ignored || 0) + (result.file_filter.style_skipped || 0) + (result.file_filter.unsupported || 0) + (result.file_filter.too_large || 0))}</span>` : ""}
    `;
    showToast("Repository indexed", result.message || result.repo_id, "success");
    stopLoader("Index ready");
  } catch (error) {
    showToast("Index failed", error.message, "error");
    stopLoader("Index failed");
  } finally {
    setButtonLoading(elements.indexButton, false, '<span class="button-icon">+</span> Index', "Indexing");
  }
});

elements.zipForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setButtonLoading(elements.zipButton, true, '<span class="button-icon">+</span> Index ZIP', "Indexing");
  startLoader("zip", "Indexing ZIP project", "Uploading, extracting, and vectorizing project files.");

  try {
    const formData = new FormData();
    formData.append("file", elements.zipFile.files[0]);
    const result = await postForm("/ai/index-zip", formData);

    if (result.multiple) {
      renderZipProjectChoices(result);
      showToast("Multiple projects found", "Choose which ZIP project to index first.", "info");
      stopLoader("Choose a ZIP project");
      return;
    }

    renderZipIndexResult(result);
    showToast("ZIP indexed", result.message || result.repo_id, "success");
    stopLoader("ZIP index ready");
  } catch (error) {
    showToast("ZIP index failed", error.message, "error");
    stopLoader("ZIP index failed");
  } finally {
    setButtonLoading(elements.zipButton, false, '<span class="button-icon">+</span> Index ZIP', "Indexing");
  }
});

elements.chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!requireRepo()) return;

  const question = elements.chatQuestion.value.trim();
  if (!question) return;

  addChatMessage("user", question);
  elements.chatQuestion.value = "";
  setButtonLoading(elements.askButton, true, '<span class="button-icon">></span> Send', "Asking");
  startLoader("ask", "Asking repository", "Searching vectors and preparing a focused answer.");

  try {
    const result = await postJson("/ai/ask", {
      repo_id: state.repoId,
      question,
    });
    renderAskResults(result);
    addChatMessage("assistant", summarizeAskAnswer(result));
    showToast("Answer ready", "The chat response and structured results are available.", "success");
    stopLoader("Answer ready");
  } catch (error) {
    addChatMessage("assistant", `Request failed: ${error.message}`);
    showToast("Ask failed", error.message, "error");
    stopLoader("Ask failed");
  } finally {
    setButtonLoading(elements.askButton, false, '<span class="button-icon">></span> Send', "Asking");
  }
});

elements.fullReviewForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!requireRepo()) return;

  elements.fullReviewButton.disabled = true;
  elements.fullReviewButton.classList.remove("is-loading");
  elements.fullReviewButton.innerHTML = '<span class="button-icon">></span> Streaming';
  hideLoader();

  try {
    const result = await streamFullReview({
      repo_id: state.repoId,
      question: elements.fullQuestion.value.trim(),
    });
    showToast("Full review complete", result.summary || "Structured findings are ready.", "success");
  } catch (error) {
    showToast("Full review failed", error.message, "error");
  } finally {
    hideLoader();
    elements.fullReviewButton.disabled = false;
    elements.fullReviewButton.classList.remove("is-loading");
    elements.fullReviewButton.innerHTML = '<span class="button-icon">></span> Run';
  }
});

elements.syntaxForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!requireRepo()) return;

  setButtonLoading(elements.syntaxButton, true, '<span class="button-icon">></span> Check syntax', "Checking");
  startLoader("syntax", "Checking syntax", "Running language-specific syntax tools and collecting snippets.");

  try {
    const result = await postJson("/ai/syntax-check", {
      repo_id: state.repoId,
    });
    renderSyntaxResults(result);
    showToast("Syntax check complete", result.summary || "Syntax findings are ready.", "success");
    stopLoader("Syntax results ready");
  } catch (error) {
    showToast("Syntax check failed", error.message, "error");
    stopLoader("Syntax check failed");
  } finally {
    setButtonLoading(elements.syntaxButton, false, '<span class="button-icon">></span> Check syntax', "Checking");
  }
});

elements.askLauncher.addEventListener("click", openChat);
elements.heroAskButton.addEventListener("click", openChat);
document.querySelectorAll("[data-route]").forEach((control) => {
  control.addEventListener("click", (event) => {
    event.preventDefault();
    showPage(control.dataset.route);
  });
});
elements.chatClose.addEventListener("click", closeChat);

elements.clearButton.addEventListener("click", () => {
  elements.emptyState.hidden = false;
  elements.summary.hidden = true;
  elements.improvements.hidden = true;
  elements.summary.textContent = "";
  elements.improvements.innerHTML = "";
  elements.issues.innerHTML = "";
  updateResultStats({});
});

setActiveRepo(state.repoId);
showPage((window.location.hash || "#dashboard").slice(1));
