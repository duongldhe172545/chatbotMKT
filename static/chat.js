// Chat client — Web Speech API cho voice input (Chrome/Edge tốt nhất)
const chatEl = document.getElementById("chat");
const formEl = document.getElementById("form");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("sendBtn");
const micBtn = document.getElementById("micBtn");
const statusEl = document.getElementById("status");

const SESSION_KEY = "em_linh_session_id";
let sessionId = localStorage.getItem(SESSION_KEY) || null;

// P0-3: chặn double-submit ở scope ngoài (form submit + sendMessage cùng check)
let isSending = false;

// ---------- UI helpers ----------
function appendBubble(role, content) {
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  div.textContent = content;
  chatEl.appendChild(div);
  chatEl.scrollTop = chatEl.scrollHeight;
  return div;
}

function clearChat() {
  chatEl.innerHTML = "";
}

function renderHistory(messages) {
  clearChat();
  for (const m of messages || []) {
    appendBubble(m.role, m.content);
  }
}

function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.classList.toggle("error", isError);
}

function setBusy(busy) {
  sendBtn.disabled = busy;
  inputEl.disabled = busy;
  micBtn.disabled = busy;
}

// ---------- Typing indicator xoay vòng ----------
// Sonnet 4.6 đôi khi mất 4-6s — tránh nhàm chán bằng message thay đổi theo thời gian.
const TYPING_MESSAGES = [
  "Em đang đọc tin nhắn của anh...",
  "Em đang nghĩ xíu...",
  "Em sắp xong rồi ạ...",
  "Anh chờ em chút nha...",
  "Em đang gõ lại cho gọn...",
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
  // Lần đầu hiện sau 2s (tránh nháy nếu LLM trả nhanh)
  const initialTimer = setTimeout(tick, 2000);
  // Sau đó đổi message mỗi 3s
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
    body: JSON.stringify({ session_id: sessionId, message }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Lỗi server");
  }
  return res.json();
}

async function sendMessage(text) {
  if (isSending) return; // P0-3: chặn double submit
  isSending = true;
  setBusy(true);
  appendBubble("dealer", text);

  const typing = createTypingBubble();

  try {
    const data = await postChat(text);
    sessionId = data.session_id;
    localStorage.setItem(SESSION_KEY, sessionId);

    typing.stop();
    appendBubble("bot", data.bot_message);

    setStatus(`Stage: ${data.stage}`);
  } catch (err) {
    typing.stop();
    setStatus(`Lỗi: ${err.message}`, true);
  } finally {
    isSending = false;
    setBusy(false);
    inputEl.focus();
  }
}

// ---------- Init: khôi phục history hoặc chào mới ----------
async function init() {
  setStatus("Đang kết nối...");
  setBusy(true);
  try {
    const data = await postChat("");
    sessionId = data.session_id;
    localStorage.setItem(SESSION_KEY, sessionId);

    if (data.messages && data.messages.length > 0) {
      renderHistory(data.messages);
    } else {
      appendBubble("bot", data.bot_message);
    }
    setStatus(`Stage: ${data.stage}`);
  } catch (err) {
    setStatus(`Lỗi: ${err.message}`, true);
  } finally {
    setBusy(false);
  }
}

// ---------- Form submit ----------
formEl.addEventListener("submit", (e) => {
  e.preventDefault();
  if (isSending) return; // P0-3: chặn ở cả form-level
  if (isRecording && recognitionRef) {
    try { recognitionRef.stop(); } catch (_) {}
  }
  const text = inputEl.value.trim();
  if (!text) return;
  inputEl.value = "";
  sendMessage(text);
});

// ---------- Web Speech API (voice → text) ----------
let recognitionRef = null;
let isRecording = false;

const SpeechRecognition =
  window.SpeechRecognition || window.webkitSpeechRecognition;

if (!SpeechRecognition) {
  micBtn.disabled = true;
  micBtn.title = "Trình duyệt không hỗ trợ voice. Dùng Chrome/Edge.";
} else {
  recognitionRef = new SpeechRecognition();
  recognitionRef.lang = "vi-VN";
  recognitionRef.continuous = false;
  recognitionRef.interimResults = true;

  let finalTranscript = "";

  micBtn.addEventListener("click", () => {
    if (isRecording) {
      recognitionRef.stop();
    } else {
      finalTranscript = "";
      recognitionRef.start();
    }
  });

  recognitionRef.onstart = () => {
    isRecording = true;
    micBtn.classList.add("recording");
    setStatus("Đang nghe... (bấm lại để dừng, sau đó kiểm tra rồi bấm Gửi)");
  };

  recognitionRef.onresult = (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const transcript = event.results[i][0].transcript;
      if (event.results[i].isFinal) {
        finalTranscript += transcript;
      } else {
        interim += transcript;
      }
    }
    inputEl.value = finalTranscript + interim;
  };

  recognitionRef.onerror = (event) => {
    setStatus(`Lỗi voice: ${event.error}`, true);
  };

  recognitionRef.onend = () => {
    isRecording = false;
    micBtn.classList.remove("recording");
    if (finalTranscript.trim()) {
      setStatus("Em nghe xong rồi ạ — anh đọc lại rồi bấm Gửi nhé.");
      inputEl.focus();
    } else {
      setStatus("Em chưa nghe rõ, anh thử nói lại giúp em với ạ.");
    }
  };
}

// ---------- P1-8: cleanup khi rời trang ----------
window.addEventListener("beforeunload", () => {
  if (recognitionRef) {
    try { recognitionRef.abort(); } catch (_) {}
    recognitionRef.onstart = null;
    recognitionRef.onresult = null;
    recognitionRef.onerror = null;
    recognitionRef.onend = null;
  }
});

// Bắt đầu
init();
