const shell = document.querySelector(".shell");
const tryButton = document.querySelector("#tryButton");
const form = document.querySelector("#chatForm");
const input = document.querySelector("#chatInput");
const sendButton = document.querySelector("#sendButton");
const messages = document.querySelector("#messages");
const chatPanel = document.querySelector(".chat-panel");
const chatStatus = document.querySelector("#chatStatus");

const sessionId = localStorage.getItem("luoying_session_id") || crypto.randomUUID();
localStorage.setItem("luoying_session_id", sessionId);

function enterChat() {
  shell.dataset.state = "chat";
  setTimeout(() => input.focus(), 760);
}

function scrollToBottom() {
  messages.scrollTop = messages.scrollHeight;
}

function createPetalAvatar(className = "message-avatar") {
  const avatar = document.createElement("div");
  avatar.className = `agent-avatar ${className}`;
  avatar.setAttribute("aria-hidden", "true");
  for (let i = 0; i < 5; i += 1) {
    avatar.appendChild(document.createElement("span"));
  }
  return avatar;
}

function createBubble(role, text = "") {
  const row = document.createElement("div");
  row.className = `message-row ${role}`;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  if (role === "assistant") row.appendChild(createPetalAvatar());
  row.appendChild(bubble);
  messages.appendChild(row);
  scrollToBottom();
  return bubble;
}

function createTrack(text) {
  const card = document.createElement("div");
  card.className = "track-card";
  card.textContent = text;
  messages.appendChild(card);
  scrollToBottom();
  return card;
}

function parseSse(raw) {
  const eventLine = raw.split("\n").find((line) => line.startsWith("event: "));
  const dataLine = raw.split("\n").find((line) => line.startsWith("data: "));
  if (!eventLine || !dataLine) return null;
  return {
    event: eventLine.slice(7),
    data: JSON.parse(dataLine.slice(6)),
  };
}

async function sendMessage(text) {
  createBubble("user", text);
  let assistantBubble = null;
  let pendingCard = createTrack("请求已接收，正在连接珞樱…");
  chatPanel.classList.add("is-thinking");
  chatStatus.textContent = "正在思考";

  function clearPending() {
    if (!pendingCard) return;
    pendingCard.remove();
    pendingCard = null;
  }

  const resp = await fetch("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      user_id: "web-user",
      user_name: "网页用户",
      text,
    }),
  });

  if (!resp.ok || !resp.body) {
    clearPending();
    assistantBubble = createBubble("assistant", "");
    assistantBubble.textContent = `请求失败：${resp.status}`;
    chatPanel.classList.remove("is-thinking");
    chatStatus.textContent = "请求失败";
    return;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";

    for (const part of parts) {
      const item = parseSse(part);
      if (!item) continue;
      const { event, data } = item;

      if (event === "track") {
        clearPending();
        createTrack(data.text || "");
      }
      if (event === "text_delta") {
        clearPending();
        if (!assistantBubble) {
          assistantBubble = createBubble("assistant", "");
          chatPanel.classList.remove("is-thinking");
          chatStatus.textContent = "正在回复";
        }
        assistantBubble.textContent += data.text || "";
      }
      if (event === "error") {
        clearPending();
        if (!assistantBubble) assistantBubble = createBubble("assistant", "");
        assistantBubble.textContent = data.error || "请求出错";
        chatPanel.classList.remove("is-thinking");
        chatStatus.textContent = "请求出错";
      }
      scrollToBottom();
    }
  }

  clearPending();
  chatPanel.classList.remove("is-thinking");
  chatStatus.textContent = "随时待命";
}

tryButton.addEventListener("click", enterChat);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;

  input.value = "";
  input.disabled = true;
  sendButton.disabled = true;
  try {
    await sendMessage(text);
  } finally {
    input.disabled = false;
    sendButton.disabled = false;
    input.focus();
  }
});
