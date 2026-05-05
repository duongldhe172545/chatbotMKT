// Admin viewer — read-only.
// Labels fetch từ /api/labels lúc init — single source of truth ở app/labels.py.
let CATEGORY_LABEL = {};
let PRIORITY_LABEL = {};
let FLAG_LABEL = {};

async function loadLabels() {
  try {
    const res = await fetch("/api/labels");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    CATEGORY_LABEL = data.category || {};
    PRIORITY_LABEL = data.priority || {};
    FLAG_LABEL = data.flag || {};
  } catch (err) {
    console.error("Không tải được labels:", err);
  }
}

// Track selected sids for bulk export
const selectedSids = new Set();

function updateExportSelectedBtn() {
  const btn = $("#exportSelectedBtn");
  const n = selectedSids.size;
  btn.disabled = n === 0;
  btn.textContent = `⬇️ Xuất đã chọn (${n})`;
}

function syncSelectAllCheckbox() {
  const all = document.querySelectorAll(".profile-check");
  const checked = document.querySelectorAll(".profile-check:checked");
  const master = $("#selectAllProfiles");
  if (!master) return;
  if (checked.length === 0) {
    master.checked = false;
    master.indeterminate = false;
  } else if (checked.length === all.length) {
    master.checked = true;
    master.indeterminate = false;
  } else {
    master.indeterminate = true;
  }
}

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ---------- Tabs ----------
$$(".tab").forEach((tab) => {
  tab.addEventListener("click", (e) => {
    e.preventDefault();
    $$(".tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    const id = tab.dataset.tab;
    $$(".panel").forEach((p) => p.classList.add("hidden"));
    $(`#panel-${id}`).classList.remove("hidden");
  });
});

// ---------- Helpers ----------
function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString("vi-VN", { hour12: false });
}

function escape(s) {
  if (s === null || s === undefined) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function cell(value, fallback = "—") {
  if (value === null || value === undefined || value === "") {
    return `<td class="muted-cell">${fallback}</td>`;
  }
  return `<td>${escape(value)}</td>`;
}

function tag(text, cls = "") {
  return `<span class="tag ${cls}">${escape(text)}</span>`;
}

function renderFlags(flags) {
  if (!flags || flags.length === 0) {
    return '<span class="muted-cell">—</span>';
  }
  return flags
    .map((f) => {
      const meta = FLAG_LABEL[f] || { text: f, cls: "flag-info" };
      return `<span class="tag ${meta.cls}" title="${escape(f)}">${escape(meta.text)}</span>`;
    })
    .join(" ");
}

// ---------- Profiles ----------
async function loadProfiles() {
  const meta = $("#profilesMeta");
  const tbody = $("#profilesTable tbody");
  meta.textContent = "đang tải...";
  tbody.innerHTML = "";

  try {
    const res = await fetch("/api/admin/profiles");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    meta.textContent = `${data.count} profile(s)`;

    if (data.count === 0) {
      tbody.innerHTML = '<tr><td colspan="13" class="empty">Chưa có profile nào CONFIRMED.</td></tr>';
      selectedSids.clear();
      updateExportSelectedBtn();
      return;
    }

    tbody.innerHTML = data.items
      .map((p) => {
        const region = [p.district, p.province].filter(Boolean).join(", ");
        const cat = CATEGORY_LABEL[p.main_category] || p.main_category || "—";
        const prio = (p.dl0_priority || [])
          .map((x) => PRIORITY_LABEL[x] || x)
          .join(", ");
        const pains = (p.pain_points || []).join("; ");
        const cClass =
          p.confirmation_status === "CONFIRMED"
            ? "confirmed"
            : p.confirmation_status === "EDITED"
            ? "pending"
            : "raw";
        const flagsHtml = renderFlags(p.flags || []);
        const sid = escape(p.session_id || "");
        const checked = selectedSids.has(p.session_id) ? "checked" : "";
        return `
          <tr>
            <td class="col-check"><input type="checkbox" class="profile-check" data-sid="${sid}" ${checked}/></td>
            ${cell(p.dealer_name)}
            ${cell(p.owner_name)}
            ${cell(p.phone_or_zalo)}
            ${cell(region)}
            ${cell(cat)}
            ${cell(p.customer_base_estimate)}
            ${cell(pains)}
            ${cell(prio)}
            <td>${flagsHtml}</td>
            <td>${tag(p.confirmation_status, cClass)}</td>
            <td>${tag(p.review_status, "raw")}</td>
            <td>${escape(fmtDate(p.created_at))}</td>
          </tr>
        `;
      })
      .join("");

    // Cleanup selected ids that no longer exist
    const validSids = new Set(data.items.map((p) => p.session_id));
    for (const sid of [...selectedSids]) {
      if (!validSids.has(sid)) selectedSids.delete(sid);
    }

    // Bind checkbox handlers
    tbody.querySelectorAll(".profile-check").forEach((cb) => {
      cb.addEventListener("click", (e) => e.stopPropagation()); // tránh trigger row click
      cb.addEventListener("change", () => {
        const sid = cb.dataset.sid;
        if (cb.checked) selectedSids.add(sid);
        else selectedSids.delete(sid);
        updateExportSelectedBtn();
        syncSelectAllCheckbox();
      });
    });

    updateExportSelectedBtn();
    syncSelectAllCheckbox();
  } catch (err) {
    meta.innerHTML = `<span class="error">Lỗi: ${escape(err.message)}</span>`;
  }
}

// ---------- Sessions ----------
async function loadSessions() {
  const meta = $("#sessionsMeta");
  const tbody = $("#sessionsTable tbody");
  meta.textContent = "đang tải...";
  tbody.innerHTML = "";

  try {
    const res = await fetch("/api/admin/sessions?limit=100");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    meta.textContent = `${data.count} session(s)`;

    if (data.count === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty">Chưa có session nào.</td></tr>';
      return;
    }

    tbody.innerHTML = data.items
      .map((s) => {
        const stageClass =
          s.stage === "DONE"
            ? "confirmed"
            : s.stage === "CONFIRMING"
            ? "pending"
            : "raw";
        return `
          <tr class="clickable" data-sid="${escape(s.session_id)}">
            <td><code style="font-size:11px">${escape(s.session_id.slice(0, 8))}…</code></td>
            ${cell(s.dealer_name)}
            ${cell(s.phone_or_zalo)}
            <td>${tag(s.stage, stageClass)}</td>
            <td>${s.message_count}</td>
            <td>${escape(fmtDate(s.updated_at))}</td>
            <td><button class="btn-secondary">Xem</button></td>
          </tr>
        `;
      })
      .join("");

    tbody.querySelectorAll("tr.clickable").forEach((tr) => {
      tr.addEventListener("click", () => openSessionDetail(tr.dataset.sid));
    });
  } catch (err) {
    meta.innerHTML = `<span class="error">Lỗi: ${escape(err.message)}</span>`;
  }
}

// ---------- Modal ----------
async function openSessionDetail(sid) {
  $("#modalTitle").textContent = `Session ${sid.slice(0, 8)}…`;
  $("#modalProfile").textContent = "loading...";
  $("#modalConfidence").textContent = "";
  $("#modalMessages").innerHTML = "";
  $("#modalExportBtn").href = `/api/admin/session/${encodeURIComponent(sid)}/export.md`;
  $("#modal").classList.remove("hidden");

  try {
    const res = await fetch(`/api/admin/session/${sid}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    $("#modalProfile").textContent = JSON.stringify(data.profile_raw, null, 2);
    $("#modalConfidence").textContent = JSON.stringify(data.confidence, null, 2);

    $("#modalMessages").innerHTML = (data.messages || [])
      .map(
        (m) =>
          `<div class="bubble ${escape(m.role)}">${escape(m.content)}</div>`
      )
      .join("");
  } catch (err) {
    $("#modalProfile").textContent = `Lỗi: ${err.message}`;
  }
}

$("#modalClose").addEventListener("click", () => {
  $("#modal").classList.add("hidden");
});
$("#modal").addEventListener("click", (e) => {
  if (e.target.id === "modal") $("#modal").classList.add("hidden");
});

// ---------- Reload buttons ----------
$("#reloadProfiles").addEventListener("click", loadProfiles);
$("#reloadSessions").addEventListener("click", loadSessions);

// ---------- Select all checkbox ----------
$("#selectAllProfiles").addEventListener("change", (e) => {
  const checked = e.target.checked;
  document.querySelectorAll(".profile-check").forEach((cb) => {
    cb.checked = checked;
    const sid = cb.dataset.sid;
    if (checked) selectedSids.add(sid);
    else selectedSids.delete(sid);
  });
  updateExportSelectedBtn();
});

// ---------- Export selected ----------
$("#exportSelectedBtn").addEventListener("click", () => {
  if (selectedSids.size === 0) return;
  const ids = encodeURIComponent([...selectedSids].join(","));
  // Trigger download
  const a = document.createElement("a");
  a.href = `/api/admin/profiles/export.md?ids=${ids}`;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
});

// ---------- Init ----------
(async () => {
  await loadLabels();
  loadProfiles();
  loadSessions();
})();
