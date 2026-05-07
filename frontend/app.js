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

function showPage(route) {
  const nextRoute = document.querySelector(`[data-page="${route}"]`) ? route : "dashboard";

  elements.pages.forEach((page) => {
    page.classList.toggle("active", page.dataset.page === nextRoute);
  });

  elements.navTabs.forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.route === nextRoute);
  });

  if (window.location.hash !== `#${nextRoute}`) {
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
  showPage("results");
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

function severityClass(severity = "") {
  const normalized = severity.toLowerCase();
  if (normalized.includes("high")) return "severity-high";
  if (normalized.includes("medium")) return "severity-medium";
  return "severity-low";
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
  const node = document.createElement("article");
  node.className = "issue";
  node.innerHTML = `
    <div class="issue-top">
      <h4>${escapeHtml(issue.file_path || "Unknown file")}</h4>
      <span class="badge ${severityClass(issue.severity)}">${escapeHtml(issue.severity || "low")}</span>
    </div>
    <div class="issue-meta">
      <span class="badge">${escapeHtml(issue.issue_type || issue.rule || "finding")}</span>
      ${language ? `<span class="badge">${escapeHtml(language)}</span>` : ""}
    </div>
    <p><strong>Problem:</strong> ${escapeHtml(issue.problem || "")}</p>
    ${issue.why_it_is_problem ? `<p><strong>Why:</strong> ${escapeHtml(issue.why_it_is_problem)}</p>` : ""}
    ${issue.suggestion ? `<p><strong>Suggestion:</strong> ${escapeHtml(issue.suggestion)}</p>` : ""}
    ${code ? `<pre class="code-block"><code>${escapeHtml(code)}</code></pre>` : ""}
  `;
  return node;
}

function prepareFullReviewStream() {
  hideLoader();
  resetResults();
  showResultsPage();
  state.fullReviewIssues = [];
  state.fullReviewCards = new Map();
  updateIssueStats(state.fullReviewIssues);
  elements.summary.hidden = false;
  elements.summary.textContent = "Starting full review...";
}

function appendFullReviewIssue(issue) {
  state.fullReviewIssues.push(issue);
  updateIssueStats(state.fullReviewIssues);
  elements.issues.appendChild(createIssueCard(issue));
}

function createLiveReviewCard(filePath, language = "") {
  const node = document.createElement("article");
  node.className = "issue live-review";
  node.innerHTML = `
    <div class="issue-top">
      <h4>${escapeHtml(filePath || "Reviewing file")}</h4>
      <span class="badge severity-medium">streaming</span>
    </div>
    <div class="issue-meta">
      <span class="badge">LLM output</span>
      ${language ? `<span class="badge">${escapeHtml(language)}</span>` : ""}
    </div>
    <pre class="code-block"><code></code></pre>
  `;
  elements.issues.appendChild(node);
  state.fullReviewCards.set(filePath, node);
  return node;
}

function appendLiveReviewToken(filePath, token) {
  const node = state.fullReviewCards.get(filePath) || createLiveReviewCard(filePath);
  const output = node.querySelector("code");
  output.textContent += token;
  output.parentElement.scrollTop = output.parentElement.scrollHeight;
}

function finishLiveReviewCard(filePath, issueCount = 0) {
  const node = state.fullReviewCards.get(filePath);

  if (!node) return;

  state.fullReviewCards.delete(filePath);

  if (issueCount > 0) {
    node.remove();
    return;
  }

  node.querySelector(".badge").textContent = "no issues";
  const output = node.querySelector("code");
  output.textContent = "No structured findings returned for this file.";
}

function renderReviewResults(result) {
  resetResults();
  showResultsPage();
  elements.summary.hidden = !result.summary;
  elements.summary.textContent = result.summary || "";

  const issues = Array.isArray(result.issues) ? result.issues : [];
  updateIssueStats(issues);

  if (!issues.length) {
    elements.issues.innerHTML = '<div class="empty-state"><strong>No issues returned</strong><span>The analysis did not report structured findings.</span></div>';
  }

  issues.forEach((issue) => {
    elements.issues.appendChild(createIssueCard(issue));
  });

  const improvements = Array.isArray(result.overall_improvements) ? result.overall_improvements : [];
  elements.improvements.hidden = !improvements.length;
  elements.improvements.innerHTML = improvements.length
    ? `<strong>Overall improvements</strong><ul>${improvements.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
    : "";
}

async function streamFullReview(payload) {
  prepareFullReviewStream();

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

      if (event.type === "status") {
        elements.summary.textContent = event.message || "Full review is running...";
      }

      if (event.type === "file_start") {
        elements.summary.textContent = `Reviewing ${event.file_path || "file"} (${event.reviewed_files || 0}/${event.total_files || 0})`;
        createLiveReviewCard(event.file_path, event.language);
      }

      if (event.type === "token") {
        appendLiveReviewToken(event.file_path, event.token || "");
      }

      if (event.type === "issue" && event.issue) {
        appendFullReviewIssue(event.issue);
      }

      if (event.type === "file_complete") {
        finishLiveReviewCard(event.file_path, event.issue_count || 0);
        elements.summary.textContent = `Reviewed ${event.reviewed_files || 0} of ${event.total_files || 0} files. Findings: ${event.total_issues || 0}.`;
      }

      if (event.type === "complete") {
        finalResult = {
          summary: event.summary || "Full review complete.",
          issues: [...state.fullReviewIssues],
          overall_improvements: event.overall_improvements || [],
        };
        elements.summary.textContent = finalResult.summary;
      }
    }
  }

  if (!state.fullReviewIssues.length && !state.fullReviewCards.size) {
    elements.issues.innerHTML = '<div class="empty-state"><strong>No issues returned</strong><span>The analysis did not report structured findings.</span></div>';
  }

  return finalResult || {
    summary: elements.summary.textContent,
    issues: [...state.fullReviewIssues],
    overall_improvements: [],
  };
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
    setActiveRepo(result.repo_id);
    elements.zipMeta.innerHTML = `
      <span>Files: ${escapeHtml(result.files_loaded ?? "--")}</span>
      <span>Chunks: ${escapeHtml(result.chunks_created ?? "--")}</span>
      <span>${result.cached ? "Cached" : "Fresh"}</span>
    `;
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

  try {
    const result = await streamFullReview({
      repo_id: state.repoId,
      question: elements.fullQuestion.value.trim(),
    });
    const improvements = Array.isArray(result.overall_improvements) ? result.overall_improvements : [];
    elements.improvements.hidden = !improvements.length;
    elements.improvements.innerHTML = improvements.length
      ? `<strong>Overall improvements</strong><ul>${improvements.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
      : "";
    showToast("Full review complete", result.summary || "Structured findings are ready.", "success");
  } catch (error) {
    showToast("Full review failed", error.message, "error");
  } finally {
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
