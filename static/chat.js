// Chat client v2 — adapt to REST v2 API under /api/v1.
// Refer routes_v2.py and ChatService.

const chatEl = document.getElementById("chat");
const formEl = document.getElementById("form");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("sendBtn");
const micBtn = document.getElementById("micBtn");
const statusEl = document.getElementById("status");

const SESSION_ID_KEY = "em_linh_session_id_v8";
const SESSION_TOKEN_KEY = "em_linh_session_token_v8";

let sessionId = localStorage.getItem(SESSION_ID_KEY) || null;
let sessionToken = localStorage.getItem(SESSION_TOKEN_KEY) || null;

// Chặn double-submit
let isSending = false;
let logoPollTimer = null;


// ---------- UI helpers ----------
function appendBubble(role, content) {
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  // Multi-line support
  div.textContent = content;
  div.style.whiteSpace = "pre-wrap";
  chatEl.appendChild(div);
  chatEl.scrollTop = chatEl.scrollHeight;
}

function appendLogoGallery(variants) {
  if (!Array.isArray(variants) || !variants.length) return;
  const existing = document.getElementById("logo-gallery");
  if (existing) existing.remove();

  const section = document.createElement("section");
  section.id = "logo-gallery";
  section.className = "logo-gallery";

  const heading = document.createElement("div");
  heading.className = "logo-gallery-heading";
  heading.textContent = `${variants.length} mẫu logo của cửa hàng`;
  section.appendChild(heading);

  const grid = document.createElement("div");
  grid.className = "logo-grid";
  for (const variant of variants) {
    const card = document.createElement("article");
    card.className = "logo-card";

    const image = document.createElement("img");
    image.src = variant.url;
    image.alt = variant.name;
    image.loading = "lazy";
    card.appendChild(image);

    const name = document.createElement("strong");
    name.textContent = variant.name;
    card.appendChild(name);

    const style = document.createElement("span");
    style.textContent = variant.style;
    card.appendChild(style);

    const link = document.createElement("a");
    link.href = variant.download_url;
    link.download = "";
    link.textContent = "Tải ảnh";
    card.appendChild(link);
    grid.appendChild(card);
  }
  section.appendChild(grid);
  chatEl.appendChild(section);
  chatEl.scrollTop = chatEl.scrollHeight;
}


function trackLogoJob(job) {
  if (!job || !["queued", "working"].includes(job.status)) {
    if (logoPollTimer) clearTimeout(logoPollTimer);
    logoPollTimer = null;
    return;
  }
  setStatus(`Đang dựng logo ${job.progress || 0}/${job.total || 3}`);
  if (logoPollTimer) clearTimeout(logoPollTimer);
  logoPollTimer = setTimeout(pollLogos, 1500);
}


async function pollLogos() {
  if (!sessionId || !sessionToken) return;
  try {
    const res = await fetch(`/api/v1/sessions/${sessionId}/logos`, {
      headers: {
        "Authorization": `Bearer ${sessionToken}`
      }
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const envelope = await res.json();
    if (!envelope.ok) throw new Error(envelope.error?.message || "Lỗi tải logo");
    
    const data = envelope.data;
    appendLogoGallery(data.logo_variants);
    if (data.logo_job?.status === "failed") {
      setStatus("Dựng logo chưa thành công, anh thử lại sau nhé.", true);
      return;
    }
    if (data.logo_job?.status === "completed") {
      const total = data.logo_job?.total || data.logo_variants?.length || 3;
      setStatus(`Đã dựng xong ${total} mẫu logo`);
      return;
    }
    trackLogoJob(data.logo_job);
  } catch (err) {
    setStatus(`Lỗi tải logo: ${err.message}`, true);
  }
}


function _addStartNewButton() {
  // Tránh add nhiều lần
  if (document.getElementById("start-new-btn")) return;
  const btn = document.createElement("button");
  btn.id = "start-new-btn";
  btn.textContent = "Bắt đầu chat mới";
  btn.style.cssText =
    "margin:12px auto;padding:10px 24px;display:block;" +
    "background:#4caf50;color:white;border:none;border-radius:6px;" +
    "cursor:pointer;font-size:14px;";
  btn.onclick = () => {
    localStorage.removeItem(SESSION_ID_KEY);
    localStorage.removeItem(SESSION_TOKEN_KEY);
    location.reload();
  };
  chatEl.appendChild(btn);
  chatEl.scrollTop = chatEl.scrollHeight;
}


function setStatus(text, isError = false) {
  if (statusEl) {
    statusEl.textContent = text;
    statusEl.classList.toggle("error", isError);
  }
}


function setBusy(busy) {
  if (sendBtn) sendBtn.disabled = busy;
  if (inputEl) inputEl.disabled = busy;
  if (micBtn) micBtn.disabled = busy;
}


// ---------- Typing indicator ----------
const TYPING_MESSAGES = [
  "Em đang đọc tin nhắn...",
  "Em đang nghĩ xíu...",
  "Em sắp xong rồi ạ...",
  "Chờ em chút nha...",
];

function createTypingBubble() {
  const div = document.createElement("div");
  div.className = "bubble bot typing";
  div.innerHTML = '<span class="typing-dots"><span></span><span></span><span></span></span><span class="typing-text"></span>';
  chatEl.appendChild(div);
  chatEl.scrollTop = chatEl.scrollHeight;

  const textEl = div.querySelector(".typing-text");
  let idx = -1;
  let stopped = false;

  const tick = () => {
    if (stopped) return;
    idx = (idx + 1) % TYPING_MESSAGES.length;
    textEl.textContent = " " + TYPING_MESSAGES[idx];
  };
  const initialTimer = setTimeout(tick, 2000);
  const interval = setInterval(tick, 3000);

  return {
    el: div,
    stop() {
      stopped = true;
      clearTimeout(initialTimer);
      clearInterval(interval);
      div.remove();
    },
  };
}


// ---------- API calls ----------
async function startNewSession() {
  const res = await fetch("/api/v1/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      channel: "web_text",
      client: {
        user_agent: navigator.userAgent
      }
    })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: { message: res.statusText } }));
    throw new Error((err.error && err.error.message) || `HTTP ${res.status}`);
  }
  const envelope = await res.json();
  if (!envelope.ok) {
    throw new Error(envelope.error?.message || "Lỗi tạo session");
  }
  
  sessionId = envelope.data.session_id;
  sessionToken = envelope.data.session_token;
  localStorage.setItem(SESSION_ID_KEY, sessionId);
  localStorage.setItem(SESSION_TOKEN_KEY, sessionToken);
  
  return envelope.data;
}


async function sendMessage(text) {
  if (isSending) return;
  isSending = true;
  setBusy(true);

  if (text) {
    appendBubble("dealer", text);
  }

  const typing = createTypingBubble();

  try {
    const idempotencyKey = crypto.randomUUID ? crypto.randomUUID() : (Math.random().toString(36).substring(2) + Date.now().toString(36));
    const clientMessageId = "cmsg-" + Date.now() + "-" + Math.random().toString(36).substring(2, 6);

    const res = await fetch(`/api/v1/sessions/${sessionId}/messages`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${sessionToken}`,
        "Idempotency-Key": idempotencyKey
      },
      body: JSON.stringify({
        message_type: "text",
        text: text,
        client_message_id: clientMessageId
      })
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: { message: res.statusText } }));
      throw new Error(err.error?.message || `HTTP ${res.status}`);
    }

    const envelope = await res.json();
    if (!envelope.ok) {
      throw new Error(envelope.error?.message || "Lỗi gửi tin nhắn");
    }

    const data = envelope.data;
    typing.stop();

    if (Array.isArray(data.events)) {
      for (const event of data.events) {
        if (event.event_type === "message") {
          const role = event.source === "user" ? "dealer" : "bot";
          appendBubble(role, event.text);
        }
      }
    }

    setStatus(`Stage: ${data.workflow_state}`);
    
    // Check if we need to poll logos
    if (data.workflow_state === "LOGO_PENDING" || data.workflow_state === "LOGO_READY" || data.workflow_state === "CLOSED" || data.workflow_state === "ESCALATED") {
      pollLogos();
    }
    
    if (data.workflow_state === "CLOSED" || data.workflow_state === "LOGO_READY" || data.workflow_state === "ESCALATED") {
      _addStartNewButton();
    }
  } catch (err) {
    typing.stop();
    setStatus(`Lỗi: ${err.message}`, true);
    appendBubble("bot", "Dạ em đang gặp xíu trục trặc, anh thử nhắn lại sau ít phút nhé.");
  } finally {
    isSending = false;
    setBusy(false);
    if (inputEl) inputEl.focus();
  }
}


// ---------- Init ----------
async function init() {
  setStatus("Đang kết nối...");
  setBusy(true);
  try {
    if (sessionId && sessionToken) {
      try {
        const res = await fetch(`/api/v1/sessions/${sessionId}`, {
          headers: {
            "Authorization": `Bearer ${sessionToken}`
          }
        });
        if (res.ok) {
          const envelope = await res.json();
          if (envelope.ok) {
            const data = envelope.data;
            chatEl.innerHTML = "";
            const events = data.recent_events || [];
            
            // Under REST v2, events are sorted oldest to newest (by event_cursor)
            for (const event of events) {
              if (event.event_type === "message") {
                const role = event.source === "user" ? "dealer" : "bot";
                appendBubble(role, event.text);
              }
            }
            
            pollLogos();
            
            if (data.workflow_state === "CLOSED" || data.workflow_state === "LOGO_READY" || data.workflow_state === "ESCALATED") {
              appendBubble("bot",
                "── Hồ sơ đã chốt ──\n\n" +
                "Anh vẫn có thể nhắn em thêm, hoặc bắt đầu một hồ sơ mới bằng nút bên dưới.");
              setStatus(`Hồ sơ đã chốt — ${events.length} tin nhắn lưu lại`, false);
              _addStartNewButton();
            } else {
              setStatus(`Resume — Stage: ${data.workflow_state}, ${events.length} tin nhắn`);
            }
            setBusy(false);
            return;
          }
        }
        // Session expired or DB cleared -> clear storage and trigger new session
        sessionId = null;
        sessionToken = null;
        localStorage.removeItem(SESSION_ID_KEY);
        localStorage.removeItem(SESSION_TOKEN_KEY);
      } catch (err) {
        sessionId = null;
        sessionToken = null;
        localStorage.removeItem(SESSION_ID_KEY);
        localStorage.removeItem(SESSION_TOKEN_KEY);
      }
    }

    // New session -> creates session + triggers greeting by sending empty string
    await startNewSession();
    await sendMessage("");
  } catch (err) {
    setStatus(`Lỗi: ${err.message}`, true);
    appendBubble("bot", "Em xin lỗi, kết nối có vấn đề. Anh thử reload trang nhé.");
  } finally {
    setBusy(false);
  }
}


// ---------- Form submit ----------
if (formEl) {
  formEl.addEventListener("submit", (e) => {
    e.preventDefault();
    if (isSending) return;
    const text = inputEl.value.trim();
    if (!text) return;
    inputEl.value = "";
    sendMessage(text);
  });
}


// ---------- Init on load ----------
init();
