// Admin Dashboard v8 — Em Linh MKT
// Refer F2C.8 admin_queue + KE_HOACH § action 21

// ---------- API helpers ----------
async function apiGet(path) {
  const res = await fetch(`/api/admin${path}`);
  if (!res.ok) {
    if (res.status === 401) {
      throw new Error("Sai username/password — reload trang để đăng nhập lại");
    }
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function apiPost(path, body = null) {
  const opts = { method: "POST" };
  if (body !== null) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(`/api/admin${path}`, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function apiDelete(path) {
  const res = await fetch(`/api/admin${path}`, { method: "DELETE" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}


// ---------- Status bar ----------
const statusBar = document.getElementById("status-bar");
function showStatus(msg, isError = false) {
  statusBar.textContent = msg;
  statusBar.classList.add("show");
  statusBar.classList.toggle("error", isError);
  setTimeout(() => statusBar.classList.remove("show"), 4000);
}


// ---------- Tab switching ----------
const tabs = document.querySelectorAll(".nav-btn");
const tabContents = {
  dashboard: document.getElementById("tab-dashboard"),
  sessions: document.getElementById("tab-sessions"),
  confirmed: document.getElementById("tab-confirmed"),
  queue: document.getElementById("tab-queue"),
};

// Conversation tone display labels (refer 1B § 2).
// This is NOT the business dealer type stored on profile.dealer_type.
const DEALER_TYPE_LABELS = {
  lua_lo: "🔥 Lửa Lò",
  khoe: "🏆 Khoe",
  lo: "😟 Lo",
  ban: "⚡ Bận",
  unknown: "❓ Unknown",
};

function dealerTypeLabel(code) {
  return DEALER_TYPE_LABELS[code] || code || "—";
}

tabs.forEach((btn) => {
  btn.addEventListener("click", () => {
    tabs.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    Object.values(tabContents).forEach((t) => t.classList.remove("active"));
    const tabName = btn.dataset.tab;
    tabContents[tabName].classList.add("active");
    // Auto-reload data
    if (tabName === "dashboard") loadStats();
    if (tabName === "sessions") loadSessions();
    if (tabName === "confirmed") loadConfirmed();
    if (tabName === "queue") loadQueue();
  });
});


// ---------- Format helpers ----------
function formatDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("vi-VN", {
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit",
    });
  } catch (_) {
    return iso;
  }
}

function shortId(id) {
  if (!id) return "—";
  return id.slice(0, 8) + "…";
}

function escapeHtml(s) {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderBadge(value, type = "stage") {
  if (!value) return "—";
  return `<span class="badge ${type}-${escapeHtml(value)}">${escapeHtml(value)}</span>`;
}

function renderFlags(flags) {
  if (!flags || flags.length === 0) return "—";
  return flags.map((f) => `<span class="badge flag">${escapeHtml(f)}</span>`).join("");
}


// ---------- Dashboard ----------
async function loadStats() {
  try {
    const stats = await apiGet("/stats");
    document.getElementById("stat-total").textContent = stats.total_sessions;
    document.getElementById("stat-confirmed").textContent =
      stats.by_confirmation.CONFIRMED || 0;
    document.getElementById("stat-queue").textContent = stats.queue_pending;
    document.getElementById("stat-queue-high").textContent = stats.queue_high;

    renderStatsTable("stats-by-stage", stats.by_stage);
    renderStatsTable("stats-by-dealer-type", stats.by_dealer_type);
    renderStatsTable("stats-by-confirmation", stats.by_confirmation);
  } catch (err) {
    showStatus(`Lỗi load stats: ${err.message}`, true);
  }
}

function renderStatsTable(tbodyId, data) {
  const tbody = document.getElementById(tbodyId);
  if (!data || Object.keys(data).length === 0) {
    tbody.innerHTML = `<tr><td colspan="2" style="text-align:center;color:#a0aec0">(chưa có data)</td></tr>`;
    return;
  }
  tbody.innerHTML = Object.entries(data)
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `<tr><td>${escapeHtml(k)}</td><td>${v}</td></tr>`)
    .join("");
}


// ---------- Sessions ----------
async function loadSessions() {
  const stage = document.getElementById("filter-stage").value;
  const confirmation = document.getElementById("filter-confirmation").value;
  const dealerType = document.getElementById("filter-dealer-type").value;

  const params = new URLSearchParams();
  if (stage) params.set("stage", stage);
  if (confirmation) params.set("confirmation_status", confirmation);
  if (dealerType) params.set("dealer_type", dealerType);
  // Phase 6 R+ Fix: load tới max 500 (backend cap), thay vì default 50
  params.set("limit", "500");

  try {
    const sessions = await apiGet(`/sessions?${params.toString()}`);
    renderSessionsTable(sessions);
    showStatus(`Loaded ${sessions.length} session (max 500)`);
  } catch (err) {
    showStatus(`Lỗi: ${err.message}`, true);
  }
}

function renderSessionsTable(sessions) {
  const tbody = document.getElementById("sessions-tbody");
  if (!sessions || sessions.length === 0) {
    tbody.innerHTML = `<tr><td colspan="12" style="text-align:center;color:#a0aec0;padding:24px">(không có session)</td></tr>`;
    return;
  }
  tbody.innerHTML = sessions
    .map(
      (s) => `
    <tr>
      <td class="mono" title="${escapeHtml(s.session_id)}">${shortId(s.session_id)}</td>
      <td>${escapeHtml(s.owner_name || "—")}</td>
      <td>${escapeHtml(s.dealer_name || "—")}</td>
      <td class="mono">${escapeHtml(s.phone_or_zalo || "—")}</td>
      <td>${renderBadge(s.stage, "stage")}</td>
      <td class="mono">${escapeHtml(s.current_slot || "—")}</td>
      <td>${s.turn_count}</td>
      <td>${renderBadge(s.confirmation_status, "status")}</td>
      <td class="mono">${dealerTypeLabel(s.detected_dealer_type)}</td>
      <td>${renderFlags(s.flags)}</td>
      <td class="mono">${formatDate(s.updated_at)}</td>
      <td>
        <button class="btn-sm btn-view" onclick="viewSession('${s.session_id}')">Xem</button>
        <button class="btn-sm btn-delete" onclick="deleteSession('${s.session_id}')">Xóa</button>
      </td>
    </tr>
  `,
    )
    .join("");
}

async function viewSession(sessionId) {
  try {
    const detail = await apiGet(`/sessions/${sessionId}`);
    renderSessionModal(detail);
  } catch (err) {
    showStatus(`Lỗi: ${err.message}`, true);
  }
}

function renderSessionModal(detail) {
  const profileEntries = Object.entries(detail.profile || {})
    .filter(([k, v]) => v !== null && v !== "" && (!Array.isArray(v) || v.length > 0))
    .map(([k, v]) => `
      <div class="kv-key">${escapeHtml(k)}</div>
      <div class="kv-value">${escapeHtml(JSON.stringify(v))}</div>
    `)
    .join("");

  const historyHtml = (detail.history || [])
    .map(
      (m) => `
    <div class="history-msg ${m.role}">
      <span class="role">${m.role === "dealer" ? "👤 Dealer" : "🤖 Bot"}:</span>${escapeHtml(m.content)}
    </div>
  `,
    )
    .join("");

  const body = document.getElementById("modal-body");
  body.innerHTML = `
    <h3>Session ${shortId(detail.session_id)}</h3>
    <div class="mono" style="color:#718096;margin-bottom:12px">${escapeHtml(detail.session_id)}</div>
    <div style="margin-bottom:16px">
      <button class="btn-sm btn-md" onclick="exportSessionMd('${detail.session_id}')">📄 Export Markdown (.md)</button>
    </div>

    <div class="kv-grid">
      <div class="kv-key">Stage</div><div class="kv-value">${renderBadge(detail.stage, "stage")}</div>
      <div class="kv-key">Current slot</div><div class="kv-value mono">${escapeHtml(detail.current_slot || "—")}</div>
      <div class="kv-key">Turn count</div><div class="kv-value">${detail.turn_count}</div>
      <div class="kv-key">Confirmation</div><div class="kv-value">${renderBadge(detail.confirmation_status, "status")}</div>
      <div class="kv-key">Review status</div><div class="kv-value">${escapeHtml(detail.review_status)}</div>
      <div class="kv-key">Dealer type / Business type</div><div class="kv-value">${escapeHtml((detail.profile && detail.profile.dealer_type) || "—")}</div>
      <div class="kv-key">Conversation tone</div><div class="kv-value">${escapeHtml(detail.detected_dealer_type || "—")}</div>
      <div class="kv-key">Form of address</div><div class="kv-value">${escapeHtml(detail.address_form)}</div>
      <div class="kv-key">Flags</div><div class="kv-value">${renderFlags(detail.flags)}</div>
      <div class="kv-key">Skipped slots</div><div class="kv-value mono">${(detail.skipped_slots || []).join(", ") || "—"}</div>
      <div class="kv-key">Channel</div><div class="kv-value">${escapeHtml(detail.channel)}</div>
      <div class="kv-key">IP</div><div class="kv-value mono">${escapeHtml(detail.ip_address || "—")}</div>
      <div class="kv-key">Created</div><div class="kv-value mono">${formatDate(detail.created_at)}</div>
      <div class="kv-key">Updated</div><div class="kv-value mono">${formatDate(detail.updated_at)}</div>
      <div class="kv-key">Closed</div><div class="kv-value mono">${formatDate(detail.closed_at)}</div>
    </div>

    <h3>Profile (${Object.keys(detail.profile || {}).filter((k) => detail.profile[k]).length} field có data)</h3>
    <div class="kv-grid">${profileEntries || '<div class="kv-value" style="grid-column:span 2;color:#a0aec0">(profile rỗng)</div>'}</div>

    <h3>History (${(detail.history || []).length} message)</h3>
    <div class="history">${historyHtml || '<div style="color:#a0aec0;padding:8px">(chưa có history)</div>'}</div>
  `;
  showModal();
}

function exportSessionMd(sessionId) {
  // Open download — browser handles HTTP Basic prompt nếu cần
  const url = `/api/admin/sessions/${sessionId}/export`;
  window.location.href = url;
}


async function bulkExportConfirmed() {
  // Lấy session_id tick trong tab confirmed
  const checkboxes = document.querySelectorAll(
    "#confirmed-tbody input[type=checkbox]:checked"
  );
  const ids = Array.from(checkboxes).map((cb) => cb.value);
  if (ids.length === 0) {
    // Nếu không tick thì export tất cả confirmed
    if (!confirm("Chưa chọn session nào — export TẤT CẢ CONFIRMED?")) return;
    const allRows = document.querySelectorAll("#confirmed-tbody tr[data-session-id]");
    if (allRows.length === 0) {
      showStatus("Chưa có session CONFIRMED để export", true);
      return;
    }
    allRows.forEach((r) => ids.push(r.dataset.sessionId));
  }
  try {
    const res = await fetch("/api/admin/sessions/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_ids: ids, include_history: true }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const blob = await res.blob();
    // Trigger download
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `em_linh_export_${Date.now()}.zip`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showStatus(`Đã export ${ids.length} session ra ZIP`);
  } catch (err) {
    showStatus(`Lỗi export: ${err.message}`, true);
  }
}


async function loadConfirmed() {
  try {
    const sessions = await apiGet("/sessions?confirmation_status=CONFIRMED&limit=500");
    renderConfirmedTable(sessions);
    document.getElementById("confirmed-count").textContent =
      `${sessions.length} hồ sơ`;
    showStatus(`Loaded ${sessions.length} CONFIRMED`);
  } catch (err) {
    showStatus(`Lỗi: ${err.message}`, true);
  }
}


function renderConfirmedTable(sessions) {
  const tbody = document.getElementById("confirmed-tbody");
  if (!sessions || sessions.length === 0) {
    tbody.innerHTML = `<tr><td colspan="11" style="text-align:center;color:#a0aec0;padding:24px">(chưa có hồ sơ CONFIRMED)</td></tr>`;
    return;
  }
  tbody.innerHTML = sessions
    .map(
      (s) => `
    <tr data-session-id="${escapeHtml(s.session_id)}">
      <td><input type="checkbox" value="${escapeHtml(s.session_id)}" /></td>
      <td class="mono" title="${escapeHtml(s.session_id)}">${shortId(s.session_id)}</td>
      <td>${escapeHtml(s.owner_name || "—")}</td>
      <td>${escapeHtml(s.dealer_name || "—")}</td>
      <td class="mono">${escapeHtml(s.phone_or_zalo || "—")}</td>
      <td title="${escapeHtml(s.address || "")}">${escapeHtml((s.address || "—").slice(0, 30))}</td>
      <td>—</td>
      <td>${dealerTypeLabel(s.detected_dealer_type)}</td>
      <td>${renderFlags(s.flags)}</td>
      <td class="mono">${formatDate(s.closed_at || s.updated_at)}</td>
      <td>
        <button class="btn-sm btn-view" onclick="viewSession('${s.session_id}')">Xem</button>
        <button class="btn-sm btn-md" onclick="exportSessionMd('${s.session_id}')">📄 .md</button>
      </td>
    </tr>
  `,
    )
    .join("");
}


async function deleteSession(sessionId) {
  if (!confirm(`Xóa session ${shortId(sessionId)}?\nProfile + queue entries cascade.`)) {
    return;
  }
  try {
    await apiDelete(`/sessions/${sessionId}`);
    showStatus(`Đã xóa session ${shortId(sessionId)}`);
    loadSessions();
  } catch (err) {
    showStatus(`Lỗi xóa: ${err.message}`, true);
  }
}


// ---------- Queue ----------
async function loadQueue() {
  const status = document.getElementById("filter-queue-status").value;
  const priority = document.getElementById("filter-queue-priority").value;
  const params = new URLSearchParams();
  params.set("status", status);
  if (priority) params.set("priority", priority);
  params.set("limit", "500");

  try {
    const queue = await apiGet(`/queue?${params.toString()}`);
    renderQueueTable(queue);
    showStatus(`Loaded ${queue.length} queue entry`);
  } catch (err) {
    showStatus(`Lỗi: ${err.message}`, true);
  }
}

function renderQueueTable(items) {
  const tbody = document.getElementById("queue-tbody");
  if (!items || items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:#a0aec0;padding:24px">(queue rỗng)</td></tr>`;
    return;
  }
  tbody.innerHTML = items
    .map(
      (q) => `
    <tr>
      <td class="mono" title="${escapeHtml(q.queue_id)}">${shortId(q.queue_id)}</td>
      <td class="mono" title="${escapeHtml(q.session_id)}">
        <a href="#" onclick="viewSession('${q.session_id}');return false;">${shortId(q.session_id)}</a>
      </td>
      <td><span class="badge flag">${escapeHtml(q.trigger)}</span></td>
      <td>${renderBadge(q.priority, "priority")}</td>
      <td>${renderBadge(q.status, "status")}</td>
      <td>${escapeHtml(q.assigned_to || "—")}</td>
      <td class="mono">${formatDate(q.created_at)}</td>
      <td>
        ${q.status === "PENDING" ? `<button class="btn-sm btn-claim" onclick="claimQueue('${q.queue_id}')">Claim</button>` : ""}
        ${q.status !== "APPROVED" && q.status !== "REJECTED" ? `
          <button class="btn-sm btn-approve" onclick="approveQueue('${q.queue_id}')">✓ Duyệt</button>
          <button class="btn-sm btn-reject" onclick="rejectQueue('${q.queue_id}')">✗ Từ chối</button>
        ` : ""}
      </td>
    </tr>
  `,
    )
    .join("");
}

async function claimQueue(queueId) {
  try {
    await apiPost(`/queue/${queueId}/claim`);
    showStatus(`Đã claim queue ${shortId(queueId)}`);
    loadQueue();
  } catch (err) {
    showStatus(`Lỗi: ${err.message}`, true);
  }
}

async function approveQueue(queueId) {
  const notes = prompt("Notes (optional):", "");
  try {
    const path = notes ? `/queue/${queueId}/approve?notes=${encodeURIComponent(notes)}` : `/queue/${queueId}/approve`;
    await apiPost(path);
    showStatus(`Đã duyệt ${shortId(queueId)}`);
    loadQueue();
  } catch (err) {
    showStatus(`Lỗi: ${err.message}`, true);
  }
}

async function rejectQueue(queueId) {
  const notes = prompt("Lý do từ chối (optional):", "");
  try {
    const path = notes ? `/queue/${queueId}/reject?notes=${encodeURIComponent(notes)}` : `/queue/${queueId}/reject`;
    await apiPost(path);
    showStatus(`Đã từ chối ${shortId(queueId)}`);
    loadQueue();
  } catch (err) {
    showStatus(`Lỗi: ${err.message}`, true);
  }
}


// ---------- Modal ----------
const modal = document.getElementById("modal");
const modalClose = document.getElementById("modal-close");
function showModal() {
  modal.classList.remove("hidden");
}
function hideModal() {
  modal.classList.add("hidden");
}
modalClose.addEventListener("click", hideModal);
modal.addEventListener("click", (e) => {
  if (e.target === modal) hideModal();
});


// ---------- Bind filters ----------
document.getElementById("btn-filter").addEventListener("click", loadSessions);
document.getElementById("btn-refresh").addEventListener("click", loadSessions);
document.getElementById("btn-queue-filter").addEventListener("click", loadQueue);
document.getElementById("btn-queue-refresh").addEventListener("click", loadQueue);
document.getElementById("btn-confirmed-refresh").addEventListener("click", loadConfirmed);
document.getElementById("btn-confirmed-bulk-export").addEventListener("click", bulkExportConfirmed);
document.getElementById("confirmed-check-all").addEventListener("change", (e) => {
  document.querySelectorAll("#confirmed-tbody input[type=checkbox]").forEach((cb) => {
    cb.checked = e.target.checked;
  });
});


// ---------- Init ----------
loadStats();
