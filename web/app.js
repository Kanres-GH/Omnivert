/* ============================ helpers ============================ */
const $ = (s) => document.querySelector(s);
const PY = () => window.pywebview && window.pywebview.api;

async function api(method, ...args) {
  const a = PY();
  if (!a || !a[method]) return null;
  try { return await a[method](...args); } catch (e) { console.error(method, e); return null; }
}

const mb = (b) => (b / 1048576).toFixed(1);

const ICON = {
  folder: '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M10 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-8l-2-2Z"/></svg>',
  pause: '<svg viewBox="0 0 24 24"><rect x="6" y="5" width="4" height="14" rx="1" fill="currentColor"/><rect x="14" y="5" width="4" height="14" rx="1" fill="currentColor"/></svg>',
  play: '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M8 5v14l11-7z"/></svg>',
  x: '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M6.4 5 5 6.4 10.6 12 5 17.6 6.4 19 12 13.4 17.6 19 19 17.6 13.4 12 19 6.4 17.6 5 12 10.6 6.4 5Z"/></svg>',
};

let MODE = "video";
const cards = new Map();      // id -> { el, mode, thumbSet }
let lastProbe = null;         // { url, title, thumbnail, audio_tracks }
let probeTimer = null;
let pollTimer = null;

/* ============================ tabs ============================ */
function positionGlider() {
  const active = document.querySelector(".tab.active");
  const glider = $("#tabGlider");
  if (!active) return;
  glider.style.width = active.offsetWidth + "px";
  glider.style.transform = `translateX(${active.offsetLeft - 4}px)`;
}

function switchMode(mode) {
  if (mode === MODE) return;
  MODE = mode;
  document.body.classList.toggle("mode-video", mode === "video");
  document.body.classList.toggle("mode-audio", mode === "audio");
  document.querySelectorAll(".tab").forEach(t =>
    t.classList.toggle("active", t.dataset.mode === mode));
  positionGlider();

  const show = mode === "video" ? $("#videoOptions") : $("#audioOptions");
  const hide = mode === "video" ? $("#audioOptions") : $("#videoOptions");
  hide.classList.add("hidden");
  show.classList.remove("hidden");
  show.classList.add("swapping");
  requestAnimationFrame(() => requestAnimationFrame(() => show.classList.remove("swapping")));
}

// Tab click. Block switching to Video while an audio-only link is loaded.
async function requestSwitch(mode) {
  if (mode === MODE) return;
  if (mode === "video" && isAudioLink($("#urlInput").value)) {
    const choice = await audioWarnDialog();
    if (choice === "switch") switchMode("audio");
    else if (choice === "cancel") { $("#urlInput").value = ""; lastProbe = null; }
    return;  // abort the switch to Video
  }
  switchMode(mode);
}

/* ============================ probe on paste ============================ */
function looksLikeUrl(v) { return /^https?:\/\/|\w+\.\w/.test(v.trim()); }

// Known audio-only platforms — switch to Audio instantly, before the probe lands.
const AUDIO_DOMAINS = /(soundcloud\.com|bandcamp\.com|mixcloud\.com|audiomack\.com|spotify\.com|music\.apple\.com|deezer\.com)/i;

function scheduleProbe() {
  const url = $("#urlInput").value.trim();
  clearTimeout(probeTimer);
  if (!url || !looksLikeUrl(url)) { $("#probeSpinner").classList.remove("show"); return; }
  if (lastProbe && lastProbe.url === url) return;
  probeTimer = setTimeout(() => doProbe(url), 550);
}

async function doProbe(url) {
  $("#probeSpinner").classList.add("show");
  const res = await api("probe", url);
  $("#probeSpinner").classList.remove("show");
  if (!res || !res.ok || res.url !== $("#urlInput").value.trim()) return;
  lastProbe = res;
}

// An audio-only source: known music domain, or the probe found no video stream.
function isAudioLink(url) {
  url = (url || "").trim();
  if (!url) return false;
  if (AUDIO_DOMAINS.test(url)) return true;
  return !!(lastProbe && lastProbe.url === url && lastProbe.is_audio);
}

// Shared warning for "audio link on the Video tab". Resolves "switch" | "cancel" | false.
function audioWarnDialog() {
  return showModal({
    title: "This looks like audio",
    text: "You're using an audio-only link on the Video tab, which may give unwanted results. Switch to the Audio tab?",
    buttons: [
      { label: "Cancel", kind: "ghost", value: "cancel" },
      { label: "Switch to Audio", kind: "primary", value: "switch" },
    ],
  });
}

/* ============================ enqueue ============================ */
function newId() { return "j" + Date.now() + Math.floor(Math.random() * 1000); }

function buildJob() {
  const url = $("#urlInput").value.trim();
  if (!url) { shake($("#pasteBox")); return null; }
  const matched = lastProbe && lastProbe.url === url ? lastProbe : null;
  const id = newId();
  let opts, ext, qtag;
  if (MODE === "video") {
    opts = { quality: $("#vQuality").value, codec: $("#vCodec").value,
             container: $("#vContainer").value };
    ext = "." + opts.container;
    qtag = opts.quality === "best" ? "Best" : opts.quality + "p";
  } else {
    opts = { container: $("#aContainer").value, quality: $("#aQuality").value };
    ext = "." + opts.container;
    qtag = opts.quality + " kbps";
  }
  return {
    id, url, mode: MODE,
    title: matched ? matched.title : url,
    thumbnail: matched ? matched.thumbnail : null,
    ext, quality: qtag, opts,
  };
}

async function enqueue() {
  const url = $("#urlInput").value.trim();
  if (!url) { shake($("#pasteBox")); return; }

  // Ensure we have a valid probe for this exact URL (validates the link).
  let probe = (lastProbe && lastProbe.url === url) ? lastProbe : null;
  if (!probe) {
    $("#probeSpinner").classList.add("show");
    probe = await api("probe", url);
    $("#probeSpinner").classList.remove("show");
  }
  if (probe && probe.ok === false) {
    await alertDialog("Couldn't load that link",
      (probe.error || "Please check the link.") +
      " If the link is valid, try again — sites occasionally rate-limit.");
    return;
  }
  if (probe && probe.ok) lastProbe = probe;

  // Audio-only link on the Video tab -> warn before downloading.
  if (MODE === "video" && isAudioLink(url)) {
    const choice = await audioWarnDialog();
    if (choice === "switch") switchMode("audio");
    else if (choice === "cancel") { $("#urlInput").value = ""; lastProbe = null; }
    return;  // don't download from the Video tab
  }

  const job = buildJob();
  if (!job) return;

  addCard(job);
  api("add_job", job);
  $("#urlInput").value = "";
  lastProbe = null;
}

function addCard(job) {
  const el = document.createElement("div");
  el.className = "q-item entering";
  el.dataset.id = job.id;
  const thumb = job.thumbnail
    ? `<div class="q-thumb"><img src="${job.thumbnail}" onerror="this.remove()"></div>`
    : `<div class="q-thumb">●</div>`;
  el.innerHTML = `
    <div class="q-fill"></div>
    ${thumb}
    <div class="q-title" title="${escapeHtml(job.title)}">${escapeHtml(job.title)}</div>
    <div class="q-meta">
      <span class="q-tag">${job.quality}</span>
      <span class="q-tag">${job.ext}</span>
      <span class="q-status">Queueing</span>
    </div>
    <div class="q-actions">
      <button class="q-btn q-folder" title="Open folder">${ICON.folder}</button>
      <button class="q-btn q-pause" title="Pause">${ICON.pause}</button>
      <button class="q-btn q-x" title="Remove">${ICON.x}</button>
    </div>`;
  el.querySelector(".q-x").addEventListener("click", () => removeCard(job.id));
  el.querySelector(".q-folder").addEventListener("click", () => api("reveal", job.id));
  el.querySelector(".q-pause").addEventListener("click", () => togglePause(job.id));
  $("#queueList").appendChild(el);
  cards.set(job.id, { el, mode: job.mode, thumbSet: !!job.thumbnail, status: "queued" });
  el.addEventListener("animationend", () => el.classList.remove("entering"), { once: true });
  refreshChrome();
  startPoll();
  $("#queueList").scrollIntoView(false);
}

function removeCard(id) {
  const c = cards.get(id);
  if (!c) return;
  c.el.classList.add("leaving");
  api("remove_job", id);
  cards.delete(id);
  setTimeout(() => { c.el.remove(); refreshChrome(); }, 300);
}

function togglePause(id) {
  const c = cards.get(id);
  if (!c) return;
  if (c.status === "paused") api("resume_job", id);
  else if (c.status === "downloading" || c.status === "queued") api("pause_job", id);
}

/* ============================ polling ============================ */
function startPoll() {
  if (pollTimer) return;
  pollTimer = setInterval(tick, 300);
}
async function tick() {
  if (cards.size === 0) { clearInterval(pollTimer); pollTimer = null; return; }
  const state = await api("poll");
  if (!state) return;
  for (const [id, c] of cards) {
    const s = state[id];
    if (!s) continue;
    updateCard(c, s);
  }
}

function updateCard(c, s) {
  const el = c.el;
  const statusEl = el.querySelector(".q-status");
  const fill = el.querySelector(".q-fill");
  const titleEl = el.querySelector(".q-title");

  if (s.title && titleEl.textContent !== s.title && s.title.startsWith("http") === false) {
    titleEl.textContent = s.title; titleEl.title = s.title;
  }
  if (!c.thumbSet && s.thumbnail) {
    el.querySelector(".q-thumb").innerHTML = `<img src="${s.thumbnail}" onerror="this.remove()">`;
    c.thumbSet = true;
  }

  // Swap the pause/continue button only when the status actually changes.
  if (c.status !== s.status) {
    c.status = s.status;
    const pause = el.querySelector(".q-pause");
    if (s.status === "done" || s.status === "error") {
      pause.style.display = "none";
    } else {
      pause.style.display = "";
      const paused = s.status === "paused";
      pause.innerHTML = paused ? ICON.play : ICON.pause;
      pause.title = paused ? "Continue" : "Pause";
    }
  }

  statusEl.className = "q-status";
  if (s.status === "downloading") {
    statusEl.classList.add("active");
    if (s.total && s.downloaded) statusEl.textContent = `${mb(s.downloaded)} / ${mb(s.total)} MB`;
    else statusEl.textContent = "Downloading…";
    fill.style.width = (s.pct || 0) + "%";
    fill.style.opacity = "";
  } else if (s.status === "paused") {
    statusEl.classList.add("paused");
    statusEl.textContent = "Paused";        // keep the partial-progress bar as-is
  } else if (s.status === "done") {
    statusEl.classList.add("done");
    statusEl.textContent = "Done";
    fill.style.width = "100%";
    fill.style.opacity = ".0";
  } else if (s.status === "error") {
    statusEl.classList.add("error");
    statusEl.textContent = "Error";
    statusEl.title = s.error || "";
    fill.style.width = "0%";
    if (!c.alerted) {
      c.alerted = true;
      alertDialog("Download failed",
        s.error || "Something went wrong with this download.");
    }
  } else {
    statusEl.textContent = "Queueing";
    fill.style.width = "0%";
  }
}

/* ============================ modal (confirm / prompt / alert) ============================ */
let modalResolve = null;
function showModal({ title, text, buttons }) {
  return new Promise((resolve) => {
    modalResolve = resolve;
    $("#modalTitle").textContent = title;
    $("#modalText").textContent = text;
    const actions = $("#modalActions");
    actions.innerHTML = "";
    buttons.forEach(b => {
      const btn = document.createElement("button");
      btn.className = "btn " + (b.kind || "ghost");
      btn.textContent = b.label;
      btn.addEventListener("click", () => closeModal(b.value));
      actions.appendChild(btn);
    });
    const ov = $("#modalOverlay");
    ov.classList.add("open");
    ov.setAttribute("aria-hidden", "false");
  });
}
function closeModal(value) {
  const ov = $("#modalOverlay");
  ov.classList.remove("open");
  ov.setAttribute("aria-hidden", "true");
  if (modalResolve) { modalResolve(value); modalResolve = null; }
}
const confirmDialog = (title, text, yes = "Confirm", no = "Cancel", yesKind = "danger") =>
  showModal({ title, text, buttons: [
    { label: no, kind: "ghost", value: false },
    { label: yes, kind: yesKind, value: true }] });
const alertDialog = (title, text) =>
  showModal({ title, text, buttons: [{ label: "OK", kind: "ghost", value: true }] });

async function clearQueue() {
  if (!cards.size) return;
  const ok = await confirmDialog("Clear the queue?",
    "This removes every item, including finished and in-progress downloads.",
    "Clear", "Cancel", "danger");
  if (!ok) return;
  for (const [, c] of cards) c.el.classList.add("leaving");
  api("clear");
  const old = new Map(cards);
  cards.clear();
  setTimeout(() => { old.forEach(c => c.el.remove()); refreshChrome(); }, 300);
}

/* ============================ chrome (empty/clear) ============================ */
function refreshChrome() {
  const has = cards.size > 0;
  $("#emptyState").style.opacity = has ? "0" : "1";
  $("#clearRow").classList.toggle("show", has);
}

/* ============================ settings ============================ */
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  $("#themeSwitch").setAttribute("aria-checked", theme === "light");
}
async function loadSettings() {
  const s = await api("get_settings");
  if (!s) return;
  applyTheme(s.theme || "dark");
  $("#metaSwitch").setAttribute("aria-checked", !!s.disable_metadata);
  $("#subSelect").value = s.subtitles || "none";
  $("#outPath").value = s.out_dir || "";
  setDevMode(!!s.dev_mode);
}

/* ============================ dev mode / logs ============================ */
let logLastId = 0;
let logTimer = null;

function setDevMode(on) {
  $("#devSwitch").setAttribute("aria-checked", on);
  $("#devBtn").hidden = !on;
  if (!on) closeDevPanel();
}
function openDevPanel() {
  $("#devPanel").classList.add("open");
  $("#devPanel").setAttribute("aria-hidden", "false");
  if (!logTimer) { pumpLogs(); logTimer = setInterval(pumpLogs, 500); }
}
function closeDevPanel() {
  $("#devPanel").classList.remove("open");
  $("#devPanel").setAttribute("aria-hidden", "true");
  if (logTimer) { clearInterval(logTimer); logTimer = null; }
}
async function pumpLogs() {
  const rows = await api("get_logs", logLastId);
  if (!rows || !rows.length) return;
  const box = $("#devLog");
  const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
  for (const e of rows) {
    logLastId = Math.max(logLastId, e.id);
    const line = document.createElement("div");
    line.className = "dev-line lvl-" + (e.lvl || "info");
    line.innerHTML = `<span class="dev-time">${e.t}</span><span class="dev-msg">${escapeHtml(e.msg)}</span>`;
    box.appendChild(line);
  }
  while (box.childElementCount > 1500) box.removeChild(box.firstChild);
  if (atBottom) box.scrollTop = box.scrollHeight;
}
async function clearLogs() {
  await api("clear_logs");
  logLastId = 0;
  $("#devLog").innerHTML = "";
}
function copyLogs() {
  const txt = [...$("#devLog").children]
    .map(l => l.textContent.replace(/\s+/, " ")).join("\n");
  navigator.clipboard?.writeText(txt).catch(() => {});
}
function toggleSettings(force) {
  const open = force ?? !$("#settingsPanel").classList.contains("open");
  $("#settingsPanel").classList.toggle("open", open);
  $("#settingsPanel").setAttribute("aria-hidden", !open);
  $("#gearBtn").classList.toggle("open", open);
}

/* ============================ misc ============================ */
function shake(el) {
  el.animate([{ transform: "translateX(0)" }, { transform: "translateX(-6px)" },
    { transform: "translateX(6px)" }, { transform: "translateX(0)" }],
    { duration: 250, easing: "ease" });
}
function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, m =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
}

/* ============================ wiring ============================ */
function wireUI() {
  document.querySelectorAll(".tab").forEach(t =>
    t.addEventListener("click", () => requestSwitch(t.dataset.mode)));

  const input = $("#urlInput");
  input.addEventListener("input", scheduleProbe);
  input.addEventListener("focus", () => $("#pasteBox").classList.add("focus"));
  input.addEventListener("blur", () => $("#pasteBox").classList.remove("focus"));
  input.addEventListener("keydown", e => { if (e.key === "Enter") enqueue(); });
  $("#downloadBtn").addEventListener("click", enqueue);

  $("#clearBtn").addEventListener("click", clearQueue);
  $("#modalOverlay").addEventListener("click", e => {
    if (e.target === $("#modalOverlay")) closeModal(false);
  });

  $("#gearBtn").addEventListener("click", e => { e.stopPropagation(); toggleSettings(); });
  document.addEventListener("click", e => {
    if (!$("#settingsPanel").contains(e.target) && e.target !== $("#gearBtn"))
      toggleSettings(false);
  });
  $("#settingsPanel").addEventListener("click", e => e.stopPropagation());

  $("#themeSwitch").addEventListener("click", () => {
    const light = $("#themeSwitch").getAttribute("aria-checked") === "true";
    const theme = light ? "dark" : "light";
    applyTheme(theme);
    api("save_settings", { theme });
  });
  $("#metaSwitch").addEventListener("click", () => {
    const on = $("#metaSwitch").getAttribute("aria-checked") === "true";
    $("#metaSwitch").setAttribute("aria-checked", !on);
    api("save_settings", { disable_metadata: !on });
  });
  $("#devSwitch").addEventListener("click", () => {
    const on = $("#devSwitch").getAttribute("aria-checked") === "true";
    setDevMode(!on);
    api("save_settings", { dev_mode: !on });
  });
  $("#devBtn").addEventListener("click", () =>
    $("#devPanel").classList.contains("open") ? closeDevPanel() : openDevPanel());
  $("#devClose").addEventListener("click", closeDevPanel);
  $("#devClear").addEventListener("click", clearLogs);
  $("#devCopy").addEventListener("click", copyLogs);
  $("#subSelect").addEventListener("change", e =>
    api("save_settings", { subtitles: e.target.value }));
  $("#folderBtn").addEventListener("click", async () => {
    const path = await api("choose_folder");
    if (path) $("#outPath").value = path;
  });

  $("#webVersion").addEventListener("click", e => {
    e.preventDefault();
    alertDialog("Coming soon", "A web version of Omnivert is on the way.");
  });
  $("#feedback").addEventListener("click", e => {
    e.preventDefault();
    alertDialog("Coming soon", "Feedback will be available soon.");
  });

  window.addEventListener("resize", positionGlider);
  positionGlider();
}

function hideLoader() { const el = $("#loader"); if (el) el.classList.add("hidden"); }

const LOADER_MIN_MS = 700;             // smallest visible time, so it never just flashes
const loaderStart = Date.now();

let booted = false;
async function boot() {
  if (booted) return;
  booted = true;
  // These are real round-trips to Python. They only resolve once the WebView2
  // <-> Python bridge is actually responsive, so the loader stays up until the
  // UI is genuinely interactive (not a fixed timer that can reveal a frozen UI).
  await loadSettings();          // applies theme/folder before the UI is shown
  await api("warm_up");          // resolves when yt-dlp has finished importing
  setTimeout(hideLoader, Math.max(0, LOADER_MIN_MS - (Date.now() - loaderStart)));
}

document.addEventListener("DOMContentLoaded", () => {
  wireUI();
  if (PY()) boot();
});
window.addEventListener("pywebviewready", boot);
// Reveal anyway if pywebview is genuinely absent (e.g. opened in a plain browser).
setTimeout(() => { if (!booted && !PY()) hideLoader(); }, 2500);
// Absolute safety net so the loader can never get stuck forever.
setTimeout(() => { if (!booted) hideLoader(); }, 30000);
