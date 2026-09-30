// Northwind Robotics chat UI. Vanilla JS, no dependencies.
// Talks to POST /api/chat and renders answers with collapsible citations.

"use strict";

const chatEl = document.getElementById("chat");
const formEl = document.getElementById("composer");
const inputEl = document.getElementById("input");
const sendEl = document.getElementById("send");
const sourceTemplate = document.getElementById("source-template");

// Conversation history sent back to the API for follow-up questions.
const history = [];

function scrollToBottom() {
  chatEl.scrollTop = chatEl.scrollHeight;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function addMessage(role, initialText) {
  const message = el("div", `message ${role}`);
  const avatar = el("div", "avatar", role === "user" ? "You" : "AI");
  const bubble = el("div", "bubble");
  if (initialText !== undefined) {
    bubble.appendChild(el("p", null, initialText));
  }
  message.append(avatar, bubble);
  chatEl.appendChild(message);
  scrollToBottom();
  return bubble;
}

function addTypingIndicator() {
  const bubble = addMessage("assistant");
  const typing = el("div", "typing");
  typing.append(el("span"), el("span"), el("span"));
  bubble.appendChild(typing);
  return bubble;
}

// Render the answer text, turning [1] style citation markers into styled chips.
function renderAnswer(bubble, text) {
  bubble.replaceChildren();
  for (const paragraph of text.split(/\n{2,}/)) {
    const p = el("p");
    const parts = paragraph.split(/(\[\d+\])/g);
    for (const part of parts) {
      if (/^\[\d+\]$/.test(part)) {
        p.appendChild(el("span", "cite", part));
      } else if (part) {
        p.appendChild(document.createTextNode(part));
      }
    }
    bubble.appendChild(p);
  }
}

function renderSources(bubble, sources) {
  if (!sources || sources.length === 0) return;
  const wrap = el("div", "sources");
  wrap.appendChild(el("div", "sources-label", "Sources"));
  sources.forEach((source, i) => {
    const node = sourceTemplate.content.firstElementChild.cloneNode(true);
    node.querySelector(".source-index").textContent = `[${i + 1}]`;
    node.querySelector(".source-title").textContent = source.title;
    node.querySelector(".source-content").textContent = source.content;
    wrap.appendChild(node);
  });
  bubble.appendChild(wrap);
}

function setBusy(busy) {
  inputEl.disabled = busy;
  sendEl.disabled = busy;
  if (!busy) inputEl.focus();
}

async function send(message) {
  addMessage("user", message);
  history.push({ role: "user", content: message });
  const pending = addTypingIndicator();
  setBusy(true);

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // Send the last few turns so follow-up questions keep their context.
      body: JSON.stringify({ message, history: history.slice(0, -1).slice(-8) }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `Request failed (${response.status})`);
    }
    const data = await response.json();
    renderAnswer(pending, data.answer);
    renderSources(pending, data.sources);
    history.push({ role: "assistant", content: data.answer });
  } catch (err) {
    pending.replaceChildren(el("p", null, `Something went wrong: ${err.message}`));
    pending.classList.add("error");
    history.pop(); // drop the failed user turn so retries start clean
  } finally {
    setBusy(false);
    scrollToBottom();
  }
}

formEl.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = inputEl.value.trim();
  if (!message || inputEl.disabled) return;
  inputEl.value = "";
  send(message);
});

// Suggestion chips fire a real question.
chatEl.addEventListener("click", (event) => {
  const chip = event.target.closest(".chip");
  if (chip && !inputEl.disabled) send(chip.textContent);
});

inputEl.focus();
