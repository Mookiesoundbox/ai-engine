const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const messages = document.getElementById("messages");
const chatArea = document.getElementById("chatArea");
const sendBtn = document.getElementById("sendBtn");
const welcomeCard = document.getElementById("welcomeCard");
const newChatBtn = document.getElementById("newChatBtn");
const sourcesPanel = document.getElementById("sourcesPanel");
const sourcesList = document.getElementById("sourcesList");
const closeSourcesBtn = document.getElementById("closeSourcesBtn");
const suggestionChips = document.querySelectorAll(".suggestion-chip");

function autoResizeTextarea() {
  messageInput.style.height = "auto";
  messageInput.style.height = `${messageInput.scrollHeight}px`;
}

messageInput.addEventListener("input", autoResizeTextarea);

messageInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    chatForm.requestSubmit();
  }
});

function scrollToBottom() {
  requestAnimationFrame(() => {
    chatArea.scrollTop = chatArea.scrollHeight;
  });
}

function createMessageRow(role, content, isTyping = false) {
  const row = document.createElement("div");
  row.className = `message-row ${role}`;

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";

  if (isTyping) {
    bubble.innerHTML = `
      <div class="typing">
        <span></span><span></span><span></span>
      </div>
    `;
  } else {
    bubble.textContent = content;
  }

  row.appendChild(bubble);
  return row;
}

function addMessage(role, content) {
  const row = createMessageRow(role, content, false);
  messages.appendChild(row);
  scrollToBottom();
  return row;
}

function addTypingIndicator() {
  const row = createMessageRow("assistant", "", true);
  row.id = "typing-indicator";
  messages.appendChild(row);
  scrollToBottom();
}

function removeTypingIndicator() {
  const existing = document.getElementById("typing-indicator");
  if (existing) existing.remove();
}

function showSources(sources = []) {
  sourcesList.innerHTML = "";

  if (!sources.length) {
    sourcesPanel.classList.add("hidden");
    return;
  }

  sources.forEach((source) => {
    const card = document.createElement(source.url ? "a" : "div");
    card.className = "source-card";

    if (source.url) {
      card.href = source.url;
      card.target = "_blank";
      card.rel = "noopener noreferrer";
    }

    card.innerHTML = `
      <h4>${escapeHtml(source.title || "Source")}</h4>
      <p>${escapeHtml(source.snippet || "")}</p>
    `;

    sourcesList.appendChild(card);
  });

  sourcesPanel.classList.remove("hidden");
}

function hideSources() {
  sourcesPanel.classList.add("hidden");
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function sendMessage(message) {
  const trimmed = message.trim();
  if (!trimmed) return;

  welcomeCard.style.display = "none";
  hideSources();

  addMessage("user", trimmed);

  messageInput.value = "";
  messageInput.style.height = "auto";
  sendBtn.disabled = true;

  addTypingIndicator();

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ message: trimmed })
    });

    if (!response.ok) {
      throw new Error("Request failed");
    }

    const data = await response.json();

    removeTypingIndicator();
    addMessage("assistant", data.reply || "No response received.");
    showSources(data.sources || []);
  } catch (error) {
    removeTypingIndicator();
    addMessage("assistant", "Something went wrong talking to the engine.");
    console.error(error);
  } finally {
    sendBtn.disabled = false;
    messageInput.focus();
  }
}

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  await sendMessage(messageInput.value);
});

suggestionChips.forEach((chip) => {
  chip.addEventListener("click", async () => {
    await sendMessage(chip.textContent);
  });
});

closeSourcesBtn.addEventListener("click", hideSources);

newChatBtn.addEventListener("click", () => {
  messages.innerHTML = "";
  sourcesList.innerHTML = "";
  hideSources();
  welcomeCard.style.display = "block";
  messageInput.value = "";
  messageInput.style.height = "auto";
  messageInput.focus();
});
