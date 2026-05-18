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
  "Em đang đọc tin nhắn của anh...",
  "Em đang nghĩ xíu...",
  "Em sắp xong rồi ạ...",
  "Anh chờ em chút nha...",
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
      // Resume session existing — fetch status
      try {
        const statusRes = await fetch(`/api/chat/${sessionId}/status`);
        if (statusRes.ok) {
          const status = await statusRes.json();
          if (status.stage === "DONE") {
            // Session đã DONE — bắt đầu mới
            sessionId = null;
            localStorage.removeItem(SESSION_KEY);
          } else {
            setStatus(`Resume session — Stage: ${status.stage}`);
            setBusy(false);
            return;
          }
        } else {
          // Session không tồn tại → clear + new
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
