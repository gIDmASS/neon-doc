/* NEON.DOC — рабочие документы: вкладка «Работа» в шаблонах и редактор документа по разделам. */
"use strict";

const WD_KIND = { text: "текст", steps: "шаги", table: "таблица", list: "список", asis_steps: "шаги AS-IS",
  choice: "выбор", figures: "рисунки", fixed: "из шаблона", heading: "заголовок" };
const LVL = { err: ["ОШИБКА", "plan"], warn: ["ВНИМАНИЕ", "text"], todo: ["УТОЧНИТЬ", "brief"], info: ["СОВЕТ", "done"] };

function galleryTabs(on) {
  return `<div class="seg gal-tabs"><button data-g="#/gallery" class="${on === "vuz" ? "on" : ""}">◆ УЧЁБА</button>
    <button data-g="#/wgallery" class="${on === "work" ? "on" : ""}">▣ РАБОТА</button></div>`;
}
function bindGalleryTabs() { $$(".gal-tabs button").forEach((b) => b.onclick = () => (location.hash = b.dataset.g)); }

// вставляем переключатель «Учёба / Работа» в обычную галерею шаблонов
const _viewGalleryVuz = viewGallery;
viewGallery = async function () {
  await _viewGalleryVuz();
  const head = $(".page-head", view);
  if (head && !$(".gal-tabs", head)) {
    $(".h1", head).insertAdjacentHTML("afterend", galleryTabs("vuz"));
    bindGalleryTabs();
  }
};

// ================================================================= галерея рабочих шаблонов
async function viewWorkGallery() {
  const [list, docs] = await Promise.all([GET("/api/wtemplates"), GET("/api/wdocs")]);
  const tname = Object.fromEntries(list.map((t) => [t.slug, t.name]));
  view.innerHTML = `
    <div class="page-head"><h1 class="h1">Шаблоны<small>Рабочие документы: Qwen заполняет по разделам из материалов и встреч</small></h1>
      ${galleryTabs("work")}<span class="grow"></span></div>
    <div class="gallery">${list.map((t) => `
      <article class="tcard wt-card" data-slug="${t.slug}">
        ${viewerHTML(t.previews || [], t.name)}
        <div class="tbody">
          <div class="tname">${esc(t.name)}</div>
          <div class="tdesc">${esc(t.description || "")}</div>
          <div class="tmeta"><span class="badge b-text">${t.kind === "fill" ? "шаблон .docx" : "Word + Confluence"}</span>
            ${(t.tags || []).slice(0, 2).map((x) => `<span class="chip">${esc(x)}</span>`).join("")}
            <span class="grow"></span><span class="vt muted">${t.docs || 0} док.</span></div>
        </div></article>`).join("")}</div>
    <div style="height:26px"></div>
    <div class="card-head"><div class="h2">Мои рабочие документы</div></div>
    <div class="rows">${docs.length ? docs.map((d) => wdRow(d, tname)).join("") :
      `<div class="empty-state"><div class="big">ПУСТО</div><p>Выбери шаблон выше — например «Описание робота»</p></div>`}</div>`;
  bindGalleryTabs();
  $$(".wt-card").forEach((c) => { bindViewer($(".tview", c)); c.onclick = () => openWorkTemplate(list.find((t) => t.slug === c.dataset.slug)); });
  bindWdRows(viewWorkGallery);
}

function wdRow(d, tname) {
  const pct = d.total ? Math.round(100 * d.filled / d.total) : 0;
  return `<div class="row wd-row" data-id="${d.id}">
    <div><div class="t">${esc(d.title)}</div><div class="s">${esc(tname[d.template] || d.template)}</div></div>
    <div class="s">${esc(d.updated || d.created)}</div>
    <div><span class="badge b-${d.last_build ? "done" : pct ? "text" : "brief"}">${d.last_build ? "собран" : pct ? "в работе" : "черновик"}</span></div>
    <div class="m">${d.filled}/${d.total} разд.</div><div class="m">${d.last_build ? "▼ " + esc(d.last_build.slice(5)) : ""}</div>
    <button class="btn danger ghost tiny" data-wdel="${d.id}">✕</button></div>`;
}
function bindWdRows(reload) {
  $$(".wd-row").forEach((r) => r.addEventListener("click", (e) => { if (!e.target.dataset.wdel) location.hash = "#/wdoc/" + r.dataset.id; }));
  $$("[data-wdel]").forEach((b) => b.addEventListener("click", async (e) => {
    e.stopPropagation();
    if (!confirm("Удалить документ со всеми материалами и сборками? (копии в Хранилище останутся)")) return;
    await DEL("/api/wdocs/" + b.dataset.wdel).catch(fail);
    reload();
  }));
}

function openWorkTemplate(t) {
  const main = (t.fields || []).filter((f) => ["code", "name"].includes(f.key));
  const m = modal(`
    <div class="card-head"><div class="h2">${esc(t.name)}</div><span class="grow"></span><button class="btn ghost tiny" id="wtX">✕</button></div>
    <p class="muted read">${esc(t.description || "")}</p>
    <div class="wt-secs">${t.sections.map((s) => `<span class="chip ${s.optional ? "dim" : ""}" title="${esc(s.hint || "")}">${s.level === 2 ? "↳ " : ""}${esc(s.title.replace(/\.$/, ""))}${s.ai ? " ✦" : ""}</span>`).join("")}</div>
    <p class="hint">✦ — раздел заполняет Qwen; остальные — вручную. Серые — необязательные.</p>
    <div class="grid g2">
      ${main.map((f) => `<label class="f">${esc(f.label.toUpperCase())}<input data-fk="${f.key}" placeholder="${esc(f.hint || "")}" value="${esc((f.default || "").replace("{today}", ""))}"></label>`).join("")}
      <label class="f span2">НАЗВАНИЕ ДОКУМЕНТА В СПИСКЕ<input id="wtTitle" placeholder="например: Сверка платежей — описание робота"></label>
    </div>
    <div style="display:flex;gap:12px;margin-top:14px"><button class="btn big" id="wtNew">▶ Новый документ</button></div>`, "wide");
  $("#wtX", m).onclick = closeModal;
  $("#wtNew", m).onclick = async () => {
    const fields = {};
    $$("[data-fk]", m).forEach((i) => { if (i.value.trim()) fields[i.dataset.fk] = i.value.trim(); });
    const title = $("#wtTitle", m).value.trim() || [fields.code, fields.name].filter(Boolean).join(" ") || "";
    try {
      const d = await POST("/api/wdocs", { template: t.slug, title, fields });
      closeModal();
      location.hash = "#/wdoc/" + d.id;
    } catch (e) { fail(e); }
  };
  ($("[data-fk]", m) || $("#wtTitle", m)).focus();
}

// ================================================================= редактор документа
let WD = null;   // {doc, tpl, dirty: Set}

async function viewWDoc(id) {
  const doc = await GET("/api/wdocs/" + id);
  const tpl = await GET("/api/wtemplates/" + doc.template);
  WD = { doc, tpl, dirty: new Set(), id };
  const f = doc.fields || {};
  view.innerHTML = `
    <div class="page-head wd-head">
      <h1 class="h1"><input class="title-in" id="wdTitle" value="${esc(doc.title)}"><small>${esc(tpl.name)} · ${tpl.kind === "fill" ? "заполнение шаблона .docx" : "Word + разметка Confluence"}</small></h1>
      <span class="grow"></span>
      <a class="btn ghost tiny" href="#/wgallery">◂ К ШАБЛОНАМ</a>
    </div>
    <div class="actionbar wd-bar">
      <button class="btn" id="wdGenAll" title="Заполнить все разделы, которые умеет Qwen (правленные вручную не трогает)">✦ ЗАПОЛНИТЬ ЧЕРЕЗ QWEN</button>
      <button class="btn ghost" id="wdGenEmpty">✦ ТОЛЬКО ПУСТЫЕ</button>
      <span class="grow"></span>
      <button class="btn ghost" id="wdCheck">✓ ПРОВЕРКА</button>
      <button class="btn ghost" id="wdQ">? ВОПРОСЫ <b id="wdQn">${doc.todo || ""}</b></button>
      <button class="btn cyan" id="wdBuild">▼ СОБРАТЬ</button>
    </div>
    <div class="wd-layout">
      <nav class="wd-toc" id="wdToc"></nav>
      <div class="wd-main">
        <section class="card" id="wd-card">
          <div class="card-head"><div class="h2">Карточка</div></div>
          <div class="grid g3">${(tpl.fields || []).map((fl) => fl.type === "bool"
            ? `<label class="check" style="align-self:end"><input type="checkbox" data-field="${fl.key}" ${f[fl.key] ? "checked" : ""}><b></b>${esc(fl.label)}</label>`
            : fl.type === "select"
              ? `<label class="f">${esc(fl.label.toUpperCase())}<select data-field="${fl.key}">${fl.options.map((o) => `<option ${o === f[fl.key] ? "selected" : ""}>${esc(o)}</option>`).join("")}</select></label>`
              : `<label class="f">${esc(fl.label.toUpperCase())}<input data-field="${fl.key}" value="${esc(f[fl.key] ?? "")}" placeholder="${esc(fl.hint || "")}"></label>`).join("")}</div>
        </section>
        <section class="card" id="wd-mat">
          <div class="card-head"><div class="h2">Материалы для Qwen</div><span class="grow"></span>
            <button class="btn ghost tiny" id="wdAddF">+ ФАЙЛЫ</button><button class="btn ghost tiny" id="wdAddS">+ ИЗ ХРАНИЛИЩА</button>
            <button class="btn ghost tiny" id="wdAddT">+ РАСШИФРОВКА</button></div>
          <label class="f">ЧТО ИЗВЕСТНО О ПРОЦЕССЕ — своими словами, можно голосом
            <textarea class="auto" id="wdBrief" rows="4" placeholder="Кто заказчик, что делает робот, из каких систем берёт данные, куда кладёт результат, расписание, особенности…">${esc(doc.brief || "")}</textarea></label>
          <div id="wdMic"></div>
          <div class="drop wd-drop" id="wdDrop">Перетащи сюда ТЗ, примеры файлов, выгрузки, письма, записи встреч (аудио/видео расшифруются сами)</div>
          <div class="wd-mats" id="wdMats"></div>
        </section>
        ${tpl.kind === "build" ? `<section class="card" id="wd-figs">
          <div class="card-head"><div class="h2">Рисунки и скриншоты</div><span class="grow"></span>
            <button class="btn ghost tiny" id="wdFigAdd">+ КАРТИНКА</button><button class="btn ghost tiny" id="wdFigS">+ ИЗ ХРАНИЛИЩА</button>
            <a class="btn ghost tiny" href="#/annot">▢ РАЗМЕТКА</a></div>
          <p class="hint">Клик по рисунку копирует строку для вставки в шаги: <code>![Название](файл)</code>. Ссылка в тексте — <code>[[figure:файл]]</code>, номер подставится сам.</p>
          <div class="wd-figs" id="wdFigs"></div></section>` : ""}
        <div id="wdSecs"></div>
        <section class="card" id="wd-out"><div class="card-head"><div class="h2">Сборки</div></div><div id="wdOuts"></div></section>
      </div>
    </div>`;
  autosizeAll(view);
  $("#wdMic").append(micButton(() => $("#wdBrief"), "НАДИКТОВАТЬ"));
  drawMats(); drawFigs(); drawSecs(); drawOuts(); drawToc();

  $("#wdTitle").addEventListener("input", debounce(() => wdSave({ title: $("#wdTitle").value }), 600));
  $$("[data-field]").forEach((i) => i.addEventListener(i.type === "checkbox" || i.tagName === "SELECT" ? "change" : "input", debounce(async () => {
    const fields = { ...WD.doc.fields };
    $$("[data-field]").forEach((x) => fields[x.dataset.field] = x.type === "checkbox" ? x.checked : x.value);
    const before = JSON.stringify(Object.fromEntries(Object.entries(WD.doc.sections).map(([k, v]) => [k, v.enabled])));
    await wdSave({ fields });
    const after = JSON.stringify(Object.fromEntries(Object.entries(WD.doc.sections).map(([k, v]) => [k, v.enabled])));
    if (before !== after) { drawSecs(); drawToc(); toast("Набор разделов обновлён под платформу"); }
  }, 500)));
  $("#wdBrief").addEventListener("input", debounce(() => wdSave({ brief: $("#wdBrief").value }), 700));

  const up = async (files) => {
    if (!files.length) return;
    const fd = new FormData(); files.forEach((x) => fd.append("files", x));
    $("#wdDrop").innerHTML = `<span class="spin">◐</span> Загружаю ${files.length} файл(ов)…`;
    try {
      const r = await api("POST", `/api/wdocs/${id}/materials`, fd, true);
      WD.doc = r.doc; drawMats();
      if (r.job && r.job.id) watchJob(r.job, () => refreshDoc());
      if (r.transcripts.length) toast(`Записи (${r.transcripts.length}) отправлены в расшифровку — текст подтянется сам`);
    } catch (e) { fail(e); }
    $("#wdDrop").textContent = "Перетащи сюда ТЗ, примеры файлов, выгрузки, письма, записи встреч (аудио/видео расшифруются сами)";
  };
  const dz = $("#wdDrop");
  dz.onclick = async () => up(await pickFiles(""));
  dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("drop-on"); });
  dz.addEventListener("dragleave", () => dz.classList.remove("drop-on"));
  dz.addEventListener("drop", (e) => { e.preventDefault(); dz.classList.remove("drop-on"); up([...e.dataTransfer.files]); });
  $("#wdAddF").onclick = async () => up(await pickFiles(""));
  $("#wdAddS").onclick = () => pickFromStorage(async (p) => {
    try { WD.doc = await POST(`/api/wdocs/${id}/materials/from-storage`, { path: p }); drawMats(); } catch (e) { fail(e); }
  }, () => true, { title: "Материал из Хранилища", start: "Работа" });
  $("#wdAddT").onclick = pickTranscript;
  if ($("#wdFigAdd")) {
    $("#wdFigAdd").onclick = async () => { for (const x of await pickFiles("image/*")) await uploadFig(x); };
    $("#wdFigS").onclick = () => pickFromStorage(async (p) => {
      try { const r = await POST(`/api/wdocs/${id}/figures/from-storage`, { path: p }); WD.doc = r.doc; drawFigs(); } catch (e) { fail(e); }
    }, (it) => it.kind === "img", { title: "Картинка из Хранилища", start: "Работа/Скриншоты" });
  }
  $("#wdGenAll").onclick = () => runGen(null, false);
  $("#wdGenEmpty").onclick = () => runGen(null, true);
  $("#wdCheck").onclick = showCheck;
  $("#wdQ").onclick = showQuestions;
  $("#wdBuild").onclick = showBuild;
}

async function refreshDoc() {
  if (!WD) return;
  WD.doc = await GET("/api/wdocs/" + WD.id);
  drawMats(); drawFigs(); drawSecs(); drawOuts(); drawToc();
  $("#wdQn").textContent = WD.doc.todo || "";
}

async function wdSave(patch) {
  try {
    WD.doc = await PUT("/api/wdocs/" + WD.id, patch);
    $("#wdQn").textContent = WD.doc.todo || "";
    drawToc();
  } catch (e) { fail(e); }
}
const secSave = debounce(() => {
  if (!WD || !WD.dirty.size) return;
  const sections = {};
  WD.dirty.forEach((sid) => {
    const s = WD.doc.sections[sid];
    sections[sid] = Object.fromEntries(["enabled", "text", "rows", "items", "steps", "value", "figures"].filter((k) => k in s).map((k) => [k, s[k]]));
  });
  WD.dirty.clear();
  wdSave({ sections });
}, 700);
function touch(sid) { WD.dirty.add(sid); secSave(); }

function drawToc() {
  const el = $("#wdToc"); if (!el) return;
  const secs = WD.tpl.sections;
  const filled = (s) => { const x = WD.doc.sections[s.id] || {};
    return !!((x.text || "").trim() || (x.rows || []).some((r) => r.some((c) => String(c).trim())) || (x.items || []).length || (x.steps || []).length || (x.figures || []).length || s.kind === "fixed" || s.kind === "heading" || s.kind === "choice"); };
  el.innerHTML = `<a data-go="wd-card">Карточка</a><a data-go="wd-mat">Материалы <i>${WD.doc.materials.length || ""}</i></a>
    ${WD.tpl.kind === "build" ? `<a data-go="wd-figs">Рисунки <i>${WD.doc.figure_files.length || ""}</i></a>` : ""}<hr>
    ${secs.map((s) => { const x = WD.doc.sections[s.id] || {}; const off = x.enabled === false;
      return `<a data-go="sec-${s.id}" class="${off ? "off" : ""} ${s.level === 2 ? "l2" : ""}"><b class="${off ? "" : filled(s) ? "ok" : "no"}"></b>${esc(s.title.replace(/\.$/, ""))}${(x.questions || []).length ? ` <i>?${x.questions.length}</i>` : ""}</a>`; }).join("")}
    <hr><a data-go="wd-out">Сборки</a>`;
  $$("[data-go]", el).forEach((a) => a.onclick = () => { const t = document.getElementById(a.dataset.go); t && t.scrollIntoView({ behavior: "smooth", block: "start" }); });
}

function drawMats() {
  const el = $("#wdMats"); if (!el) return;
  const ms = WD.doc.materials || [];
  el.innerHTML = ms.length ? ms.map((m) => `<div class="att">
      <b class="k">${m.kind === "transcript" ? "♪" : m.kind === "image" ? "◩" : m.kind === "media" ? "▶" : "▤"}</b>
      <span>${esc(m.name)}</span>
      <i>${m.kind === "transcript" ? ({ done: "расшифровано", running: "идёт расшифровка", new: "в очереди", error: "ошибка", missing: "нет" }[m.status] || m.status) + " · " : ""}${m.chars ? Math.round(m.chars / 1000) + "k симв." : m.kind === "image" ? "картинка — Qwen её не читает" : "—"}</i>
      ${m.transcript ? `<a class="btn ghost tiny" href="#/transcribe/${m.transcript}">ОТКРЫТЬ</a>` : ""}
      <button class="btn ghost tiny" data-mdel="${esc(m.transcript || m.name)}" data-tr="${m.transcript ? 1 : ""}">✕</button></div>`).join("")
    : `<p class="hint">Пока пусто. Чем больше материалов (ТЗ, переписка, расшифровки встреч), тем меньше [уточнить] в разделах.</p>`;
  $$("[data-mdel]", el).forEach((b) => b.onclick = async () => {
    try {
      WD.doc = b.dataset.tr ? await POST(`/api/wdocs/${WD.id}/transcripts`, { tid: b.dataset.mdel, on: false })
        : await DEL(`/api/wdocs/${WD.id}/materials/${encodeURIComponent(b.dataset.mdel)}`);
      drawMats(); drawToc();
    } catch (e) { fail(e); }
  });
}

async function pickTranscript() {
  const list = (await GET("/api/transcripts").catch(() => [])).filter((t) => !(WD.doc.transcripts || []).includes(t.id));
  const m = modal(`<div class="card-head"><div class="h2">Расшифровка встречи</div><span class="grow"></span><button class="btn ghost tiny" id="ptX">✕</button></div>
    <div class="pick-list">${list.length ? list.map((t) => `<div class="pick-it" data-t="${t.id}"><b class="k">♪</b><span>${esc(t.title)}</span><i>${esc(t.created || "")} · ${t.status}</i></div>`).join("")
      : `<p class="hint">Нет расшифровок. Загрузи запись прямо в «Материалы» или в раздел «Расшифровка».</p>`}</div>`);
  $("#ptX", m).onclick = closeModal;
  $$("[data-t]", m).forEach((r) => r.onclick = async () => {
    closeModal();
    try { WD.doc = await POST(`/api/wdocs/${WD.id}/transcripts`, { tid: r.dataset.t, on: true }); drawMats(); drawToc(); } catch (e) { fail(e); }
  });
}

async function uploadFig(file, section, caption) {
  const fd = new FormData(); fd.append("file", file); fd.append("section", section || ""); fd.append("caption", caption || "");
  try { const r = await api("POST", `/api/wdocs/${WD.id}/figures`, fd, true); WD.doc = r.doc; drawFigs(); drawSecs(); drawToc(); return r.name; }
  catch (e) { fail(e); }
}
const figUrl = (n) => `/api/wdocs/${WD.id}/figures/${encodeURIComponent(n)}?v=${Date.now() % 100000}`;

function drawFigs() {
  const el = $("#wdFigs"); if (!el) return;
  const fs = WD.doc.figure_files || [];
  el.innerHTML = fs.length ? fs.map((n) => `<figure class="wd-fig" data-n="${esc(n)}"><img src="${figUrl(n)}"><figcaption>${esc(n)}</figcaption>
    <button class="btn ghost tiny" data-fdel="${esc(n)}">✕</button></figure>`).join("") : `<p class="hint">Скриншоты систем для шагов: по требованиям — у каждого шага с интерфейсом, с рамкой, поле робота видно вместе с окружением.</p>`;
  $$(".wd-fig", el).forEach((f) => f.onclick = (e) => {
    if (e.target.dataset.fdel) return;
    const n = f.dataset.n, line = `![${n.replace(/\.\w+$/, "").replace(/[_-]+/g, " ")}](${n})`;
    navigator.clipboard.writeText(line).then(() => toast("Скопировано: " + line), () => toast(line));
  });
  $$("[data-fdel]", el).forEach((b) => b.onclick = async (e) => {
    e.stopPropagation();
    if (!confirm("Удалить рисунок?")) return;
    try { WD.doc = await DEL(`/api/wdocs/${WD.id}/figures/${encodeURIComponent(b.dataset.fdel)}`); drawFigs(); drawSecs(); } catch (er) { fail(er); }
  });
}

// ---------------------------------------------------------------- разделы
function drawSecs() {
  const box = $("#wdSecs"); if (!box) return;
  box.innerHTML = WD.tpl.sections.map((s) => {
    const x = WD.doc.sections[s.id] || {};
    const off = x.enabled === false;
    return `<section class="card wd-sec ${off ? "off" : ""} ${s.level === 2 ? "l2" : ""}" id="sec-${s.id}" data-sid="${s.id}">
      <div class="card-head">
        <div class="h2">${esc(s.title)}</div><span class="badge b-text">${WD_KIND[s.kind] || s.kind}</span>
        ${x.generated ? `<span class="vt muted" title="Заполнено Qwen">✦ ${esc(x.generated.slice(5))}${x.edited ? " · правка" : ""}</span>` : ""}
        <span class="grow"></span>
        ${s.optional ? `<label class="check"><input type="checkbox" data-en ${off ? "" : "checked"}><b></b>в документе</label>` : ""}
        ${s.hint ? `<button class="btn ghost tiny" data-hint>ⓘ</button>` : ""}
        ${s.ai ? `<button class="btn ghost tiny" data-gen>✦ QWEN</button><button class="btn ghost tiny" data-prompt title="Показать запрос к модели">{ }</button>` : ""}
      </div>
      <p class="hint wd-hint" hidden>${esc(s.hint || "")}</p>
      ${s.intro ? `<p class="hint wd-intro">${esc(s.intro)}</p>` : ""}
      ${(x.questions || []).length ? `<div class="wd-qs">${x.questions.map((q) => `<span class="chip q">? ${esc(q)}</span>`).join("")}</div>` : ""}
      <div class="wd-body">${off ? `<p class="hint">Раздел выключен${s.off_if ? " (не нужен для выбранной платформы)" : ""} — в документ не попадёт.</p>` : secEditor(s, x)}</div>
    </section>`;
  }).join("");
  $$(".wd-sec", box).forEach((el) => bindSec(el, WD.tpl.sections.find((s) => s.id === el.dataset.sid)));
  autosizeAll(box);
}

function cellTA(v, ro, cls = "") { return `<textarea class="auto wd-cell ${cls}" rows="1" ${ro ? "readonly" : ""}>${esc(v ?? "")}</textarea>`; }

function secEditor(s, x) {
  switch (s.kind) {
    case "text": case "steps":
      return `<textarea class="auto wd-text ${s.kind === "steps" || WD.tpl.kind === "build" ? "mono" : ""}" rows="${s.kind === "steps" ? 10 : 4}" placeholder="${esc(s.kind === "steps" ? "1. Робот открывает …, робот переходит на **Шаг 2**.\n   1. Если …, робот переходит на **Шаг 3**.\n   2. Если …, робот …" : "Текст раздела или нажми ✦ QWEN")}">${esc(x.text || "")}</textarea>
        ${WD.tpl.kind === "build" ? `<details class="wd-help"><summary>Разметка</summary><pre>${esc(MARKUP_TIP)}</pre></details>` : ""}`;
    case "table": {
      const fixed = s.fixed_rows ? (s.fixed_col ?? 0) : -1;
      const rows = x.rows || [];
      return `<div class="tbl-wrap"><table class="wd-tbl"><tr>${s.columns.map((c) => `<th>${esc(c)}</th>`).join("")}${s.fixed_rows ? "" : "<th></th>"}</tr>
        ${rows.map((r, i) => `<tr data-r="${i}">${s.columns.map((_, j) => `<td>${s.autonum && j === 0 ? `<span class="vt">${i + 1}</span>` : cellTA(r[j], j === fixed, j === fixed ? "ro" : "")}</td>`).join("")}
          ${s.fixed_rows ? "" : `<td class="wd-rx"><button class="btn ghost tiny" data-rdel="${i}">✕</button></td>`}</tr>`).join("")}</table></div>
        ${s.fixed_rows ? "" : `<div class="wd-tools"><button class="btn ghost tiny" data-radd>+ СТРОКА</button>
          ${s.id === "materials" ? `<button class="btn ghost tiny" data-fromfiles>⇣ ИЗ ПРИЛОЖЕННЫХ ФАЙЛОВ</button>` : ""}</div>`}`;
    }
    case "list":
      return `<textarea class="auto wd-list" rows="4" placeholder="по пункту на строку">${esc((x.items || []).join("\n"))}</textarea><p class="hint">По пункту на строку. «;» и «.» в конце расставятся сами.</p>`;
    case "asis_steps":
      return `<div class="wd-steps">${(x.steps || []).map((st, i) => `<div class="wd-step" data-i="${i}">
          <div class="wd-step-h"><b class="vt">ШАГ ${i + 1}</b><input data-k="title" value="${esc(st.title)}" placeholder="Название шага">
            <input data-k="role" value="${esc(st.role)}" placeholder="Роль" class="role"><button class="btn ghost tiny" data-sdel="${i}">✕</button></div>
          <textarea class="auto" data-k="actions" rows="2" placeholder="Действия пользователя — по строке">${esc((st.actions || []).join("\n"))}</textarea></div>`).join("")}</div>
        <div class="wd-tools"><button class="btn ghost tiny" data-sadd>+ ШАГ</button><span class="hint">Из шагов собираются и таблица «Описание схемы», и пошаговое описание.</span></div>`;
    case "choice":
      return `<div class="seg wd-choice">${(s.options || []).map((o) => `<button data-v="${esc(o)}" class="${x.value === o ? "on" : ""}">${esc(o.toUpperCase())}</button>`).join("")}</div>
        <textarea class="auto wd-text" rows="2" placeholder="Обоснование (необязательно)">${esc(x.text || "")}</textarea>`;
    case "figures":
      return `<div class="wd-figs">${(x.figures || []).map((f, i) => `<figure class="wd-fig big" data-i="${i}"><img src="${figUrl(f.file)}">
          <input value="${esc(f.caption || "")}" placeholder="Подпись" data-cap="${i}"><button class="btn ghost tiny" data-fx="${i}">✕</button></figure>`).join("")}</div>
        <div class="wd-tools">${!s.max || (x.figures || []).length < s.max ? `<button class="btn ghost tiny" data-figadd>+ КАРТИНКА</button><button class="btn ghost tiny" data-figst>+ ИЗ ХРАНИЛИЩА</button>` : ""}
          ${s.caption_word ? `<span class="hint">Подпись: «${esc(s.caption_word)} N – «…»» ${s.align === "left" ? "слева" : "по центру"}, номер жирным.</span>` : ""}</div>`;
    case "fixed":
      return `<p class="hint">Текст переносится из шаблона без изменений.</p>`;
    default:
      return "";
  }
}

const MARKUP_TIP = `1. Робот … переходит на **Шаг 2**.        нумерованный пункт
   1. Если …, робот …                       подпункт (отступ 3 пробела) → a.
      1. Если …                             третий уровень → i.
   > Примечание: …                          курсивом под пунктом, без условий
#Дата регистрации#                           переменная (жирным)
**жирный**  *курсив*
![Окно авторизации](login.png)               рисунок; ссылка: [[figure:login.png]]
Таблица: Маппинг полей {#map}                подпись; ссылка: [[table:map]]
| № | Входные данные | Целевое поле | Способ |
|---|---|---|---|
\`\`\`sql SQL-запрос для получения N          блок «раскрыть → информация»
SELECT **id** FROM t
\`\`\`
Шаблон: Ошибка авторизации                   шаблон уведомления (строки ниже)`;

function bindSec(el, s) {
  const sid = s.id;
  const x = () => WD.doc.sections[sid];
  const en = $("[data-en]", el);
  if (en) en.onchange = () => { x().enabled = en.checked; touch(sid); setTimeout(() => { drawSecs(); drawToc(); }, 50); };
  const hb = $("[data-hint]", el); if (hb) hb.onclick = () => { const h = $(".wd-hint", el); h.hidden = !h.hidden; };
  const gb = $("[data-gen]", el); if (gb) gb.onclick = () => runGen([sid]);
  const pb = $("[data-prompt]", el); if (pb) pb.onclick = async () => {
    const txt = await api("GET", `/api/wdocs/${WD.id}/prompt/${sid}`).catch(fail);
    if (!txt) return;
    const m = modal(`<div class="card-head"><div class="h2">Запрос к Qwen — «${esc(s.title)}»</div><span class="grow"></span>
      <button class="btn ghost tiny" id="prC">КОПИРОВАТЬ</button><button class="btn ghost tiny" id="prX">✕</button></div>
      <p class="hint">Так видит задачу модель. Можно скопировать и отправить в любой другой чат.</p><pre class="wd-prompt">${esc(txt)}</pre>`, "wide");
    $("#prX", m).onclick = closeModal;
    $("#prC", m).onclick = () => navigator.clipboard.writeText(txt).then(() => toast("Скопировано"));
  };
  const ta = $(".wd-text", el);
  if (ta) ta.addEventListener("input", () => { x().text = ta.value; touch(sid); });
  const li = $(".wd-list", el);
  if (li) li.addEventListener("input", () => { x().items = li.value.split("\n").map((v) => v.trim()).filter(Boolean); touch(sid); });
  if (s.kind === "table") {
    const read = () => {
      x().rows = $$("tr[data-r]", el).map((tr) => s.columns.map((_, j) => {
        const td = tr.children[j]; const t = $("textarea", td);
        return t ? t.value : String(+tr.dataset.r + 1);
      }));
    };
    $$(".wd-cell", el).forEach((c) => c.addEventListener("input", () => { read(); touch(sid); }));
    $$("[data-rdel]", el).forEach((b) => b.onclick = () => { read(); x().rows.splice(+b.dataset.rdel, 1); touch(sid); redrawSec(sid); });
    const ra = $("[data-radd]", el); if (ra) ra.onclick = () => { read(); x().rows.push(s.columns.map(() => "")); touch(sid); redrawSec(sid, true); };
    const ff = $("[data-fromfiles]", el); if (ff) ff.onclick = () => {
      read();
      const have = new Set(x().rows.map((r) => r.join(" ")));
      const files = (WD.doc.materials || []).filter((m) => m.kind !== "transcript");
      if (!files.length) return toast("Сначала приложи файлы в «Материалы»", true);
      files.forEach((m) => { if (![...have].some((h) => h.includes(m.name))) { const r = s.columns.map(() => ""); r[s.columns.length > 2 ? 2 : 1] = m.name; x().rows.push(r); } });
      x().rows = x().rows.filter((r) => r.some((c, j) => (j || !s.autonum) && String(c).trim()));
      touch(sid); redrawSec(sid);
      toast("Файлы добавлены — описание можно попросить у ✦ QWEN");
    };
  }
  if (s.kind === "asis_steps") {
    const read = () => { x().steps = $$(".wd-step", el).map((st) => ({ title: $("[data-k=title]", st).value, role: $("[data-k=role]", st).value,
      actions: $("[data-k=actions]", st).value.split("\n").map((v) => v.trim()).filter(Boolean) })); };
    $$(".wd-step input, .wd-step textarea", el).forEach((i) => i.addEventListener("input", () => { read(); touch(sid); }));
    $$("[data-sdel]", el).forEach((b) => b.onclick = () => { read(); x().steps.splice(+b.dataset.sdel, 1); touch(sid); redrawSec(sid); });
    $("[data-sadd]", el).onclick = () => { read(); (x().steps = x().steps || []).push({ title: "", role: "", actions: [] }); touch(sid); redrawSec(sid, true); };
  }
  if (s.kind === "choice") {
    $$(".wd-choice button", el).forEach((b) => b.onclick = () => { x().value = b.dataset.v; $$(".wd-choice button", el).forEach((q) => q.classList.toggle("on", q === b)); touch(sid); });
  }
  if (s.kind === "figures") {
    $$("[data-cap]", el).forEach((i) => i.addEventListener("input", () => { x().figures[+i.dataset.cap].caption = i.value; touch(sid); }));
    $$("[data-fx]", el).forEach((b) => b.onclick = () => { x().figures.splice(+b.dataset.fx, 1); touch(sid); redrawSec(sid); });
    const fa = $("[data-figadd]", el); if (fa) fa.onclick = async () => { const fs = await pickFiles("image/*", !s.max); for (const f of fs) await uploadFig(f, sid, f.name.replace(/\.\w+$/, "")); };
    const fs = $("[data-figst]", el); if (fs) fs.onclick = () => pickFromStorage(async (p) => {
      try { const r = await POST(`/api/wdocs/${WD.id}/figures/from-storage`, { path: p, section: sid, caption: p.split("/").pop().replace(/\.\w+$/, "") }); WD.doc = r.doc; drawSecs(); drawFigs(); }
      catch (e) { fail(e); }
    }, (it) => it.kind === "img", { title: "Картинка из Хранилища", start: "Работа" });
  }
}

function redrawSec(sid, focusLast) {
  const el = document.getElementById("sec-" + sid);
  const s = WD.tpl.sections.find((q) => q.id === sid);
  $(".wd-body", el).innerHTML = secEditor(s, WD.doc.sections[sid]);
  bindSec(el, s);
  autosizeAll(el);
  if (focusLast) {
    const rows = $$("tr[data-r], .wd-step", el);
    const last = rows[rows.length - 1];
    const t = last && $("textarea:not([readonly]), input", last);
    if (t) t.focus();
  }
}

// ---------------------------------------------------------------- Qwen / проверка / вопросы / сборка
async function runGen(sections, onlyEmpty) {
  if (WD.dirty.size) { secSave(); await new Promise((r) => setTimeout(r, 900)); }
  if (!sections && !confirm(onlyEmpty ? "Заполнить через Qwen только пустые разделы?" :
    "Заполнить через Qwen все разделы? Разделы, правленные вручную, не трогаются. Займёт несколько минут.")) return;
  try {
    const j = await POST(`/api/wdocs/${WD.id}/generate`, { sections, only_empty: !!onlyEmpty });
    watchJob(j, () => refreshDoc());
  } catch (e) { fail(e); }
}

async function showCheck() {
  if (WD.dirty.size) { secSave(); await new Promise((r) => setTimeout(r, 900)); }
  const list = await GET(`/api/wdocs/${WD.id}/check`).catch(fail);
  if (!list) return;
  const cnt = (l) => list.filter((x) => x.level === l).length;
  const m = modal(`<div class="card-head"><div class="h2">Проверка${WD.tpl.rules ? " по «Требованиям к оформлению»" : ""}</div><span class="grow"></span><button class="btn ghost tiny" id="ckX">✕</button></div>
    <div class="chips">${Object.entries(LVL).map(([k, [l]]) => `<span class="chip">${l}: ${cnt(k)}</span>`).join("")}</div>
    <div class="wd-check">${list.length ? list.map((x) => `<div class="wd-ck" data-sid="${esc(x.sid || "")}"><span class="badge b-${LVL[x.level][1]}">${LVL[x.level][0]}</span>
      <b>${esc(x.section)}</b><span>${esc(x.msg)}</span></div>`).join("") : `<p class="ok-line">✓ Замечаний нет</p>`}</div>
    <p class="hint">Автопроверка ловит то, что видно по тексту: шаги не от лица робота, условия без «Если», нет перехода на **Шаг N**, списки из одного пункта, переменные без #…#, файлы без расширения, примечания с условиями, дни запуска и праздники, рисунки без файла. Смысл проверяешь ты.</p>`, "wide");
  $("#ckX", m).onclick = closeModal;
  $$(".wd-ck[data-sid]", m).forEach((r) => r.onclick = () => { if (!r.dataset.sid) return; closeModal();
    const t = document.getElementById("sec-" + r.dataset.sid); if (t) { t.scrollIntoView({ behavior: "smooth" }); t.classList.add("flash"); setTimeout(() => t.classList.remove("flash"), 1500); } });
}

async function showQuestions() {
  if (WD.dirty.size) { secSave(); await new Promise((r) => setTimeout(r, 900)); }
  const q = await GET(`/api/wdocs/${WD.id}/questions`).catch(fail);
  if (!q) return;
  const m = modal(`<div class="card-head"><div class="h2">Вопросы к заказчику</div><span class="grow"></span>
      <button class="btn ghost tiny" id="qC">КОПИРОВАТЬ</button><button class="btn ghost tiny" id="qE">▼ В ФАЙЛ</button><button class="btn ghost tiny" id="qX">✕</button></div>
    <p class="hint">Собраны из вопросов Qwen и всех [уточнить: …] в тексте. Отметь заданные — они исчезнут из списка.</p>
    <div class="wd-qlist">${q.groups.length ? q.groups.map((g) => `<div class="h3">${esc(g.title)}</div>${g.items.map((it) =>
      `<label class="check"><input type="checkbox" data-q="${esc(it)}"><b></b>${esc(it)}</label>`).join("")}`).join("") : `<p class="ok-line">✓ Открытых вопросов нет</p>`}</div>`, "wide");
  $("#qX", m).onclick = closeModal;
  $("#qC", m).onclick = () => navigator.clipboard.writeText(q.text).then(() => toast("Скопировано — можно вставить в письмо или Telegram"));
  $("#qE", m).onclick = () => exportDialog({ title: "Вопросы к заказчику", text: q.text.split("\n").slice(2).join("\n"), name: "Вопросы — " + WD.doc.title,
    folder: "Работа/Бэклог вопросов", subtitle: WD.doc.title });
  $$("[data-q]", m).forEach((c) => c.onchange = async () => {
    const done = new Set(WD.doc.questions_done || []);
    c.checked ? done.add(c.dataset.q) : done.delete(c.dataset.q);
    await wdSave({ questions_done: [...done] });
    $("#wdQn").textContent = WD.doc.todo || "";
  });
}

function showBuild() {
  const conf = WD.tpl.kind === "build";
  const m = modal(`<div class="card-head"><div class="h2">Собрать документ</div><span class="grow"></span><button class="btn ghost tiny" id="bX">✕</button></div>
    <div class="seg" id="bFmt"><button data-f="docx" class="on">WORD</button><button data-f="pdf">PDF</button><button data-f="txt">TXT</button>${conf ? `<button data-f="confluence">CONFLUENCE</button>` : ""}</div>
    <p class="hint" id="bHint"></p>
    <label class="check"><input type="checkbox" id="bSt" checked><b></b>Положить копию в Хранилище (${esc(WD.tpl.storage_folder || "Работа")})</label>
    <div style="margin-top:12px;display:flex;gap:10px"><button class="btn big" id="bGo">▼ СОБРАТЬ</button>
      ${conf ? `<button class="btn ghost" id="bWiki">⧉ КОПИРОВАТЬ РАЗМЕТКУ</button>` : ""}</div>
    <div id="bRes" class="wd-bres"></div>`);
  const hints = { docx: WD.tpl.kind === "fill" ? "Заполняется исходный шаблон: обложка, стили, подписи и ссылки на таблицы сохраняются. Незаполненное остаётся подсвеченным жёлтым." :
      "Word по «Требованиям к оформлению»: подписи «Таблица/Рисунок N – «…»», номера жирным, рисунки в рамке, списки «1. a. i.», запросы в рамке «раскрыть».",
    pdf: "PDF через Word (или LibreOffice, если Word нет).", txt: "Простой текст — для письма или чата.",
    confluence: "ZIP: page.txt (вставить: «+» → «Разметка» → Confluence wiki), картинки для вложений, .docx для импорта и инструкция." };
  let fmt = "docx";
  const setF = (f) => { fmt = f; $$("#bFmt button", m).forEach((b) => b.classList.toggle("on", b.dataset.f === f)); $("#bHint", m).textContent = hints[f]; };
  $$("#bFmt button", m).forEach((b) => b.onclick = () => setF(b.dataset.f));
  setF("docx");
  $("#bX", m).onclick = closeModal;
  if (conf) $("#bWiki", m).onclick = async () => {
    const t = await api("GET", `/api/wdocs/${WD.id}/confluence`).catch(fail);
    if (t) navigator.clipboard.writeText(t).then(() => toast("Разметка скопирована. В Confluence: «+» → «Разметка» → вставить. Картинки приложи к странице отдельно."));
  };
  $("#bGo", m).onclick = async () => {
    if (WD.dirty.size) { secSave(); await new Promise((r) => setTimeout(r, 900)); }
    const b = $("#bGo", m); b.disabled = true; b.innerHTML = `<span class="spin">◐</span> СОБИРАЮ`;
    try {
      const r = await POST(`/api/wdocs/${WD.id}/build`, { format: fmt, to_storage: $("#bSt", m).checked });
      $("#bRes", m).innerHTML = `<div class="ok-line">✓ ${esc(r.name)}</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">
          <button class="btn tiny" data-o="open">ОТКРЫТЬ</button><button class="btn ghost tiny" data-o="reveal">В ПАПКЕ</button>
          <a class="btn ghost tiny" href="${r.url}" download>СКАЧАТЬ</a>
          ${r.storage ? `<a class="btn ghost tiny" href="#/files/${encodeURIComponent(r.storage.split("/").slice(0, -1).join("/"))}">В ХРАНИЛИЩЕ</a>` : ""}</div>
        ${(r.warnings || []).length ? `<div class="wd-warn">${r.warnings.map((w) => `<div>⚠ ${esc(w)}</div>`).join("")}</div>` : ""}`;
      $$("[data-o]", m).forEach((x) => x.onclick = () => POST(`/api/wdocs/${WD.id}/out/${encodeURIComponent(r.name)}/open`, { reveal: x.dataset.o === "reveal" }).catch(fail));
      refreshDoc();
    } catch (e) { fail(e); }
    b.disabled = false; b.innerHTML = "▼ СОБРАТЬ";
  };
}

function drawOuts() {
  const el = $("#wdOuts"); if (!el) return;
  const os = WD.doc.outputs || [];
  el.innerHTML = os.length ? os.map((o) => `<div class="att"><b class="k">${/\.pdf$/.test(o.name) ? "PDF" : /\.zip$/.test(o.name) ? "ZIP" : /\.txt$/.test(o.name) ? "TXT" : "W"}</b>
      <span>${esc(o.name)}</span><i>${esc(o.time)} · ${fmtSize(o.size)}</i>
      <button class="btn ghost tiny" data-oo="${esc(o.name)}">ОТКРЫТЬ</button><a class="btn ghost tiny" href="/api/wdocs/${WD.id}/out/${encodeURIComponent(o.name)}" download>СКАЧАТЬ</a></div>`).join("")
    : `<p class="hint">Пока не собирали. Кнопка «▼ СОБРАТЬ» наверху.</p>`;
  $$("[data-oo]", el).forEach((b) => b.onclick = () => POST(`/api/wdocs/${WD.id}/out/${encodeURIComponent(b.dataset.oo)}/open`, {}).catch(fail));
}

// ================================================================= «Работы»: рабочие документы тоже там
const _viewWorksVuz = viewWorks;
viewWorks = async function () {
  await _viewWorksVuz();
  const [docs, tpls] = await Promise.all([GET("/api/wdocs").catch(() => []), GET("/api/wtemplates").catch(() => [])]);
  const tname = Object.fromEntries(tpls.map((t) => [t.slug, t.name]));
  view.insertAdjacentHTML("beforeend", `<div style="height:26px"></div>
    <div class="card-head"><div class="h2">Рабочие документы</div><span class="grow"></span><a class="btn ghost tiny" href="#/wgallery">+ НОВЫЙ</a></div>
    <div class="rows">${docs.length ? docs.map((d) => wdRow(d, tname)).join("") : `<p class="hint">Нет. Шаблоны → вкладка «Работа».</p>`}</div>`);
  bindWdRows(() => viewWorks());
};

// маршруты
routes.push([/^#\/wgallery$/, () => viewWorkGallery()], [/^#\/wdoc\/([^/]+)$/, (a) => viewWDoc(a)]);

route();
