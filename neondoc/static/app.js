/* NEON.DOC — фронтенд без сборки: чистый JS, хэш-роутер, API на /api */
"use strict";

// ================================================================= helpers
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const view = $("#view");

async function api(method, url, body, isForm) {
  const opt = { method, headers: {} };
  if (body !== undefined) {
    if (isForm) opt.body = body;
    else { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  }
  const r = await fetch(url, opt);
  const ct = r.headers.get("content-type") || "";
  const data = ct.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new Error((data && data.detail) || r.statusText);
  return data;
}
const GET = (u) => api("GET", u), PUT = (u, b) => api("PUT", u, b), POST = (u, b) => api("POST", u, b), DEL = (u) => api("DELETE", u);

function toast(msg, err) {
  const t = document.createElement("div");
  t.className = "toast" + (err ? " err" : "");
  t.textContent = msg;
  $("#toasts").append(t);
  setTimeout(() => t.remove(), err ? 7000 : 3500);
}
const fail = (e) => toast(e.message || String(e), true);

function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}
function autosize(ta) {
  ta.style.height = "auto";
  ta.style.height = ta.scrollHeight + 4 + "px";
}
function autosizeAll(root) { $$("textarea.auto", root).forEach(autosize); }
document.addEventListener("input", (e) => { if (e.target.matches("textarea.auto")) autosize(e.target); });

function fmtMin(m) {
  if (m == null) return "—";
  if (m < 60) return Math.round(m) + " мин";
  return (m / 60).toFixed(1).replace(".", ",") + " ч";
}
function pickFiles(accept, multiple = true) {
  return new Promise((res) => {
    const i = document.createElement("input");
    i.type = "file"; i.accept = accept || ""; i.multiple = multiple;
    i.onchange = () => res([...i.files]);
    i.click();
  });
}

// ================================================================= health LEDs
let HEALTH = null;
async function pollHealth() {
  try {
    HEALTH = await GET("/api/health");
    setLed("ollama", HEALTH.ollama ? "ok" : "bad");
    setLed("model", HEALTH.model_ok ? "ok" : HEALTH.ollama ? "warn" : "bad", (HEALTH.model || "MODEL").toUpperCase());
    const v = HEALTH.voice || {};
    setLed("whisper", v.state === "ready" ? "ok" : v.state === "error" ? "bad" : v.whisper_installed ? "warn" : "bad");
    setLed("mic", v.mic ? (v.recording ? "bad" : "ok") : "bad");
  } catch {
    ["ollama", "model", "whisper", "mic"].forEach((k) => setLed(k, "bad"));
  }
}
function setLed(k, cls, label) {
  const el = $(`[data-led="${k}"]`);
  el.className = "led " + cls;
  if (label) $("span", el).textContent = label;
}
setInterval(pollHealth, 6000);

// ================================================================= job console
const CON = { job: null, since: 0, timer: null, onDone: [] };
const conEl = $("#console"), logEl = $("#jobLog");
$(".console-bar").addEventListener("click", (e) => { if (!e.target.closest("button") || e.target.id === "consoleToggle") toggleConsole(); });
$("#jobStop").addEventListener("click", async (e) => { e.stopPropagation(); await POST("/api/jobs/stop").catch(fail); });
function toggleConsole(force) {
  const open = force ?? !conEl.classList.contains("open");
  conEl.classList.toggle("open", open);
  $("#consoleToggle").textContent = open ? "▼" : "▲";
}
function logLine(text) {
  const span = document.createElement("span");
  if (/ОШИБКА|ошибки:|СТОП|НЕ ИСПРАВЛЕНО/.test(text)) span.className = "e";
  else if (/— OK|Готово|сохранено/.test(text)) span.className = "ok";
  else if (/•|уточнить/.test(text)) span.className = "w";
  span.textContent = text + "\n";
  logEl.append(span);
  logEl.scrollTop = logEl.scrollHeight;
}
function watchJob(job, onDone) {
  if (onDone) CON.onDone.push(onDone);
  if (CON.job && CON.job.id === job.id && CON.timer) return;
  CON.job = job; CON.since = 0; logEl.textContent = "";
  $("#jobTitle").textContent = job.title;
  conEl.classList.add("busy"); conEl.classList.remove("err");
  toggleConsole(true);
  clearInterval(CON.timer);
  CON.timer = setInterval(tickJob, 700);
  tickJob();
}
async function tickJob() {
  if (!CON.job) return;
  let j;
  try { j = await GET(`/api/jobs/${CON.job.id}?since=${CON.since}`); } catch { return; }
  j.lines.forEach(logLine);
  CON.since = j.total_lines;
  const s = Math.floor(j.elapsed);
  $("#jobTime").textContent = String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
  if (j.status !== "running") {
    clearInterval(CON.timer); CON.timer = null;
    conEl.classList.remove("busy");
    if (j.status !== "done") conEl.classList.add("err");
    $("#jobTitle").textContent = `${j.title} — ${j.status === "done" ? "готово" : j.status === "stopped" ? "остановлено" : "ошибка"}`;
    const cbs = CON.onDone; CON.onDone = [];
    cbs.forEach((cb) => cb(j));
    if (j.status === "error") toast(j.error || "Ошибка", true);
  }
}
async function resumeJob() {
  const j = await GET("/api/jobs/current").catch(() => null);
  if (j && j.status === "running") watchJob(j, () => route());
}
const jobRunning = () => conEl.classList.contains("busy");

// ================================================================= mic
let MIC = null;
function micButton(getTarget, label = "ГОЛОС") {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "mic";
  b.innerHTML = `<span class="dot"></span><span class="l">${label}</span><span class="lvl"><i></i></span>`;
  b.addEventListener("click", async () => {
    if (b.classList.contains("busy")) return;
    if (MIC && MIC.btn !== b) return toast("Сначала останови другую запись", true);
    if (!MIC) {
      try { await POST("/api/voice/start"); } catch (e) { return fail(e); }
      MIC = { btn: b, timer: setInterval(async () => {
        const v = await GET("/api/voice/level").catch(() => null);
        if (v) { $(".lvl i", b).style.width = Math.round(v.level * 100) + "%"; $(".l", b).textContent = "REC " + v.seconds.toFixed(0) + "с"; }
      }, 160) };
      b.classList.add("rec");
    } else {
      clearInterval(MIC.timer); MIC = null;
      b.classList.remove("rec"); b.classList.add("busy");
      $(".l", b).innerHTML = `<span class="spin">◐</span> WHISPER`;
      try {
        const r = await POST("/api/voice/stop");
        const ta = getTarget();
        if (ta && r.text) {
          const pos = ta.selectionStart ?? ta.value.length;
          const before = ta.value.slice(0, pos), after = ta.value.slice(pos);
          const sep = before && !/\s$/.test(before) ? " " : "";
          ta.value = before + sep + r.text + after;
          ta.dispatchEvent(new Event("input", { bubbles: true }));
          ta.focus();
        }
        toast(`Расшифровано за ${r.seconds} с (${r.device})`);
      } catch (e) { fail(e); }
      b.classList.remove("busy");
      $(".l", b).textContent = label;
      pollHealth();
    }
  });
  return b;
}

// ================================================================= router
const routes = [
  [/^#\/gallery$/, () => viewGallery()], [/^#\/works$/, () => viewWorks()], [/^#\/work\/([^/]+)(?:\/(\w+))?$/, (a, b) => viewWork(a, b)],
  [/^#\/chat(?:\/(.+))?$/, (a) => viewChat(a)], [/^#\/template\/([^/]+)$/, (a) => viewTemplateEditor(a)], [/^#\/settings(?:\/(\w+))?$/, (a) => viewSettings(a)],
  [/^#\/files(?:\/(.*))?$/, (a) => viewFiles(a ? decodeURIComponent(a) : "")], [/^#\/transcribe(?:\/([^/]+))?$/, (a) => viewTranscribe(a)],
  [/^#\/annot$/, () => ANNOT.view()],
];
async function route() {
  const h = location.hash || "#/gallery";
  $("#modal").classList.remove("open");
  document.body.dataset.view = (h.match(/^#\/(\w+)/) || [])[1] || "";
  $$(".nav a").forEach((a) => a.classList.toggle("on", h.startsWith(a.getAttribute("href")) ||
    (a.dataset.nav === "works" && (h.startsWith("#/work/") || h.startsWith("#/wdoc/"))) ||
    (a.dataset.nav === "gallery" && (h.startsWith("#/template/") || h.startsWith("#/wgallery")))));
  for (const [re, fn] of routes) {
    const m = h.match(re);
    if (m) {
      try { await fn(...m.slice(1)); } catch (e) { fail(e); }
      view.scrollTop = 0;
      return;
    }
  }
  location.hash = "#/gallery";
}
window.addEventListener("hashchange", route);

// ================================================================= preview viewer (колесо листает страницы)
function viewerHTML(previews, label) {
  if (!previews.length) return `<div class="tview"><div class="empty">НЕТ ПРЕВЬЮ<br>добавь картинки в редакторе шаблона</div></div>`;
  return `<div class="tview" data-i="0">
    ${previews.map((p, i) => `<img src="${p}" class="${i ? "" : "on"}" alt="${esc(label)} — стр. ${i + 1}" loading="lazy">`).join("")}
    <span class="pager">01/${String(previews.length).padStart(2, "0")}</span>
    <span class="wheel-hint">⟲ КОЛЕСО — ЛИСТАТЬ</span>
    <div class="dots">${previews.map((_, i) => `<i class="${i ? "" : "on"}"></i>`).join("")}</div></div>`;
}
function bindViewer(tv, onChange) {
  if (!tv || !$("img", tv)) return;
  let last = 0;
  const imgs = $$("img", tv), dots = $$(".dots i", tv), pager = $(".pager", tv);
  const set = (i) => {
    i = (i + imgs.length) % imgs.length;
    tv.dataset.i = i;
    imgs.forEach((im, k) => im.classList.toggle("on", k === i));
    dots.forEach((d, k) => d.classList.toggle("on", k === i));
    pager.textContent = String(i + 1).padStart(2, "0") + "/" + String(imgs.length).padStart(2, "0");
    onChange && onChange(i);
  };
  tv.addEventListener("wheel", (e) => {
    e.preventDefault();
    const now = Date.now();
    if (now - last < 110) return;
    last = now;
    set(+tv.dataset.i + (e.deltaY > 0 ? 1 : -1));
  }, { passive: false });
  tv.setPage = set;
}

// ================================================================= GALLERY
let GAL_FILTER = { q: "", cat: "" };
async function viewGallery() {
  const list = await GET("/api/templates");
  const cats = [...new Set(list.map((t) => t.category).filter(Boolean))];
  view.innerHTML = `
    <div class="page-head">
      <h1 class="h1">Шаблоны<small>Наведи на карточку и крути колесо — листаются страницы</small></h1>
      <span class="grow"></span>
      <button class="btn cyan" id="newTpl">+ Новый шаблон</button>
    </div>
    <div class="filters">
      <input id="q" placeholder="Поиск: название, тег, дисциплина…" value="${esc(GAL_FILTER.q)}">
      <div class="chips">${["", ...cats].map((c) => `<span class="chip click ${GAL_FILTER.cat === c ? "on" : ""}" data-cat="${esc(c)}">${c || "Все"}</span>`).join("")}</div>
    </div>
    <div class="gallery" id="gal"></div>`;
  const draw = () => {
    const q = GAL_FILTER.q.toLowerCase();
    const items = list.filter((t) => (!GAL_FILTER.cat || t.category === GAL_FILTER.cat) &&
      (!q || [t.name, t.description, t.meta.discipline, ...(t.tags || [])].join(" ").toLowerCase().includes(q)));
    $("#gal").innerHTML = items.map((t) => `
      <article class="tcard" data-slug="${t.slug}">
        ${viewerHTML(t.previews, t.name)}
        <div class="tbody">
          <div class="tname">${esc(t.name)}</div>
          <div class="tdesc">${esc(t.description)}</div>
          <div class="tmeta"><span class="badge b-text">${esc(t.category)}</span>
            ${(t.tags || []).slice(0, 3).map((x) => `<span class="chip">${esc(x)}</span>`).join("")}
            <span class="grow"></span><span class="vt muted">${t.works} раб.</span></div>
        </div>
      </article>`).join("") + `<button class="tnew" id="newTpl2">+<br>НОВЫЙ<br>ШАБЛОН</button>`;
    $$(".tcard").forEach((c) => {
      bindViewer($(".tview", c));
      c.addEventListener("click", () => openTemplate(list.find((t) => t.slug === c.dataset.slug)));
    });
    $("#newTpl2").onclick = () => (location.hash = "#/template/new");
  };
  draw();
  $("#q").addEventListener("input", (e) => { GAL_FILTER.q = e.target.value; draw(); });
  $$(".filters .chip").forEach((c) => c.addEventListener("click", () => { GAL_FILTER.cat = c.dataset.cat; viewGallery(); }));
  $("#newTpl").onclick = () => (location.hash = "#/template/new");
}

function openTemplate(t) {
  const m = $("#modal");
  const meta = t.meta || {};
  m.innerHTML = `<div class="modal">
    ${viewerHTML(t.previews, t.name)}
    <div class="modal-body">
      <div style="display:flex;gap:12px;align-items:flex-start">
        <div class="grow"><h2 class="h1" style="font-size:16px">${esc(t.name)}</h2>
          <p class="muted read">${esc(t.description)}</p></div>
        <button class="btn ghost tiny" id="mClose">✕</button>
      </div>
      <div class="thumbs">${t.previews.map((p, i) => `<img src="${p}" data-i="${i}" class="${i ? "" : "on"}">`).join("")}</div>
      <div class="kv">
        <b>Тип работы</b><span>${esc(meta.work_type)}</span>
        <b>Дисциплина</b><span>${esc(meta.discipline || "—")}${meta.module ? ", " + esc(meta.module) : ""}</span>
        <b>Структура</b><span>${[meta.toc && "содержание", meta.intro ? "введение" : "«Цель работы» в 1-м разделе",
          meta.conclusion && meta.conclusion.toLowerCase(), meta.h1_new_page && "разделы с новой страницы"].filter(Boolean).join(", ")}</span>
        <b>Разделы</b><span>${t.fixed_sections.length ? t.fixed_sections.map((s) => esc(s.title)).join(" → ") : "план составляет модель"}</span>
        <b>Участники</b><span>${t.roles.length ? t.roles.map(esc).join(", ") : "—"}</span>
      </div>
      <label class="f">НАЗВАНИЕ НОВОЙ РАБОТЫ<input id="mTitle" placeholder="например: ЛР №6 — EPC барбершопа"></label>
      <div style="display:flex;gap:12px;flex-wrap:wrap">
        <button class="btn big" id="mNew">▶ Новая работа</button>
        <button class="btn ghost" id="mEdit">✎ Редактировать шаблон</button>
      </div>
    </div></div>`;
  m.classList.add("open");
  const tv = $(".tview", m);
  bindViewer(tv, (i) => $$(".thumbs img", m).forEach((x, k) => x.classList.toggle("on", k === i)));
  $$(".thumbs img", m).forEach((im) => im.addEventListener("click", () => tv.setPage && tv.setPage(+im.dataset.i)));
  $("#mClose").onclick = () => m.classList.remove("open");
  m.onclick = (e) => { if (e.target === m) m.classList.remove("open"); };
  $("#mEdit").onclick = () => (location.hash = "#/template/" + t.slug);
  $("#mNew").onclick = async () => {
    try {
      const w = await POST("/api/works", { template: t.slug, title: $("#mTitle").value.trim() });
      location.hash = "#/work/" + w.id;
    } catch (e) { fail(e); }
  };
  $("#mTitle").focus();
}

// ================================================================= WORKS
async function viewWorks() {
  const [list, M, tpls] = await Promise.all([GET("/api/works"), GET("/api/metrics"), GET("/api/templates")]);
  const tname = Object.fromEntries(tpls.map((t) => [t.slug, t.name]));
  const maxBar = Math.max(M.manual_total || 0, M.after_total || 0, 1);
  view.innerHTML = `
    <div class="page-head"><h1 class="h1">Работы<small>История и цифры для кейса «до / после»</small></h1></div>
    <div class="tiles">
      <div class="tile" style="--c:var(--pink)"><b>${M.works}</b><span>работ</span></div>
      <div class="tile" style="--c:var(--green)"><b>${M.done}</b><span>собрано .docx</span></div>
      <div class="tile" style="--c:var(--cyan)"><b>${fmtMin(M.model_minutes)}</b><span>работы модели</span></div>
      <div class="tile" style="--c:var(--yellow)"><b>${M.first_try_rate ?? "—"}${M.first_try_rate != null ? "%" : ""}</b><span>с первой попытки</span></div>
      <div class="tile" style="--c:var(--orange)"><b>${M.todo_total}</b><span>[уточнить] в текстах</span></div>
      <div class="tile" style="--c:var(--violet)"><b>${M.saved_minutes != null ? fmtMin(M.saved_minutes) : "—"}</b><span>сэкономлено</span></div>
    </div>
    ${M.paired ? `<div class="card glow"><div class="h2">До / после · ${M.paired} работ с замером</div>
      <div class="compare">
        <div class="bar"><span>Вручную</span><i style="width:${(100 * M.manual_total) / maxBar}%"></i><span>${fmtMin(M.manual_total)}</span></div>
        <div class="bar after"><span>NEON.DOC</span><i style="width:${(100 * M.after_total) / maxBar}%"></i><span>${fmtMin(M.after_total)}</span></div>
      </div><p class="hint">«После» = время модели + твоё время на проверку и правки (вводится на шаге «Готово»).</p></div>`
      : `<div class="card"><p class="hint" style="margin:0">Чтобы появилось сравнение «до / после», на шаге «Готово» каждой работы укажи, сколько она заняла бы вручную и сколько ушло на проверку.</p></div>`}
    <div style="height:22px"></div>
    <div class="rows">${list.length ? list.map((w) => {
      const st = w.has_docx ? "done" : w.stats.calls ? "text" : "brief";
      const lbl = { done: "готово", text: "в работе", brief: "черновик" }[st];
      return `<div class="row" data-id="${w.id}">
        <div><div class="t">${esc(w.title)}</div><div class="s">${esc(tname[w.template] || w.template)}</div></div>
        <div class="s">${esc(w.created)}</div>
        <div><span class="badge b-${st}">${lbl}</span></div>
        <div class="m">${w.stats.model_seconds ? Math.round(w.stats.model_seconds) + " с · " + w.stats.calls + " выз." : "—"}</div>
        <div class="m">${w.stats.todo ? w.stats.todo + " ?" : ""}</div>
        <button class="btn danger ghost tiny" data-del="${w.id}">✕</button></div>`;
    }).join("") : `<div class="empty-state"><div class="big">ПУСТО</div><p>Выбери шаблон в галерее и создай первую работу</p>
      <a class="btn" href="#/gallery">◆ К шаблонам</a></div>`}</div>`;
  $$(".row").forEach((r) => r.addEventListener("click", (e) => {
    if (e.target.dataset.del) return;
    location.hash = "#/work/" + r.dataset.id;
  }));
  $$("[data-del]").forEach((b) => b.addEventListener("click", async (e) => {
    e.stopPropagation();
    if (!confirm("Удалить работу со всеми файлами?")) return;
    await DEL("/api/works/" + b.dataset.del).catch(fail);
    viewWorks();
  }));
}

// ================================================================= WORK
const STEPS = [["brief", "Задание"], ["plan", "План"], ["text", "Текст"], ["done", "Готово"]];
let W = null;   // текущая работа

async function viewWork(id, step) {
  W = await GET("/api/works/" + id);
  const T = await GET("/api/templates/" + W.template).catch(() => null);
  W._tpl = T;
  const reach = { brief: true, plan: !!W.outline, text: !!W.report, done: !!W.docx };
  step = step && reach[step] ? step : W.stage;
  const order = STEPS.map((s) => s[0]);
  view.innerHTML = `
    <div class="page-head">
      <h1 class="h1 work-title"><span id="wTitle">${esc(W.title)}</span><small>${esc(T ? T.name : W.template)} · ${esc(W.created)}</small></h1>
      <span class="grow"></span>
      <button class="btn ghost tiny" id="openFolder">▣ ПАПКА</button>
      <a class="btn ghost tiny" href="#/chat/new?work=${W.id}" id="askChat">✦ ОБСУДИТЬ С QWEN</a>
    </div>
    <div class="stepper">${STEPS.map(([k, l], i) => `<div class="step ${k === step ? "on" : ""} ${reach[k] ? "reach" : "lock"}
      ${order.indexOf(k) < order.indexOf(W.stage) || (k === "done" && W.docx) ? "done" : ""}" data-step="${k}"><b>${i + 1}</b>${l}</div>`).join("")}</div>
    <div class="work"><div id="stepBody"></div><aside class="rail" id="rail"></aside></div>`;
  $$(".step.reach").forEach((s) => s.addEventListener("click", () => (location.hash = `#/work/${W.id}/${s.dataset.step}`)));
  $("#openFolder").onclick = () => POST(`/api/works/${W.id}/open?what=folder`).catch(fail);
  $("#askChat").onclick = (e) => { e.preventDefault(); newChat(W.id); };
  renderRail();
  ({ brief: stepBrief, plan: stepPlan, text: stepText, done: stepDone })[step]();
}

function renderRail() {
  const s = W.stats;
  $("#rail").innerHTML = `
    <div class="card"><div class="h2">Статистика</div>
      <div class="stat"><span>Время модели</span><b>${s.model_seconds ? Math.round(s.model_seconds) + " с" : "—"}</b></div>
      <div class="stat"><span>Вызовов модели</span><b>${s.calls || "—"}</b></div>
      <div class="stat"><span>С первой попытки</span><b>${s.steps ? s.first_try + "/" + s.steps : "—"}</b></div>
      <div class="stat"><span>Токенов написано</span><b>${s.tokens_out || "—"}</b></div>
      <div class="stat"><span>[уточнить]</span><b style="color:${s.todo ? "var(--yellow)" : ""}">${s.todo}</b></div>
    </div>
    ${W.review.length ? `<div class="card review"><div class="h2" style="color:var(--yellow)">Проверь руками</div>
      <ul style="margin:0;padding-left:18px">${W.review.slice(0, 12).map((r) => `<li>${esc(r)}</li>`).join("")}</ul></div>` : ""}
    ${W.docx ? `<div class="card"><div class="h2">Документ</div><p class="vt" style="margin:0 0 12px;word-break:break-all">${esc(W.docx)}</p>
      <button class="btn" id="railOpen">▶ ОТКРЫТЬ В WORD</button></div>` : ""}`;
  const ro = $("#railOpen");
  if (ro) ro.onclick = () => POST(`/api/works/${W.id}/open`).catch(fail);
}

const saveWork = debounce(async (patch) => {
  try { const w = await PUT("/api/works/" + W.id, patch); Object.assign(W, { attachments: w.attachments, figures: w.figures }); }
  catch (e) { fail(e); }
}, 500);

function collectBrief() {
  const m = { ...W.meta };
  $$("[data-meta]").forEach((el) => {
    const k = el.dataset.meta;
    if (el.type === "checkbox") m[k] = el.checked;
    else if (k === "semester" || k === "year") m[k] = parseInt(el.value || "0", 10) || m[k];
    else if (k === "conclusion") m[k] = el.value || null;
    else if (k === "module") m[k] = el.value.trim() || null;
    else m[k] = el.value;
  });
  return {
    title: $("#fTitle").value.trim() || W.title,
    meta: m,
    roles: W.roles,
    brief: { task: $("#bTask").value, data: $("#bData").value, decisions: $("#bDec").value },
    sources: $("#bSrc").value,
  };
}

function stepBrief() {
  const m = W.meta, T = W._tpl || { fixed_sections: [] };
  const tf = (k, label, ph = "", cls = "") => `<label class="f ${cls}">${label}<input data-meta="${k}" value="${esc(m[k] ?? "")}" placeholder="${esc(ph)}"></label>`;
  $("#stepBody").innerHTML = `
    <div class="card"><div class="card-head"><div class="h2">Титул</div><span class="grow"></span>
      <span class="hint">поля титульного листа — модель их не трогает</span></div>
      <div class="grid g4">
        <label class="f span2">НАЗВАНИЕ РАБОТЫ (для себя)<input id="fTitle" value="${esc(W.title)}"></label>
        <label class="f">ТИП<select data-meta="work_type">${["Лабораторная работа", "Практическая работа", "Реферат", "Курсовая работа"]
          .map((x) => `<option ${m.work_type === x ? "selected" : ""}>${x}</option>`).join("")}</select></label>
        ${tf("number", "№", "4-5")}
        ${tf("topic", "ТЕМА", "", "span4")}
        ${tf("discipline", "ДИСЦИПЛИНА", "ТИПУП", "span2")}
        ${tf("module", "МОДУЛЬ", "модуль «…» (можно пусто)", "span2")}
        ${tf("teacher", "ПРЕПОДАВАТЕЛЬ")}${tf("date", "ДАТА СДАЧИ")}${tf("semester", "СЕМЕСТР")}${tf("year", "ГОД")}
        ${tf("file_code", "КОД В ИМЕНИ ФАЙЛА", "TIPUP")}${tf("file_prefix", "ПРЕФИКС ФАЙЛА", "Ivanov_GROUP_00_0", "span3")}
        <div class="span4 chips" style="gap:22px">
          <label class="check"><input type="checkbox" data-meta="toc" ${m.toc ? "checked" : ""}><b></b>Содержание</label>
          <label class="check"><input type="checkbox" data-meta="intro" ${m.intro ? "checked" : ""}><b></b>Введение</label>
          <label class="check"><input type="checkbox" data-meta="h1_new_page" ${m.h1_new_page ? "checked" : ""}><b></b>Разделы с новой страницы</label>
          <label class="f" style="flex-direction:row;align-items:center">ИТОГ:&nbsp;<select data-meta="conclusion" style="width:auto">
            ${["ВЫВОДЫ", "ЗАКЛЮЧЕНИЕ", ""].map((x) => `<option value="${x}" ${(m.conclusion || "") === x ? "selected" : ""}>${x || "нет"}</option>`).join("")}</select></label>
        </div>
      </div></div>

    <div class="card"><div class="card-head"><div class="h2">Участники</div><span class="grow"></span>
      <span class="hint">валидатор не пропустит в таблицах исполнителей не из списка</span></div>
      <div class="chips" id="roles"></div></div>

    ${[["bTask", "Задание", "task", "Текст задания из методички: что нужно сделать, структура отчёта…"],
       ["bData", "Исходные данные", "data", "Факты о предприятии, процессе, системах, участниках. Модель берёт факты только отсюда."],
       ["bDec", "Мои решения", "decisions", "Твоя логика: разбиение процессов, выбранные варианты, что важно подчеркнуть."]]
      .map(([id, title, key, ph]) => `<div class="card"><div class="field-head"><div class="h2">${title}</div>
        <span class="hint" id="${id}N"></span><span data-mic="${id}"></span></div>
        <textarea id="${id}" class="read auto" rows="5" placeholder="${esc(ph)}">${esc(W.brief[key] || "")}</textarea></div>`).join("")}

    <div class="card"><div class="card-head"><div class="h2">Вложения</div><span class="grow"></span>
      <span class="hint">.docx .pdf .txt .md, аудио (.mp3 .wav .m4a) — расшифрует Whisper</span></div>
      <div class="drop" id="dropA">⇪ Перетащи файлы сюда или нажми, чтобы выбрать</div>
      <div class="files" id="attList"></div></div>

    <div class="card"><div class="card-head"><div class="h2">Рисунки</div><span class="grow"></span>
      <span class="hint">PNG из draw.io; id = имя, на которое сошлётся текст</span></div>
      <div style="display:flex;gap:10px"><input id="figId" placeholder="id рисунка, например epc_main" style="max-width:280px">
        <button class="btn ghost" id="figAdd">+ ДОБАВИТЬ PNG</button></div>
      <div class="figs" id="figList"></div></div>

    <div class="card"><div class="card-head"><div class="h2">Источники</div><span class="grow"></span>
      <span class="hint">по одному в строке, по ГОСТ Р 7.0.100; модель их не придумывает</span></div>
      <textarea id="bSrc" class="read auto" rows="3">${esc(W.sources || "")}</textarea></div>

    <div class="actionbar">
      <span class="hint">${T.fixed_sections.length ? "Разделы заданы шаблоном: модель сформулирует цель, план можно будет поправить." : "Модель составит план — на следующем шаге ты его проверишь и поправишь."}</span>
      <span class="grow"></span>
      ${W.outline ? `<button class="btn ghost" id="toPlan">К ПЛАНУ →</button>` : ""}
      <button class="btn big" id="goPlan">▶ ${W.outline ? "ПЕРЕСОСТАВИТЬ ПЛАН" : "СОСТАВИТЬ ПЛАН"}</button>
    </div>`;
  ["bTask", "bData", "bDec"].forEach((id) => $(`[data-mic="${id}"]`).replaceWith(micButton(() => $("#" + id))));
  autosizeAll($("#stepBody"));
  renderRoles(); renderAttachments(); renderFigures();
  const count = () => ["bTask", "bData", "bDec"].forEach((id) => ($("#" + id + "N").textContent = $("#" + id).value.length + " симв."));
  count();
  $("#stepBody").addEventListener("input", () => { count(); saveWork(collectBrief()); });
  $("#stepBody").addEventListener("change", () => saveWork(collectBrief()));
  // вложения
  const dz = $("#dropA");
  dz.onclick = async () => uploadAttachments(await pickFiles(""));
  dz.ondragover = (e) => { e.preventDefault(); dz.classList.add("over"); };
  dz.ondragleave = () => dz.classList.remove("over");
  dz.ondrop = (e) => { e.preventDefault(); dz.classList.remove("over"); uploadAttachments([...e.dataTransfer.files]); };
  $("#figAdd").onclick = async () => {
    const id = $("#figId").value.trim();
    if (!/^[a-z0-9_\-]+$/.test(id)) return toast("id: латиница в нижнем регистре, цифры, _ и -", true);
    const [f] = await pickFiles("image/*", false);
    if (!f) return;
    const fd = new FormData(); fd.append("file", f); fd.append("fig_id", id);
    try { const w = await api("POST", `/api/works/${W.id}/figures`, fd, true); W.figures = w.figures; renderFigures(); $("#figId").value = ""; }
    catch (e) { fail(e); }
  };
  const go = async () => {
    const b = collectBrief();
    if (!(b.brief.task + b.brief.data).trim()) return toast("Заполни задание или исходные данные", true);
    if (!b.meta.topic.trim()) return toast("Укажи тему на титуле", true);
    if (W.outline && !confirm("План и текст будут составлены заново. Продолжить?")) return;
    try {
      await PUT("/api/works/" + W.id, b);
      const j = await POST(`/api/works/${W.id}/plan`);
      watchJob(j, (res) => { if (res.status === "done") location.hash = `#/work/${W.id}/plan`; route(); });
    } catch (e) { fail(e); }
  };
  $("#goPlan").onclick = go;
  if ($("#toPlan")) $("#toPlan").onclick = () => (location.hash = `#/work/${W.id}/plan`);
}

function renderRoles() {
  const el = $("#roles");
  el.innerHTML = W.roles.map((r, i) => `<span class="chip">${esc(r)}<button data-i="${i}">✕</button></span>`).join("") +
    `<input id="roleIn" placeholder="+ роль и Enter">`;
  $$("button", el).forEach((b) => b.onclick = () => { W.roles.splice(+b.dataset.i, 1); renderRoles(); saveWork(collectBrief()); });
  $("#roleIn").onkeydown = (e) => {
    if (e.key === "Enter" && e.target.value.trim()) {
      W.roles.push(e.target.value.trim()); renderRoles(); saveWork(collectBrief()); $("#roleIn").focus();
    }
  };
}

async function uploadAttachments(files) {
  if (!files.length) return;
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  try {
    const r = await api("POST", `/api/works/${W.id}/attachments`, fd, true);
    W.attachments = r.work.attachments; renderAttachments();
    if (r.job && r.job.id) watchJob(r.job, async () => { const w = await GET("/api/works/" + W.id); W.attachments = w.attachments; renderAttachments(); });
    else if (r.job && r.job.error) toast(r.job.error, true);
  } catch (e) { fail(e); }
}
function renderAttachments() {
  $("#attList").innerHTML = W.attachments.map((a) => `<div class="file"><span>${a.audio ? "♪" : "▤"}</span>
    <span class="n">${esc(a.name)}</span>
    <span class="s">${a.pending ? '<span class="spin">◐</span> расшифровка…' : a.chars ? a.chars + " симв. текста" : "без текста"}</span>
    <button class="btn danger ghost tiny" data-n="${esc(a.name)}">✕</button></div>`).join("");
  $$("#attList [data-n]").forEach((b) => b.onclick = async () => {
    const w = await DEL(`/api/works/${W.id}/attachments/${encodeURIComponent(b.dataset.n)}`).catch(fail);
    if (w) { W.attachments = w.attachments; renderAttachments(); }
  });
}
function renderFigures(el = $("#figList")) {
  if (!el) return;
  el.innerHTML = W.figures.map((f) => `<div class="fig"><img src="/api/works/${W.id}/figures/${encodeURIComponent(f)}?t=${Date.now()}">
    <div><span>${esc(f.replace(/\.\w+$/, ""))}</span><button class="btn danger ghost tiny" data-f="${esc(f)}">✕</button></div></div>`).join("");
  $$("[data-f]", el).forEach((b) => b.onclick = async () => {
    const w = await DEL(`/api/works/${W.id}/figures/${encodeURIComponent(b.dataset.f)}`).catch(fail);
    if (w) { W.figures = w.figures; renderFigures(el); }
  });
}

// ---------------------------------------------------------------- шаг 2: план
function stepPlan() {
  const o = structuredClone(W.outline);
  const draw = () => {
    $("#stepBody").innerHTML = `
      <div class="card glow"><div class="field-head"><div class="h2">Цель работы</div><span class="hint">начинается с глагола</span></div>
        <textarea id="goal" class="read auto" rows="2">${esc(o.goal)}</textarea></div>
      ${o.sections.map((s, i) => `<div class="card"><div class="plan-sec">
        <div class="num">${i + 1}</div>
        <div class="grid">
          <input class="sec-title" data-k="title" data-i="${i}" value="${esc(s.title)}" placeholder="Заголовок раздела">
          <label class="f">ЧТО РАСКРЫТЬ<textarea class="read auto" rows="2" data-k="purpose" data-i="${i}">${esc(s.purpose)}</textarea></label>
          <div class="grid g2">
            <label class="f">ТАБЛИЦЫ (по одной в строке)<textarea class="auto" rows="2" data-k="tables" data-i="${i}">${esc(s.tables.join("\n"))}</textarea></label>
            <label class="f">РИСУНКИ (по одному в строке)<textarea class="auto" rows="2" data-k="figures" data-i="${i}">${esc(s.figures.join("\n"))}</textarea></label>
          </div>
        </div>
        <div class="tools">
          <button class="btn ghost tiny" data-mv="-1" data-i="${i}" ${i ? "" : "disabled"}>▲</button>
          <button class="btn ghost tiny" data-mv="1" data-i="${i}" ${i < o.sections.length - 1 ? "" : "disabled"}>▼</button>
          <button class="btn danger ghost tiny" data-rm="${i}">✕</button>
        </div></div></div>`).join("")}
      <button class="btn ghost" id="addSec" style="margin-top:18px">+ РАЗДЕЛ</button>
      <div class="actionbar">
        <span class="hint">Введение и выводы в план не входят — их добавит программа по настройкам титула.</span><span class="grow"></span>
        ${W.report ? `<button class="btn ghost" id="toText">К ТЕКСТУ →</button>` : ""}
        <button class="btn big" id="goWrite">▶ ${W.report ? "ПЕРЕПИСАТЬ ТЕКСТ" : "НАПИСАТЬ ТЕКСТ"}</button>
      </div>`;
    autosizeAll($("#stepBody"));
    $$("[data-mv]").forEach((b) => b.onclick = () => {
      const i = +b.dataset.i, j = i + +b.dataset.mv;
      [o.sections[i], o.sections[j]] = [o.sections[j], o.sections[i]]; draw();
    });
    $$("[data-rm]").forEach((b) => b.onclick = () => { if (o.sections.length > 1) { o.sections.splice(+b.dataset.rm, 1); draw(); } });
    $("#addSec").onclick = () => { o.sections.push({ title: "", purpose: "", tables: [], figures: [] }); draw(); };
    $("#goal").oninput = (e) => (o.goal = e.target.value);
    $$("[data-k]").forEach((el) => el.oninput = () => {
      const s = o.sections[+el.dataset.i], k = el.dataset.k;
      s[k] = k === "tables" || k === "figures" ? el.value.split("\n").map((x) => x.trim()).filter(Boolean) : el.value;
    });
    if ($("#toText")) $("#toText").onclick = () => (location.hash = `#/work/${W.id}/text`);
    $("#goWrite").onclick = async () => {
      if (o.sections.some((s) => !s.title.trim())) return toast("У каждого раздела нужен заголовок", true);
      if (W.report && !confirm("Изменённые разделы будут написаны заново, нетронутые — сохранятся. Продолжить?")) return;
      try {
        await PUT(`/api/works/${W.id}/outline`, o);
        const j = await POST(`/api/works/${W.id}/write`);
        watchJob(j, (res) => { if (res.status === "done") location.hash = `#/work/${W.id}/text`; route(); });
      } catch (e) { fail(e); }
    };
  };
  draw();
}

// ---------------------------------------------------------------- шаг 3: текст
function stepText() {
  const R = structuredClone(W.report);
  const figSet = new Set(W.figures.map((f) => f.replace(/\.\w+$/, "")));
  const blockHTML = (b, si, path) => {
    const p = `data-p="${path}"`;
    if (b.type === "paragraph") return `<div class="blk"><span class="blk-tag">¶</span>
      <textarea class="read auto" ${p} data-f="text" rows="2">${esc(b.text)}</textarea></div>`;
    if (b.type === "list") return `<div class="blk"><span class="blk-tag">СПИСОК</span>
      <textarea class="read auto" ${p} data-f="items" rows="3">${esc(b.items.join("\n"))}</textarea></div>`;
    if (b.type === "figure") return `<div class="blk"><span class="blk-tag">РИС</span>
      <div class="cap">РИСУНОК · id <b>${esc(b.id)}</b> <input ${p} data-f="caption" value="${esc(b.caption)}"></div>
      ${figSet.has(b.id) ? `<img src="/api/works/${W.id}/figures/${encodeURIComponent(W.figures.find((f) => f.startsWith(b.id + ".")))}" style="max-width:100%;max-height:260px;background:#fff">`
        : `<div class="drop" data-fig="${esc(b.id)}">Нет файла figures/${esc(b.id)}.png — нажми, чтобы загрузить</div>`}</div>`;
    if (b.type === "table") return `<div class="blk"><span class="blk-tag">ТАБЛ</span>
      <div class="cap">ТАБЛИЦА · id <b>${esc(b.id)}</b> <input ${p} data-f="caption" value="${esc(b.caption)}"></div>
      <div class="tbl-wrap"><table class="ed"><tr>${b.columns.map((c, ci) => `<th><textarea class="auto" rows="1" ${p} data-col="${ci}">${esc(c)}</textarea></th>`).join("")}<td class="x"></td></tr>
      ${b.rows.map((r, ri) => `<tr>${b.columns.map((_, ci) => `<td><textarea class="auto" rows="1" ${p} data-row="${ri}" data-col="${ci}">${esc(r[ci] ?? "")}</textarea></td>`).join("")}
        <td class="x"><button ${p} data-delrow="${ri}">✕</button></td></tr>`).join("")}</table></div>
      <button class="btn ghost tiny" style="margin-top:8px" ${p} data-addrow="1">+ строка</button></div>`;
    return "";
  };
  const secHTML = (s, si) => `<div class="card"><div class="card-head">
      <span class="vt" style="color:var(--pink);font-size:28px">${si + 1}</span>
      <input class="sec-title grow" data-sec="${si}" value="${esc(s.title)}">
      <button class="btn ghost tiny" data-regen="${si + 1}" title="Модель перепишет этот раздел, остальные не тронет">↻ ПЕРЕПИСАТЬ</button></div>
      ${s.blocks.map((b, bi) => blockHTML(b, si, `s.${si}.b.${bi}`)).join("")}
      ${(s.subsections || []).map((sub, ui) => `<div style="margin-top:20px"><input class="sec-title" data-subsec="${si}.${ui}" value="${esc(sub.title)}" style="font-size:14px">
        ${sub.blocks.map((b, bi) => blockHTML(b, si, `s.${si}.u.${ui}.b.${bi}`)).join("")}</div>`).join("")}</div>`;
  const parts = (key, title) => R[key] && R[key].length ? `<div class="card"><div class="h2">${title}</div>
    ${R[key].map((t, i) => `<div class="blk"><textarea class="read auto" data-part="${key}" data-i="${i}" rows="2">${esc(t)}</textarea></div>`).join("")}</div>` : "";

  $("#stepBody").innerHTML = `
    <div class="card"><div class="hint">Ссылки <span class="refs">[[table:id]]</span> и <span class="refs">[[figure:id]]</span> превратятся в «Таблица 1», «Рисунок 2».
      Жёлтым в Word будет выделено всё, что модель пометила <span class="refs">[уточнить: …]</span>.</div></div>
    <div class="card glow"><div class="h2">Цель работы</div><textarea class="read auto" id="rGoal" rows="2">${esc(R.goal)}</textarea></div>
    ${parts("intro", "Введение")}
    ${R.sections.map(secHTML).join("")}
    ${parts("conclusion", R.meta.conclusion || "Выводы")}
    <div class="actionbar"><span class="hint" id="dirty">Правки сохраняются при сборке</span><span class="grow"></span>
      <button class="btn big" id="build">▶ СОХРАНИТЬ И СОБРАТЬ .DOCX</button></div>`;
  autosizeAll($("#stepBody"));
  const resolve = (path) => {
    const a = path.split(".");
    let s = R.sections[+a[1]];
    if (a[2] === "u") s = s.subsections[+a[3]];
    return s.blocks[+a[a.length - 1]];
  };
  const markDirty = () => ($("#dirty").textContent = "● Есть несохранённые правки");
  $("#stepBody").addEventListener("input", (e) => {
    const el = e.target;
    markDirty();
    if (el.id === "rGoal") R.goal = el.value;
    else if (el.dataset.sec) R.sections[+el.dataset.sec].title = el.value;
    else if (el.dataset.subsec) { const [a, b] = el.dataset.subsec.split("."); R.sections[+a].subsections[+b].title = el.value; }
    else if (el.dataset.part) R[el.dataset.part][+el.dataset.i] = el.value;
    else if (el.dataset.p) {
      const b = resolve(el.dataset.p);
      if (el.dataset.f === "items") b.items = el.value.split("\n").filter((x) => x.trim());
      else if (el.dataset.f) b[el.dataset.f] = el.value;
      else if (el.dataset.row !== undefined) b.rows[+el.dataset.row][+el.dataset.col] = el.value;
      else if (el.dataset.col !== undefined) b.columns[+el.dataset.col] = el.value;
    }
  });
  $$("[data-delrow]").forEach((x) => x.onclick = () => { const b = resolve(x.dataset.p); b.rows.splice(+x.dataset.delrow, 1); W.report = R; stepText(); markDirty(); });
  $$("[data-addrow]").forEach((x) => x.onclick = () => { const b = resolve(x.dataset.p); b.rows.push(b.columns.map(() => "–")); W.report = R; stepText(); markDirty(); });
  $$("[data-fig]").forEach((d) => d.onclick = async () => {
    const [f] = await pickFiles("image/*", false);
    if (!f) return;
    const fd = new FormData(); fd.append("file", f); fd.append("fig_id", d.dataset.fig);
    try { const w = await api("POST", `/api/works/${W.id}/figures`, fd, true); W.figures = w.figures; W.report = R; stepText(); } catch (e) { fail(e); }
  });
  $$("[data-regen]").forEach((b) => b.onclick = async () => {
    if (!confirm("Модель перепишет раздел заново. Твои правки в нём пропадут. Продолжить?")) return;
    try {
      await PUT(`/api/works/${W.id}/report`, R);
      const j = await POST(`/api/works/${W.id}/sections/${b.dataset.regen}/regenerate`);
      watchJob(j, () => route());
    } catch (e) { fail(e); }
  });
  $("#build").onclick = async () => {
    const btn = $("#build");
    btn.disabled = true; btn.innerHTML = `<span class="spin">◐</span> СБОРКА`;
    try {
      const r = await PUT(`/api/works/${W.id}/report`, R);
      r.lines.forEach((l) => toast(l));
      location.hash = `#/work/${W.id}/done`;
    } catch (e) { fail(e); btn.disabled = false; btn.textContent = "▶ СОХРАНИТЬ И СОБРАТЬ .DOCX"; }
  };
}

// ---------------------------------------------------------------- шаг 4: готово
function stepDone() {
  $("#stepBody").innerHTML = `
    <div class="card glow done-hero">
      <div class="hero-big">ДОКУМЕНТ СОБРАН</div>
      <div class="file-name">${esc(W.docx)}</div>
      <div style="display:flex;gap:14px;justify-content:center;flex-wrap:wrap">
        <button class="btn big" id="dOpen">▶ ОТКРЫТЬ В WORD</button>
        <button class="btn ghost" id="dFolder">▣ ОТКРЫТЬ ПАПКУ</button>
        <button class="btn ghost" id="dRebuild">↻ ПЕРЕСОБРАТЬ</button>
      </div>
    </div>
    <div class="card"><div class="card-head"><div class="h2">Выгрузить</div><span class="grow"></span>
      <span class="hint">копия ляжет в Хранилище → ВУЗ → ${esc(W.meta.discipline || "предмет")} → ${esc({"Лабораторная работа":"Лабораторные","Практическая работа":"Практические","Реферат":"Рефераты","Курсовая работа":"Курсовые"}[W.meta.work_type] || "Материалы")}</span></div>
      <div style="display:flex;gap:12px;flex-wrap:wrap">
        <button class="btn" data-exp="pdf">▼ PDF</button><button class="btn ghost" data-exp="docx">▼ WORD</button>
        <button class="btn ghost" data-exp="txt">▼ TXT</button></div>
      <div id="expRes" class="hint" style="margin-top:10px"></div></div>
    <div class="card"><div class="card-head"><div class="h2">Замер для кейса</div><span class="grow"></span>
      <span class="hint">из этих цифр собирается сравнение «до / после» на странице «Работы»</span></div>
      <div class="grid g2">
        <label class="f">СКОЛЬКО ЗАНЯЛО БЫ ВРУЧНУЮ, МИН<input type="number" id="mMan" min="0" value="${W.manual_minutes ?? ""}"></label>
        <label class="f">СКОЛЬКО УШЛО НА ПРОВЕРКУ И ПРАВКИ, МИН<input type="number" id="mRev" min="0" value="${W.review_minutes ?? ""}"></label>
        <label class="f span2">ЗАМЕТКИ (что пришлось править, что модель придумала)<textarea id="mNotes" class="read auto" rows="3">${esc(W.notes || "")}</textarea></label>
      </div></div>
    <div class="card"><div class="card-head"><div class="h2">Превью для галереи</div></div>
      <p class="hint">Сделать картинки страниц этой работы превью шаблона «${esc(W._tpl ? W._tpl.name : W.template)}» (нужен Word).</p>
      <button class="btn ghost" id="dPrev">◆ СДЕЛАТЬ ПРЕВЬЮ ШАБЛОНА</button></div>`;
  autosizeAll($("#stepBody"));
  $("#dOpen").onclick = () => POST(`/api/works/${W.id}/open`).catch(fail);
  $$("[data-exp]").forEach((b) => b.onclick = async () => {
    const old = b.innerHTML; b.disabled = true; b.innerHTML = `<span class="spin">◐</span> ${b.dataset.exp.toUpperCase()}`;
    try { const r = await GET(`/api/works/${W.id}/export?fmt=${b.dataset.exp}`); fileResult($("#expRes"), r.path); }
    catch (e) { fail(e); }
    b.disabled = false; b.innerHTML = old;
  });
  $("#dFolder").onclick = () => POST(`/api/works/${W.id}/open?what=folder`).catch(fail);
  $("#dRebuild").onclick = async () => {
    try { const r = await POST(`/api/works/${W.id}/render`); r.lines.forEach((l) => toast(l)); } catch (e) { fail(e); }
  };
  const save = debounce(() => PUT("/api/works/" + W.id, {
    manual_minutes: $("#mMan").value === "" ? null : +$("#mMan").value,
    review_minutes: $("#mRev").value === "" ? null : +$("#mRev").value,
    notes: $("#mNotes").value,
  }).catch(fail), 500);
  ["mMan", "mRev", "mNotes"].forEach((id) => $("#" + id).addEventListener("input", save));
  $("#dPrev").onclick = async () => {
    const fd = new FormData(); fd.append("work_id", W.id);
    try { const j = await api("POST", `/api/templates/${W.template}/previews/from-docx`, fd, true); watchJob(j, () => toast("Превью обновлены")); }
    catch (e) { fail(e); }
  };
}

// ================================================================= TEMPLATE EDITOR
async function viewTemplateEditor(slug) {
  const isNew = slug === "new";
  const t = isNew ? { name: "", category: "ВУЗ", description: "", tags: [], meta: { work_type: "Практическая работа", discipline: "",
    module: null, semester: 3, teacher: "______________", file_code: "XX", toc: false, intro: false, conclusion: "ВЫВОДЫ", h1_new_page: true },
    roles: [], fixed_sections: [], prompt_hints: "", brief_skeleton: { task: "", data: "", decisions: "" }, previews: [] }
    : await GET("/api/templates/" + slug);
  const works = isNew ? [] : (await GET("/api/works")).filter((w) => w.has_docx);
  const m = t.meta;
  const fx = structuredClone(t.fixed_sections || []);
  view.innerHTML = `
    <div class="page-head"><h1 class="h1">${isNew ? "Новый шаблон" : "Шаблон"}<small>${esc(t.name || "тип работы: титул, структура, подсказки модели")}</small></h1>
      <span class="grow"></span>${isNew ? "" : `<button class="btn danger ghost" id="tDel">✕ УДАЛИТЬ</button>`}</div>
    <div class="work"><div>
      <div class="card"><div class="h2">Описание</div><div class="grid g4">
        <label class="f span2">НАЗВАНИЕ<input id="tName" value="${esc(t.name)}" placeholder="ЛР по ТИПУП"></label>
        <label class="f">КАТЕГОРИЯ<select id="tCat">${["ВУЗ", "Работа", "Другое"].map((c) => `<option ${t.category === c ? "selected" : ""}>${c}</option>`).join("")}</select></label>
        <label class="f">ТЕГИ (через запятую)<input id="tTags" value="${esc((t.tags || []).join(", "))}"></label>
        <label class="f span4">ОПИСАНИЕ<textarea id="tDesc" class="read auto" rows="2">${esc(t.description)}</textarea></label></div></div>
      <div class="card"><div class="h2">Титул и структура по умолчанию</div><div class="grid g4">
        <label class="f">ТИП<select data-tm="work_type">${["Лабораторная работа", "Практическая работа", "Реферат", "Курсовая работа"].map((x) => `<option ${m.work_type === x ? "selected" : ""}>${x}</option>`).join("")}</select></label>
        <label class="f">ДИСЦИПЛИНА<input data-tm="discipline" value="${esc(m.discipline || "")}"></label>
        <label class="f span2">МОДУЛЬ<input data-tm="module" value="${esc(m.module || "")}"></label>
        <label class="f">ПРЕПОДАВАТЕЛЬ<input data-tm="teacher" value="${esc(m.teacher || "")}"></label>
        <label class="f">СЕМЕСТР<input data-tm="semester" value="${esc(m.semester || "")}"></label>
        <label class="f">КОД ФАЙЛА<input data-tm="file_code" value="${esc(m.file_code || "")}"></label>
        <label class="f">ИТОГ<select data-tm="conclusion">${["ВЫВОДЫ", "ЗАКЛЮЧЕНИЕ", ""].map((x) => `<option value="${x}" ${(m.conclusion || "") === x ? "selected" : ""}>${x || "нет"}</option>`).join("")}</select></label>
        <div class="span4 chips" style="gap:22px">
          <label class="check"><input type="checkbox" data-tm="toc" ${m.toc ? "checked" : ""}><b></b>Содержание</label>
          <label class="check"><input type="checkbox" data-tm="intro" ${m.intro ? "checked" : ""}><b></b>Введение</label>
          <label class="check"><input type="checkbox" data-tm="h1_new_page" ${m.h1_new_page ? "checked" : ""}><b></b>Разделы с новой страницы</label></div>
        <label class="f span4">УЧАСТНИКИ ПО УМОЛЧАНИЮ (через запятую)<input id="tRoles" value="${esc((t.roles || []).join(", "))}"></label></div></div>
      <div class="card"><div class="card-head"><div class="h2">Фиксированные разделы</div><span class="grow"></span>
        <span class="hint">если заданы — модель не планирует структуру, а пишет по ним</span></div>
        <div id="fx"></div><button class="btn ghost tiny" id="fxAdd">+ РАЗДЕЛ</button></div>
      <div class="card"><div class="field-head"><div class="h2">Подсказки модели</div><span class="hint">добавляются к системному промпту</span></div>
        <textarea id="tHints" class="read auto" rows="4" placeholder="Например: таблицы стрелок IDEF0 — столбцы Блок / Вход / Управление / Выход / Механизм">${esc(t.prompt_hints || "")}</textarea></div>
      <div class="card"><div class="h2">Заготовка задания</div><div class="grid">
        <label class="f">ЗАДАНИЕ<textarea id="sTask" class="read auto" rows="3">${esc(t.brief_skeleton?.task || "")}</textarea></label>
        <label class="f">ИСХОДНЫЕ ДАННЫЕ<textarea id="sData" class="read auto" rows="3">${esc(t.brief_skeleton?.data || "")}</textarea></label>
        <label class="f">МОИ РЕШЕНИЯ<textarea id="sDec" class="read auto" rows="2">${esc(t.brief_skeleton?.decisions || "")}</textarea></label></div></div>
      <div class="actionbar"><span class="grow"></span><button class="btn big" id="tSave">▶ СОХРАНИТЬ ШАБЛОН</button></div>
    </div>
    <aside class="rail"><div class="card"><div class="h2">Превью</div>
      ${isNew ? `<p class="hint">Сохрани шаблон, чтобы добавить картинки.</p>` : `
      <div style="width:100%">${viewerHTML(t.previews, t.name)}</div>
      <div class="thumbs" style="margin-top:12px">${t.previews.map((p) => { const n = p.split("/").pop().split("?")[0];
        return `<span style="position:relative"><img src="${p}"><button class="btn danger ghost tiny" data-pv="${n}" style="position:absolute;top:2px;right:2px;padding:3px 5px">✕</button></span>`; }).join("")}</div>
      <div class="grid" style="margin-top:14px">
        <button class="btn ghost tiny" id="pvImg">+ КАРТИНКИ (PNG/JPG)</button>
        <button class="btn ghost tiny" id="pvDocx">◆ ИЗ ФАЙЛА .DOCX</button>
        ${works.length ? `<select id="pvWork"><option value="">◆ из готовой работы…</option>${works.map((w) => `<option value="${w.id}">${esc(w.title)}</option>`).join("")}</select>` : ""}
      </div><p class="hint">Колесо мыши над картинкой листает страницы.</p>`}</div></aside></div>`;
  autosizeAll(view);
  if (!isNew) bindViewer($(".rail .tview"));
  const drawFx = () => {
    $("#fx").innerHTML = fx.map((s, i) => `<div class="grid g2" style="margin-bottom:12px;padding-bottom:12px;border-bottom:1px dashed var(--line)">
      <input data-fx="${i}" data-k="title" value="${esc(s.title)}" placeholder="Заголовок">
      <div style="display:flex;gap:8px"><input data-fx="${i}" data-k="tables" value="${esc((s.tables || []).join("; "))}" placeholder="таблицы через ;">
        <input data-fx="${i}" data-k="figures" value="${esc((s.figures || []).join("; "))}" placeholder="рисунки через ;">
        <button class="btn danger ghost tiny" data-fxrm="${i}">✕</button></div>
      <textarea class="span2 auto" rows="1" data-fx="${i}" data-k="purpose" placeholder="что раскрыть">${esc(s.purpose)}</textarea></div>`).join("") || `<p class="hint">Нет — план составляет модель.</p>`;
    $$("[data-fx]").forEach((el) => el.oninput = () => {
      const s = fx[+el.dataset.fx], k = el.dataset.k;
      s[k] = k === "tables" || k === "figures" ? el.value.split(";").map((x) => x.trim()).filter(Boolean) : el.value;
    });
    $$("[data-fxrm]").forEach((b) => b.onclick = () => { fx.splice(+b.dataset.fxrm, 1); drawFx(); });
  };
  drawFx();
  $("#fxAdd").onclick = () => { fx.push({ title: "", purpose: "", tables: [], figures: [] }); drawFx(); };
  const collect = () => {
    const meta = { ...m };
    $$("[data-tm]").forEach((el) => {
      const k = el.dataset.tm;
      meta[k] = el.type === "checkbox" ? el.checked : k === "semester" ? parseInt(el.value, 10) || 1 : k === "module" ? el.value.trim() || null
        : k === "conclusion" ? el.value || null : el.value;
    });
    return { name: $("#tName").value.trim() || "Без названия", category: $("#tCat").value, description: $("#tDesc").value,
      tags: $("#tTags").value.split(",").map((x) => x.trim()).filter(Boolean), meta,
      roles: $("#tRoles").value.split(",").map((x) => x.trim()).filter(Boolean),
      fixed_sections: fx.filter((s) => s.title.trim()), prompt_hints: $("#tHints").value,
      brief_skeleton: { task: $("#sTask").value, data: $("#sData").value, decisions: $("#sDec").value } };
  };
  $("#tSave").onclick = async () => {
    try {
      const r = isNew ? await POST("/api/templates", collect()) : await PUT("/api/templates/" + slug, collect());
      toast("Шаблон сохранён");
      if (isNew) location.hash = "#/template/" + r.slug; else viewTemplateEditor(slug);
    } catch (e) { fail(e); }
  };
  if (!isNew) {
    $("#tDel").onclick = async () => { if (confirm("Удалить шаблон? Работы останутся.")) { await DEL("/api/templates/" + slug); location.hash = "#/gallery"; } };
    $$("[data-pv]").forEach((b) => b.onclick = async () => { await DEL(`/api/templates/${slug}/previews/${b.dataset.pv}`).catch(fail); viewTemplateEditor(slug); });
    $("#pvImg").onclick = async () => {
      const files = await pickFiles("image/*");
      if (!files.length) return;
      const fd = new FormData(); files.forEach((f) => fd.append("files", f));
      await api("POST", `/api/templates/${slug}/previews`, fd, true).catch(fail);
      viewTemplateEditor(slug);
    };
    $("#pvDocx").onclick = async () => {
      const [f] = await pickFiles(".docx", false);
      if (!f) return;
      const fd = new FormData(); fd.append("file", f);
      try { const j = await api("POST", `/api/templates/${slug}/previews/from-docx`, fd, true); watchJob(j, () => viewTemplateEditor(slug)); } catch (e) { fail(e); }
    };
    if ($("#pvWork")) $("#pvWork").onchange = async (e) => {
      if (!e.target.value) return;
      const fd = new FormData(); fd.append("work_id", e.target.value);
      try { const j = await api("POST", `/api/templates/${slug}/previews/from-docx`, fd, true); watchJob(j, () => viewTemplateEditor(slug)); } catch (er) { fail(er); }
    };
  }
}

// чат, настройки, хранилище, расшифровка и запуск — в views.js
