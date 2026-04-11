const ACTIVE_THREAD_KEY = "scientificAgentActiveThread";

const state = {
  baseUrl: localStorage.getItem("scientificAgentBaseUrl") || "http://127.0.0.1:8000",
  runId: "",
  pollHandle: null,
  latestRun: null,
  announcedSteps: new Set(),
  lastRunStatus: "",
  threads: [],
  activeThreadId: localStorage.getItem(ACTIVE_THREAD_KEY) || "",
  showArchivedThreads: false,
  threadSearch: "",
  memoryProposals: [],
  selectedProposalFilenames: [],
  membershipPayload: null,
  selectedHypothesisKey: "",
  selectedNegativeKey: "",
  selectedExperimentId: "",
  selectedExperimentRunId: "",
  experimentData: {
    specifications: [],
    protocols: [],
    runs: [],
    qualityControlReviews: [],
    interpretations: [],
  },
};

const qs = (id) => document.getElementById(id);
const qsa = (selector) => Array.from(document.querySelectorAll(selector));

function nowIso() {
  return new Date().toISOString();
}

function currentIdentity() {
  return {
    user_id: qs("userIdInput")?.value.trim() || "",
    project_id: qs("projectIdInput")?.value.trim() || "",
    group_id: qs("groupIdInput")?.value.trim() || "",
    group_role: qs("groupRoleInput")?.value.trim() || "",
  };
}

function identityQueryString() {
  const params = new URLSearchParams();
  const identity = currentIdentity();
  Object.entries(identity).forEach(([key, value]) => {
    if (value) {
      params.set(key, value);
    }
  });
  const query = params.toString();
  return query ? `?${query}` : "";
}

function getActiveThread() {
  return state.threads.find((thread) => thread.thread_id === state.activeThreadId) || null;
}

function setActiveThreadId(threadId) {
  state.activeThreadId = threadId;
  localStorage.setItem(ACTIVE_THREAD_KEY, threadId);
}

function resetRunAnnouncements() {
  state.announcedSteps = new Set();
  state.lastRunStatus = "";
  state.selectedHypothesisKey = "";
  state.selectedNegativeKey = "";
  state.selectedExperimentId = "";
  state.selectedExperimentRunId = "";
}

function syncStateFromActiveThread() {
  const thread = getActiveThread();
  state.runId = thread?.run_id || "";
  state.latestRun = null;
  resetRunAnnouncements();
  if (thread) {
    qs("userIdInput").value = thread.user_id || "";
    qs("projectIdInput").value = thread.project_id || "";
    qs("groupIdInput").value = thread.group_id || "";
    qs("groupRoleInput").value = thread.group_role || "";
  } else {
    qs("userIdInput").value = "";
    qs("projectIdInput").value = "";
    qs("groupIdInput").value = "";
    qs("groupRoleInput").value = "";
  }
}

function setBaseUrl(value) {
  state.baseUrl = value.replace(/\/+$/, "");
  localStorage.setItem("scientificAgentBaseUrl", state.baseUrl);
  qs("baseUrl").value = state.baseUrl;
}

function setAccessStatus(message = "", tone = "info") {
  const node = qs("accessStatus");
  if (!node) {
    return;
  }
  if (!message) {
    node.textContent = "";
    node.className = "access-banner hidden";
    return;
  }
  node.textContent = message;
  node.className = `access-banner ${tone}`;
}

function parseApiError(error) {
  try {
    return JSON.parse(error.message || "{}");
  } catch {
    return { detail: error.message || "Unknown error" };
  }
}

function describeAccessError(error) {
  const payload = parseApiError(error);
  const detail = String(payload.detail || "");
  const identity = currentIdentity();
  const scopedIdentity = [
    identity.user_id ? `user ${identity.user_id}` : "",
    identity.project_id ? `project ${identity.project_id}` : "",
    identity.group_id ? `group ${identity.group_id}` : "",
    identity.group_role ? `role ${identity.group_role}` : "",
  ]
    .filter(Boolean)
    .join(", ");

  if (detail.includes("Thread access denied")) {
    return `You cannot open this research thread with the current identity${scopedIdentity ? ` (${scopedIdentity})` : ""}. Make sure you are a member of the matching project or group.`;
  }
  if (detail.includes("Thread update denied") || detail.includes("Thread delete denied") || detail.includes("Thread message append denied")) {
    return `You do not have write access to this thread${scopedIdentity ? ` as ${scopedIdentity}` : ""}. You usually need to be the owner or a contributor in the linked project or group.`;
  }
  if (detail.includes("Run access denied") || detail.includes("Report access denied") || detail.includes("Usage access denied") || detail.includes("Graph access denied")) {
    return `You do not have access to this investigation run${scopedIdentity ? ` as ${scopedIdentity}` : ""}. Check that you belong to the same project or research group.`;
  }
  if (detail.includes("Workflow submission denied")) {
    return `You cannot start a workflow for this project/group with the current identity${scopedIdentity ? ` (${scopedIdentity})` : ""}.`;
  }
  if (detail.includes("403")) {
    return `Access denied for the current identity${scopedIdentity ? ` (${scopedIdentity})` : ""}.`;
  }
  return "";
}

function handleUiError(error, targetId = "", fallbackMessage = "") {
  const accessMessage = describeAccessError(error);
  if (accessMessage) {
    setAccessStatus(accessMessage, "error");
  }
  if (targetId) {
    renderJson(targetId, { error: accessMessage || fallbackMessage || error.message });
  }
}

async function api(path, options = {}) {
  const response = await fetch(`${state.baseUrl}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const text = await response.text();
  let payload;
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    payload = { raw: text };
  }
  if (!response.ok) {
    throw new Error(JSON.stringify(payload, null, 2));
  }
  return payload;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function normalizeText(value) {
  return String(value || "").toLowerCase();
}

function termSet(value) {
  return new Set(
    normalizeText(value)
      .match(/[a-z0-9_]+/g)
      ?.filter((term) => term.length >= 4) || []
  );
}

function overlapCount(left, right) {
  let count = 0;
  for (const term of left) {
    if (right.has(term)) {
      count += 1;
    }
  }
  return count;
}

function renderJson(targetId, payload) {
  qs(targetId).textContent =
    typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
}

function setPanelStatus(targetId, message = "") {
  const node = qs(targetId);
  if (!node) {
    return;
  }
  node.textContent = message;
}

function roleRank(role) {
  return { viewer: 0, contributor: 1, curator: 2, admin: 3 }[role] ?? -1;
}

function eventTimeValue(timestamp) {
  const value = Date.parse(timestamp || "");
  return Number.isNaN(value) ? 0 : value;
}

function selectedProposalItems() {
  const selected = new Set(state.selectedProposalFilenames);
  return state.memoryProposals.filter((item) => selected.has(item.filename));
}

function renderProposalList(items) {
  const root = qs("memoryProposalList");
  if (!root) {
    return;
  }
  root.innerHTML = "";
  const targetScope = qs("proposalTargetFilter")?.value.trim() || "";
  const filtered = (Array.isArray(items) ? items : []).filter((item) => {
    if (targetScope && item.target_scope !== targetScope) {
      return false;
    }
    return true;
  });

  if (filtered.length === 0) {
    root.innerHTML = `
      <div class="stack-card">
        <strong>No pending proposals.</strong>
        <div class="stack-meta">Curator and admin users will see promotion proposals here.</div>
      </div>
    `;
    setPanelStatus("memoryProposalStatus", "No pending promotion proposals.");
    return;
  }

  setPanelStatus(
    "memoryProposalStatus",
    `${filtered.length} proposal${filtered.length === 1 ? "" : "s"} waiting for review. ${selectedProposalItems().length} selected.`
  );

  for (const item of filtered) {
    const card = document.createElement("div");
    card.className = "stack-card";
    const checked = state.selectedProposalFilenames.includes(item.filename) ? "checked" : "";
    card.innerHTML = `
      <div class="proposal-header">
        <input type="checkbox" data-action="select" ${checked} />
        <div>
          <strong>${escapeHtml(item.title || item.filename)}</strong>
          <div class="stack-meta">${escapeHtml(item.source_scope)} -> ${escapeHtml(item.target_scope)} | proposed by ${escapeHtml(item.proposed_by || "unknown")}</div>
        </div>
      </div>
      <div class="stack-body">${escapeHtml(item.summary || "No summary.")}</div>
      <div class="proposal-actions">
        <button type="button" class="secondary compact" data-action="inspect">Inspect</button>
        <button type="button" class="secondary compact" data-action="approve">Approve</button>
        <button type="button" class="secondary compact" data-action="reject">Reject</button>
      </div>
    `;
    card.querySelector('[data-action="select"]').addEventListener("change", (event) => {
      const selected = new Set(state.selectedProposalFilenames);
      if (event.target.checked) {
        selected.add(item.filename);
      } else {
        selected.delete(item.filename);
      }
      state.selectedProposalFilenames = Array.from(selected);
      renderProposalList(state.memoryProposals);
    });
    card.querySelector('[data-action="inspect"]').addEventListener("click", () => {
      qs("memoryPromoteFilename").value = item.filename;
      qs("memoryFilename").value = item.filename;
      qs("memoryPromoteScope").value = item.target_scope || "group";
      loadMemoryAudit(item.filename).catch((error) => setPanelStatus("memoryAuditStatus", describeAccessError(error) || error.message));
    });
    card.querySelector('[data-action="approve"]').addEventListener("click", () => {
      qs("memoryPromoteFilename").value = item.filename;
      qs("memoryPromoteScope").value = item.target_scope || "group";
      approveProposal(item).catch((error) => setPanelStatus("memoryProposalStatus", describeAccessError(error) || error.message));
    });
    card.querySelector('[data-action="reject"]').addEventListener("click", () => {
      qs("memoryPromoteFilename").value = item.filename;
      rejectProposal(item).catch((error) => setPanelStatus("memoryProposalStatus", describeAccessError(error) || error.message));
    });
    root.appendChild(card);
  }
}

function renderAuditTimeline(payload) {
  const root = qs("memoryAuditTimeline");
  if (!root) {
    return;
  }
  root.innerHTML = "";
  const events = (Array.isArray(payload?.events) ? payload.events : []).slice().sort((left, right) => {
    return eventTimeValue(right.timestamp) - eventTimeValue(left.timestamp);
  });
  if (events.length === 0) {
    root.innerHTML = `
      <div class="stack-card audit-card">
        <strong>No audit events yet.</strong>
        <div class="stack-meta">Select a memory proposal to inspect its history.</div>
      </div>
    `;
    setPanelStatus("memoryAuditStatus", "No audit events available.");
    return;
  }

  setPanelStatus(
    "memoryAuditStatus",
    `${payload.title || payload.filename || "Memory"} | status: ${payload.status || "unknown"} | scope: ${payload.scope || "unknown"}`
  );
  for (const event of events) {
    const card = document.createElement("div");
    card.className = "stack-card audit-card";
    const label =
      {
        created: "Created",
        proposal: "Proposal",
        approved: "Approved",
        rejected: "Rejected",
      }[event.kind] || (event.kind || "Event");
    card.innerHTML = `
      <div class="audit-kind">${escapeHtml(label)}</div>
      <div class="stack-meta">${escapeHtml(event.actor || "system")}</div>
      <div class="stack-body">${escapeHtml(event.detail || "")}</div>
      <div class="audit-timestamp">${escapeHtml(event.timestamp || "timestamp unavailable")}</div>
    `;
    root.appendChild(card);
  }
}

function renderMembershipList(payload) {
  const root = qs("membershipList");
  if (!root) {
    return;
  }
  root.innerHTML = "";
  state.membershipPayload = payload;
  const search = qs("memberSearch")?.value.trim().toLowerCase() || "";
  const roleFilter = qs("memberRoleFilter")?.value.trim() || "";
  const sortMode = qs("memberSort")?.value.trim() || "role-desc";
  const members = (Array.isArray(payload?.members) ? payload.members : [])
    .filter((member) => {
      if (roleFilter && member.role !== roleFilter) {
        return false;
      }
      if (!search) {
        return true;
      }
      const haystack = `${member.display_name || ""} ${member.user_id || ""}`.toLowerCase();
      return haystack.includes(search);
    })
    .slice()
    .sort((left, right) => {
      if (sortMode === "role-desc") {
        return roleRank(right.role) - roleRank(left.role) || String(left.user_id).localeCompare(String(right.user_id));
      }
      if (sortMode === "role-asc") {
        return roleRank(left.role) - roleRank(right.role) || String(left.user_id).localeCompare(String(right.user_id));
      }
      const leftName = String(left.display_name || left.user_id || "");
      const rightName = String(right.display_name || right.user_id || "");
      return sortMode === "name-desc"
        ? rightName.localeCompare(leftName)
        : leftName.localeCompare(rightName);
    });
  if (members.length === 0) {
    root.innerHTML = `
      <div class="stack-card member-card">
        <strong>No members loaded.</strong>
        <div class="stack-meta">Use the buttons above to load or create group/project memberships.</div>
      </div>
    `;
    setPanelStatus("membershipStatus", "No members found for the selected scope.");
    return;
  }

  setPanelStatus(
    "membershipStatus",
    `${payload.scope || "scope"}: ${payload.scope_id || "unknown"} | ${members.length} member${members.length === 1 ? "" : "s"}`
  );
  for (const member of members) {
    const card = document.createElement("div");
    card.className = "stack-card member-card";
    card.innerHTML = `
      <strong>${escapeHtml(member.display_name || member.user_id || "Unnamed member")}</strong>
      <div class="stack-meta">${escapeHtml(member.user_id || "unknown user")}</div>
      <div class="member-meta-row">
        <span class="scope-pill">${escapeHtml(member.role || "unknown role")}</span>
      </div>
    `;
    root.appendChild(card);
  }
}

function renderEmptyWorkspace() {
  renderWorkflowSummary({});
  renderWorkflowDiagnostics({});
  renderWorkflowTimeline({});
  renderHypotheses({});
  renderEvidence({});
  renderNegativeResults({});
  renderGraphVisual({});
  renderMemorySearchResults({});
  renderUsageSummary({});
  buildExperimentDetailView({});
  renderJson("workflowOutput", {});
  renderJson("reportOutput", {});
  renderJson("usageOutput", {});
  renderJson("graphOutput", {});
}

async function ensureThreadsLoaded() {
  const joiner = identityQueryString() ? "&" : "?";
  const payload = await api(`/threads${identityQueryString()}${joiner}include_archived=true`);
  state.threads = Array.isArray(payload) ? payload : [];

  if (state.threads.length === 0) {
    const created = await api("/threads", {
      method: "POST",
      body: JSON.stringify({
        title: "Hypothermia Investigation",
        created_at: nowIso(),
        ...currentIdentity(),
      }),
    });
    state.threads = [created];
  }

  const active =
    state.threads.find((thread) => thread.thread_id === state.activeThreadId) || state.threads[0];
  setActiveThreadId(active.thread_id);
  syncStateFromActiveThread();
}

async function refreshThreads() {
  const joiner = identityQueryString() ? "&" : "?";
  const payload = await api(`/threads${identityQueryString()}${joiner}include_archived=true`);
  state.threads = Array.isArray(payload) ? payload : [];
  if (!getActiveThread() && state.threads.length > 0) {
    setActiveThreadId(state.threads[0].thread_id);
    syncStateFromActiveThread();
  }
  renderThreadList();
  renderThreadControls();
  renderChat();
  renderThreadSnapshot();
  updateCurrentRunLabel();
}

async function createThread(title, initialMessage = null) {
  const thread = await api("/threads", {
    method: "POST",
    body: JSON.stringify({
      title,
      created_at: nowIso(),
      ...currentIdentity(),
      initial_message: initialMessage,
    }),
  });
  await refreshThreads();
  setActiveThreadId(thread.thread_id);
  syncStateFromActiveThread();
  renderThreadList();
  renderThreadControls();
  renderChat();
  renderThreadSnapshot();
  updateCurrentRunLabel();
  return thread;
}

async function updateThread(threadId, patch) {
  const thread = await api(`/threads/${threadId}${identityQueryString()}`, {
    method: "PATCH",
    body: JSON.stringify({
      ...patch,
      updated_at: nowIso(),
    }),
  });
  const index = state.threads.findIndex((item) => item.thread_id === threadId);
  if (index >= 0) {
    state.threads[index] = thread;
  } else {
    state.threads.unshift(thread);
  }
  return thread;
}

function buildThreadSnapshot(thread, runPayload = null) {
  const hypotheses = collectHypotheses(runPayload || {});
  const evidence = collectEvidence(runPayload || {});
  const negativeResults = collectNegativeResults(runPayload || {});
  const challengedHypothesisIds = Array.isArray(runPayload?.research_state?.challenged_hypothesis_ids)
    ? runPayload.research_state.challenged_hypothesis_ids
    : [];
  const beliefUpdate = runPayload?.research_state?.belief_update_summary || {};
  const executionCycle = runPayload?.research_state?.execution_cycle_summary || {};
  return {
    current_question: summarizeThreadQuestion(thread),
    main_hypotheses: hypotheses.length
      ? hypotheses.slice(0, 2).map((item) => item.name || item.title || item.prediction || "Untitled hypothesis")
      : ["No hypotheses yet."],
    key_evidence: evidence.length
      ? evidence.slice(0, 2).map((item) => `${item.title}: ${item.evidence}`)
      : ["No evidence summary yet."],
    negative_results: negativeResults.length
      ? negativeResults.slice(0, 3).map((item) => `${item.result} (${item.source})`)
      : ["No failed attempts captured yet."],
    challenged_hypotheses: challengedHypothesisIds.length
      ? challengedHypothesisIds.slice(0, 4)
      : hypotheses.length && negativeResults.length
        ? hypotheses.slice(0, 2).map((item) => item.hypothesis_id || item.name || "unknown hypothesis")
        : [],
    open_question: summarizeOpenQuestion(thread, runPayload || {}),
    recent_status: thread?.run_id
      ? `Last run: ${thread.run_id}${runPayload?.status ? ` (${runPayload.status})` : ""}`
      : "No run attached to this thread yet.",
    recommended_next_stage: runPayload?.research_state?.recommended_next_stage || "",
    next_cycle_goals: Array.isArray(beliefUpdate.next_cycle_goals) ? beliefUpdate.next_cycle_goals.slice(0, 3) : [],
    belief_update: {
      consensus_status: beliefUpdate.consensus_status || "",
      current_consensus: beliefUpdate.current_consensus || "",
      challenged_hypothesis_count: beliefUpdate.challenged_hypothesis_count || 0,
      status_counts: beliefUpdate.status_counts || {},
    },
    experiment_summary: {
      experiment_run_count: executionCycle.experiment_run_count || 0,
      quality_control_review_count: executionCycle.quality_control_review_count || 0,
      interpretation_record_count: executionCycle.interpretation_record_count || 0,
      next_decisions: Array.isArray(executionCycle.next_decisions) ? executionCycle.next_decisions.slice(0, 3) : [],
    },
    stage_machine: runPayload?.research_state?.stage_machine || {},
    literature_quality: runPayload?.research_state?.literature_quality_summary || {},
    manifest_summary: runPayload?.research_state?.run_manifest_summary || {},
    collaboration_identity: [
      thread?.user_id ? `user:${thread.user_id}` : "",
      thread?.project_id ? `project:${thread.project_id}` : "",
      thread?.group_id ? `group:${thread.group_id}` : "",
      thread?.group_role ? `role:${thread.group_role}` : "",
    ].filter(Boolean),
  };
}

async function syncThreadSnapshot(runPayload = null) {
  const thread = getActiveThread();
  if (!thread) {
    return null;
  }
  const snapshot = buildThreadSnapshot(thread, runPayload);
  const updated = await updateThread(thread.thread_id, { snapshot });
  const index = state.threads.findIndex((record) => record.thread_id === thread.thread_id);
  if (index >= 0) {
    state.threads[index] = updated;
  }
  return updated;
}

async function syncThreadIdentity() {
  const thread = getActiveThread();
  if (!thread) {
    return null;
  }
  const updated = await updateThread(thread.thread_id, currentIdentity());
  const index = state.threads.findIndex((record) => record.thread_id === thread.thread_id);
  if (index >= 0) {
    state.threads[index] = updated;
  }
  return updated;
}

async function appendThreadMessage(threadId, role, content) {
  const thread = await api(`/threads/${threadId}/messages${identityQueryString()}`, {
    method: "POST",
    body: JSON.stringify({
      role,
      content,
      created_at: nowIso(),
    }),
  });
  const index = state.threads.findIndex((item) => item.thread_id === threadId);
  if (index >= 0) {
    state.threads[index] = thread;
  }
  return thread;
}

async function pushChat(role, content) {
  const thread = getActiveThread();
  if (!thread) {
    return;
  }
  const updated = await appendThreadMessage(thread.thread_id, role, content);
  const index = state.threads.findIndex((item) => item.thread_id === thread.thread_id);
  if (index >= 0) {
    state.threads[index] = updated;
  }
  await syncThreadSnapshot(state.latestRun);
  renderChat();
  renderThreadSnapshot();
}

function renderThreadList() {
  const root = qs("threadList");
  root.innerHTML = "";
  const filteredThreads = state.threads.filter((thread) => {
    if (!state.showArchivedThreads && thread.archived) {
      return false;
    }
    if (!state.threadSearch.trim()) {
      return true;
    }
    const haystack = [
      thread.title,
      thread.snapshot?.current_question,
      ...(Array.isArray(thread.snapshot?.main_hypotheses) ? thread.snapshot.main_hypotheses : []),
      ...(Array.isArray(thread.snapshot?.key_evidence) ? thread.snapshot.key_evidence : []),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(state.threadSearch.trim().toLowerCase());
  });

  if (filteredThreads.length === 0) {
    root.innerHTML = `<div class="stack-card"><strong>No matching threads.</strong><div class="stack-meta">Adjust the search or archive filter.</div></div>`;
    return;
  }

  for (const thread of filteredThreads) {
    const snapshot = thread.snapshot || {};
    const preview =
      snapshot.current_question ||
      (Array.isArray(snapshot.main_hypotheses) ? snapshot.main_hypotheses[0] : "") ||
      "No research summary yet.";
    const negativePreview = Array.isArray(snapshot.negative_results) ? snapshot.negative_results[0] : "";
    const status = snapshot.recent_status || (thread.run_id ? `Last run: ${thread.run_id}` : "No run yet");
    const scopes = [
      thread.user_id ? `user:${thread.user_id}` : "",
      thread.project_id ? `project:${thread.project_id}` : "",
      thread.group_id ? `group:${thread.group_id}` : "",
      thread.group_role ? `role:${thread.group_role}` : "",
    ].filter(Boolean);
    const button = document.createElement("button");
    button.type = "button";
    button.className = `thread-chip ${thread.thread_id === state.activeThreadId ? "active" : ""} ${thread.archived ? "archived" : ""}`;
    button.innerHTML = `
      <div class="thread-chip-title">${escapeHtml(thread.title)}</div>
      <div class="thread-chip-meta">${escapeHtml(status)}</div>
      <div class="thread-chip-preview">${escapeHtml(preview)}</div>
      ${negativePreview ? `<div class="thread-chip-preview negative-preview">Failed route: ${escapeHtml(negativePreview)}</div>` : ""}
      <div class="thread-chip-scopes">
        ${scopes.length
          ? scopes.map((item) => `<span class="scope-pill">${escapeHtml(item)}</span>`).join("")
          : `<span class="scope-pill">unscoped</span>`}
      </div>
    `;
    button.addEventListener("click", async () => {
      setActiveThreadId(thread.thread_id);
      syncStateFromActiveThread();
      renderThreadList();
      renderThreadControls();
      renderChat();
      renderThreadSnapshot();
      updateCurrentRunLabel();
      if (state.runId) {
        qs("runIdInput").value = state.runId;
        await loadWorkflow().catch(() => undefined);
        await Promise.allSettled([loadReport(), loadUsage(), loadGraph()]);
      } else {
        qs("runIdInput").value = "";
        renderEmptyWorkspace();
      }
    });
    root.appendChild(button);
  }
}

function renderThreadControls() {
  const thread = getActiveThread();
  qs("threadTitleInput").value = thread?.title || "";
}

function renderChat() {
  const root = qs("chatTranscript");
  root.innerHTML = "";
  const thread = getActiveThread();
  const messages = Array.isArray(thread?.chat) ? thread.chat : [];
  if (messages.length === 0) {
    root.innerHTML = `
      <div class="chat-item system">
        <div class="chat-role">system</div>
        Start a research thread, continue a literature review, or refine an existing hypothesis set.
      </div>
    `;
    return;
  }

  for (const item of messages.slice(-16)) {
    const node = document.createElement("div");
    node.className = `chat-item ${item.role}`;
    node.innerHTML = `
      <div class="chat-role">${escapeHtml(item.role)}</div>
      <div>${escapeHtml(item.content)}</div>
    `;
    root.appendChild(node);
  }
  root.scrollTop = root.scrollHeight;
}

function lastUserMessage(thread) {
  const messages = Array.isArray(thread?.chat) ? thread.chat : [];
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === "user") {
      return messages[index].content;
    }
  }
  return null;
}

function lastAssistantMessage(thread) {
  const messages = Array.isArray(thread?.chat) ? thread.chat : [];
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === "assistant") {
      return messages[index].content;
    }
  }
  return null;
}

function summarizeThreadQuestion(thread) {
  return lastUserMessage(thread) || "No explicit question captured yet.";
}

function extractClaimText(claim) {
  if (!claim || typeof claim !== "object") {
    return "";
  }
  return claim.statement || claim.claim || claim.name || claim.title || "";
}

function collectHypotheses(runPayload) {
  const steps = Array.isArray(runPayload?.steps) ? runPayload.steps : [];
  const hypotheses = [];
  for (const step of steps) {
    const items = step?.parsed_output?.hypotheses;
    if (Array.isArray(items)) {
      for (let index = 0; index < items.length; index += 1) {
        const item = items[index];
        const key = `${step.profile_name || "unknown"}::${item?.hypothesis_id || index + 1}`;
        hypotheses.push({ ...item, source_step: step.profile_name || "unknown", hypothesis_key: key });
      }
    }
  }
  return hypotheses;
}

function getSelectedHypothesis(runPayload = state.latestRun || {}) {
  if (!state.selectedHypothesisKey) {
    return null;
  }
  const hypotheses = collectHypotheses(runPayload || {});
  return hypotheses.find((item) => item.hypothesis_key === state.selectedHypothesisKey) || null;
}

function deriveRelatedExperimentContext(runPayload = state.latestRun || {}) {
  const selected = getSelectedHypothesis(runPayload);
  const context = {
    selectedHypothesis: selected,
    selectedHypothesisId: selected?.hypothesis_id || "",
    relatedExperimentIds: new Set(),
    relatedRunIds: new Set(),
  };
  if (!selected) {
    return context;
  }
  for (const item of state.experimentData.specifications || []) {
    const hypothesisIds = Array.isArray(item?.hypothesis_ids) ? item.hypothesis_ids.map((value) => String(value)) : [];
    if (hypothesisIds.includes(context.selectedHypothesisId)) {
      context.relatedExperimentIds.add(String(item.experiment_id || ""));
    }
  }
  for (const item of state.experimentData.interpretations || []) {
    const linkedIds = [
      ...(Array.isArray(item?.supported_hypothesis_ids) ? item.supported_hypothesis_ids : []),
      ...(Array.isArray(item?.weakened_hypothesis_ids) ? item.weakened_hypothesis_ids : []),
      ...(Array.isArray(item?.inconclusive_hypothesis_ids) ? item.inconclusive_hypothesis_ids : []),
    ].map((value) => String(value));
    if (linkedIds.includes(context.selectedHypothesisId)) {
      if (item.experiment_id) {
        context.relatedExperimentIds.add(String(item.experiment_id));
      }
      if (item.run_id) {
        context.relatedRunIds.add(String(item.run_id));
      }
    }
  }
  for (const item of state.experimentData.runs || []) {
    if (context.relatedExperimentIds.has(String(item.experiment_id || "")) && item.run_id) {
      context.relatedRunIds.add(String(item.run_id));
    }
  }
  return context;
}

function deriveReverseExperimentContext() {
  const context = {
    selectedExperimentId: state.selectedExperimentId || "",
    selectedExperimentRunId: state.selectedExperimentRunId || "",
    relatedHypothesisIds: new Set(),
  };
  if (!context.selectedExperimentId && !context.selectedExperimentRunId) {
    return context;
  }
  for (const item of state.experimentData.specifications || []) {
    if (context.selectedExperimentId && String(item?.experiment_id || "") === context.selectedExperimentId) {
      for (const value of Array.isArray(item?.hypothesis_ids) ? item.hypothesis_ids : []) {
        context.relatedHypothesisIds.add(String(value));
      }
    }
  }
  for (const item of state.experimentData.interpretations || []) {
    const matchesExperiment =
      context.selectedExperimentId && String(item?.experiment_id || "") === context.selectedExperimentId;
    const matchesRun =
      context.selectedExperimentRunId && String(item?.run_id || "") === context.selectedExperimentRunId;
    if (!matchesExperiment && !matchesRun) {
      continue;
    }
    for (const value of [
      ...(Array.isArray(item?.supported_hypothesis_ids) ? item.supported_hypothesis_ids : []),
      ...(Array.isArray(item?.weakened_hypothesis_ids) ? item.weakened_hypothesis_ids : []),
      ...(Array.isArray(item?.inconclusive_hypothesis_ids) ? item.inconclusive_hypothesis_ids : []),
    ]) {
      context.relatedHypothesisIds.add(String(value));
    }
  }
  return context;
}

function buildHypothesisKeyMap(runPayload = state.latestRun || {}) {
  const map = {};
  for (const item of collectHypotheses(runPayload || {})) {
    map[item.hypothesis_key] = item;
  }
  return map;
}

function collectEvidence(runPayload) {
  const steps = Array.isArray(runPayload?.steps) ? runPayload.steps : [];
  const records = [];
  for (const step of steps) {
    const parsed = step?.parsed_output;
    if (!parsed || typeof parsed !== "object") {
      continue;
    }

    const claims = Array.isArray(parsed.claims) ? parsed.claims : [];
    for (const claim of claims) {
      const statement = extractClaimText(claim);
      const evidence = Array.isArray(claim.evidence)
        ? claim.evidence.join(" | ")
        : claim.evidence || claim.support || "No evidence listed";
      const uncertainty = claim.uncertainty || claim.uncertainties || "Not stated";
      records.push({
        source: step.profile_name || "unknown",
        title: statement || "Unnamed claim",
        evidence,
        uncertainty: Array.isArray(uncertainty) ? uncertainty.join(" | ") : uncertainty,
        quality: claim.quality_grade || "",
        bias: claim.bias_risk || "",
        conflictGroup: claim.conflict_group || "",
        conflictNote: claim.conflict_note || "",
      });
    }

    const standaloneEvidence = Array.isArray(parsed.evidence) ? parsed.evidence : [];
    for (const item of standaloneEvidence) {
      const text =
        item.statement || item.summary || item.title || item.description || JSON.stringify(item);
      records.push({
        source: step.profile_name || "unknown",
        title: text,
        evidence: item.source_ref || item.source || item.citation || "Evidence record",
        uncertainty: item.uncertainty || item.applicability || "Not stated",
        quality: item.quality_grade || "",
        bias: item.bias_risk || "",
        conflictGroup: item.conflict_group || "",
        conflictNote: item.conflict_note || "",
      });
    }
  }
  return records;
}

function collectNegativeResults(runPayload) {
  const steps = Array.isArray(runPayload?.steps) ? runPayload.steps : [];
  const records = [];
  for (const step of steps) {
    const items = step?.parsed_output?.negative_results;
    if (!Array.isArray(items)) {
      continue;
    }
    for (let index = 0; index < items.length; index += 1) {
      const item = items[index];
      if (!item || typeof item !== "object") {
        continue;
      }
      records.push({
        source: step.profile_name || "unknown",
        negative_key: `${step.profile_name || "unknown"}::negative::${index + 1}`,
        result: item.result || "Untitled negative result",
        reason: item.why_it_failed_or_did_not_support || "No failure analysis recorded.",
        implication: item.implication || "No implication captured.",
      });
    }
  }
  return records;
}

function linkHypothesesAndNegativeResults(runPayload) {
  const hypotheses = collectHypotheses(runPayload);
  const negativeResults = collectNegativeResults(runPayload);
  const linkMap = {
    hypotheses,
    negativeResults,
    byHypothesis: {},
    byNegative: {},
  };

  const backendLinks = Array.isArray(runPayload?.claim_graph?.negative_result_links)
    ? runPayload.claim_graph.negative_result_links
    : [];
  if (backendLinks.length > 0) {
    for (const hypothesis of hypotheses) {
      linkMap.byHypothesis[hypothesis.hypothesis_key] = [];
    }
    for (const negative of negativeResults) {
      linkMap.byNegative[negative.negative_key] = [];
    }
    for (const item of backendLinks) {
      const hypothesisId = String(item?.hypothesis_id || "").trim();
      const negativeId = String(item?.negative_result_id || "").trim();
      if (!hypothesisId || !negativeId) {
        continue;
      }
      if (!Array.isArray(linkMap.byHypothesis[hypothesisId])) {
        linkMap.byHypothesis[hypothesisId] = [];
      }
      if (!Array.isArray(linkMap.byNegative[negativeId])) {
        linkMap.byNegative[negativeId] = [];
      }
      if (!linkMap.byHypothesis[hypothesisId].includes(negativeId)) {
        linkMap.byHypothesis[hypothesisId].push(negativeId);
      }
      if (!linkMap.byNegative[negativeId].includes(hypothesisId)) {
        linkMap.byNegative[negativeId].push(hypothesisId);
      }
    }
    return linkMap;
  }

  for (const hypothesis of hypotheses) {
    const hypothesisTerms = termSet(
      [
        hypothesis.name,
        hypothesis.mechanism,
        hypothesis.prediction,
        ...(Array.isArray(hypothesis.failure_conditions) ? hypothesis.failure_conditions : []),
      ].join(" ")
    );
    const linkedNegatives = [];
    for (const negative of negativeResults) {
      const negativeTerms = termSet(
        [negative.result, negative.reason, negative.implication].join(" ")
      );
      const overlap = overlapCount(hypothesisTerms, negativeTerms);
      if (overlap > 0) {
        linkedNegatives.push({ key: negative.negative_key, overlap });
      }
    }
    linkedNegatives.sort((left, right) => right.overlap - left.overlap);
    linkMap.byHypothesis[hypothesis.hypothesis_key] = linkedNegatives.map((item) => item.key);
  }

  for (const negative of negativeResults) {
    const negativeTerms = termSet([negative.result, negative.reason, negative.implication].join(" "));
    const linkedHypotheses = [];
    for (const hypothesis of hypotheses) {
      const hypothesisTerms = termSet(
        [
          hypothesis.name,
          hypothesis.mechanism,
          hypothesis.prediction,
          ...(Array.isArray(hypothesis.failure_conditions) ? hypothesis.failure_conditions : []),
        ].join(" ")
      );
      const overlap = overlapCount(negativeTerms, hypothesisTerms);
      if (overlap > 0) {
        linkedHypotheses.push({ key: hypothesis.hypothesis_key, overlap });
      }
    }
    linkedHypotheses.sort((left, right) => right.overlap - left.overlap);
    linkMap.byNegative[negative.negative_key] = linkedHypotheses.map((item) => item.key);
  }

  return linkMap;
}

function summarizeOpenQuestion(thread, runPayload) {
  const lastAssistant = lastAssistantMessage(thread);
  if (lastAssistant) {
    return lastAssistant;
  }
  if (runPayload?.status && runPayload.status !== "completed") {
    return `Run status is ${runPayload.status}. Investigation is still in progress.`;
  }
  return "No unresolved question captured yet.";
}

function renderThreadSnapshot() {
  const root = qs("threadSnapshot");
  const thread = getActiveThread();
  const snapshot = thread?.snapshot || buildThreadSnapshot(thread, state.latestRun && thread?.run_id === state.runId ? state.latestRun : null);

  root.innerHTML = `
    <div class="snapshot-block">
      <div class="snapshot-title">Current Question</div>
      <div class="snapshot-body">${escapeHtml(snapshot.current_question || "No explicit question captured yet.")}</div>
    </div>
    <div class="snapshot-block">
      <div class="snapshot-title">Collaboration Context</div>
      <div class="snapshot-body">${escapeHtml((snapshot.collaboration_identity || []).join("\n") || "No collaboration identity set.")}</div>
    </div>
    <div class="snapshot-block">
      <div class="snapshot-title">Main Hypotheses</div>
      <div class="snapshot-body">${escapeHtml((snapshot.main_hypotheses || []).join("\n"))}</div>
    </div>
    <div class="snapshot-block">
      <div class="snapshot-title">Key Evidence</div>
      <div class="snapshot-body">${escapeHtml((snapshot.key_evidence || []).join("\n"))}</div>
    </div>
    <div class="snapshot-block negative-snapshot">
      <div class="snapshot-title">Negative Results</div>
      <div class="snapshot-body">${escapeHtml((snapshot.negative_results || []).join("\n"))}</div>
    </div>
    <div class="snapshot-block negative-snapshot">
      <div class="snapshot-title">Challenged Hypotheses</div>
      <div class="snapshot-body">${escapeHtml((snapshot.challenged_hypotheses || []).join("\n") || "No challenged hypotheses recorded yet.")}</div>
    </div>
    <div class="snapshot-block">
      <div class="snapshot-title">Open Question</div>
      <div class="snapshot-body">${escapeHtml(snapshot.open_question || "No unresolved question captured yet.")}</div>
    </div>
    <div class="snapshot-block">
      <div class="snapshot-title">Recent Status</div>
      <div class="snapshot-body">${escapeHtml(snapshot.recent_status || "No run attached to this thread yet.")}${snapshot.recommended_next_stage ? `\nNext stage: ${escapeHtml(snapshot.recommended_next_stage)}` : ""}</div>
    </div>
    <div class="snapshot-block">
      <div class="snapshot-title">State Machine</div>
      <div class="snapshot-body">${escapeHtml(
        [
          snapshot.stage_machine?.current_stage ? `Current: ${snapshot.stage_machine.current_stage}` : "",
          Array.isArray(snapshot.stage_machine?.missing_prerequisites) && snapshot.stage_machine.missing_prerequisites.length
            ? `Missing: ${snapshot.stage_machine.missing_prerequisites.slice(0, 3).join(" | ")}`
            : "",
        ].filter(Boolean).join("\n") || "No stage-machine diagnostics yet."
      )}</div>
    </div>
      <div class="snapshot-block">
        <div class="snapshot-title">Quality And Reproducibility</div>
        <div class="snapshot-body">${escapeHtml(
          [
            snapshot.literature_quality?.dominant_grade
            ? `Evidence quality: ${snapshot.literature_quality.dominant_grade}`
            : "",
          snapshot.manifest_summary?.artifact_count !== undefined
            ? `Artifacts: ${snapshot.manifest_summary.artifact_count}`
            : "",
            snapshot.manifest_summary?.input_file_count !== undefined
              ? `Inputs: ${snapshot.manifest_summary.input_file_count}`
              : "",
          ].filter(Boolean).join("\n") || "No quality or reproducibility summary yet."
        )}</div>
      </div>
      <div class="snapshot-block">
        <div class="snapshot-title">Belief Update</div>
        <div class="snapshot-body">${escapeHtml(
          [
            snapshot.belief_update?.consensus_status
              ? `Consensus status: ${snapshot.belief_update.consensus_status}`
              : "",
            snapshot.belief_update?.current_consensus
              ? `Current consensus: ${snapshot.belief_update.current_consensus}`
              : "",
            snapshot.belief_update?.challenged_hypothesis_count
              ? `Challenged hypotheses: ${snapshot.belief_update.challenged_hypothesis_count}`
              : "",
            snapshot.next_cycle_goals?.length
              ? `Next cycle goals: ${snapshot.next_cycle_goals.join(" | ")}`
              : "",
          ].filter(Boolean).join("\n") || "No belief update summary yet."
        )}</div>
      </div>
      <div class="snapshot-block">
        <div class="snapshot-title">Experiment Summary</div>
        <div class="snapshot-body">${escapeHtml(
          [
            snapshot.experiment_summary?.experiment_run_count !== undefined
              ? `Runs: ${snapshot.experiment_summary.experiment_run_count}`
              : "",
            snapshot.experiment_summary?.quality_control_review_count !== undefined
              ? `Quality reviews: ${snapshot.experiment_summary.quality_control_review_count}`
              : "",
            snapshot.experiment_summary?.interpretation_record_count !== undefined
              ? `Interpretations: ${snapshot.experiment_summary.interpretation_record_count}`
              : "",
            snapshot.experiment_summary?.next_decisions?.length
              ? `Next decisions: ${snapshot.experiment_summary.next_decisions.join(" | ")}`
              : "",
          ].filter(Boolean).join("\n") || "No experiment execution summary yet."
        )}</div>
      </div>
    `;
  }

function updateCurrentRunLabel() {
  qs("currentRunLabel").textContent = state.runId || "No active run";
}

function activateTab(targetId) {
  const button = document.querySelector(`.tab-button[data-target="${targetId}"]`);
  const panel = qs(targetId);
  if (!button || !panel) {
    return;
  }
  const group = button.parentElement;
  group.querySelectorAll(".tab-button").forEach((item) => item.classList.remove("active"));
  button.classList.add("active");
  const card = group.parentElement;
  card.querySelectorAll(":scope > .tab-panel").forEach((item) => item.classList.remove("active"));
  panel.classList.add("active");
}

function summarizeStepOutput(step) {
  const parsed = step?.parsed_output;
  if (!parsed || typeof parsed !== "object") {
    return "No structured output captured for this step yet.";
  }
  if (Array.isArray(parsed.claims) && parsed.claims.length > 0) {
    return `Claims: ${parsed.claims.length}. ${extractClaimText(parsed.claims[0])}`;
  }
  if (Array.isArray(parsed.hypotheses) && parsed.hypotheses.length > 0) {
    const first = parsed.hypotheses[0];
    return `Hypotheses: ${parsed.hypotheses.length}. ${first.name || first.title || "Untitled hypothesis"}`;
  }
  if (Array.isArray(parsed.key_findings) && parsed.key_findings.length > 0) {
    return `Key findings: ${parsed.key_findings[0]}`;
  }
  if (typeof parsed.summary === "string") {
    return parsed.summary;
  }
  return JSON.stringify(parsed).slice(0, 220);
}

function renderWorkflowSummary(runPayload) {
  const root = qs("workflowSummary");
  const status = runPayload?.status || "unknown";
  const steps = Array.isArray(runPayload?.steps) ? runPayload.steps.length : 0;
  const dynamic = runPayload?.dynamic_routing;
  const researchState = runPayload?.research_state || {};
  const runManifest = runPayload?.run_manifest || {};
  const negativeCount = researchState.negative_result_count ?? collectNegativeResults(runPayload).length;
  root.innerHTML = `
    <div class="summary-card">
      <span class="meta-label">Status</span>
      <strong>${escapeHtml(status)}</strong>
    </div>
    <div class="summary-card">
      <span class="meta-label">Steps</span>
      <strong>${escapeHtml(steps)}</strong>
    </div>
    <div class="summary-card">
      <span class="meta-label">Dynamic Routing</span>
      <strong>${dynamic === undefined ? "Unknown" : dynamic ? "Enabled" : "Disabled"}</strong>
    </div>
    <div class="summary-card">
      <span class="meta-label">Negative Results</span>
      <strong>${escapeHtml(String(negativeCount))}</strong>
      <div class="stack-meta">${escapeHtml(researchState.recommended_next_stage ? `next: ${researchState.recommended_next_stage}` : "No stage recommendation yet")}</div>
    </div>
    <div class="summary-card">
      <span class="meta-label">Evidence Quality</span>
      <strong>${escapeHtml(researchState?.literature_quality_summary?.dominant_grade || "unknown")}</strong>
      <div class="stack-meta">${escapeHtml(
        researchState?.conflict_attribution?.directional_conflict_count
          ? `${researchState.conflict_attribution.directional_conflict_count} conflict groups`
          : "No explicit conflict groups yet"
      )}</div>
    </div>
    <div class="summary-card">
      <span class="meta-label">Artifacts</span>
      <strong>${escapeHtml(String(Array.isArray(runManifest?.artifacts) ? runManifest.artifacts.length : 0))}</strong>
      <div class="stack-meta">${escapeHtml(
        Array.isArray(runManifest?.seeds) && runManifest.seeds.length
          ? `seeds: ${runManifest.seeds.join(", ")}`
          : "No explicit seeds recorded"
      )}</div>
    </div>
  `;
}

function renderWorkflowDiagnostics(runPayload) {
  const root = qs("workflowDiagnostics");
  if (!root) {
    return;
  }
  const researchState = runPayload?.research_state || {};
  const stageMachine = researchState.stage_machine || {};
  const quality = researchState.literature_quality_summary || {};
  const conflict = researchState.conflict_attribution || {};
  const runManifest = runPayload?.run_manifest || {};
  const cards = [
    {
      title: "State Machine",
      tone: stageMachine.invalid_transitions?.length || stageMachine.missing_prerequisites?.length ? "warning" : "info",
      body: [
        stageMachine.current_stage ? `Current: ${stageMachine.current_stage}` : "",
        Array.isArray(stageMachine.allowed_next_stages) && stageMachine.allowed_next_stages.length
          ? `Allowed next: ${stageMachine.allowed_next_stages.join(", ")}`
          : "",
        Array.isArray(stageMachine.invalid_transitions) && stageMachine.invalid_transitions.length
          ? `Invalid: ${stageMachine.invalid_transitions.join(", ")}`
          : "",
        Array.isArray(stageMachine.missing_prerequisites) && stageMachine.missing_prerequisites.length
          ? `Missing: ${stageMachine.missing_prerequisites.slice(0, 4).join(" | ")}`
          : "No stage blockers detected.",
      ].filter(Boolean).join("\n"),
    },
    {
      title: "Literature Quality",
      tone: quality.dominant_grade === "low" || quality.dominant_grade === "very_low" ? "warning" : "info",
      body: [
        `Dominant grade: ${quality.dominant_grade || "unknown"}`,
        quality.counts ? `Counts: ${Object.entries(quality.counts).map(([k, v]) => `${k}=${v}`).join(", ")}` : "",
        conflict.conflict_group_count ? `Conflict groups: ${conflict.conflict_group_count}` : "",
        conflict.directional_conflict_count ? `Directional conflicts: ${conflict.directional_conflict_count}` : "",
      ].filter(Boolean).join("\n"),
    },
    {
      title: "Reproducibility",
      tone: "info",
      body: [
        Array.isArray(runManifest.tools_used) && runManifest.tools_used.length
          ? `Tools: ${runManifest.tools_used.join(", ")}`
          : "Tools: none",
        Array.isArray(runManifest.input_files) ? `Input files: ${runManifest.input_files.length}` : "",
        Array.isArray(runManifest.artifacts) ? `Artifacts: ${runManifest.artifacts.length}` : "",
        Array.isArray(runManifest.seeds) && runManifest.seeds.length
          ? `Seeds: ${runManifest.seeds.join(", ")}`
          : "Seeds: none",
      ].filter(Boolean).join("\n"),
    },
    {
      title: "Permissions",
      tone: "info",
      body: [
        "File and data access now follows path-scoped policy.",
        "Sensitive paths, blocked extensions, and out-of-root file access are denied before tool execution.",
      ].join("\n"),
    },
  ];

  root.innerHTML = cards
    .map(
      (card) => `
        <div class="diagnostic-card ${escapeHtml(card.tone)}">
          <div class="diagnostic-title">${escapeHtml(card.title)}</div>
          <div class="diagnostic-body">${escapeHtml(card.body)}</div>
        </div>
      `
    )
    .join("");
}

function renderWorkflowTimeline(runPayload) {
  const root = qs("workflowTimeline");
  root.innerHTML = "";
  const steps = Array.isArray(runPayload?.steps) ? runPayload.steps : [];
  if (steps.length === 0) {
    root.innerHTML = `
      <div class="stack-card">
        <strong>No workflow steps yet.</strong>
        <div class="stack-meta">Run an investigation to populate the timeline.</div>
      </div>
    `;
    return;
  }

  for (const step of steps) {
    const card = document.createElement("div");
    card.className = "stack-card";
    const negativeCount = Array.isArray(step?.parsed_output?.negative_results)
      ? step.parsed_output.negative_results.length
      : 0;
    const stageAssessment = step?.parsed_output?.stage_assessment || {};
    const missing = Array.isArray(stageAssessment.missing_prerequisites)
      ? stageAssessment.missing_prerequisites.slice(0, 3).join(" | ")
      : "";
    card.innerHTML = `
      <strong>${escapeHtml(step.profile_name || "unknown specialist")}</strong>
      <div class="stack-meta">status: ${escapeHtml(step.status || "unknown")}</div>
      ${stageAssessment.current_stage ? `<div class="stack-meta">stage: ${escapeHtml(stageAssessment.current_stage)} -> ${escapeHtml(stageAssessment.next_stage || "unknown")}</div>` : ""}
      <div class="stack-body">${escapeHtml(summarizeStepOutput(step))}</div>
      ${negativeCount ? `<div class="stack-meta">negative results: ${escapeHtml(String(negativeCount))}</div>` : ""}
      ${missing ? `<div class="stack-meta">missing prerequisites: ${escapeHtml(missing)}</div>` : ""}
    `;
    root.appendChild(card);
  }
}

function renderHypotheses(runPayload) {
  const root = qs("hypothesisBoard");
  root.innerHTML = "";
  const links = linkHypothesesAndNegativeResults(runPayload);
  const reverseContext = deriveReverseExperimentContext();
  const hypotheses = links.hypotheses;
  if (hypotheses.length === 0) {
    root.innerHTML = `
      <div class="stack-card">
        <strong>No hypotheses yet.</strong>
        <div class="stack-meta">Run a workflow and open the hypotheses tab.</div>
      </div>
    `;
    return;
  }

  for (const item of hypotheses) {
    const title = item.name || item.title || "Untitled hypothesis";
    const prediction = item.prediction || item.statement || item.summary || "No prediction captured.";
    const status = item.status || "active";
    const linkedNegativeKeys = links.byHypothesis[item.hypothesis_key] || [];
    const isActive = state.selectedHypothesisKey === item.hypothesis_key;
    const isRelated =
      (state.selectedNegativeKey && linkedNegativeKeys.includes(state.selectedNegativeKey)) ||
      reverseContext.relatedHypothesisIds.has(String(item.hypothesis_id || ""));
    const card = document.createElement("div");
    card.className = `stack-card claim-card clickable-card${isActive ? " selected-card" : ""}${isRelated ? " related-card" : ""}`;
    card.innerHTML = `
      <strong>${escapeHtml(title)}</strong>
      <div class="stack-meta">status: ${escapeHtml(status)} · source: ${escapeHtml(item.source_step)}</div>
      <div class="stack-body">${escapeHtml(prediction)}</div>
      ${linkedNegativeKeys.length ? `<div class="stack-meta">linked failed attempts: ${escapeHtml(String(linkedNegativeKeys.length))}</div>` : ""}
    `;
      card.addEventListener("click", () => {
        state.selectedHypothesisKey =
          state.selectedHypothesisKey === item.hypothesis_key ? "" : item.hypothesis_key;
        if (state.selectedHypothesisKey) {
          state.selectedNegativeKey = "";
          state.selectedExperimentId = "";
          state.selectedExperimentRunId = "";
        }
        renderHypotheses(runPayload);
        renderNegativeResults(runPayload);
        renderExperimentPanelsFromCache();
        activateTab("hypothesisPanel");
      });
    root.appendChild(card);
  }
}

function renderEvidence(runPayload) {
  const root = qs("evidenceBoard");
  root.innerHTML = "";
  const evidence = collectEvidence(runPayload);
  if (evidence.length === 0) {
    root.innerHTML = `
      <div class="stack-card">
        <strong>No evidence table yet.</strong>
        <div class="stack-meta">Structured claims and evidence will appear after a workflow completes.</div>
      </div>
    `;
    return;
  }

  for (const item of evidence) {
    const card = document.createElement("div");
    const qualityTone = String(item.quality || "").toLowerCase();
    const biasTone = String(item.bias || "").toLowerCase();
    card.className = `stack-card evidence-card${item.conflictGroup ? " conflict" : ""}`;
    card.innerHTML = `
      <strong>${escapeHtml(item.title)}</strong>
      <div class="stack-meta">source: ${escapeHtml(item.source)}</div>
      <div class="stack-body"><strong>Evidence:</strong> ${escapeHtml(item.evidence)}</div>
      <div class="stack-body"><strong>Uncertainty:</strong> ${escapeHtml(item.uncertainty)}</div>
      ${
        item.conflictGroup
          ? `<div class="stack-body"><strong>Conflict attribution:</strong> ${escapeHtml(item.conflictGroup)}${item.conflictNote ? ` | ${escapeHtml(item.conflictNote)}` : ""}</div>`
          : ""
      }
      ${
        item.quality
          ? `<div class="quality-badge ${escapeHtml(qualityTone)}">quality ${escapeHtml(item.quality)}</div>`
          : ""
      }
      ${
        item.bias
          ? `<div class="quality-badge ${escapeHtml(biasTone === "high" ? "high_bias" : biasTone === "medium" ? "medium_bias" : biasTone || "unclear")}">bias ${escapeHtml(item.bias)}</div>`
          : ""
      }
    `;
    root.appendChild(card);
  }
}

function renderNegativeResults(runPayload) {
  const root = qs("negativeResultsBoard");
  if (!root) {
    return;
  }
  root.innerHTML = "";
  const links = linkHypothesesAndNegativeResults(runPayload);
  const reverseContext = deriveReverseExperimentContext();
  const hypothesisByKey = Object.fromEntries((links.hypotheses || []).map((item) => [item.hypothesis_key, item]));
  const results = links.negativeResults;
  if (results.length === 0) {
    root.innerHTML = `
      <div class="stack-card">
        <strong>No negative results yet.</strong>
        <div class="stack-meta">Failed attempts and non-supporting findings will appear here once the workflow captures them.</div>
      </div>
    `;
    return;
  }

  for (const item of results) {
    const linkedHypothesisKeys = links.byNegative[item.negative_key] || [];
    const isActive = state.selectedNegativeKey === item.negative_key;
    const isRelated =
      (state.selectedHypothesisKey && linkedHypothesisKeys.includes(state.selectedHypothesisKey)) ||
      linkedHypothesisKeys.some((key) => reverseContext.relatedHypothesisIds.has(String(hypothesisByKey[key]?.hypothesis_id || "")));
    const card = document.createElement("div");
    card.className = `stack-card negative-card clickable-card${isActive ? " selected-card" : ""}${isRelated ? " related-card" : ""}`;
    card.innerHTML = `
      <strong>${escapeHtml(item.result)}</strong>
      <div class="stack-meta">source: ${escapeHtml(item.source)}</div>
      <div class="stack-body"><strong>Why it failed:</strong> ${escapeHtml(item.reason)}</div>
      <div class="stack-body"><strong>Implication:</strong> ${escapeHtml(item.implication)}</div>
      ${linkedHypothesisKeys.length ? `<div class="stack-meta">linked hypotheses: ${escapeHtml(String(linkedHypothesisKeys.length))}</div>` : ""}
    `;
      card.addEventListener("click", () => {
        state.selectedNegativeKey =
          state.selectedNegativeKey === item.negative_key ? "" : item.negative_key;
        if (state.selectedNegativeKey) {
          state.selectedHypothesisKey = "";
          state.selectedExperimentId = "";
          state.selectedExperimentRunId = "";
        }
        renderNegativeResults(runPayload);
        renderHypotheses(runPayload);
        renderExperimentPanelsFromCache();
        activateTab("negativeResultsPanel");
      });
    root.appendChild(card);
  }
}

function activateMostRelevantWorkspaceTabForExperiment(recordType, record = {}) {
  if (recordType === "interpretation") {
    activateTab(record?.negative_result ? "negativeResultsPanel" : "hypothesisPanel");
    return;
  }
  if (recordType === "qualityControlReview") {
    activateTab("workflowPanel");
    return;
  }
  if (recordType === "run") {
    activateTab("workflowPanel");
    return;
  }
  if (recordType === "protocol") {
    activateTab("workflowPanel");
    return;
  }
  activateTab("hypothesisPanel");
}

function buildExperimentDetailView(runPayload = state.latestRun || {}) {
  const root = qs("experimentDetail");
  if (!root) {
    return;
  }

  const selectedExperimentId = String(state.selectedExperimentId || "");
  const selectedExperimentRunId = String(state.selectedExperimentRunId || "");
  const selectedRun =
    (state.experimentData.runs || []).find((item) => String(item?.run_id || "") === selectedExperimentRunId) || null;
  const effectiveExperimentId =
    selectedExperimentId || String(selectedRun?.experiment_id || "");
  const specification =
    (state.experimentData.specifications || []).find(
      (item) => String(item?.experiment_id || "") === effectiveExperimentId
    ) || null;
  const protocols = (state.experimentData.protocols || []).filter(
    (item) => String(item?.experiment_id || "") === effectiveExperimentId
  );
  const runs = (state.experimentData.runs || []).filter(
    (item) =>
      String(item?.experiment_id || "") === effectiveExperimentId ||
      (selectedExperimentRunId && String(item?.run_id || "") === selectedExperimentRunId)
  );
  const qualityControlReviews = (state.experimentData.qualityControlReviews || []).filter(
    (item) =>
      String(item?.experiment_id || "") === effectiveExperimentId ||
      (selectedExperimentRunId && String(item?.run_id || "") === selectedExperimentRunId)
  );
  const interpretations = (state.experimentData.interpretations || []).filter(
    (item) =>
      String(item?.experiment_id || "") === effectiveExperimentId ||
      (selectedExperimentRunId && String(item?.run_id || "") === selectedExperimentRunId)
  );

  if (!effectiveExperimentId && !selectedExperimentRunId) {
    root.innerHTML = `
      <div class="experiment-detail-card">
        <strong>No experiment selected.</strong>
        <div class="stack-meta">Choose a specification, protocol, run, quality control review, or interpretation to inspect the full execution chain.</div>
      </div>
    `;
    return;
  }

  const reverseContext = deriveReverseExperimentContext();
  const negativeLinks = linkHypothesesAndNegativeResults(runPayload);
  const hypothesisMap = Object.fromEntries(
    collectHypotheses(runPayload).map((item) => [String(item.hypothesis_id || ""), item])
  );
  const linkedHypotheses = Array.from(reverseContext.relatedHypothesisIds)
    .map((identifier) => hypothesisMap[String(identifier)])
    .filter(Boolean);
  const linkedHypothesisKeys = new Set(linkedHypotheses.map((item) => String(item.hypothesis_key || "")));
  const linkedNegativeResults = (negativeLinks.negativeResults || []).filter((item) => {
    const linkedKeys = Array.isArray(negativeLinks.byNegative?.[item.negative_key])
      ? negativeLinks.byNegative[item.negative_key]
      : [];
    return linkedKeys.some((key) => linkedHypothesisKeys.has(String(key)));
  });
  const protocolStepPreview = protocols
    .flatMap((item) => (Array.isArray(item.steps) ? item.steps.slice(0, 3) : []))
    .filter(Boolean)
    .slice(0, 5);
  const qualityWarnings = qualityControlReviews
    .flatMap((item) => {
      const records = [];
      if (item.quality_control_status && item.quality_control_status !== "passed") {
        records.push(`${item.review_id || "review"}: ${item.quality_control_status}`);
      }
      if (Array.isArray(item.issues)) {
        records.push(...item.issues.slice(0, 2));
      }
      if (item.recommended_action) {
        records.push(`action: ${item.recommended_action}`);
      }
      return records;
    })
    .filter(Boolean)
    .slice(0, 5);

  const nextDecisions = interpretations
    .map((item) => String(item?.next_decision || "").trim())
    .filter(Boolean)
    .slice(0, 4);

  const renderList = (items, fallback) => {
    if (!items.length) {
      return `<div class="stack-meta">${escapeHtml(fallback)}</div>`;
    }
    return `
      <ul class="experiment-detail-list">
        ${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
      </ul>
    `;
  };

  const renderInteractiveList = (items, fallback, type) => {
    if (!items.length) {
      return `<div class="stack-meta">${escapeHtml(fallback)}</div>`;
    }
    return `
      <ul class="experiment-detail-list">
        ${items
          .map(
            (item) => `
              <li>
                <button type="button" class="detail-link" data-detail-type="${escapeHtml(type)}" data-detail-key="${escapeHtml(item.key)}">
                  ${escapeHtml(item.label)}
                </button>
              </li>
            `
          )
          .join("")}
      </ul>
    `;
  };

  root.innerHTML = `
    <div class="experiment-detail-card selected-card">
      <strong>${escapeHtml(specification?.title || effectiveExperimentId || selectedExperimentRunId || "Experiment detail")}</strong>
      <div class="stack-meta">
        experiment: ${escapeHtml(effectiveExperimentId || "not resolved")}
        ${selectedExperimentRunId ? ` | selected run: ${escapeHtml(selectedExperimentRunId)}` : ""}
        ${specification?.discipline ? ` | discipline: ${escapeHtml(specification.discipline)}` : ""}
      </div>
      <div class="stack-body">${escapeHtml(specification?.goal || specification?.research_question || "No experiment goal captured yet.")}</div>
      <div class="experiment-detail-grid">
        <div class="experiment-detail-section">
          <div class="snapshot-title">Linked Hypotheses</div>
          ${renderInteractiveList(
            linkedHypotheses.map((item) => ({
              key: String(item.hypothesis_key || ""),
              label: item.name || item.title || item.prediction || item.hypothesis_id || "Untitled hypothesis",
            })),
            "No linked hypotheses resolved."
            ,
            "hypothesis"
          )}
        </div>
        <div class="experiment-detail-section">
          <div class="snapshot-title">Execution Summary</div>
          ${renderList(
            [
              `${protocols.length} protocol${protocols.length === 1 ? "" : "s"}`,
              `${runs.length} run${runs.length === 1 ? "" : "s"}`,
              `${qualityControlReviews.length} quality control review${qualityControlReviews.length === 1 ? "" : "s"}`,
              `${interpretations.length} interpretation${interpretations.length === 1 ? "" : "s"}`,
            ],
            "No execution records yet."
          )}
        </div>
        <div class="experiment-detail-section">
          <div class="snapshot-title">Protocol Highlights</div>
          ${renderList(
            [
              ...protocols.slice(0, 3).map((item) => `${item.protocol_id || "protocol"}${item.version ? ` (${item.version})` : ""}`),
              ...protocolStepPreview,
            ].slice(0, 5),
            "No protocol recorded yet."
          )}
        </div>
        <div class="experiment-detail-section">
          <div class="snapshot-title">Run And Quality State</div>
          ${renderList(
            [
              ...runs.slice(0, 3).map((item) => `${item.run_id || "run"}: ${item.status || "unknown status"}`),
              ...qualityControlReviews
                .slice(0, 3)
                .map(
                  (item) =>
                    `${item.review_id || "review"}: ${item.quality_control_status || "unknown"}${
                      item.evidence_reliability ? ` | reliability ${item.evidence_reliability}` : ""
                    }`
                ),
            ],
            "No run or quality control record yet."
          )}
        </div>
        <div class="experiment-detail-section">
          <div class="snapshot-title">Interpretation</div>
          ${renderList(
            interpretations
              .slice(0, 3)
              .map(
                (item) =>
                  `${item.interpretation_id || "interpretation"}${
                    item.negative_result ? " | negative result" : ""
                  }${item.next_decision ? ` | ${item.next_decision}` : ""}`
              ),
            "No interpretation recorded yet."
          )}
        </div>
        <div class="experiment-detail-section">
          <div class="snapshot-title">Challenges And Failures</div>
          ${renderInteractiveList(
            linkedNegativeResults.slice(0, 3).map((item) => ({
              key: String(item.negative_key || ""),
              label: `${item.result}${item.reason ? ` | ${item.reason}` : ""}`,
            })),
            "No linked failed attempts or quality warnings."
            ,
            "negative"
          )}
          ${
            qualityWarnings.length
              ? `<div class="stack-body"><strong>Quality warnings:</strong>\n${escapeHtml(qualityWarnings.join("\n"))}</div>`
              : ""
          }
        </div>
        <div class="experiment-detail-section">
          <div class="snapshot-title">Next Decisions</div>
          ${renderList(nextDecisions, "No next decision captured yet.")}
        </div>
      </div>
    </div>
  `;

  qsa("#experimentDetail .detail-link").forEach((node) => {
    node.addEventListener("click", () => {
      const type = node.dataset.detailType || "";
      const key = node.dataset.detailKey || "";
      if (!key) {
        return;
      }
      if (type === "hypothesis") {
        state.selectedHypothesisKey = key;
        state.selectedNegativeKey = "";
        renderHypotheses(runPayload);
        renderNegativeResults(runPayload);
        renderExperimentPanelsFromCache();
        activateTab("hypothesisPanel");
        return;
      }
      if (type === "negative") {
        state.selectedNegativeKey = key;
        state.selectedHypothesisKey = "";
        renderNegativeResults(runPayload);
        renderHypotheses(runPayload);
        renderExperimentPanelsFromCache();
        activateTab("negativeResultsPanel");
      }
    });
  });
}

function renderMemorySearchResults(payload) {
  const root = qs("memorySearchList");
  if (!root) {
    return;
  }
  root.innerHTML = "";
  const results = Array.isArray(payload?.results) ? payload.results : [];
  if (results.length === 0) {
    return;
  }
  for (const item of results) {
    const tags = Array.isArray(item.tags) ? item.tags : [];
    const isNegative = tags.includes("negative-result") || tags.includes("failed-attempt");
    const card = document.createElement("div");
    card.className = `stack-card ${isNegative ? "negative-card" : ""}`.trim();
    card.innerHTML = `
      <strong>${escapeHtml(item.title || item.filename || "Untitled memory")}</strong>
      <div class="stack-meta">${escapeHtml(item.scope || "unknown")} · ${escapeHtml(item.memory_type || item.type || "memory")} · ${escapeHtml(item.status || "active")}</div>
      <div class="stack-body">${escapeHtml(item.summary || item.excerpt || "No summary.")}</div>
    `;
    root.appendChild(card);
  }
}

function renderGraphVisual(payload) {
  const root = qs("graphVisual");
  const claims = Array.isArray(payload?.claims) ? payload.claims : [];
  const evidence = Array.isArray(payload?.evidence) ? payload.evidence : [];
  const negativeLinks = Array.isArray(payload?.negative_result_links) ? payload.negative_result_links : [];

  if (claims.length === 0 && evidence.length === 0) {
    root.innerHTML = `
      <div class="graph-column">
        <div class="graph-column-title">Graph Preview</div>
        <div class="graph-node">
          <div class="graph-node-text">No claim graph available yet. Complete a run and load the graph panel.</div>
        </div>
      </div>
    `;
    return;
  }

  const claimHtml = claims
    .slice(0, 6)
    .map((item, index) => {
      const text = item.statement || item.claim || item.title || JSON.stringify(item).slice(0, 140);
      const id = item.id || `claim-${index + 1}`;
      return `
        <div class="graph-node claim">
          <div class="graph-node-id">${escapeHtml(id)}</div>
          <div class="graph-node-text">${escapeHtml(text)}</div>
        </div>
      `;
    })
    .join("");

  const evidenceHtml = evidence
    .slice(0, 6)
    .map((item, index) => {
      const text =
        item.statement || item.summary || item.title || item.description || JSON.stringify(item).slice(0, 140);
      const id = item.id || `evidence-${index + 1}`;
      return `
        <div class="graph-node evidence">
          <div class="graph-node-id">${escapeHtml(id)}</div>
          <div class="graph-node-text">${escapeHtml(text)}</div>
        </div>
      `;
    })
    .join("");

  root.innerHTML = `
    <div class="graph-column">
      <div class="graph-column-title">Claims</div>
      ${claimHtml || `<div class="graph-node"><div class="graph-node-text">No claims returned.</div></div>`}
    </div>
    <div class="graph-column">
      <div class="graph-column-title">Evidence</div>
      ${evidenceHtml || `<div class="graph-node"><div class="graph-node-text">No evidence returned.</div></div>`}
    </div>
    <div class="graph-column">
      <div class="graph-column-title">Negative Challenge Links</div>
      ${
        negativeLinks.length
          ? negativeLinks
              .slice(0, 8)
              .map(
                (item) => `
                  <div class="graph-node">
                    <div class="graph-node-id">${escapeHtml(item.negative_result_id || "negative")} -> ${escapeHtml(item.hypothesis_id || "hypothesis")}</div>
                    <div class="graph-node-text">${escapeHtml(item.relation || "challenges")}</div>
                  </div>
                `
              )
              .join("")
          : `<div class="graph-node"><div class="graph-node-text">No negative-result challenge links returned.</div></div>`
      }
    </div>
  `;
}

function renderUsageSummary(payload) {
  const root = qs("usageSummaryCards");
  if (!root) {
    return;
  }
  const total = payload?.total || {};
  const byProfile = Array.isArray(payload?.by_profile) ? payload.by_profile : [];
  const runManifest = state.latestRun?.run_manifest || {};
  root.innerHTML = `
    <div class="diagnostic-card info">
      <div class="diagnostic-title">Token Budget</div>
      <div class="diagnostic-body">Total tokens: ${escapeHtml(String(total.total_tokens ?? 0))}
Input: ${escapeHtml(String(total.input_tokens ?? 0))}
Output: ${escapeHtml(String(total.output_tokens ?? 0))}</div>
    </div>
    <div class="diagnostic-card info">
      <div class="diagnostic-title">Estimated Cost</div>
      <div class="diagnostic-body">USD ${escapeHtml(String(total.estimated_cost_usd ?? 0))}
Rounds: ${escapeHtml(String(total.rounds ?? 0))}
Profiles: ${escapeHtml(String(byProfile.length))}</div>
    </div>
    <div class="diagnostic-card info">
      <div class="diagnostic-title">Run Manifest</div>
      <div class="diagnostic-body">Inputs: ${escapeHtml(String(Array.isArray(runManifest.input_files) ? runManifest.input_files.length : 0))}
Artifacts: ${escapeHtml(String(Array.isArray(runManifest.artifacts) ? runManifest.artifacts.length : 0))}
Seeds: ${escapeHtml(Array.isArray(runManifest.seeds) && runManifest.seeds.length ? runManifest.seeds.join(", ") : "none")}</div>
    </div>
    <div class="diagnostic-card info">
      <div class="diagnostic-title">Models Used</div>
      <div class="diagnostic-body">${escapeHtml(
        Array.isArray(runManifest.models_used) && runManifest.models_used.length
          ? runManifest.models_used.slice(0, 4).map((item) => `${item.profile_name}: ${item.model}`).join("\n")
          : "No model manifest loaded yet."
      )}</div>
    </div>
  `;
}

async function announceRunProgress(runPayload) {
  const status = runPayload?.status || "";
  const steps = Array.isArray(runPayload?.steps) ? runPayload.steps : [];

  for (const step of steps) {
    const key = `${state.runId}:${step.profile_name}:${step.status}`;
    if (step.status === "completed" && !state.announcedSteps.has(key)) {
      state.announcedSteps.add(key);
      await pushChat(
        "assistant",
        `${step.profile_name || "A specialist"} finished. ${summarizeStepOutput(step)}`
      );
    }
  }

  if (status && status !== state.lastRunStatus) {
    state.lastRunStatus = status;
    if (status === "running") {
      await pushChat("system", `Run ${state.runId} is now in progress.`);
    }
  }
}

function autoFocusAfterCompletion(runPayload) {
  const negativeResults = collectNegativeResults(runPayload);
  if (negativeResults.length > 0) {
    activateTab("negativeResultsPanel");
    return;
  }
  const hypotheses = collectHypotheses(runPayload);
  const evidence = collectEvidence(runPayload);
  if (hypotheses.length > 0) {
    activateTab("hypothesisPanel");
    return;
  }
  if (evidence.length > 0) {
    activateTab("evidencePanel");
    return;
  }
  activateTab("reportPanel");
}

async function renderWorkflow(runPayload) {
  state.latestRun = runPayload;
  await announceRunProgress(runPayload);
  await syncThreadSnapshot(runPayload);
  renderJson("workflowOutput", runPayload);
  renderWorkflowSummary(runPayload);
  renderWorkflowDiagnostics(runPayload);
  renderWorkflowTimeline(runPayload);
  renderHypotheses(runPayload);
  renderEvidence(runPayload);
  renderNegativeResults(runPayload);
  renderExperimentPanelsFromCache();
  renderThreadSnapshot();
}

async function checkHealth() {
  try {
    const payload = await api("/health");
    qs("healthStatus").textContent = `Connected: ${payload.status}`;
    setAccessStatus("");
  } catch {
    qs("healthStatus").textContent = "Connection failed";
  }
}

async function loadRuns() {
  const payload = await api(`/workflow/runs${identityQueryString()}`);
  const container = qs("runsList");
  container.innerHTML = "";
  if (!Array.isArray(payload) || payload.length === 0) {
    container.textContent = "No runs yet.";
    return;
  }

  for (const run of payload.slice().reverse()) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "run-item";
    item.innerHTML = `
      <strong>${escapeHtml(run.topic)}</strong>
      <div class="run-meta">${escapeHtml(run.run_id)}</div>
      <div class="run-meta">status: ${escapeHtml(run.status)}</div>
    `;
    item.addEventListener("click", async () => {
      const thread = getActiveThread();
      qs("runIdInput").value = run.run_id;
      state.runId = run.run_id;
      resetRunAnnouncements();
      if (thread) {
        const updated = await updateThread(thread.thread_id, { run_id: run.run_id });
        const index = state.threads.findIndex((record) => record.thread_id === thread.thread_id);
        if (index >= 0) {
          state.threads[index] = updated;
        }
      }
      updateCurrentRunLabel();
      await pushChat("system", `Loaded historical run ${run.run_id}.`);
      activateTab("workflowPanel");
      activateTab("runsPanel");
      await loadWorkflow();
      await Promise.allSettled([loadReport(), loadUsage(), loadGraph()]);
    });
    container.appendChild(item);
  }
}

async function startWorkflow(promptText) {
  const topic = (promptText || qs("topic").value).trim();
  if (!topic) {
    qs("runStatus").textContent = "Prompt cannot be empty.";
    return;
  }
  await pushChat("user", topic);
  const payload = {
    topic,
    dynamic_routing: qs("dynamicRouting").checked,
    ...currentIdentity(),
  };
  const result = await api("/workflow/run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  state.runId = result.run_id;
  resetRunAnnouncements();
  const thread = getActiveThread();
  if (thread) {
    const updated = await updateThread(thread.thread_id, {
      run_id: result.run_id,
      title: !thread.title || thread.title === "Untitled Research Thread" ? topic.slice(0, 42) : thread.title,
    });
    const index = state.threads.findIndex((record) => record.thread_id === thread.thread_id);
    if (index >= 0) {
      state.threads[index] = updated;
    }
    renderThreadList();
    renderThreadControls();
  }
  qs("runIdInput").value = state.runId;
  qs("runStatus").textContent = `Workflow submitted: ${state.runId}`;
  updateCurrentRunLabel();
  await pushChat("system", `Workflow submitted with run id ${state.runId}.`);
  activateTab("workflowPanel");
  await loadWorkflow();
  await loadRuns();
  startPolling();
}

function startPolling() {
  if (state.pollHandle) {
    clearInterval(state.pollHandle);
  }
  state.pollHandle = setInterval(async () => {
    if (!state.runId) {
      return;
    }
    try {
      const payload = await api(`/workflow/${state.runId}${identityQueryString()}`);
      await renderWorkflow(payload);
      if (payload.status === "completed" || payload.status === "failed") {
        clearInterval(state.pollHandle);
        state.pollHandle = null;
        await pushChat("assistant", `Run ${state.runId} finished with status ${payload.status}.`);
        await loadRuns();
        await Promise.all([loadReport(), loadUsage(), loadGraph()]);
        autoFocusAfterCompletion(payload);
      }
    } catch (error) {
      clearInterval(state.pollHandle);
      state.pollHandle = null;
      renderJson("workflowOutput", { error: error.message });
    }
  }, 3000);
}

async function loadWorkflow() {
  const runId = qs("runIdInput").value.trim();
  if (!runId) {
    return;
  }
  state.runId = runId;
  const thread = getActiveThread();
  if (thread) {
    const updated = await updateThread(thread.thread_id, { run_id: runId });
    const index = state.threads.findIndex((record) => record.thread_id === thread.thread_id);
    if (index >= 0) {
      state.threads[index] = updated;
    }
  }
  updateCurrentRunLabel();
  const scopedPayload = await api(`/workflow/${runId}${identityQueryString()}`);
  await renderWorkflow(scopedPayload);
}

async function loadGraph() {
  const runId = qs("runIdInput").value.trim();
  if (!runId) {
    return;
  }
  const payload = await api(`/graph/${runId}${identityQueryString()}`);
  renderGraphVisual(payload);
  renderJson("graphOutput", payload);
  activateTab("graphPanel");
}

async function loadUsage() {
  const runId = qs("runIdInput").value.trim();
  if (!runId) {
    return;
  }
  const payload = await api(`/usage/${runId}${identityQueryString()}`);
  renderUsageSummary(payload);
  renderJson("usageOutput", payload);
  activateTab("usagePanel");
}

async function loadReport() {
  const runId = qs("runIdInput").value.trim();
  if (!runId) {
    return;
  }
  const payload = await api(`/reports/${runId}${identityQueryString()}`);
  renderJson("reportOutput", payload);
  activateTab("reportPanel");
}

function parseLineList(value) {
  return String(value || "")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function renderExperimentRecords(targetId, items, formatter) {
  const root = qs(targetId);
  if (!root) {
    return;
  }
  root.innerHTML = "";
  const records = Array.isArray(items) ? items : [];
  if (records.length === 0) {
    root.innerHTML = `
      <div class="stack-card">
        <strong>No records yet.</strong>
        <div class="stack-meta">Create one above or refresh the collection.</div>
      </div>
    `;
    return;
  }
  for (let index = 0; index < records.length; index += 1) {
    const item = records[index];
    const card = document.createElement("div");
    card.className = "stack-card";
    card.dataset.recordIndex = String(index);
    card.innerHTML = formatter(item, index);
    root.appendChild(card);
  }
}

function renderExperimentPanelsFromCache() {
  const experimentContext = deriveRelatedExperimentContext(state.latestRun || {});
  const selectedExperimentId = state.selectedExperimentId || "";
  const selectedExperimentRunId = state.selectedExperimentRunId || "";
  buildExperimentDetailView(state.latestRun || {});

  renderExperimentRecords("experimentSpecificationsList", state.experimentData.specifications, (item) => {
    const related = experimentContext.relatedExperimentIds.has(String(item.experiment_id || ""));
    const selected = selectedExperimentId && String(item.experiment_id || "") === selectedExperimentId;
    return `
      <div class="${selected ? "selected-card" : related ? "related-card" : ""}">
        <strong>${escapeHtml(item.title || item.experiment_id || "Untitled experiment")}</strong>
        <div class="stack-meta">${escapeHtml(item.experiment_id || "")} | ${escapeHtml(item.discipline || "unknown")}${selected ? " | selected experiment" : related ? " | linked to selected hypothesis" : ""}</div>
        <div class="stack-body">${escapeHtml(item.goal || item.research_question || "No goal captured.")}</div>
      </div>
    `;
  });

  renderExperimentRecords("experimentalProtocolsList", state.experimentData.protocols, (item) => {
    const related = experimentContext.relatedExperimentIds.has(String(item.experiment_id || ""));
    const selected = selectedExperimentId && String(item.experiment_id || "") === selectedExperimentId;
    return `
      <div class="${selected ? "selected-card" : related ? "related-card" : ""}">
        <strong>${escapeHtml(item.protocol_id || "Untitled protocol")}</strong>
        <div class="stack-meta">${escapeHtml(item.experiment_id || "")} | version ${escapeHtml(item.version || "")}${selected ? " | selected experiment" : related ? " | linked to selected hypothesis" : ""}</div>
        <div class="stack-body">${escapeHtml((Array.isArray(item.steps) ? item.steps.slice(0, 4).join("\n") : "No steps captured.") || "No steps captured.")}</div>
      </div>
    `;
  });

  renderExperimentRecords("experimentRunsList", state.experimentData.runs, (item) => {
    const related =
      experimentContext.relatedExperimentIds.has(String(item.experiment_id || "")) ||
      experimentContext.relatedRunIds.has(String(item.run_id || ""));
    const selected =
      (selectedExperimentRunId && String(item.run_id || "") === selectedExperimentRunId) ||
      (selectedExperimentId && String(item.experiment_id || "") === selectedExperimentId);
    return `
      <div class="${selected ? "selected-card" : related ? "related-card" : ""}">
        <strong>${escapeHtml(item.run_id || "Untitled run")}</strong>
        <div class="stack-meta">${escapeHtml(item.experiment_id || "")} | ${escapeHtml(item.status || "unknown")}${selected ? " | selected experiment" : related ? " | linked to selected hypothesis" : ""}</div>
        <div class="stack-body">${escapeHtml(`protocol: ${item.protocol_id || "unknown"}${item.operator ? `\noperator: ${item.operator}` : ""}`)}</div>
      </div>
    `;
  });

  renderExperimentRecords("qualityControlReviewsList", state.experimentData.qualityControlReviews, (item) => {
    const related =
      experimentContext.relatedExperimentIds.has(String(item.experiment_id || "")) ||
      experimentContext.relatedRunIds.has(String(item.run_id || ""));
    const selected =
      (selectedExperimentRunId && String(item.run_id || "") === selectedExperimentRunId) ||
      (selectedExperimentId && String(item.experiment_id || "") === selectedExperimentId);
    return `
      <div class="${selected ? "selected-card" : related ? "related-card" : ""}">
        <strong>${escapeHtml(item.review_id || "Untitled review")}</strong>
        <div class="stack-meta">${escapeHtml(item.run_id || "")} | ${escapeHtml(item.quality_control_status || "unknown")}${selected ? " | selected experiment" : related ? " | linked to selected hypothesis" : ""}</div>
        <div class="stack-body">${escapeHtml(item.recommended_action || "No recommended action captured.")}</div>
      </div>
    `;
  });

  renderExperimentRecords("interpretationRecordsList", state.experimentData.interpretations, (item) => {
    const linkedHypothesisIds = [
      ...(Array.isArray(item?.supported_hypothesis_ids) ? item.supported_hypothesis_ids : []),
      ...(Array.isArray(item?.weakened_hypothesis_ids) ? item.weakened_hypothesis_ids : []),
      ...(Array.isArray(item?.inconclusive_hypothesis_ids) ? item.inconclusive_hypothesis_ids : []),
    ].map((value) => String(value));
    const related =
      linkedHypothesisIds.includes(experimentContext.selectedHypothesisId) ||
      experimentContext.relatedExperimentIds.has(String(item.experiment_id || "")) ||
      experimentContext.relatedRunIds.has(String(item.run_id || ""));
    const selected =
      (selectedExperimentRunId && String(item.run_id || "") === selectedExperimentRunId) ||
      (selectedExperimentId && String(item.experiment_id || "") === selectedExperimentId);
    return `
      <div class="${selected ? "selected-card" : related ? "related-card" : ""}">
        <strong>${escapeHtml(item.interpretation_id || "Untitled interpretation")}</strong>
        <div class="stack-meta">${escapeHtml(item.run_id || "")} | negative result: ${escapeHtml(String(Boolean(item.negative_result)))}${selected ? " | selected experiment" : related ? " | linked to selected hypothesis" : ""}</div>
        <div class="stack-body">${escapeHtml(item.next_decision || "No next decision captured.")}</div>
      </div>
    `;
  });

  qsa("#experimentSpecificationsList .stack-card").forEach((card, index) => {
    card.addEventListener("click", () => {
      const item = state.experimentData.specifications[index];
      if (!item?.experiment_id) {
        return;
      }
      state.selectedExperimentId =
        state.selectedExperimentId === String(item.experiment_id) ? "" : String(item.experiment_id);
      state.selectedExperimentRunId = "";
      state.selectedHypothesisKey = "";
      state.selectedNegativeKey = "";
      renderExperimentPanelsFromCache();
      renderHypotheses(state.latestRun || {});
      renderNegativeResults(state.latestRun || {});
      activateMostRelevantWorkspaceTabForExperiment("specification", item);
      activateTab("experimentsPanel");
    });
  });

  qsa("#experimentalProtocolsList .stack-card").forEach((card, index) => {
    card.addEventListener("click", () => {
      const item = state.experimentData.protocols[index];
      const experimentId = String(item?.experiment_id || "");
      if (!experimentId) {
        return;
      }
      state.selectedExperimentId = state.selectedExperimentId === experimentId ? "" : experimentId;
      state.selectedExperimentRunId = "";
      state.selectedHypothesisKey = "";
      state.selectedNegativeKey = "";
      renderExperimentPanelsFromCache();
      renderHypotheses(state.latestRun || {});
      renderNegativeResults(state.latestRun || {});
      activateMostRelevantWorkspaceTabForExperiment("protocol", item);
      activateTab("experimentsPanel");
    });
  });

  qsa("#experimentRunsList .stack-card").forEach((card, index) => {
    card.addEventListener("click", () => {
      const item = state.experimentData.runs[index];
      const runId = String(item?.run_id || "");
      if (!runId) {
        return;
      }
      state.selectedExperimentRunId = state.selectedExperimentRunId === runId ? "" : runId;
      state.selectedExperimentId = "";
      state.selectedHypothesisKey = "";
      state.selectedNegativeKey = "";
      renderExperimentPanelsFromCache();
      renderHypotheses(state.latestRun || {});
      renderNegativeResults(state.latestRun || {});
      activateMostRelevantWorkspaceTabForExperiment("run", item);
      activateTab("experimentsPanel");
    });
  });

  qsa("#qualityControlReviewsList .stack-card").forEach((card, index) => {
    card.addEventListener("click", () => {
      const item = state.experimentData.qualityControlReviews[index];
      const runId = String(item?.run_id || "");
      if (!runId) {
        return;
      }
      state.selectedExperimentRunId = state.selectedExperimentRunId === runId ? "" : runId;
      state.selectedExperimentId = "";
      state.selectedHypothesisKey = "";
      state.selectedNegativeKey = "";
      renderExperimentPanelsFromCache();
      renderHypotheses(state.latestRun || {});
      renderNegativeResults(state.latestRun || {});
      activateMostRelevantWorkspaceTabForExperiment("qualityControlReview", item);
      activateTab("experimentsPanel");
    });
  });

  qsa("#interpretationRecordsList .stack-card").forEach((card, index) => {
    card.addEventListener("click", () => {
      const item = state.experimentData.interpretations[index];
      const runId = String(item?.run_id || "");
      if (!runId) {
        return;
      }
      state.selectedExperimentRunId = state.selectedExperimentRunId === runId ? "" : runId;
      state.selectedExperimentId = "";
      state.selectedHypothesisKey = "";
      state.selectedNegativeKey = "";
      renderExperimentPanelsFromCache();
      renderHypotheses(state.latestRun || {});
      renderNegativeResults(state.latestRun || {});
      activateMostRelevantWorkspaceTabForExperiment("interpretation", item);
      activateTab("experimentsPanel");
    });
  });
}

async function loadExperimentSpecifications() {
  const payload = await api(`/experiments/specifications${identityQueryString()}`);
  state.experimentData.specifications = Array.isArray(payload.results) ? payload.results : [];
  renderExperimentPanelsFromCache();
  activateTab("experimentsPanel");
}

async function saveExperimentSpecification() {
  await api("/experiments/specifications", {
    method: "POST",
    body: JSON.stringify({
      experiment_id: qs("experimentSpecificationId").value.trim(),
      title: qs("experimentSpecificationTitle").value.trim(),
      discipline: qs("experimentSpecificationDiscipline").value,
      hypothesis_ids: [],
      research_question: qs("topic").value.trim(),
      goal: qs("experimentSpecificationGoal").value.trim(),
      decision_type: qs("experimentSpecificationDecisionType").value,
      success_criteria: [],
      failure_criteria: [],
      priority: "medium",
      status: "planned",
      discipline_payload: {},
      ...currentIdentity(),
    }),
  });
  await loadExperimentSpecifications();
}

async function loadExperimentalProtocols() {
  const experimentId = qs("experimentalProtocolExperimentId").value.trim();
  const joiner = identityQueryString() ? "&" : "?";
  const suffix = experimentId ? `${identityQueryString()}${joiner}experiment_id=${encodeURIComponent(experimentId)}` : identityQueryString();
  const payload = await api(`/experiments/protocols${suffix}`);
  state.experimentData.protocols = Array.isArray(payload.results) ? payload.results : [];
  renderExperimentPanelsFromCache();
  activateTab("experimentsPanel");
}

async function saveExperimentalProtocol() {
  await api("/experiments/protocols", {
    method: "POST",
    body: JSON.stringify({
      protocol_id: qs("experimentalProtocolId").value.trim(),
      experiment_id: qs("experimentalProtocolExperimentId").value.trim(),
      version: qs("experimentalProtocolVersion").value.trim() || "v1",
      inputs: [],
      controls: [],
      steps: parseLineList(qs("experimentalProtocolSteps").value),
      measurement_plan: [],
      expected_outputs: [],
      risk_points: [],
      quality_control_checks: [],
      discipline_payload: {},
      ...currentIdentity(),
    }),
  });
  await loadExperimentalProtocols();
}

async function loadExperimentRuns() {
  const experimentId = qs("experimentRunExperimentId").value.trim();
  const joiner = identityQueryString() ? "&" : "?";
  const suffix = experimentId ? `${identityQueryString()}${joiner}experiment_id=${encodeURIComponent(experimentId)}` : identityQueryString();
  const payload = await api(`/experiments/runs${suffix}`);
  state.experimentData.runs = Array.isArray(payload.results) ? payload.results : [];
  renderExperimentPanelsFromCache();
  activateTab("experimentsPanel");
}

async function saveExperimentRun() {
  await api("/experiments/runs", {
    method: "POST",
    body: JSON.stringify({
      run_id: qs("experimentRunId").value.trim(),
      experiment_id: qs("experimentRunExperimentId").value.trim(),
      protocol_id: qs("experimentRunProtocolId").value.trim(),
      status: qs("experimentRunStatus").value,
      operator: qs("experimentRunOperator").value.trim(),
      started_at: "",
      ended_at: "",
      configuration_snapshot: {},
      environment_snapshot: {},
      seed: null,
      discipline_payload: {},
      ...currentIdentity(),
    }),
  });
  await loadExperimentRuns();
}

async function loadQualityControlReviews() {
  const experimentId = qs("qualityControlReviewExperimentId").value.trim();
  const joiner = identityQueryString() ? "&" : "?";
  const suffix = experimentId ? `${identityQueryString()}${joiner}experiment_id=${encodeURIComponent(experimentId)}` : identityQueryString();
  const payload = await api(`/experiments/quality-control-reviews${suffix}`);
  state.experimentData.qualityControlReviews = Array.isArray(payload.results) ? payload.results : [];
  renderExperimentPanelsFromCache();
  activateTab("experimentsPanel");
}

async function saveQualityControlReview() {
  await api("/experiments/quality-control-reviews", {
    method: "POST",
    body: JSON.stringify({
      review_id: qs("qualityControlReviewId").value.trim(),
      run_id: qs("qualityControlReviewRunId").value.trim(),
      experiment_id: qs("qualityControlReviewExperimentId").value.trim(),
      quality_control_status: qs("qualityControlReviewStatus").value,
      issues: [],
      possible_artifacts: [],
      protocol_deviations: [],
      quality_control_checks_run: [],
      missing_quality_control_checks: [],
      affected_outputs: [],
      repeat_required: qs("qualityControlReviewStatus").value === "failed",
      blocking_severity: qs("qualityControlReviewStatus").value === "failed" ? "high" : "low",
      evidence_reliability: qs("qualityControlReviewReliability").value,
      usable_for_interpretation: qs("qualityControlReviewStatus").value !== "failed",
      recommended_action: qs("qualityControlReviewAction").value.trim(),
      discipline_payload: {},
      ...currentIdentity(),
    }),
  });
  await loadQualityControlReviews();
}

async function loadInterpretationRecords() {
  const experimentId = qs("interpretationExperimentId").value.trim();
  const joiner = identityQueryString() ? "&" : "?";
  const suffix = experimentId ? `${identityQueryString()}${joiner}experiment_id=${encodeURIComponent(experimentId)}` : identityQueryString();
  const payload = await api(`/experiments/interpretations${suffix}`);
  state.experimentData.interpretations = Array.isArray(payload.results) ? payload.results : [];
  renderExperimentPanelsFromCache();
  activateTab("experimentsPanel");
}

async function saveInterpretationRecord() {
  await api("/experiments/interpretations", {
    method: "POST",
    body: JSON.stringify({
      interpretation_id: qs("interpretationRecordId").value.trim(),
      run_id: qs("interpretationRunId").value.trim(),
      experiment_id: qs("interpretationExperimentId").value.trim(),
      supported_hypothesis_ids: [],
      weakened_hypothesis_ids: [],
      inconclusive_hypothesis_ids: [],
      negative_result: qs("interpretationNegativeResult").checked,
      claim_updates: [],
      confidence: "medium",
      next_decision: qs("interpretationDecision").value.trim(),
      discipline_payload: {},
      ...currentIdentity(),
    }),
  });
  await loadInterpretationRecords();
}

async function searchMemory() {
  const scope = qs("memoryScopeFilter").value.trim();
  const payload = await api("/memory/search", {
    method: "POST",
    body: JSON.stringify({
      query: qs("memoryQuery").value,
      max_results: 5,
      ...currentIdentity(),
      scopes: scope ? [scope] : [],
    }),
  });
  renderMemorySearchResults(payload);
  renderJson("memorySearchOutput", payload);
  activateTab("memoryPanel");
}

async function loadMemoryProposals() {
  const identity = currentIdentity();
  const params = new URLSearchParams({
    user_id: identity.user_id,
    project_id: identity.project_id,
    group_id: identity.group_id,
    group_role: identity.group_role,
  });
  const payload = await api(`/memory/proposals?${params.toString()}`);
  state.memoryProposals = Array.isArray(payload.results) ? payload.results : [];
  renderProposalList(state.memoryProposals);
  setPanelStatus(
    "memoryProposalStatus",
    state.memoryProposals.length
      ? `${state.memoryProposals.length} proposal${state.memoryProposals.length === 1 ? "" : "s"} loaded.`
      : "No pending promotion proposals."
  );
  activateTab("memoryPanel");
}

async function loadMemoryAudit(filename) {
  const identity = currentIdentity();
  const params = new URLSearchParams({
    filename,
    user_id: identity.user_id,
    group_id: identity.group_id,
    group_role: identity.group_role,
  });
  const payload = await api(`/memory/audit?${params.toString()}`);
  renderAuditTimeline(payload);
  activateTab("memoryPanel");
}

async function saveMemory() {
  const scope = qs("memorySaveScope").value.trim() || "project";
  const visibility = qs("memorySaveVisibility").value.trim() || "private";
  const payload = await api("/memory/save", {
    method: "POST",
    body: JSON.stringify({
      title: qs("memoryTitle").value,
      summary: qs("memorySummary").value,
      memory_type: "fact",
      scope,
      visibility,
      content: qs("memoryContent").value,
      owner_agent: "web-ui",
      ...currentIdentity(),
    }),
  });
  renderJson("memorySaveOutput", payload);
  activateTab("memoryPanel");
}

async function reviewMemory() {
  const payload = await api("/memory/review", {
    method: "POST",
    body: JSON.stringify({
      filename: qs("memoryFilename").value,
      status: qs("memoryReviewStatus").value,
      needs_review: false,
      validated_by: ["web-ui"],
      ...currentIdentity(),
    }),
  });
  renderJson("memoryReviewOutput", payload);
  activateTab("memoryPanel");
}

async function promoteMemory() {
  const payload = await api("/memory/promote", {
    method: "POST",
    body: JSON.stringify({
      filename: qs("memoryPromoteFilename").value,
      target_scope: qs("memoryPromoteScope").value,
      target_visibility: qs("memoryPromoteVisibility").value,
      ...currentIdentity(),
    }),
  });
  renderJson("memoryPromoteOutput", payload);
  await loadMemoryProposals().catch(() => undefined);
  activateTab("memoryPanel");
}

async function approveProposal(item) {
  const identity = currentIdentity();
  const payload = await api("/memory/proposals/approve", {
    method: "POST",
    body: JSON.stringify({
      filename: item.filename,
      target_scope: item.target_scope || qs("memoryPromoteScope").value,
      target_visibility: item.visibility || qs("memoryPromoteVisibility").value,
      ...identity,
    }),
  });
  setPanelStatus("memoryProposalStatus", payload.message || "Proposal approved.");
  await loadMemoryProposals().catch(() => undefined);
  await loadMemoryAudit(item.filename).catch(() => undefined);
}

async function rejectProposal(item) {
  const identity = currentIdentity();
  const payload = await api("/memory/proposals/reject", {
    method: "POST",
    body: JSON.stringify({
      filename: item.filename,
      ...identity,
    }),
  });
  setPanelStatus("memoryProposalStatus", payload.message || "Proposal rejected.");
  await loadMemoryProposals().catch(() => undefined);
  await loadMemoryAudit(item.filename).catch(() => undefined);
}

async function approveSelectedProposals() {
  const items = selectedProposalItems();
  if (items.length === 0) {
    setPanelStatus("memoryProposalStatus", "Select at least one proposal to approve.");
    return;
  }
  for (const item of items) {
    await approveProposal(item);
  }
  state.selectedProposalFilenames = [];
  await loadMemoryProposals().catch(() => undefined);
}

async function rejectSelectedProposals() {
  const items = selectedProposalItems();
  if (items.length === 0) {
    setPanelStatus("memoryProposalStatus", "Select at least one proposal to reject.");
    return;
  }
  for (const item of items) {
    await rejectProposal(item);
  }
  state.selectedProposalFilenames = [];
  await loadMemoryProposals().catch(() => undefined);
}

async function saveGroupRole() {
  const identity = currentIdentity();
  const payload = await api("/collaboration/group-role", {
    method: "POST",
    body: JSON.stringify({
      group_id: identity.group_id,
      user_id: identity.user_id,
      role: identity.group_role || "contributor",
    }),
  });
  renderJson("memoryReviewOutput", {
    message: `Saved role ${payload.role} for ${payload.user_id} in ${payload.group_id}.`,
    payload,
  });
  await loadMemoryProposals().catch(() => undefined);
}

async function loadGroupMembers() {
  const groupId = qs("groupIdInput").value.trim();
  if (!groupId) {
    setPanelStatus("membershipStatus", "Set Group ID first.");
    return;
  }
  const payload = await api(`/collaboration/groups/${encodeURIComponent(groupId)}/members`);
  renderMembershipList(payload);
  activateTab("memoryPanel");
}

async function addGroupMember() {
  const groupId = qs("groupIdInput").value.trim();
  if (!groupId) {
    setPanelStatus("membershipStatus", "Set Group ID first.");
    return;
  }
  await api(`/collaboration/groups/${encodeURIComponent(groupId)}/members`, {
    method: "POST",
    body: JSON.stringify({
      user_id: qs("memberUserId").value.trim(),
      display_name: qs("memberDisplayName").value.trim(),
      role: qs("memberRole").value,
    }),
  });
  setPanelStatus("membershipStatus", "Group member saved.");
  await loadGroupMembers().catch(() => undefined);
}

async function loadProjectMembers() {
  const projectId = qs("projectIdInput").value.trim();
  if (!projectId) {
    setPanelStatus("membershipStatus", "Set Project ID first.");
    return;
  }
  const payload = await api(`/collaboration/projects/${encodeURIComponent(projectId)}/members`);
  renderMembershipList(payload);
  activateTab("memoryPanel");
}

async function addProjectMember() {
  const projectId = qs("projectIdInput").value.trim();
  if (!projectId) {
    setPanelStatus("membershipStatus", "Set Project ID first.");
    return;
  }
  await api(`/collaboration/projects/${encodeURIComponent(projectId)}/members`, {
    method: "POST",
    body: JSON.stringify({
      user_id: qs("memberUserId").value.trim(),
      display_name: qs("memberDisplayName").value.trim(),
      role: qs("memberRole").value,
    }),
  });
  setPanelStatus("membershipStatus", "Project member saved.");
  await loadProjectMembers().catch(() => undefined);
}

function wireTabs() {
  qsa(".tab-button").forEach((button) => {
    button.addEventListener("click", () => activateTab(button.dataset.target));
  });
}

window.addEventListener("DOMContentLoaded", async () => {
  setBaseUrl(state.baseUrl);
  renderGraphVisual({});
  wireTabs();

  try {
    await ensureThreadsLoaded();
    setAccessStatus("");
    renderThreadList();
    renderThreadControls();
    renderChat();
    renderThreadSnapshot();
    updateCurrentRunLabel();
    if (state.runId) {
      qs("runIdInput").value = state.runId;
    }
  } catch (error) {
    const friendly = describeAccessError(error);
    if (friendly) {
      setAccessStatus(friendly, "error");
      qs("runStatus").textContent = friendly;
    } else {
      qs("runStatus").textContent = `Failed to load threads: ${error.message}`;
    }
  }

  qs("saveBaseUrl").addEventListener("click", async () => {
    setBaseUrl(qs("baseUrl").value);
    await checkHealth();
    await refreshThreads().catch(() => undefined);
  });

  qs("saveThreadTitle").addEventListener("click", async () => {
    const thread = getActiveThread();
    if (!thread) {
      return;
    }
    const title = qs("threadTitleInput").value.trim();
    if (!title) {
      return;
    }
    const updated = await updateThread(thread.thread_id, { title }).catch((error) => {
      handleUiError(error, "workflowOutput", "Failed to rename thread.");
      throw error;
    });
    const index = state.threads.findIndex((record) => record.thread_id === thread.thread_id);
    if (index >= 0) {
      state.threads[index] = updated;
    }
    await syncThreadSnapshot(state.latestRun);
    renderThreadList();
    renderThreadSnapshot();
  });

  qs("archiveThread").addEventListener("click", async () => {
    const thread = getActiveThread();
    if (!thread) {
      return;
    }
    const updated = await updateThread(thread.thread_id, { archived: !thread.archived }).catch((error) => {
      handleUiError(error, "workflowOutput", "Failed to archive thread.");
      throw error;
    });
    const index = state.threads.findIndex((record) => record.thread_id === thread.thread_id);
    if (index >= 0) {
      state.threads[index] = updated;
    }
    renderThreadList();
    renderThreadSnapshot();
  });

  qs("deleteThread").addEventListener("click", async () => {
    const thread = getActiveThread();
    if (!thread) {
      return;
    }
    await api(`/threads/${thread.thread_id}${identityQueryString()}`, { method: "DELETE" }).catch((error) => {
      handleUiError(error, "workflowOutput", "Failed to delete thread.");
      throw error;
    });
    await refreshThreads();
    if (!getActiveThread() && state.threads.length > 0) {
      setActiveThreadId(state.threads[0].thread_id);
      syncStateFromActiveThread();
    }
    renderThreadList();
    renderThreadControls();
    renderChat();
    renderThreadSnapshot();
    updateCurrentRunLabel();
    if (state.runId) {
      qs("runIdInput").value = state.runId;
    } else {
      qs("runIdInput").value = "";
      renderEmptyWorkspace();
    }
  });

  qs("threadSearch").addEventListener("input", (event) => {
    state.threadSearch = event.target.value;
    renderThreadList();
  });

  qs("showArchivedThreads").addEventListener("change", (event) => {
    state.showArchivedThreads = event.target.checked;
    renderThreadList();
  });

  ["userIdInput", "projectIdInput", "groupIdInput", "groupRoleInput"].forEach((id) => {
    qs(id).addEventListener("change", () => {
      setAccessStatus("");
      syncThreadIdentity()
        .then(() => {
          renderThreadList();
          renderThreadSnapshot();
        })
        .catch(() => undefined);
    });
  });

  qs("newThread").addEventListener("click", async () => {
    const prompt = qs("topic").value.trim();
  const thread = await createThread(prompt ? prompt.slice(0, 42) : "New Research Thread");
    setActiveThreadId(thread.thread_id);
    syncStateFromActiveThread();
    renderThreadList();
    renderThreadControls();
    renderChat();
    renderThreadSnapshot();
    updateCurrentRunLabel();
    qs("runIdInput").value = "";
    renderEmptyWorkspace();
    await pushChat("system", "Started a new research thread. Use the prompt box to continue this investigation.");
  });

  qs("runWorkflow").addEventListener("click", () =>
    startWorkflow().catch((error) => {
      const friendly = describeAccessError(error);
      if (friendly) {
        setAccessStatus(friendly, "error");
        qs("runStatus").textContent = friendly;
      } else {
        qs("runStatus").textContent = `Workflow failed to start: ${error.message}`;
      }
    })
  );

  qsa("[data-quick-prompt]").forEach((button) => {
    button.addEventListener("click", () => {
      const prompt = button.dataset.quickPrompt || "";
      qs("topic").value = prompt;
      startWorkflow(prompt).catch((error) => {
        const friendly = describeAccessError(error);
        if (friendly) {
          setAccessStatus(friendly, "error");
          qs("runStatus").textContent = friendly;
        } else {
          qs("runStatus").textContent = `Workflow failed to start: ${error.message}`;
        }
      });
    });
  });

  qs("refreshRuns").addEventListener("click", () =>
    loadRuns().catch((error) => {
      handleUiError(error, "usageOutput", "Failed to load runs.");
      qs("runsList").textContent = describeAccessError(error) || `Failed to load runs: ${error.message}`;
    })
  );
  qs("loadRun").addEventListener("click", () =>
    loadWorkflow().catch((error) => handleUiError(error, "workflowOutput", "Failed to load workflow."))
  );
  qs("loadGraph").addEventListener("click", () =>
    loadGraph().catch((error) => handleUiError(error, "graphOutput", "Failed to load graph."))
  );
  qs("loadUsage").addEventListener("click", () =>
    loadUsage().catch((error) => handleUiError(error, "usageOutput", "Failed to load usage."))
  );
  qs("loadReport").addEventListener("click", () =>
    loadReport().catch((error) => handleUiError(error, "reportOutput", "Failed to load report."))
  );
  qs("loadExperimentSpecifications").addEventListener("click", () =>
    loadExperimentSpecifications().catch((error) => handleUiError(error, "", "Failed to load experiment specifications."))
  );
  qs("saveExperimentSpecification").addEventListener("click", () =>
    saveExperimentSpecification().catch((error) => handleUiError(error, "", "Failed to save experiment specification."))
  );
  qs("loadExperimentalProtocols").addEventListener("click", () =>
    loadExperimentalProtocols().catch((error) => handleUiError(error, "", "Failed to load experimental protocols."))
  );
  qs("saveExperimentalProtocol").addEventListener("click", () =>
    saveExperimentalProtocol().catch((error) => handleUiError(error, "", "Failed to save experimental protocol."))
  );
  qs("loadExperimentRuns").addEventListener("click", () =>
    loadExperimentRuns().catch((error) => handleUiError(error, "", "Failed to load experiment runs."))
  );
  qs("saveExperimentRun").addEventListener("click", () =>
    saveExperimentRun().catch((error) => handleUiError(error, "", "Failed to save experiment run."))
  );
  qs("loadQualityControlReviews").addEventListener("click", () =>
    loadQualityControlReviews().catch((error) => handleUiError(error, "", "Failed to load quality control reviews."))
  );
  qs("saveQualityControlReview").addEventListener("click", () =>
    saveQualityControlReview().catch((error) => handleUiError(error, "", "Failed to save quality control review."))
  );
  qs("loadInterpretationRecords").addEventListener("click", () =>
    loadInterpretationRecords().catch((error) => handleUiError(error, "", "Failed to load interpretation records."))
  );
  qs("saveInterpretationRecord").addEventListener("click", () =>
    saveInterpretationRecord().catch((error) => handleUiError(error, "", "Failed to save interpretation record."))
  );
  qs("searchMemory").addEventListener("click", () =>
    searchMemory().catch((error) => renderJson("memorySearchOutput", { error: error.message }))
  );
  qs("loadMemoryProposals").addEventListener("click", () =>
    loadMemoryProposals().catch((error) => setPanelStatus("memoryProposalStatus", describeAccessError(error) || error.message))
  );
  qs("approveSelectedProposals").addEventListener("click", () =>
    approveSelectedProposals().catch((error) => setPanelStatus("memoryProposalStatus", describeAccessError(error) || error.message))
  );
  qs("rejectSelectedProposals").addEventListener("click", () =>
    rejectSelectedProposals().catch((error) => setPanelStatus("memoryProposalStatus", describeAccessError(error) || error.message))
  );
  qs("saveMemory").addEventListener("click", () =>
    saveMemory().catch((error) => renderJson("memorySaveOutput", { error: error.message }))
  );
  qs("reviewMemory").addEventListener("click", () =>
    reviewMemory().catch((error) => renderJson("memoryReviewOutput", { error: error.message }))
  );
  qs("promoteMemory").addEventListener("click", () =>
    promoteMemory().catch((error) => renderJson("memoryPromoteOutput", { error: error.message }))
  );
  qs("saveGroupRole").addEventListener("click", () =>
    saveGroupRole().catch((error) => renderJson("memoryReviewOutput", { error: error.message }))
  );
  qs("loadGroupMembers").addEventListener("click", () =>
    loadGroupMembers().catch((error) => setPanelStatus("membershipStatus", describeAccessError(error) || error.message))
  );
  qs("addGroupMember").addEventListener("click", () =>
    addGroupMember().catch((error) => setPanelStatus("membershipStatus", describeAccessError(error) || error.message))
  );
  qs("loadProjectMembers").addEventListener("click", () =>
    loadProjectMembers().catch((error) => setPanelStatus("membershipStatus", describeAccessError(error) || error.message))
  );
  qs("addProjectMember").addEventListener("click", () =>
    addProjectMember().catch((error) => setPanelStatus("membershipStatus", describeAccessError(error) || error.message))
  );
  ["memberSearch", "memberRoleFilter", "memberSort"].forEach((id) => {
    qs(id).addEventListener("input", () => {
      if (state.membershipPayload) {
        renderMembershipList(state.membershipPayload);
      }
    });
    qs(id).addEventListener("change", () => {
      if (state.membershipPayload) {
        renderMembershipList(state.membershipPayload);
      }
    });
  });
  qs("proposalTargetFilter").addEventListener("change", () => {
    renderProposalList(state.memoryProposals);
  });

  checkHealth().catch(() => undefined);
  loadRuns().catch(() => undefined);
  loadMemoryProposals().catch(() => undefined);
  loadExperimentSpecifications().catch(() => undefined);
  renderAuditTimeline({ events: [] });
});
