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
};

// (10.7) Đã bỏ nhãn tone Lửa Lò/Khoe — phân loại tone không còn dùng ở reply
// (reply dùng tone chung), nhãn cũ là dead code + lấy nhầm dữ liệu.

function navigateTo(path) {
  window.history.pushState({}, "", path);
  handleRoute();
}

function switchTab(tabName) {
  tabs.forEach((b) => b.classList.remove("active"));
  const btn = document.querySelector(`.nav-btn[data-tab="${tabName}"]`);
  if (btn) btn.classList.add("active");
  
  Object.values(tabContents).forEach((t) => t.classList.remove("active"));
  if (tabContents[tabName]) {
    tabContents[tabName].classList.add("active");
  }
  
  if (tabName === "dashboard") loadStats();
  if (tabName === "sessions") loadSessions();
  if (tabName === "confirmed") loadConfirmed();
}

function handleRoute() {
  const path = window.location.pathname;
  if (path === "/admin" || path === "/admin/" || path === "/admin/dashboard") {
    switchTab("dashboard");
    hideModalDirect();
  } else if (path === "/admin/sessions" || path === "/admin/sessions/") {
    switchTab("sessions");
    hideModalDirect();
  } else if (path.startsWith("/admin/sessions/")) {
    const sessionId = path.split("/").pop();
    switchTab("sessions");
    if (sessionId) {
      viewSessionDirect(sessionId);
    }
  } else if (path === "/admin/confirmed" || path === "/admin/confirmed/") {
    switchTab("confirmed");
    hideModalDirect();
  } else {
    switchTab("dashboard");
    hideModalDirect();
  }
}

tabs.forEach((btn) => {
  btn.addEventListener("click", () => {
    const tabName = btn.dataset.tab;
    navigateTo(`/admin/${tabName}`);
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
    document.getElementById("stat-active").textContent = stats.by_status.ACTIVE || 0;
    document.getElementById("stat-closed").textContent = stats.by_status.CLOSED || 0;
    document.getElementById("stat-rejected").textContent = stats.by_status.REJECTED || 0;

    renderStatsTable("stats-by-stage", stats.by_stage);
    renderStatsTable("stats-by-status", stats.by_status);
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
  const status = document.getElementById("filter-status").value;
  const confirmation = document.getElementById("filter-confirmation").value;

  const params = new URLSearchParams();
  if (stage) params.set("stage", stage);
  if (status) params.set("status", status);
  if (confirmation) params.set("confirmation_status", confirmation);
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

async function updateSessionStatus(sessionId, status) {
  try {
    await apiPost(`/sessions/${sessionId}/status`, { status });
    showStatus(`Đã cập nhật trạng thái session ${shortId(sessionId)} thành ${status}`);
    loadSessions();
    loadStats();
  } catch (err) {
    showStatus(`Lỗi cập nhật trạng thái: ${err.message}`, true);
  }
}

function renderSessionsTable(sessions) {
  const tbody = document.getElementById("sessions-tbody");
  if (!sessions || sessions.length === 0) {
    tbody.innerHTML = `<tr><td colspan="10" style="text-align:center;color:#a0aec0;padding:24px">(không có session)</td></tr>`;
    return;
  }
  tbody.innerHTML = sessions
    .map(
      (s) => {
        let actionButtons = "";
        if (s.status === "ACTIVE") {
          actionButtons = `
            <button class="btn-sm btn-approve" onclick="updateSessionStatus('${s.session_id}', 'CLOSED')">Chốt</button>
            <button class="btn-sm btn-reject" onclick="updateSessionStatus('${s.session_id}', 'REJECTED')">Không chốt</button>
          `;
        } else {
          actionButtons = `
            <button class="btn-sm btn-view" style="background:#4a5568" onclick="updateSessionStatus('${s.session_id}', 'ACTIVE')">Mở lại</button>
          `;
        }
        return `
          <tr>
            <td class="mono" title="${escapeHtml(s.session_id)}">${shortId(s.session_id)}</td>
            <td>${escapeHtml(s.owner_name || "—")}</td>
            <td>${escapeHtml(s.dealer_name || "—")}</td>
            <td class="mono">${escapeHtml(s.phone_or_zalo || "—")}</td>
            <td>${renderBadge(s.stage, "stage")}</td>
            <td>${s.turn_count}</td>
            <td>${renderBadge(s.confirmation_status, "status")}</td>
            <td>${renderBadge(s.status, "status")}</td>
            <td class="mono">${formatDate(s.updated_at)}</td>
            <td>
              <button class="btn-sm btn-view" onclick="viewSession('${s.session_id}')">Xem</button>
              ${actionButtons}
              <button class="btn-sm btn-delete" onclick="deleteSession('${s.session_id}')">Xóa</button>
            </td>
          </tr>
        `;
      }
    )
    .join("");
}

async function viewSession(sessionId) {
  navigateTo(`/admin/sessions/${sessionId}`);
}

async function viewSessionDirect(sessionId) {
  try {
    const detail = await apiGet(`/sessions/${sessionId}`);
    renderSessionModal(detail);
  } catch (err) {
    showStatus(`Lỗi: ${err.message}`, true);
  }
}

function renderSessionModal(detail) {
  const p = detail.profile || {};
  
  // 1. Thông tin cơ bản — LUÔN hiện đủ (rỗng → "(chưa có)") để admin biết còn THIẾU gì.
  // Đã bỏ field RÁC: phone_secondary, zalo (số phụ), district (Quận/Huyện), category_stack,
  // customer_segment_signal — bot không thu, đã xoá khỏi schema.
  const basicFields = [
    { label: "Chủ cửa hàng (Owner)", value: p.owner_name },
    { label: "Tên cửa hàng (Dealer)", value: p.dealer_name },
    { label: "Số điện thoại / Zalo", value: p.phone_or_zalo },
    { label: "Địa chỉ", value: p.address },
    { label: "Tỉnh / Xã chuẩn hóa", value: p.province && p.ward ? `${p.ward}, ${p.province}` : (p.province || p.ward) },
    { label: "Mô hình kinh doanh", value: p.business_model_signal || p.dealer_type },
    { label: "Sản phẩm chính", value: p.main_product },
    { label: "Kênh liên hệ chính", value: p.primary_contact_channel }
  ];
  
  // 2. 9 Criteria Fields (C1-C9) — `keys` = field(s) để tra status (SKIPPED = khách không cung cấp)
  const criteriaFields = [
    { label: "C1. Tỉ lệ khách cũ", value: p.customer_old_percentage, keys: ["customer_old_percentage"] },
    { label: "C2. Quy trình cọc/thanh toán + tự chủ vốn", value: p.payment_terms_signal, keys: ["payment_terms_signal"] },
    { label: "C3. Quy mô & độ ổn định đội thợ", value: p.est_team_size ? `${p.est_team_size} người ${p.team_stability_signal ? ' — ' + p.team_stability_signal : ''}` : p.team_stability_signal, keys: ["est_team_size", "team_stability_signal"] },
    { label: "C4. Trách nhiệm xử lý bảo hành", value: p.warranty_responsibility_signal, keys: ["warranty_responsibility_signal"] },
    { label: "C5. Động lực & nút thắt", value: [p.customer_pain, p.motivation_signal ? `(Động lực: ${p.motivation_signal})` : null].filter(Boolean).join(" "), keys: ["motivation_signal", "customer_pain"] },
    { label: "C6. Độ phủ địa bàn (organic vs ads)", value: p.local_dominance_signal, keys: ["local_dominance_signal"] },
    { label: "C7. Cách lưu thông tin khách", value: p.customer_storage_method, keys: ["customer_storage_method"] },
    { label: "C8. Hãng nhập & đàm phán cung ứng", value: [p.supplier_brands ? (Array.isArray(p.supplier_brands) ? p.supplier_brands.join(", ") : p.supplier_brands) : null, p.supplier_negotiation_signal ? `(Đàm phán: ${p.supplier_negotiation_signal})` : null].filter(Boolean).join(" — "), keys: ["supplier_brands", "supplier_negotiation_signal"] },
    { label: "C9. Mạng lưới & sức ảnh hưởng", value: [p.facebook ? `Facebook: ${p.facebook} ${p.fb_marketing_status ? '(' + p.fb_marketing_status + ')' : ''}` : null, p.community_network_signal ? `Mạng lưới: ${p.community_network_signal}` : null].filter(Boolean).join(" — "), keys: ["community_network_signal", "facebook"] }
  ];
  
  // 3. Logo/Brandkit — LUÔN hiện đủ (rỗng → "(chưa có)").
  const _logoIntentVi = { unclarified: "Chưa rõ", upgrade: "Nâng cấp logo cũ", redesign: "Thiết kế lại", new: "Làm mới hoàn toàn" };
  const brandkitFields = [
    { label: "Đồng ý nhận bộ thương hiệu", value: p.brandkit_consent === "yes" ? "Có ✓" : (p.brandkit_consent === "no" ? "Không ✗" : null) },
    { label: "Nhu cầu logo hiện có", value: p.logo_existing_intent ? (_logoIntentVi[p.logo_existing_intent] || p.logo_existing_intent) : null },
    { label: "Màu chủ đạo & Phong thủy", value: p.color_accent ? `${p.color_accent} ${p.feng_shui_signal ? '(' + p.feng_shui_signal + ')' : ''}` : p.feng_shui_signal },
    { label: "Gu logo / phong cách", value: p.logo_style },
    { label: "Slogan", value: p.slogan_preference }
    // Đã bỏ: logo_initials / brand_name_short / initials_full / slogan_options
    // (tàn dư luồng tự-gen-logo cũ — _conv_derive không chạy ở runtime gemini → luôn rỗng).
  ];

  // showEmpty=true: LUÔN hiện đủ field (rỗng → "(chưa có)") — dùng cho trường cơ bản
  // để admin biết là THIẾU, không phải bị ẩn (10.2).
  const isEmptyVal = (v) => v === null || v === undefined || v === "" || (Array.isArray(v) && v.length === 0);
  const renderFormFields = (fields, showEmpty = false) => {
    const rows = showEmpty ? fields : fields.filter(f => !isEmptyVal(f.value));
    if (rows.length === 0) return "";  // nhóm phụ rỗng → không chèn gì (ghép sau lõi)
    return rows.map(f => {
      const valHtml = isEmptyVal(f.value)
        ? '<span style="color:#a0aec0">(chưa có)</span>'
        : (f.label.includes("Slogan gợi ý") ? f.value : escapeHtml(f.value));
      return `
      <div class="kv-key">${escapeHtml(f.label)}</div>
      <div class="kv-value">${valHtml}</div>
    `;
    }).join("");
  };

  // 9 tiêu chí: LUÔN hiện đủ 9 dòng — rỗng thì nói rõ khách không cung cấp (SKIPPED)
  // hay hệ thống chưa thu, để admin biết là thiếu data thật hay khách từ chối.
  const fs = detail.field_status || {};
  const fr = detail.field_raw || {};
  const rawOf = (keys) => { for (const k of (keys || [])) { if (fr[k]) return String(fr[k]); } return null; };
  const renderCriteriaFields = (fields) => fields.map(f => {
    const hasVal = f.value !== null && f.value !== undefined && f.value !== ""
      && (!Array.isArray(f.value) || f.value.length > 0);
    const raw = rawOf(f.keys);
    let display;
    if (hasVal) {
      display = escapeHtml(f.value);
      // câu gốc của khách nếu khác giá trị đã chuẩn hoá
      if (raw && raw.trim() && raw.trim() !== String(f.value).trim()) {
        display += ` <span style="color:#a0aec0">(gốc: "${escapeHtml(raw)}")</span>`;
      }
    } else if ((f.keys || []).some(k => fs[k] === "SKIPPED")) {
      display = '<span style="color:#dd6b20">— khách không cung cấp</span>';
      if (raw && raw.trim()) {
        display += ` <span style="color:#a0aec0">(khách nói: "${escapeHtml(raw)}")</span>`;
      }
    } else {
      display = '<span style="color:#a0aec0">— chưa thu (hệ thống chưa hỏi tới)</span>';
    }
    return `<div class="kv-key">${escapeHtml(f.label)}</div><div class="kv-value">${display}</div>`;
  }).join("");

  const basicHtml = renderFormFields(basicFields, true);
  const criteriaHtml = renderCriteriaFields(criteriaFields);
  const brandkitHtml = renderFormFields(brandkitFields, true);

  const historyHtml = (detail.history || [])
    .map(
      (m) => `
    <div class="history-msg ${m.role}">
      <span class="role">${m.role === "dealer" ? "👤 Dealer" : "🤖 Bot"}:</span>${escapeHtml(m.content)}
    </div>
  `,
    )
    .join("");

  const turnsHtml = (detail.turns || [])
    .map(
      (t, index) => `
    <div class="turn-trace-card" style="border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px; margin-bottom: 12px; background: #f7fafc; text-align: left;">
      <div style="display:flex; justify-content:space-between; align-items:center; border-bottom: 1px solid #edf2f7; padding-bottom: 6px; margin-bottom: 8px;">
        <span style="font-weight:bold; color:#2d3748;">Turn ${index + 1} (${escapeHtml(t.turn_id)})</span>
        <span style="font-size:11px; color:#a0aec0;">${formatDate(t.created_at)}</span>
      </div>
      <div class="kv-grid" style="font-size:13px; row-gap:4px;">
        <div class="kv-key" style="color:#718096;">Objective</div>
        <div class="kv-value">
          <span class="badge stage-${escapeHtml(t.suggested_objective?.type || 'unknown')}">${escapeHtml(t.suggested_objective?.type || '—')}</span>
          ${t.suggested_objective?.target_field ? `<code style="background:#edf2f7; padding:2px 4px; border-radius:4px; font-family:monospace;">${escapeHtml(t.suggested_objective.target_field)}</code>` : ''}
        </div>
        <div class="kv-key" style="color:#718096;">Observations</div>
        <div class="kv-value">
          ${Object.entries(t.observations || {})
            .filter(([_, v]) => v)
            .map(([k, v]) => `<span style="font-size:11px; background:#e2e8f0; color:#4a5568; padding:1px 6px; border-radius:12px; margin-right:4px; display:inline-block;">${escapeHtml(k)}: ${escapeHtml(JSON.stringify(v))}</span>`)
            .join("") || "—"}
        </div>
        <div class="kv-key" style="color:#718096;">Guidelines</div>
        <div class="kv-value">
          ${(t.matched_guideline_ids || []).map(g => `<span class="badge flag" style="background:#ebf8ff; color:#2b6cb0; border:1px solid #bee3f8; margin-right:4px;">${escapeHtml(g)}</span>`).join("") || "—"}
        </div>
        <div class="kv-key" style="color:#718096;">Backend Latency</div>
        <div class="kv-value mono">${t.backend_latency_ms || 0}ms</div>
        <div class="kv-key" style="color:#718096;">Total Latency</div>
        <div class="kv-value mono">${t.turn_aggregation_latency_ms || 0}ms</div>
        <div class="kv-key" style="color:#718096;">Model ID</div>
        <div class="kv-value mono">${escapeHtml(t.model_id || 'stub')}</div>
      </div>
      <div style="margin-top: 8px;">
        <details>
          <summary style="cursor:pointer; font-size:12px; color:#4299e1; user-select:none;">Xem chi tiết full JSON trace</summary>
          <pre style="font-size:11px; background:#1a202c; color:#a0aec0; padding:10px; border-radius:4px; margin-top:6px; overflow-x:auto; font-family:monospace; white-space:pre-wrap;">${escapeHtml(JSON.stringify(t.trace, null, 2))}</pre>
        </details>
      </div>
    </div>
  `
    )
    .join("");

  const body = document.getElementById("modal-body");
  body.innerHTML = `
    <h3>Session ${shortId(detail.session_id)}</h3>
    <div class="mono" style="color:#718096;margin-bottom:12px">${escapeHtml(detail.session_id)}</div>
    <div style="margin-bottom:16px">
      <button class="btn-sm btn-md" onclick="exportSessionMd('${detail.session_id}')">📄 Export Markdown (.md)</button>
    </div>

    <div class="kv-grid" style="margin-bottom:24px">
      <div class="kv-key">Trạng thái</div><div class="kv-value">${renderBadge(detail.status, "status")}</div>
      <div class="kv-key">Stage</div><div class="kv-value">${renderBadge(detail.stage, "stage")}</div>
      <div class="kv-key">Turn count</div><div class="kv-value">${detail.turn_count}</div>
      <div class="kv-key">Review status (Dealer)</div><div class="kv-value">${escapeHtml(detail.review_status)}</div>
      <div class="kv-key">Form of address</div><div class="kv-value">${escapeHtml(detail.address_form)}</div>
      <div class="kv-key">Channel</div><div class="kv-value">${escapeHtml(detail.channel)}</div>
      <div class="kv-key">IP</div><div class="kv-value mono">${escapeHtml(detail.ip_address || "—")}</div>
      <div class="kv-key">Created</div><div class="kv-value mono">${formatDate(detail.created_at)}</div>
      <div class="kv-key">Updated</div><div class="kv-value mono">${formatDate(detail.updated_at)}</div>
      <div class="kv-key">Closed</div><div class="kv-value mono">${formatDate(detail.closed_at)}</div>
    </div>

    <h3>🏪 1. Thông tin cơ bản</h3>
    <div class="kv-grid" style="margin-bottom:24px">${basicHtml}</div>

    <h3>🛠 2. 9 Tiêu chí đánh giá</h3>
    <div class="kv-grid" style="margin-bottom:24px">${criteriaHtml}</div>

    <h3>🎁 3. Thông tin bổ sung làm Logo & Thương hiệu</h3>
    <div class="kv-grid" style="margin-bottom:24px">${brandkitHtml}</div>

    <h3>History (${(detail.history || []).length} message)</h3>
    <div class="history">${historyHtml || '<div style="color:#a0aec0;padding:8px">(chưa có history)</div>'}</div>

    <h3>Conversation Turns & Traces (${(detail.turns || []).length} turns)</h3>
    <div class="turns" style="max-height: 400px; overflow-y: auto; padding-right: 4px; display: flex; flex-direction: column;">
      ${turnsHtml || '<div style="color:#a0aec0;padding:8px">(chưa có turn trace)</div>'}
    </div>
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
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;color:#a0aec0;padding:24px">(chưa có hồ sơ CONFIRMED)</td></tr>`;
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


// ---------- Modal ----------
const modal = document.getElementById("modal");
const modalClose = document.getElementById("modal-close");
function showModal() {
  modal.classList.remove("hidden");
}
function hideModalDirect() {
  modal.classList.add("hidden");
}
function hideModal() {
  modal.classList.add("hidden");
  const path = window.location.pathname;
  if (path.startsWith("/admin/sessions/")) {
    navigateTo("/admin/sessions");
  }
}
modalClose.addEventListener("click", hideModal);
modal.addEventListener("click", (e) => {
  if (e.target === modal) hideModal();
});


// ---------- Bind filters ----------
document.getElementById("btn-filter").addEventListener("click", loadSessions);
document.getElementById("btn-refresh").addEventListener("click", loadSessions);
document.getElementById("btn-confirmed-refresh").addEventListener("click", loadConfirmed);
document.getElementById("btn-confirmed-bulk-export").addEventListener("click", bulkExportConfirmed);
document.getElementById("confirmed-check-all").addEventListener("change", (e) => {
  document.querySelectorAll("#confirmed-tbody input[type=checkbox]").forEach((cb) => {
    cb.checked = e.target.checked;
  });
});


// ---------- Init ----------
window.addEventListener("popstate", handleRoute);
handleRoute();
