(() => {
  const state = {
    channel: "",
    messages: [],
    selectedId: null,
    activeTab: "preview",
    replyChannels: new Set(),
  };

  const isInbound = (m) => m.extra && m.extra.direction === "inbound";

  const els = {
    status: document.getElementById("status"),
    refresh: document.getElementById("refresh"),
    clear: document.getElementById("clear"),
    settingsBtn: document.getElementById("settings-btn"),
    settings: document.getElementById("settings"),
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
          <div class="row1"><span class="channel">${escapeHtml(m.channel)}${isInbound(m) ? ' <span class="badge">inbound</span>' : ""}</span><span class="time">${fmtTime(m.received_at)}</span></div>
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
      ${replyBox(m)}
    `;
    renderTab(m);
    wireReply(m);

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

  function replyBox(m) {
    if (isInbound(m) || !state.replyChannels.has(m.channel)) return "";
    return `
      <div class="reply">
        <h3>Simulate a user reply</h3>
        <p class="reply-hint">Delivers an inbound ${escapeHtml(m.channel)} event to your app, as if the recipient replied.</p>
        <textarea id="reply-text" placeholder="Type the reply the user would send back…"></textarea>
        <div class="reply-actions">
          <button id="send-reply">Send reply to app</button>
          <span id="reply-status" class="reply-status"></span>
        </div>
      </div>`;
  }

  function wireReply(m) {
    const btn = document.getElementById("send-reply");
    if (!btn) return;
    const textEl = document.getElementById("reply-text");
    const statusEl = document.getElementById("reply-status");
    btn.onclick = async () => {
      const text = (textEl.value || "").trim();
      if (!text) { textEl.focus(); return; }
      btn.disabled = true;
      statusEl.textContent = "sending…";
      statusEl.className = "reply-status";
      try {
        const res = await fetch(`/api/messages/${m.id}/reply`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        });
        const data = await res.json();
        if (!res.ok) {
          statusEl.textContent = data.error || `error ${res.status}`;
          statusEl.className = "reply-status err";
        } else {
          statusEl.textContent = `delivered → app responded ${data.app_status}`;
          statusEl.className = "reply-status ok";
          textEl.value = "";
        }
      } catch (e) {
        statusEl.textContent = String(e);
        statusEl.className = "reply-status err";
      } finally {
        btn.disabled = false;
      }
    };
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

  async function loadChannels() {
    try {
      const res = await fetch("/api/channels");
      const data = await res.json();
      state.replyChannels = new Set(
        (data.channels || []).filter((c) => c.reply).map((c) => c.name)
      );
    } catch {
      /* capabilities are best-effort; reply box just won't show */
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

  function toggleSettings(open) {
    els.settings.classList.toggle("hidden", !open);
    if (open) loadSettingsForms();
  }

  function settingField(s) {
    const id = "set-" + s.key;
    const note = s.locked
      ? `<span class="setting-note locked">set via env var</span>`
      : s.source === "runtime"
      ? `<span class="setting-note ok">set here</span>`
      : "";
    let placeholder = "";
    if (s.secret) {
      placeholder = s.set ? "•••••••• (set — leave blank to keep)" : "not set";
    } else if (!s.value && !s.locked) {
      placeholder = "not set";
    }
    return `
      <div class="setting-field">
        <label for="${id}">${escapeHtml(s.label)} ${note}</label>
        <input id="${id}" type="${s.secret ? "password" : "text"}"
               data-key="${escapeHtml(s.key)}" data-secret="${s.secret ? "1" : ""}"
               value="${escapeHtml(s.secret ? "" : s.value)}"
               placeholder="${escapeHtml(placeholder)}"
               ${s.locked ? "disabled" : ""} autocomplete="off" />
        ${s.help ? `<p class="setting-help">${escapeHtml(s.help)}</p>` : ""}
      </div>`;
  }

  function renderSettingsForm(container, channelSettings) {
    const allLocked = channelSettings.every((s) => s.locked);
    container.innerHTML = `
      ${channelSettings.map(settingField).join("")}
      <div class="setting-actions">
        <button class="setting-save"${allLocked ? " disabled" : ""}>Save</button>
        <span class="setting-status"></span>
      </div>`;
    const btn = container.querySelector(".setting-save");
    const statusEl = container.querySelector(".setting-status");
    if (!btn) return;
    btn.onclick = async () => {
      const updates = {};
      container.querySelectorAll("input[data-key]").forEach((inp) => {
        if (inp.disabled) return;
        const secret = inp.dataset.secret === "1";
        const val = inp.value;
        // Secrets left blank mean "keep current"; everything else is sent verbatim.
        if (secret && val === "") return;
        updates[inp.dataset.key] = val;
      });
      if (!Object.keys(updates).length) {
        statusEl.textContent = "nothing to save";
        statusEl.className = "setting-status";
        return;
      }
      btn.disabled = true;
      statusEl.textContent = "saving…";
      statusEl.className = "setting-status";
      try {
        const res = await fetch("/api/settings", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(updates),
        });
        const data = await res.json();
        if (!res.ok) {
          statusEl.textContent = (data.rejected || []).map((r) => `${r.key}: ${r.reason}`).join("; ") || `error ${res.status}`;
          statusEl.className = "setting-status err";
        } else {
          statusEl.textContent = "saved";
          statusEl.className = "setting-status ok";
          await loadSettingsForms(); // reflect new source/locked state
          await loadChannels(); // a newly-configured channel may now reply
        }
      } catch (e) {
        statusEl.textContent = String(e);
        statusEl.className = "setting-status err";
      } finally {
        btn.disabled = false;
      }
    };
  }

  async function loadSettingsForms() {
    const containers = document.querySelectorAll(".setup-settings[data-settings-for]");
    if (!containers.length) return;
    try {
      const res = await fetch("/api/settings");
      const data = await res.json();
      const byChannel = {};
      for (const c of data.channels || []) byChannel[c.name] = c.settings;
      containers.forEach((el) => {
        const settings = byChannel[el.dataset.settingsFor];
        if (settings) renderSettingsForm(el, settings);
        else el.innerHTML = "";
      });
    } catch {
      containers.forEach((el) => {
        el.innerHTML = `<p class="setup-desc">Couldn't load settings.</p>`;
      });
    }
  }

  els.refresh.onclick = loadMessages;
  els.clear.onclick = clearAll;
  els.settingsBtn.onclick = () => toggleSettings(true);
  els.settings.addEventListener("click", (e) => {
    if (e.target.hasAttribute("data-close")) toggleSettings(false);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !els.settings.classList.contains("hidden")) toggleSettings(false);
  });
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

  loadChannels().then(loadMessages);
  connectStream();
})();
