const state = {
  repoId: localStorage.getItem("repoAnalyzer.repoId") || "",
};

const elements = {
  activeRepo: document.querySelector("#activeRepo"),
  statusDot: document.querySelector("#statusDot"),
  indexForm: document.querySelector("#indexForm"),
  askForm: document.querySelector("#askForm"),
  repoLink: document.querySelector("#repoLink"),
  question: document.querySelector("#question"),
  indexButton: document.querySelector("#indexButton"),
  askButton: document.querySelector("#askButton"),
  indexMeta: document.querySelector("#indexMeta"),
  emptyState: document.querySelector("#emptyState"),
  summary: document.querySelector("#summary"),
  issues: document.querySelector("#issues"),
  improvements: document.querySelector("#improvements"),
  clearButton: document.querySelector("#clearButton"),
  toast: document.querySelector("#toast"),
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

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("show");
  window.clearTimeout(showToast.timeout);
  showToast.timeout = window.setTimeout(() => {
    elements.toast.classList.remove("show");
  }, 3500);
}

function setButtonLoading(button, isLoading, idleHtml, loadingText) {
  button.disabled = isLoading;
  button.classList.toggle("is-loading", isLoading);
  button.innerHTML = isLoading
    ? `<span class="button-icon"></span> ${escapeHtml(loadingText)}`
    : idleHtml;
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

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

function renderResults(result) {
  elements.emptyState.hidden = true;
  elements.summary.hidden = !result.summary;
  elements.summary.textContent = result.summary || "";
  elements.issues.innerHTML = "";

  const issues = Array.isArray(result.issues) ? result.issues : [];
  if (!issues.length) {
    elements.issues.innerHTML = '<div class="empty-state"><strong>No issues returned</strong><span>The model did not report structured findings for this question.</span></div>';
  }

  issues.forEach((issue) => {
    const code = issue.improved_code?.code;
    const language = issue.improved_code?.language || "code";
    const node = document.createElement("article");
    node.className = "issue";
    node.innerHTML = `
      <div class="issue-top">
        <h4>${escapeHtml(issue.file_path || "Unknown file")}</h4>
        <span class="badge ${severityClass(issue.severity)}">${escapeHtml(issue.severity || "low")}</span>
      </div>
      <div class="issue-meta">
        <span class="badge">${escapeHtml(issue.issue_type || "finding")}</span>
      </div>
      <p><strong>Problem:</strong> ${escapeHtml(issue.problem || "")}</p>
      <p><strong>Why:</strong> ${escapeHtml(issue.why_it_is_problem || "")}</p>
      <p><strong>Suggestion:</strong> ${escapeHtml(issue.suggestion || "")}</p>
      ${code ? `<pre class="code-block" aria-label="Improved ${escapeHtml(language)} code"><code>${escapeHtml(code)}</code></pre>` : ""}
    `;
    elements.issues.appendChild(node);
  });

  const improvements = Array.isArray(result.overall_improvements) ? result.overall_improvements : [];
  elements.improvements.hidden = !improvements.length;
  elements.improvements.innerHTML = improvements.length
    ? `<strong>Overall improvements</strong><ul>${improvements.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
    : "";
}

elements.indexForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setButtonLoading(elements.indexButton, true, '<span class="button-icon">+</span> Index', "Indexing...");

  try {
    const result = await postJson("/ai/index", { repo_link: elements.repoLink.value.trim() });
    setActiveRepo(result.repo_id);
    elements.indexMeta.innerHTML = `
      <span>Files: ${escapeHtml(result.files_loaded ?? "--")}</span>
      <span>Chunks: ${escapeHtml(result.chunks_created ?? "--")}</span>
    `;
    showToast(result.message || "Repository indexed");
  } catch (error) {
    showToast(error.message);
  } finally {
    setButtonLoading(elements.indexButton, false, '<span class="button-icon">+</span> Index', "Indexing...");
  }
});

elements.askForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.repoId) {
    showToast("Index a repository first.");
    return;
  }

  setButtonLoading(elements.askButton, true, '<span class="button-icon">></span> Run review', "Reviewing...");

  try {
    const result = await postJson("/ai/ask", {
      repo_id: state.repoId,
      question: elements.question.value.trim(),
    });
    renderResults(result);
    showToast("Review complete");
  } catch (error) {
    showToast(error.message);
  } finally {
    setButtonLoading(elements.askButton, false, '<span class="button-icon">></span> Run review', "Reviewing...");
  }
});

elements.clearButton.addEventListener("click", () => {
  elements.emptyState.hidden = false;
  elements.summary.hidden = true;
  elements.improvements.hidden = true;
  elements.summary.textContent = "";
  elements.improvements.innerHTML = "";
  elements.issues.innerHTML = "";
});

setActiveRepo(state.repoId);
