/* PHOS Viewer — Library screen application */

const API_BASE = ""; // Same origin

const state = {
    runs: [],
    filterKind: "",
    filterPool: "",
    hasAtlas: false,
    starredOnly: false,
    search: "",
};

const runListEl = document.getElementById("run-list");
const emptyStateEl = document.getElementById("empty-state");
const searchEl = document.getElementById("search");
const filterKindEl = document.getElementById("filter-kind");
const filterPoolEl = document.getElementById("filter-pool");
const hasAtlasEl = document.getElementById("has-atlas");
const showStarredEl = document.getElementById("show-starred");
const refreshEl = document.getElementById("refresh");

async function fetchRuns() {
    try {
        const response = await fetch(`${API_BASE}/api/runs`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        state.runs = await response.json();
        render();
    } catch (err) {
        console.error("Failed to load runs:", err);
        runListEl.innerHTML = `<p class="error">Failed to load runs: ${err.message}</p>`;
        emptyStateEl.style.display = "none";
    }
}

function render() {
    const filtered = state.runs.filter(run => {
        const kindMatch = state.filterKind === "" || run.kind === state.filterKind;
        const poolMatch = state.filterPool === "" || run.pool === state.filterPool;
        const hasAtlasMatch = !state.hasAtlas || true; // We don't know yet without fetching detail
        const starMatch = !state.showStarred || true; // Sidecar not yet implemented
        const searchMatch = state.search === "" ||
            run.title.toLowerCase().includes(state.search.toLowerCase()) ||
            run.run_id.toLowerCase().includes(state.search.toLowerCase());
        return kindMatch && poolMatch && hasAtlasMatch && starMatch && searchMatch;
    });

    if (filtered.length === 0) {
        runListEl.innerHTML = "";
        emptyStateEl.style.display = "block";
        return;
    }

    emptyStateEl.style.display = "none";

    runListEl.innerHTML = filtered.map(run => `
        <a href="detail.html?run=${encodeURIComponent(run.name)}" class="run-card">
            <h3>${escapeHtml(run.title)}</h3>
            <div class="meta">
                <span class="badge ${run.kind}">${escapeHtml(run.kind)}</span>
                <span class="badge ${run.pool}">${escapeHtml(run.pool)}</span>
            </div>
            <div class="headline">
                <span>ID: ${run.run_id.substring(0, 12)}...</span>
            </div>
        </a>
    `).join("");
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function init() {
    searchEl.addEventListener("input", (e) => {
        state.search = e.target.value;
        render();
    });

    filterKindEl.addEventListener("change", (e) => {
        state.filterKind = e.target.value;
        render();
    });

    filterPoolEl.addEventListener("change", (e) => {
        state.filterPool = e.target.value;
        render();
    });

    hasAtlasEl.addEventListener("change", (e) => {
        state.hasAtlas = e.target.checked;
        render();
    });

    showStarredEl.addEventListener("change", (e) => {
        state.showStarred = e.target.checked;
        render();
    });

    refreshEl.addEventListener("click", () => {
        fetchRuns();
    });

    fetchRuns();
}

init();
