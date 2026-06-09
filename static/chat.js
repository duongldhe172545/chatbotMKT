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

let isSending = false;


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

function appendAddressForm(eventId, isSubmitted = false) {
  const formId = `address-form-${eventId}`;
  if (document.getElementById(formId)) return;

  const card = document.createElement("div");
  card.id = formId;
  card.className = "address-form-card";
  if (isSubmitted) {
    card.className += " submitted";
  }

  const title = document.createElement("div");
  title.className = "form-title";
  title.innerHTML = `
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/>
      <circle cx="12" cy="10" r="3"/>
    </svg>
    Nhập Địa Chỉ Cửa Hàng
  `;
  card.appendChild(title);

  // Group 1: Tỉnh / Thành phố
  const grpProv = document.createElement("div");
  grpProv.className = "address-form-group";
  const lblProv = document.createElement("label");
  lblProv.textContent = "Tỉnh / Thành phố *";
  const inpProv = document.createElement("input");
  inpProv.type = "text";
  inpProv.placeholder = "Ví dụ: Hà Nội, TP.HCM, Hải Phòng...";
  inpProv.required = true;
  if (isSubmitted) inpProv.disabled = true;
  grpProv.appendChild(lblProv);
  grpProv.appendChild(inpProv);
  card.appendChild(grpProv);

  // Group 2: Xã / Phường / Thị trấn
  const grpWard = document.createElement("div");
  grpWard.className = "address-form-group";
  const lblWard = document.createElement("label");
  lblWard.textContent = "Xã / Phường / Thị trấn *";
  const inpWard = document.createElement("input");
  inpWard.type = "text";
  inpWard.placeholder = "Ví dụ: Phường Cát Linh, Xã Đại Thịnh...";
  inpWard.required = true;
  if (isSubmitted) inpWard.disabled = true;
  grpWard.appendChild(lblWard);
  grpWard.appendChild(inpWard);
  card.appendChild(grpWard);

  // Group 3: Địa chỉ chi tiết
  const grpDetail = document.createElement("div");
  grpDetail.className = "address-form-group";
  const lblDetail = document.createElement("label");
  lblDetail.textContent = "Địa chỉ chi tiết (Số nhà, Tên đường...) *";
  const inpDetail = document.createElement("input");
  inpDetail.type = "text";
  inpDetail.placeholder = "Ví dụ: 123 Lê Lợi, Thôn Đông...";
  inpDetail.required = true;
  if (isSubmitted) inpDetail.disabled = true;
  grpDetail.appendChild(lblDetail);
  grpDetail.appendChild(inpDetail);
  card.appendChild(grpDetail);

  // Submit button
  const submitBtn = document.createElement("button");
  submitBtn.className = "address-form-submit";
  submitBtn.textContent = isSubmitted ? "Đã xác nhận" : "Xác nhận địa chỉ";
  if (isSubmitted) submitBtn.disabled = true;
  card.appendChild(submitBtn);

  // Error message placeholder
  const errText = document.createElement("div");
  errText.style.color = "var(--danger)";
  errText.style.fontSize = "12px";
  errText.style.marginTop = "-6px";
  errText.style.display = "none";
  card.appendChild(errText);

  if (!isSubmitted) {
    submitBtn.addEventListener("click", () => {
      const provVal = inpProv.value.trim();
      const wardVal = inpWard.value.trim();
      const detailVal = inpDetail.value.trim();

      if (!provVal || !wardVal || !detailVal) {
        errText.textContent = "Vui lòng nhập đầy đủ cả 3 thông tin.";
        errText.style.display = "block";
        return;
      }

      errText.style.display = "none";

      // Form ward value with prefix if missing
      let formattedWard = wardVal;
      const lowerWard = wardVal.toLowerCase();
      if (
        !lowerWard.startsWith("phường") &&
        !lowerWard.startsWith("xã") &&
        !lowerWard.startsWith("thị trấn") &&
        !/^p\s*\d/.test(lowerWard) &&
        !/^p\.\s*\d/.test(lowerWard)
      ) {
        if (/^\d+$/.test(wardVal)) {
          formattedWard = "Phường " + wardVal;
        } else {
          formattedWard = "Phường " + wardVal;
        }
      }

      const fullAddressText = `${detailVal}, ${formattedWard}, ${provVal}`;
      
      inpProv.disabled = true;
      inpWard.disabled = true;
      inpDetail.disabled = true;
      submitBtn.disabled = true;
      submitBtn.textContent = "Đã gửi";
      card.classList.add("submitted");

      sendMessage(fullAddressText);
    });
  }

  chatEl.appendChild(card);
  chatEl.scrollTop = chatEl.scrollHeight;
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
    const addressFilled = !!(data.profile_snapshot?.all_fields?.address);
    typing.stop();

    if (Array.isArray(data.events)) {
      for (const event of data.events) {
        if (event.event_type === "message") {
          const role = event.source === "user" ? "dealer" : "bot";
          appendBubble(role, event.text);
          if (event.message_type === "address_form" && role === "bot") {
            appendAddressForm(event.event_id, addressFilled);
          }
        }
      }
    }

    setStatus(`Stage: ${data.workflow_state}`);
    
    if (data.status === "CLOSED" || data.status === "REJECTED") {
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
            const addressFilled = !!(data.profile_snapshot?.all_fields?.address);
            chatEl.innerHTML = "";
            const events = data.recent_events || [];
            
            // Under REST v2, events are sorted oldest to newest (by event_cursor)
            for (const event of events) {
              if (event.event_type === "message") {
                const role = event.source === "user" ? "dealer" : "bot";
                appendBubble(role, event.text);
                if (event.message_type === "address_form" && role === "bot") {
                  appendAddressForm(event.event_id, addressFilled);
                }
              }
            }
            
            if (data.status === "CLOSED" || data.status === "REJECTED") {
              let finalTitle = data.status === "CLOSED" ? "── Hồ sơ đã chốt ──" : "── Hồ sơ không chốt ──";
              let finalLabel = data.status === "CLOSED" ? "Hồ sơ đã chốt" : "Hồ sơ không chốt";
              appendBubble("bot",
                `${finalTitle}\n\n` +
                "Anh vẫn có thể nhắn em thêm, hoặc bắt đầu một hồ sơ mới bằng nút bên dưới.");
              setStatus(`${finalLabel} — ${events.length} tin nhắn lưu lại`, false);
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
