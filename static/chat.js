// Chat client v8 — adapt /api/chat response format.
// Refer app/api/chat.py: ChatResponse {session_id, reply, stage, current_slot, is_first_turn}

const chatEl = document.getElementById("chat");
const formEl = document.getElementById("form");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("sendBtn");
const micBtn = document.getElementById("micBtn");
const statusEl = document.getElementById("status");

const SESSION_KEY = "em_linh_session_id_v8";
let sessionId = localStorage.getItem(SESSION_KEY) || null;

// Chặn double-submit
let isSending = false;


// ---------- UI helpers ----------
function appendBubble(role, content) {
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  // Multi-line support (greeting có \n + card có ASCII art)
  div.textContent = content;
  div.style.whiteSpace = "pre-wrap";
  chatEl.appendChild(div);
  chatEl.scrollTop = chatEl.scrollHeight;
}


// Phase 6 R+ 2026-05-25: button "Bắt đầu chat mới" khi session DONE.
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
    localStorage.removeItem(SESSION_KEY);
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


// ---------- API call ----------
async function postChat(message) {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      message: message || "",
      channel: "web",
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}


async function sendMessage(text) {
  if (isSending) return;
  isSending = true;
  setBusy(true);
  appendBubble("dealer", text);

  const typing = createTypingBubble();

  try {
    const data = await postChat(text);
    sessionId = data.session_id;
    localStorage.setItem(SESSION_KEY, sessionId);

    typing.stop();
    appendBubble("bot", data.reply);

    setStatus(`Stage: ${data.stage}${data.current_slot ? ' | Slot: ' + data.current_slot : ''}`);
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
    if (sessionId) {
      // Resume session existing — fetch history + restore UI
      // Phase 6 R+ 2026-05-25 (user feedback): KHÔNG auto-clear khi DONE.
      // Render lịch sử full, hiển thị thông báo session đã đóng + cho dealer
      // option bắt đầu mới (reload trang).
      try {
        const histRes = await fetch(`/api/chat/${sessionId}/history`);
        if (histRes.ok) {
          const data = await histRes.json();
          // Render lịch sử full (cả khi DONE để dealer xem lại)
          chatEl.innerHTML = "";
          for (const msg of data.messages || []) {
            appendBubble(msg.role, msg.content);
          }
          if (data.stage === "DONE") {
            // Session đã đóng — disable input, show notice
            appendBubble("bot",
              "── Cuộc trò chuyện này đã kết thúc ──\n\n" +
              "Anh muốn bắt đầu lại từ đầu thì bấm nút bên dưới nhé.");
            setStatus(`Session đã đóng — ${(data.messages || []).length} tin nhắn lưu lại`, false);
            // Disable input + show start-new button
            if (inputEl) inputEl.disabled = true;
            if (sendBtn) sendBtn.disabled = true;
            _addStartNewButton();
            setBusy(false);
            return;
          }
          setStatus(`Resume — Stage: ${data.stage}, ${(data.messages || []).length} tin nhắn`);
          setBusy(false);
          return;
        } else {
          // Session không tồn tại (DB cleared) → clear + new
          sessionId = null;
          localStorage.removeItem(SESSION_KEY);
        }
      } catch (_) {
        sessionId = null;
      }
    }

    // Session mới → POST với session_id=null → backend trả greeting
    const data = await postChat("");
    sessionId = data.session_id;
    localStorage.setItem(SESSION_KEY, sessionId);
    appendBubble("bot", data.reply);
    setStatus(`Stage: ${data.stage}`);
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
