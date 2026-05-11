const shell = document.querySelector(".shell");
const tryButton = document.querySelector("#tryButton");
const form = document.querySelector("#chatForm");
const input = document.querySelector("#chatInput");
const sendButton = document.querySelector("#sendButton");
const messages = document.querySelector("#messages");
const chatPanel = document.querySelector(".chat-panel");
const chatStatus = document.querySelector("#chatStatus");

const STREAM_IDLE_TIMEOUT_MS = 45000;

const sessionId = localStorage.getItem("luoying_session_id") || crypto.randomUUID();
localStorage.setItem("luoying_session_id", sessionId);

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function safeHref(value) {
  const href = value.replaceAll("&amp;", "&").trim();
  if (href.startsWith("#") || href.startsWith("/")) return escapeHtml(href);
  try {
    const url = new URL(href, window.location.origin);
    if (["http:", "https:", "mailto:"].includes(url.protocol)) return escapeHtml(href);
  } catch {
    return "";
  }
  return "";
}

function safeImageSrc(value) {
  const src = value.replaceAll("&amp;", "&").trim();
  if (src.startsWith("/")) return escapeHtml(src);
  try {
    const url = new URL(src, window.location.origin);
    if (["http:", "https:"].includes(url.protocol)) return escapeHtml(src);
  } catch {
    return "";
  }
  return "";
}

function renderInlineMarkdown(value) {
  return escapeHtml(value)
    .replace(/`([^`\n]+)`/g, "<code>$1</code>")
    .replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (_, alt, src) => {
      const safe = safeImageSrc(src);
      if (!safe) return `&#33;&#91;${alt}&#93;(${src})`;
      return `<img src="${safe}" alt="${alt}" loading="lazy" decoding="async">`;
    })
    .replace(/(^|[^!])\[([^\]]+)\]\(([^)\s]+)\)/g, (_, prefix, label, href) => {
      const safe = safeHref(href);
      if (!safe) return `${prefix}${label}`;
      return `${prefix}<a href="${safe}" target="_blank" rel="noopener noreferrer">${label}</a>`;
    })
    .replace(/~~([^~\n]+)~~/g, "<del>$1</del>")
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/\n/g, "<br>");
}

function renderMarkdown(markdown) {
  const lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let index = 0;

  function matchUnorderedItem(line) {
    return line.match(/^[-*]\s+(.*)$/) || (line.match(/^[-*]\s*$/) ? ["", ""] : null);
  }

  function matchOrderedItem(line) {
    return line.match(/^\d+\.\s+(.*)$/) || (line.match(/^\d+\.\s*$/) ? ["", ""] : null);
  }

  function isHorizontalRule(line) {
    return /^(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line.trim());
  }

  function splitTableRow(line) {
    let value = line.trim();
    if (value.startsWith("|")) value = value.slice(1);
    if (value.endsWith("|")) value = value.slice(0, -1);
    return value.split("|").map((cell) => cell.trim());
  }

  function isTableSeparator(line) {
    const cells = splitTableRow(line);
    return cells.length >= 2 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
  }

  function tableAlignments(line) {
    return splitTableRow(line).map((cell) => {
      if (cell.startsWith(":") && cell.endsWith(":")) return "center";
      if (cell.endsWith(":")) return "right";
      if (cell.startsWith(":")) return "left";
      return "";
    });
  }

  function tableCellAttr(alignments, cellIndex) {
    const align = alignments[cellIndex] || "";
    return align ? ` class="align-${align}"` : "";
  }

  function renderTableRow(cells, tag, alignments) {
    return `<tr>${cells.map((cell, cellIndex) => (
      `<${tag}${tableCellAttr(alignments, cellIndex)}>${renderInlineMarkdown(cell)}</${tag}>`
    )).join("")}</tr>`;
  }

  function consumeParagraph() {
    const chunk = [];
    while (index < lines.length) {
      const line = lines[index];
      if (
        !line.trim() ||
        /^```/.test(line) ||
        /^#{1,6}\s+/.test(line) ||
        isHorizontalRule(line) ||
        (line.includes("|") && lines[index + 1] && isTableSeparator(lines[index + 1])) ||
        /^[-*]\s+/.test(line) ||
        /^\d+\.\s+/.test(line) ||
        /^>\s?/.test(line)
      ) break;
      chunk.push(line);
      index += 1;
    }
    if (chunk.length) html.push(`<p>${renderInlineMarkdown(chunk.join("\n"))}</p>`);
    if (!chunk.length && index < lines.length) {
      html.push(`<p>${renderInlineMarkdown(lines[index])}</p>`);
      index += 1;
    }
  }

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    const fence = line.match(/^```\s*([\w-]*)/);
    if (fence) {
      index += 1;
      const code = [];
      while (index < lines.length && !/^```/.test(lines[index])) {
        code.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      const lang = fence[1] ? ` class="language-${escapeHtml(fence[1])}"` : "";
      html.push(
        `<div class="code-block"><button class="copy-code" type="button" aria-label="复制代码" title="复制代码"></button>` +
        `<pre><code${lang}>${escapeHtml(code.join("\n"))}</code></pre></div>`
      );
      continue;
    }

    if (isHorizontalRule(line)) {
      html.push("<hr>");
      index += 1;
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      index += 1;
      continue;
    }

    if (line.includes("|") && lines[index + 1] && isTableSeparator(lines[index + 1])) {
      const headers = splitTableRow(line);
      const alignments = tableAlignments(lines[index + 1]);
      index += 2;
      const rows = [];
      while (index < lines.length && lines[index].trim() && lines[index].includes("|")) {
        if (isHorizontalRule(lines[index]) || /^```/.test(lines[index]) || /^#{1,6}\s+/.test(lines[index])) break;
        rows.push(splitTableRow(lines[index]));
        index += 1;
      }
      html.push(
        `<div class="table-wrap"><table><thead>${renderTableRow(headers, "th", alignments)}</thead>` +
        `<tbody>${rows.map((row) => renderTableRow(row, "td", alignments)).join("")}</tbody></table></div>`
      );
      continue;
    }

    const unordered = matchUnorderedItem(line);
    if (unordered) {
      html.push("<ul>");
      while (index < lines.length) {
        const item = matchUnorderedItem(lines[index]);
        if (!item) break;
        html.push(`<li>${renderInlineMarkdown(item[1])}</li>`);
        index += 1;
      }
      html.push("</ul>");
      continue;
    }

    const ordered = matchOrderedItem(line);
    if (ordered) {
      html.push("<ol>");
      while (index < lines.length) {
        const item = matchOrderedItem(lines[index]);
        if (!item) break;
        html.push(`<li>${renderInlineMarkdown(item[1])}</li>`);
        index += 1;
      }
      html.push("</ol>");
      continue;
    }

    const quote = line.match(/^>\s?(.+)$/);
    if (quote) {
      const chunk = [];
      while (index < lines.length) {
        const item = lines[index].match(/^>\s?(.*)$/);
        if (!item) break;
        chunk.push(item[1]);
        index += 1;
      }
      html.push(`<blockquote>${renderInlineMarkdown(chunk.join("\n"))}</blockquote>`);
      continue;
    }

    consumeParagraph();
  }

  return html.join("");
}

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

function renderAssistantBubble(bubble, markdown) {
  bubble.classList.add("markdown-body");
  bubble.innerHTML = renderMarkdown(markdown);
}

function setAssistantStreaming(bubble, active) {
  const row = bubble?.closest(".message-row.assistant");
  if (row) row.classList.toggle("is-streaming", active);
}

function createMarkdownRenderer(bubble) {
  let latest = "";
  let frameId = 0;

  function flush() {
    frameId = 0;
    renderAssistantBubble(bubble, latest);
    scrollToBottom();
  }

  return {
    update(markdown) {
      latest = markdown;
      if (frameId) return;
      frameId = requestAnimationFrame(flush);
    },
    flushNow(markdown = latest) {
      latest = markdown;
      if (frameId) {
        cancelAnimationFrame(frameId);
        frameId = 0;
      }
      flush();
    },
  };
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
  let assistantMarkdown = "";
  let markdownRenderer = null;
  let pendingCard = createTrack("请求已接收，正在连接珞樱…");
  let idleTimer = 0;
  let failed = false;
  const controller = new AbortController();
  chatPanel.classList.add("is-thinking");
  chatStatus.textContent = "正在思考";

  function clearPending() {
    if (!pendingCard) return;
    pendingCard.remove();
    pendingCard = null;
  }

  function resetIdleTimer() {
    window.clearTimeout(idleTimer);
    idleTimer = window.setTimeout(() => {
      controller.abort();
    }, STREAM_IDLE_TIMEOUT_MS);
  }

  function ensureAssistantBubble() {
    if (assistantBubble) return assistantBubble;
    assistantBubble = createBubble("assistant", "");
    markdownRenderer = createMarkdownRenderer(assistantBubble);
    return assistantBubble;
  }

  try {
    resetIdleTimer();
    const resp = await fetch("/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      body: JSON.stringify({
        session_id: sessionId,
        user_id: "web-user",
        user_name: "网页用户",
        text,
      }),
    });

    if (!resp.ok || !resp.body) {
      throw new Error(`请求失败：${resp.status}`);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let streamDone = false;

    while (!streamDone) {
      const { done, value } = await reader.read();
      if (done) break;
      resetIdleTimer();
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
          ensureAssistantBubble();
          chatStatus.textContent = "正在回复";
          setAssistantStreaming(assistantBubble, true);
          assistantMarkdown += data.text || "";
          markdownRenderer.update(assistantMarkdown);
        }
        if (event === "error") {
          throw new Error(data.error || "请求出错");
        }
        if (event === "done") {
          streamDone = true;
          break;
        }
        scrollToBottom();
      }
    }

    if (markdownRenderer) markdownRenderer.flushNow(assistantMarkdown);
  } catch (error) {
    failed = true;
    clearPending();
    ensureAssistantBubble();
    const isAbort = error instanceof DOMException && error.name === "AbortError";
    const message = isAbort
      ? "连接太久没有新内容，已经自动停止。你可以重新发送。"
      : error.message || "请求出错";
    assistantMarkdown = assistantMarkdown
      ? `${assistantMarkdown}\n\n> ${message}`
      : message;
    markdownRenderer.flushNow(assistantMarkdown);
    setAssistantStreaming(assistantBubble, false);
    chatStatus.textContent = "请求已停止";
  } finally {
    window.clearTimeout(idleTimer);
    clearPending();
    if (markdownRenderer) markdownRenderer.flushNow(assistantMarkdown);
    setAssistantStreaming(assistantBubble, false);
    chatPanel.classList.remove("is-thinking");
    if (!failed) chatStatus.textContent = "随时待命";
  }
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

messages.addEventListener("click", async (event) => {
  const button = event.target.closest(".copy-code");
  if (!button) return;

  const block = button.closest(".code-block");
  const code = block?.querySelector("code")?.textContent || "";
  if (!code) return;

  try {
    await navigator.clipboard.writeText(code);
    button.classList.add("is-copied");
    button.setAttribute("title", "已复制");
    window.setTimeout(() => {
      button.classList.remove("is-copied");
      button.setAttribute("title", "复制代码");
    }, 1200);
  } catch {
    button.setAttribute("title", "复制失败");
  }
});
