const API = "http://localhost:8000";
let currentRepo = "";

function setApiStatus(online) {
    document.querySelectorAll("#api-status, #api-status-landing").forEach(dot => {
        dot.classList.toggle("offline", !online);
    });
    const label = document.getElementById("api-status-label");
    if (label) label.textContent = online ? "API connected" : "API unavailable";
}

async function readApiResponse(res) {
    const raw = await res.text();
    let data = {};
    if (raw) {
        try {
            data = JSON.parse(raw);
        } catch {
            data = { detail: raw.trim() };
        }
    }

    if (!res.ok) {
        throw new Error(data.detail || data.message || `Request failed with status ${res.status}`);
    }

    return data;
}

function isGithubRepoUrl(value) {
    try {
        const url = new URL(value);
        const parts = url.pathname.split("/").filter(Boolean);
        return /(^|\.)github\.com$/i.test(url.hostname) && parts.length >= 2;
    } catch {
        return false;
    }
}

// ── Tab navigation ──────────────────────────────────────────────
const TAB_TITLES = {
    analyze: "Analyze Repository", overview: "Architecture Overview",
    query: "Ask AI", bugs: "Bug Finder", smells: "Code Smells",
    patterns: "Design Patterns", debt: "Technical Debt",
    graph: "Dependency Graph", tools: "AI Tools", repos: "Repositories",
};

function showTab(name) {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
    document.getElementById(`tab-${name}`).classList.add("active");
    document.getElementById("page-title").textContent = TAB_TITLES[name] || name;
    document.querySelector(`[data-tab="${name}"]`)?.classList.add("active");
}

// ── Global repo selector ────────────────────────────────────────
async function onGlobalRepoChange() {
    currentRepo = document.getElementById("global-repo").value;
    const repo = currentRepo;
    if (!repo) {
        updateDashboardMetrics();
        return;
    }

    try {
        const res = await fetch(`${API}/repository/${encodeURIComponent(repo)}`);
        const data = await readApiResponse(res);
        if (currentRepo !== repo) return;
        updateDashboardMetrics({
            entities_found: data.entity_count,
            chunks_indexed: data.chunk_count,
            bugs_found: (data.bugs || []).length,
            smells_found: (data.smells || []).length,
            patterns_found: (data.patterns || []).length,
            debt_grade: data.debt?.grade || "—",
        });
    } catch (err) {
        console.error("Could not load selected repository metrics:", err);
        updateDashboardMetrics();
    }
}

function getRepo() {
    currentRepo = document.getElementById("global-repo").value;
    if (!currentRepo) { alert("Please select a repository from the top bar first."); return null; }
    return currentRepo;
}

function updateDashboardMetrics(data = {}) {
    const repoName = currentRepo || "No repository connected";
    const badge = document.getElementById("repo-badge");
    if (badge) badge.textContent = repoName;

    const kpis = {
        entities: document.getElementById("kpi-entities"),
        chunks: document.getElementById("kpi-chunks"),
        issues: document.getElementById("kpi-issues"),
        debt: document.getElementById("kpi-debt"),
    };

    if (!currentRepo || !data || Object.keys(data).length === 0) {
        kpis.entities.textContent = "—";
        kpis.chunks.textContent = "—";
        kpis.issues.textContent = "—";
        kpis.debt.textContent = "—";
        return;
    }

    const issuesTotal = Number(data.bugs_found || 0) + Number(data.smells_found || 0) + Number(data.patterns_found || 0);
    kpis.entities.textContent = data.entities_found ?? "—";
    kpis.chunks.textContent = data.chunks_indexed ?? "—";
    kpis.issues.textContent = String(issuesTotal);
    kpis.debt.textContent = data.debt_grade || "—";
}

// ── API health ──────────────────────────────────────────────────
async function checkAPI() {
    try {
        const r = await fetch(`${API}/`);
        setApiStatus(r.ok);
    } catch { setApiStatus(false); }
}

// ── Analyze ─────────────────────────────────────────────────────
async function analyzeRepository() {
    const url    = document.getElementById("repo-url").value.trim();
    const branch = document.getElementById("repo-branch").value.trim() || "main";
    if (!url) { alert("Please enter a repository URL"); return; }
    if (!isGithubRepoUrl(url)) { alert("Please enter a full GitHub repository URL, like https://github.com/user/repository"); return; }

    const status = document.getElementById("analysis-status");
    const btn    = document.getElementById("analyze-btn");
    btn.disabled = true;
    status.style.display = "block";
    status.className = "alert alert-loading";
    status.innerHTML = `<span class="spinner"></span>Cloning and analyzing… this may take a few minutes.`;

    try {
        const res  = await fetch(`${API}/analyze`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ repo_url: url, branch, languages: ["python", "javascript"] }),
        });
        const data = await readApiResponse(res);
        status.className = "alert alert-success";
        status.innerHTML =
            `Done — <strong>${data.entities_found}</strong> entities · ` +
            `<strong>${data.chunks_indexed}</strong> chunks · ` +
            `<strong>${data.bugs_found}</strong> bugs · ` +
            `<strong>${data.smells_found}</strong> smells · ` +
            `<strong>${data.patterns_found}</strong> patterns · ` +
            `Debt grade <strong>${data.debt_grade}</strong>`;
        currentRepo = data.repo_id;
        updateDashboardMetrics(data);
        await loadRepositories();
        document.getElementById("global-repo").value = data.repo_id;
    } catch (err) {
        status.className = "alert alert-error";
        status.textContent = `Error: ${err.message}`;
    } finally { btn.disabled = false; }
}

// ── Load repositories ───────────────────────────────────────────
async function loadRepositories() {
    try {
        const res  = await fetch(`${API}/repositories`);
        const data = await res.json();
        const repos = data.repositories || [];

        // Sidebar
        document.getElementById("sidebar-repo-list").innerHTML = repos.length
            ? repos.map(r => `<div class="sidebar-repo-item" onclick="selectRepo('${r.repo_id}')" title="${r.url}">${r.repo_id}</div>`).join("")
            : `<p class="muted-sm">None yet</p>`;

        // Global dropdown
        const opts = '<option value="">— select repo —</option>' +
            repos.map(r => `<option value="${r.repo_id}">${r.repo_id}</option>`).join("");
        document.getElementById("global-repo").innerHTML = opts;
        if (currentRepo) document.getElementById("global-repo").value = currentRepo;

        const currentRepoData = repos.find(r => r.repo_id === currentRepo);
        if (currentRepoData) {
            updateDashboardMetrics({
                entities_found: currentRepoData.entity_count,
                chunks_indexed: currentRepoData.chunk_count,
                bugs_found: 0,
                smells_found: 0,
                patterns_found: 0,
                debt_grade: currentRepoData.debt_grade || "—",
            });
        } else {
            updateDashboardMetrics();
        }

        // Repos tab
        const gradeColor = { A: "#10b981", B: "#84cc16", C: "#f59e0b", D: "#f97316", F: "#ef4444" };
        document.getElementById("repos-list").innerHTML = repos.length
            ? repos.map(r => `
                <div class="repo-card">
                    <h4>${r.repo_id}</h4>
                    <p><a href="${r.url}" target="_blank">${r.url}</a></p>
                    <p>${new Date(r.analyzed_at).toLocaleString()}</p>
                    <button class="btn" type="button" onclick="rebuildRepository('${r.repo_id}', this)">Rebuild search index</button>
                    <div class="repo-stats">
                        <div class="repo-stat"><strong>${r.entity_count}</strong> entities</div>
                        <div class="repo-stat"><strong>${r.chunk_count}</strong> chunks</div>
                        <div class="repo-stat grade-tag" style="background:${gradeColor[r.debt_grade] || '#6366f1'}22;color:${gradeColor[r.debt_grade] || '#6366f1'}">Grade ${r.debt_grade}</div>
                    </div>
                </div>`).join("")
            : `<p class="muted-sm">No repositories analyzed yet.</p>`;
    } catch (err) { console.error(err); }
}

function selectRepo(id) {
    currentRepo = id;
    document.getElementById("global-repo").value = id;
    showTab("overview");
    loadArchSummary();
}

async function rebuildRepository(repoId, button) {
    if (!confirm(`Rebuild the search index for ${repoId}? This reclones the repository and uses the embedding API.`)) return;

    const originalLabel = button.textContent;
    button.disabled = true;
    button.textContent = "Rebuilding…";
    try {
        const repo = await readApiResponse(await fetch(`${API}/repository/${encodeURIComponent(repoId)}`));
        const data = await readApiResponse(await fetch(`${API}/analyze`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                repo_url: repo.url,
                branch: repo.branch || "main",
                languages: ["python", "javascript"],
                force_reindex: true,
            }),
        }));
        currentRepo = repoId;
        await loadRepositories();
        document.getElementById("global-repo").value = repoId;
        updateDashboardMetrics(data);
        alert(`Search index rebuilt for ${repoId}. Try your question again.`);
    } catch (err) {
        alert(`Could not rebuild the search index: ${err.message}`);
        button.textContent = originalLabel;
    } finally {
        button.disabled = false;
    }
}

// ── Architecture summary ────────────────────────────────────────
async function loadArchSummary() {
    const repo = getRepo(); if (!repo) return;
    const box  = document.getElementById("arch-result");
    const text = document.getElementById("arch-text");
    box.style.display = "block";
    text.innerHTML = `<span class="spinner"></span>Generating architecture summary…`;

    try {
        const res  = await fetch(`${API}/architecture-summary/${repo}`);
        const data = await res.json();
        text.innerHTML = marked.parse(data.summary || "No summary available.");

        // Stats
        const repoData = await (await fetch(`${API}/repository/${repo}`)).json();
        const arch = repoData.architecture || {};
        updateDashboardMetrics({
            entities_found: repoData.entity_count || 0,
            chunks_indexed: repoData.chunk_count || 0,
            bugs_found: (repoData.bugs || []).length,
            smells_found: (repoData.smells || []).length,
            patterns_found: (repoData.patterns || []).length,
            debt_grade: repoData.debt?.grade || "—",
        });
        document.getElementById("arch-stats-card").style.display = "block";
        document.getElementById("arch-stats").innerHTML = `
            <div class="stat-box"><strong>${arch.file_count || 0}</strong><span>Files</span></div>
            <div class="stat-box"><strong>${arch.total_lines_of_code?.toLocaleString() || 0}</strong><span>Lines of Code</span></div>
            <div class="stat-box"><strong>${repoData.entity_count || 0}</strong><span>Entities</span></div>
            <div class="stat-box"><strong>${repoData.chunk_count || 0}</strong><span>Code Chunks</span></div>`;
    } catch (err) {
        const message = err.message.includes("generativelanguage.googleapis.com") || err.message.includes("Gemini API")
            ? "AI architecture summary is currently unavailable. Please check the Gemini API key, model settings, and service quota."
            : err.message;
        text.innerHTML = `<span style="color:var(--error)">${message}</span>`;
    }
}

// ── Q&A ─────────────────────────────────────────────────────────
function setQ(q) { document.getElementById("question-input").value = q; showTab("query"); }

function learningResourcesHtml(resources) {
    if (!resources?.length) return "";
    return `<div class="learning-resources"><h4>Learn more</h4><p class="muted-sm">Selected from the languages and topics in this answer.</p><div class="resource-list">${resources.map(resource =>
        `<a class="resource-link" href="${resource.url}" target="_blank" rel="noopener noreferrer"><span>${resource.type}</span>${resource.title}<b aria-hidden="true">↗</b></a>`
    ).join("")}</div></div>`;
}

function renderLearningResources(resources) {
    const box = document.getElementById("learning-resources");
    if (!resources?.length) { box.hidden = true; box.innerHTML = ""; return; }
    box.hidden = false;
    const cards = resources.map(resource =>
        `<a class="resource-link" href="${resource.url}" target="_blank" rel="noopener noreferrer"><span>${resource.type}</span>${resource.title}</a>`
    ).join("");
    box.innerHTML = `<h4>Learn more</h4><p class="muted-sm">Selected from the languages and topics in this answer.</p><div class="resource-list">${cards}</div>`;
}

async function askQuestion() {
    const repo     = getRepo(); if (!repo) return;
    const question = document.getElementById("question-input").value.trim();
    if (!question) { alert("Please enter a question"); return; }

    const box  = document.getElementById("qa-result");
    const text = document.getElementById("answer-text");
    const conf = document.getElementById("confidence-score");
    const model = document.getElementById("answer-model");
    box.style.display = "block";
    text.innerHTML = `<span class="spinner"></span>Thinking…`;
    conf.textContent = "";
    model.textContent = "";
    renderLearningResources([]);

    try {
        const res  = await fetch(`${API}/query`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question, repo_id: repo, context_depth: 5 }),
        });
        const data = await res.json();
        if (res.ok) {
            text.innerHTML = marked.parse(data.answer);
            renderLearningResources(data.learning_resources);
            model.textContent = data.model ? `Answered by ${data.model}` : "";
            const pct = (data.confidence * 100).toFixed(1);
            conf.textContent = `Confidence: ${pct}%`;
            conf.className = `badge${data.confidence < 0.3 ? " low" : ""}`;
        } else {
            text.innerHTML = `<span style="color:var(--error)">${data.detail}</span>`;
        }
    } catch (err) { text.innerHTML = `<span style="color:var(--error)">${err.message}</span>`; }
}

// ── Bugs ─────────────────────────────────────────────────────────
async function loadBugs() {
    const repo = getRepo(); if (!repo) return;
    const container = document.getElementById("bugs-container");
    container.innerHTML = `<span class="spinner"></span>Loading bugs…`;
    try {
        const data = await (await fetch(`${API}/bugs/${repo}`)).json();
        const bugs = data.bugs || [];
        if (!bugs.length) { container.innerHTML = `<div class="empty-state"><p>No bugs detected.</p></div>`; return; }
        container.innerHTML = `<p class="muted-sm" style="margin-bottom:12px">${bugs.length} issue(s) found</p><div class="issue-list">${bugs.map(b => issueCard(b)).join("")}</div>`;
    } catch (err) { container.innerHTML = `<span style="color:var(--error)">${err.message}</span>`; }
}

// ── Smells ───────────────────────────────────────────────────────
async function loadSmells() {
    const repo = getRepo(); if (!repo) return;
    const container = document.getElementById("smells-container");
    container.innerHTML = `<span class="spinner"></span>Loading code smells…`;
    try {
        const data   = await (await fetch(`${API}/smells/${repo}`)).json();
        const smells = data.smells || [];
        if (!smells.length) { container.innerHTML = `<div class="empty-state"><p>No code smells detected.</p></div>`; return; }
        container.innerHTML = `<p class="muted-sm" style="margin-bottom:12px">${smells.length} smell(s) found</p><div class="issue-list">${smells.map(s => issueCard(s)).join("")}</div>`;
    } catch (err) { container.innerHTML = `<span style="color:var(--error)">${err.message}</span>`; }
}

function issueCard(item) {
    const sev = item.severity || "low";
    const file = item.file_path ? item.file_path.split(/[\\/]/).slice(-2).join("/") : "";
    return `
    <div class="issue-card ${sev}">
        <div class="issue-header">
            <span class="issue-type">${(item.type || "").replace(/_/g, " ")}</span>
            <span class="sev-badge sev-${sev}">${sev}</span>
        </div>
        <div class="issue-file">${file}${item.line_number ? ` : line ${item.line_number}` : ""}</div>
        <div class="issue-desc">${item.description || ""}</div>
        ${item.suggestion ? `<div class="issue-suggestion">${item.suggestion}</div>` : ""}
    </div>`;
}

// ── Patterns ─────────────────────────────────────────────────────
async function loadPatterns() {
    const repo = getRepo(); if (!repo) return;
    const container = document.getElementById("patterns-container");
    container.innerHTML = `<span class="spinner"></span>Detecting design patterns…`;
    try {
        const data     = await (await fetch(`${API}/patterns/${repo}`)).json();
        const patterns = data.patterns || [];
        if (!patterns.length) { container.innerHTML = `<div class="empty-state"><p>No design patterns detected.</p></div>`; return; }
        container.innerHTML = `<p class="muted-sm" style="margin-bottom:12px">${patterns.length} pattern(s) found</p>
        <div class="pattern-grid">${patterns.map(p => `
            <div class="pattern-card">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
                    <div class="pattern-name">${p.name}</div>
                    <span class="pattern-conf conf-${p.confidence}">${p.confidence}</span>
                </div>
                <div class="pattern-file">${p.file_path.split(/[\\/]/).slice(-2).join("/")} : line ${p.line_number}</div>
                <div class="pattern-desc">${p.description}</div>
            </div>`).join("")}</div>`;
    } catch (err) { container.innerHTML = `<span style="color:var(--error)">${err.message}</span>`; }
}

// ── Technical Debt ───────────────────────────────────────────────
async function loadDebt() {
    const repo = getRepo(); if (!repo) return;
    const container = document.getElementById("debt-container");
    container.innerHTML = `<span class="spinner"></span>Calculating technical debt…`;
    try {
        const data = await (await fetch(`${API}/debt/${repo}`)).json();
        const d    = data.debt || {};
        const maxScore = Math.max(...(d.top_files || []).map(f => f.score), 1);
        container.innerHTML = `
        <div class="debt-grade-box">
            <div class="grade-circle grade-${d.grade}">${d.grade}</div>
            <div class="debt-summary"><strong>Score: ${d.score}/100</strong><br>${d.summary}</div>
        </div>
        <div class="debt-stats">
            <div class="debt-stat"><strong style="color:var(--error)">${d.high_severity}</strong><span>High Severity</span></div>
            <div class="debt-stat"><strong style="color:var(--warning)">${d.medium_severity}</strong><span>Medium Severity</span></div>
            <div class="debt-stat"><strong style="color:var(--info)">${d.low_severity}</strong><span>Low Severity</span></div>
        </div>
        ${d.top_files?.length ? `
        <div class="top-files">
            <h4>Top Offending Files</h4>
            ${d.top_files.map(f => `
            <div class="top-file-row">
                <div class="top-file-name" title="${f.file}">${f.file.split(/[\\/]/).slice(-2).join("/")}</div>
                <div class="top-file-bar-wrap"><div class="top-file-bar" style="width:${Math.round(f.score/maxScore*100)}%"></div></div>
                <div class="top-file-score">${f.score}</div>
            </div>`).join("")}
        </div>` : ""}`;
    } catch (err) { container.innerHTML = `<span style="color:var(--error)">${err.message}</span>`; }
}

// ── Dependency Graph ─────────────────────────────────────────────
async function loadGraph() {
    const repo = getRepo(); if (!repo) return;
    const container = document.getElementById("graph-container");
    container.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted)"><span class="spinner"></span>Building graph…</div>`;
    try {
        const data = await (await fetch(`${API}/dependency-graph/${repo}`)).json();
        if (!data.nodes?.length) {
            container.innerHTML = `<div class="empty-state"><p>No dependency data available.</p></div>`;
            return;
        }
        const nodes = new vis.DataSet(data.nodes.map(n => ({ id: n.id, label: n.label, color: { background: "#1e1e3f", border: "#6366f1", highlight: { background: "#6366f1", border: "#a5b4fc" } }, font: { color: "#e2e8f0", size: 12 } })));
        const edges = new vis.DataSet(data.edges.map(e => ({ from: e.from, to: e.to, arrows: "to", color: { color: "#2a2a50", highlight: "#6366f1" } })));
        new vis.Network(container, { nodes, edges }, {
            physics: { stabilization: { iterations: 100 }, barnesHut: { gravitationalConstant: -3000 } },
            interaction: { hover: true, tooltipDelay: 200 },
            layout: { improvedLayout: true },
        });
    } catch (err) { container.innerHTML = `<span style="color:var(--error)">${err.message}</span>`; }
}

// ── AI Tools ─────────────────────────────────────────────────────
function showToolResult(html) {
    document.getElementById("tool-result").style.display = "block";
    document.getElementById("tool-text").innerHTML = html;
}

async function explainEntity() {
    const repo = getRepo(); if (!repo) return;
    const name = prompt("Enter the function or class name to explain:");
    if (!name) return;
    showToolResult(`<span class="spinner"></span>Explaining <strong>${name}</strong>…`);
    try {
        const res  = await fetch(`${API}/explain/${repo}?entity_name=${encodeURIComponent(name)}`, { method: "POST" });
        const data = await res.json();
        showToolResult(res.ok ? marked.parse(data.explanation) + learningResourcesHtml(data.learning_resources) : `<span style="color:var(--error)">${data.detail}</span>`);
    } catch (err) { showToolResult(`<span style="color:var(--error)">${err.message}</span>`); }
}

async function findImplementation() {
    const repo = getRepo(); if (!repo) return;
    const feat = prompt("What feature do you want to find? (e.g. 'authentication', 'database connection'):");
    if (!feat) return;
    showToolResult(`<span class="spinner"></span>Searching for <strong>${feat}</strong>…`);
    try {
        const res  = await fetch(`${API}/find/${repo}?feature=${encodeURIComponent(feat)}`, { method: "POST" });
        const data = await res.json();
        showToolResult(res.ok ? marked.parse(data.implementation) + learningResourcesHtml(data.learning_resources) : `<span style="color:var(--error)">${data.detail}</span>`);
    } catch (err) { showToolResult(`<span style="color:var(--error)">${err.message}</span>`); }
}

async function getRefactoring() {
    const repo = getRepo(); if (!repo) return;
    showToolResult(`<span class="spinner"></span>Generating refactoring suggestions…`);
    try {
        const res  = await fetch(`${API}/refactor/${repo}`, { method: "POST" });
        const data = await res.json();
        showToolResult(res.ok ? marked.parse(data.suggestions) : `<span style="color:var(--error)">${data.detail}</span>`);
    } catch (err) { showToolResult(`<span style="color:var(--error)">${err.message}</span>`); }
}

async function generateTests() {
    const repo = getRepo(); if (!repo) return;
    const name = prompt("Enter the function or class name to generate tests for:");
    if (!name) return;
    showToolResult(`<span class="spinner"></span>Generating pytest tests for <strong>${name}</strong>…`);
    try {
        const res  = await fetch(`${API}/generate-tests/${repo}?entity_name=${encodeURIComponent(name)}`, { method: "POST" });
        const data = await res.json();
        if (res.ok) {
            showToolResult(`<p style="color:var(--text-muted);margin-bottom:10px">Framework: <strong>${data.framework}</strong></p>` + marked.parse("```python\n" + data.tests + "\n```"));
        } else {
            showToolResult(`<span style="color:var(--error)">${data.detail}</span>`);
        }
    } catch (err) { showToolResult(`<span style="color:var(--error)">${err.message}</span>`); }
}

// ── Sidebar resize ───────────────────────────────────────────────
function initSidebarResize() {
    const sidebar = document.getElementById("sidebar");
    const handle  = document.getElementById("sidebar-resize");
    if (!sidebar || !handle) return;
    let dragging  = false;
    let startX, startW;

    handle.addEventListener("mousedown", e => {
        dragging = true;
        startX   = e.clientX;
        startW   = sidebar.offsetWidth;
        handle.classList.add("dragging");
        document.body.style.cursor    = "col-resize";
        document.body.style.userSelect = "none";
    });

    document.addEventListener("mousemove", e => {
        if (!dragging) return;
        const w = Math.min(400, Math.max(160, startW + (e.clientX - startX)));
        sidebar.style.width    = w + "px";
        sidebar.style.minWidth = w + "px";
    });

    document.addEventListener("mouseup", () => {
        if (!dragging) return;
        dragging = false;
        handle.classList.remove("dragging");
        document.body.style.cursor    = "";
        document.body.style.userSelect = "";
    });
}

// ── Init ─────────────────────────────────────────────────────────
window.addEventListener("load", () => {
    checkAPI();
    loadRepositories();
    setInterval(checkAPI, 30000);
});
