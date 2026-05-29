(() => {
  const state = {
    channel: "",
    messages: [],
    selectedId: null,
    activeTab: "preview",
  };

  const els = {
    status: document.getElementById("status"),
    refresh: document.getElementById("refresh"),
    clear: document.getElementById("clear"),
    channelList: document.getElementById("channel-list"),
    messageList: document.getElementById("message-list"),
    detail: document.getElementById("detail"),
    countTotal: document.getElementById("count-total"),
  };

  const fmtTime = (epoch) => new Date(epoch * 1000).toLocaleTimeString();
  const escapeHtml = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));

  function setStatus(text, cls) {
    els.status.textContent = text;
    els.status.className = "status " + (cls || "");
  }

  function summaryText(m) {
    const s = m.summary || {};
    return s.subject || s.text || s.event || s.method || s.kind || JSON.stringify(s);
  }

  function summaryAddress(m) {
    const s = m.summary || {};
    if (s.to) return `to ${s.to}`;
    if (s.channel && m.channel === "slack") return s.channel;
    if (s.chat_id) return `chat ${s.chat_id}`;
    if (s.targets) return s.targets;
    return m.channel;
  }

  function renderList() {
    const filtered = state.channel
      ? state.messages.filter((m) => m.channel === state.channel)
      : state.messages;
    els.messageList.innerHTML = filtered
      .map(
        (m) => `
        <li data-id="${m.id}" class="${m.id === state.selectedId ? "active" : ""}">
          <div class="row1"><span class="channel">${escapeHtml(m.channel)}</span><span class="time">${fmtTime(m.received_at)}</span></div>
          <div class="summary">${escapeHtml(summaryText(m))}</div>
          <div class="preview">${escapeHtml(summaryAddress(m) + " · " + (m.preview || ""))}</div>
        </li>`
      )
      .join("") || `<li style="padding:24px;color:#8b95a3;text-align:center;">No messages</li>`;
    updateCounts();
  }

  function updateCounts() {
    els.countTotal.textContent = state.messages.length;
    const counts = {};
    for (const m of state.messages) counts[m.channel] = (counts[m.channel] || 0) + 1;
    document.querySelectorAll("#channel-list li[data-channel]").forEach((li) => {
      const ch = li.dataset.channel;
      const span = li.querySelector(".count");
      if (span && ch) span.textContent = counts[ch] || 0;
    });
  }

  function renderDetail() {
    const m = state.messages.find((x) => x.id === state.selectedId);
    if (!m) {
      els.detail.innerHTML = `<p class="empty">Select a message to view its contents.</p>`;
      return;
    }
    const summary = m.summary || {};
    const summaryRows = Object.entries(summary)
      .map(([k, v]) => `<dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v)}</dd>`)
      .join("");

    const tabs = ["preview"];
    if (m.channel === "mail" && m.body && m.body.html) tabs.push("html");
    tabs.push("body", "headers", "raw");

    const tabButtons = tabs
      .map((t) => `<button data-tab="${t}" class="${t === state.activeTab ? "active" : ""}">${t}</button>`)
      .join("");

    els.detail.innerHTML = `
      <h2>
        <span>${escapeHtml(m.channel)} · ${escapeHtml(summaryText(m))}</span>
        <button id="delete-msg" class="danger">Delete</button>
      </h2>
      <dl>
        <dt>id</dt><dd><code>${escapeHtml(m.id)}</code></dd>
        <dt>received</dt><dd>${new Date(m.received_at * 1000).toLocaleString()}</dd>
        ${summaryRows}
      </dl>
      <div class="tabs">${tabButtons}</div>
      <div id="tab-content"></div>
    `;
    renderTab(m);

    document.getElementById("delete-msg").onclick = async () => {
      await fetch(`/api/messages/${m.id}`, { method: "DELETE" });
      state.messages = state.messages.filter((x) => x.id !== m.id);
      state.selectedId = null;
      renderList();
      renderDetail();
    };
    els.detail.querySelectorAll(".tabs button").forEach((b) => {
      b.onclick = () => {
        state.activeTab = b.dataset.tab;
        renderDetail();
      };
    });
  }

  function renderTab(m) {
    const c = document.getElementById("tab-content");
    const tab = state.activeTab;
    if (tab === "preview") {
      c.innerHTML = `<pre>${escapeHtml(m.preview || "(no preview)")}</pre>`;
    } else if (tab === "html") {
      const blob = new Blob([m.body.html], { type: "text/html" });
      const url = URL.createObjectURL(blob);
      c.innerHTML = `<iframe sandbox src="${url}"></iframe>`;
    } else if (tab === "headers") {
      c.innerHTML = `<pre>${escapeHtml(JSON.stringify(m.headers || {}, null, 2))}</pre>`;
    } else if (tab === "raw" && m.channel === "mail") {
      c.innerHTML = `<pre>${escapeHtml((m.body && m.body.raw) || "")}</pre>`;
    } else {
      c.innerHTML = `<pre>${escapeHtml(JSON.stringify(m.body, null, 2))}</pre>`;
    }
  }

  async function loadMessages() {
    const url = "/api/messages?limit=500" + (state.channel ? `&channel=${state.channel}` : "");
    const res = await fetch(url);
    const data = await res.json();
    state.messages = data.messages;
    renderList();
    renderDetail();
  }

  async function clearAll() {
    if (!confirm("Clear all captured messages?")) return;
    await fetch("/api/messages", { method: "DELETE" });
    state.messages = [];
    state.selectedId = null;
    renderList();
    renderDetail();
  }

  function selectChannel(ch) {
    state.channel = ch;
    document.querySelectorAll("#channel-list li").forEach((li) => {
      li.classList.toggle("active", li.dataset.channel === ch);
    });
    renderList();
  }

  function connectStream() {
    const es = new EventSource("/api/stream");
    es.onopen = () => setStatus("live", "connected");
    es.onerror = () => {
      setStatus("disconnected", "disconnected");
      es.close();
      setTimeout(connectStream, 2000);
    };
    es.addEventListener("message", (e) => {
      const m = JSON.parse(e.data);
      state.messages.unshift(m);
      if (state.messages.length > 1000) state.messages.pop();
      renderList();
    });
  }

  els.refresh.onclick = loadMessages;
  els.clear.onclick = clearAll;
  els.channelList.addEventListener("click", (e) => {
    const li = e.target.closest("li");
    if (li) selectChannel(li.dataset.channel || "");
  });
  els.messageList.addEventListener("click", (e) => {
    const li = e.target.closest("li[data-id]");
    if (li) {
      state.selectedId = li.dataset.id;
      state.activeTab = "preview";
      renderList();
      renderDetail();
    }
  });

  loadMessages();
  connectStream();
})();
