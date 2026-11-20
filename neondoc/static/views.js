/* NEON.DOC — новые разделы: Хранилище, Расшифровка, Чат с файлами, Настройки и темы. */
"use strict";

// ================================================================= общие мелочи
const KIND_IC = { folder: "▰", doc: "W", pdf: "PDF", txt: "TXT", xls: "XLS", ppt: "PPT", img: "◩", bpmn: "⬡", audio: "♪", video: "▶", zip: "ZIP", file: "▤" };
const fmtSize = (n) => n == null ? "" : n < 1024 ? n + " Б" : n < 1048576 ? (n / 1024).toFixed(0) + " КБ" : (n / 1048576).toFixed(1).replace(".", ",") + " МБ";
const fmtTs = (s) => { s = Math.max(0, s || 0); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = Math.floor(s % 60);
  return (h ? h + ":" + String(m).padStart(2, "0") : String(m).padStart(2, "0")) + ":" + String(x).padStart(2, "0"); };
const openFile = (path, reveal) => POST("/api/files/open", { path, reveal: !!reveal }).catch(fail);
const rawUrl = (path, dl) => "/api/files/raw?path=" + encodeURIComponent(path) + (dl ? "&download=1" : "");

function fileResult(el, path) {
  if (!el) return toast("Сохранено: " + path);
  el.innerHTML = `<span class="ok-line">✓ ${esc(path)}</span>
    <button class="btn ghost tiny" data-fr="open">ОТКРЫТЬ</button><button class="btn ghost tiny" data-fr="reveal">В ПАПКЕ</button>
    <a class="btn ghost tiny" href="#/files/${encodeURIComponent(path.split("/").slice(0, -1).join("/"))}">В ХРАНИЛИЩЕ</a>`;
  $("[data-fr=open]", el).onclick = () => openFile(path);
  $("[data-fr=reveal]", el).onclick = () => openFile(path, true);
}

function modal(inner, cls = "") {
  const m = $("#modal");
  m.innerHTML = `<div class="modal small ${cls}">${inner}</div>`;
  m.classList.add("open");
  m.onclick = (e) => { if (e.target === m) closeModal(); };
  return $(".modal", m);
}
const closeModal = () => $("#modal").classList.remove("open");

async function folderOptions(sel) {
  const fs = await GET("/api/files/folders").catch(() => []);
  return fs.filter((f) => !f.startsWith("_Корзина")).map((f) => `<option ${f === sel ? "selected" : ""}>${esc(f)}</option>`).join("");
}

/** Выбор файла или папки из хранилища. */
function pickFromStorage(cb, filter = () => true, opts = {}) {
  const m = modal(`<div class="card-head"><div class="h2">${esc(opts.title || "Хранилище")}</div><span class="grow"></span>
    <button class="btn ghost tiny" id="pkX">✕</button></div>
    <div class="crumbs" id="pkCr"></div><div class="pick-list" id="pkL"></div>
    ${opts.dir ? `<div class="actionbar" style="position:static"><span class="grow"></span><button class="btn" id="pkOk">ВЫБРАТЬ ЭТУ ПАПКУ</button></div>` : ""}`);
  let cur = opts.start || "";
  const go = async (p) => {
    const d = await GET("/api/files/list?path=" + encodeURIComponent(p)).catch(() => null);
    if (!d) return;
    cur = d.path;
    $("#pkCr", m).innerHTML = d.crumbs.map((c) => `<a data-p="${esc(c.path)}">${esc(c.name)}</a>`).join(" / ");
    $$("#pkCr a", m).forEach((a) => a.onclick = () => go(a.dataset.p));
    const items = d.items.filter((it) => it.dir || (!opts.dir && filter(it)));
    $("#pkL", m).innerHTML = items.map((it) => `<div class="pick-it" data-p="${esc(it.path)}" data-d="${it.dir ? 1 : ""}">
      <b class="k k-${it.kind}">${KIND_IC[it.kind] || "▤"}</b><span>${esc(it.name)}</span><i>${it.dir ? "" : fmtSize(it.size)}</i></div>`).join("")
      || `<p class="hint">Пусто</p>`;
    $$(".pick-it", m).forEach((r) => r.onclick = () => { if (r.dataset.d) go(r.dataset.p); else { closeModal(); cb(r.dataset.p); } });
  };
  $("#pkX", m).onclick = closeModal;
  if (opts.dir) $("#pkOk", m).onclick = () => { closeModal(); cb(cur); };
  go(cur);
}

/** Выгрузить текст (ответ Qwen, конспект) в Word / PDF / TXT. */
async function exportDialog({ title = "", text, name, folder = "Входящие", subtitle = "" }) {
  const m = modal(`<div class="card-head"><div class="h2">Выгрузить документ</div><span class="grow"></span><button class="btn ghost tiny" id="exX">✕</button></div>
    <div class="grid">
      <label class="f">ЗАГОЛОВОК В ДОКУМЕНТЕ<input id="exT" value="${esc(title)}"></label>
      <label class="f">ИМЯ ФАЙЛА<input id="exN" value="${esc(name || title || "документ")}"></label>
      <label class="f">ПАПКА<select id="exF">${await folderOptions(folder)}</select></label>
      <div class="seg" id="exFmt"><button data-f="docx" class="on">WORD</button><button data-f="pdf">PDF</button><button data-f="txt">TXT</button></div>
      <p class="hint">Word и PDF оформляются по ГОСТ-правилам: Times New Roman 14, интервал 1,5, отступ 1,25. Таблицы из ответа станут таблицами Word.</p>
      <button class="btn big" id="exGo">▼ ВЫГРУЗИТЬ</button><div id="exRes" class="hint"></div>
    </div>`);
  let fmt = "docx";
  $$("#exFmt button", m).forEach((b) => b.onclick = () => { fmt = b.dataset.f; $$("#exFmt button", m).forEach((x) => x.classList.toggle("on", x === b)); });
  $("#exX", m).onclick = closeModal;
  $("#exGo", m).onclick = async () => {
    const b = $("#exGo", m); b.disabled = true; b.innerHTML = `<span class="spin">◐</span> СОХРАНЯЮ`;
    try {
      const r = await POST("/api/export", { title: $("#exT", m).value, name: $("#exN", m).value, text, format: fmt, folder: $("#exF", m).value, subtitle });
      fileResult($("#exRes", m), r.path);
    } catch (e) { fail(e); }
    b.disabled = false; b.innerHTML = "▼ ВЫГРУЗИТЬ";
  };
}

// ---------------------------------------------------------------- markdown (с таблицами)
function md(t) {
  const blocks = [];
  let s = String(t ?? "").replace(/```(\w*)\n?([\s\S]*?)```/g, (_, l, c) => { blocks.push(`<pre>${esc(c)}</pre>`); return `\u0000${blocks.length - 1}\u0000`; });
  const inl = (x) => esc(x).replace(/`([^`\n]+)`/g, "<code>$1</code>").replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>")
    .replace(/(^|[\s(])\*([^*\n]+)\*(?=[\s).,!?]|$)/g, "$1<i>$2</i>").replace(/\[(\d{1,2}:\d{2}(?::\d{2})?)\]/g, `<span class="tc" data-tc="$1">[$1]</span>`);
  const lines = s.split("\n"), out = [];
  for (let i = 0; i < lines.length;) {
    const ln = lines[i], tr = ln.trim();
    if (/^\u0000\d+\u0000$/.test(tr)) { out.push(blocks[+tr.slice(1, -1)]); i++; continue; }
    if (tr.startsWith("|") && i + 1 < lines.length && /^\|?\s*:?-{2,}/.test(lines[i + 1].trim())) {
      const rows = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        const cells = lines[i].trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
        if (!cells.every((c) => /^:?-{2,}:?$/.test(c) || !c)) rows.push(cells);
        i++;
      }
      out.push(`<div class="mdt"><table>${rows.map((r, k) => `<tr>${r.map((c) => k ? `<td>${inl(c)}</td>` : `<th>${inl(c)}</th>`).join("")}</tr>`).join("")}</table></div>`);
      continue;
    }
    const h = tr.match(/^(#{1,4})\s+(.+)$/);
    if (h) { out.push(`<div class="mdh h${h[1].length}">${inl(h[2])}</div>`); i++; continue; }
    if (/^([-*•]|\d+[.)])\s+/.test(tr)) {
      const ord = /^\d/.test(tr), items = [];
      while (i < lines.length && /^\s*([-*•]|\d+[.)])\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*([-*•]|\d+[.)])\s+/, "")); i++; }
      out.push(`<${ord ? "ol" : "ul"}>${items.map((x) => `<li>${inl(x)}</li>`).join("")}</${ord ? "ol" : "ul"}>`);
      continue;
    }
    if (!tr) { i++; continue; }
    const buf = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|[-*•]\s|\d+[.)]\s|\||\u0000)/.test(lines[i].trim())) { buf.push(inl(lines[i])); i++; }
    out.push(`<p>${buf.join("<br>")}</p>`);
  }
  return out.join("");
}

// ================================================================= ХРАНИЛИЩЕ
let FS = { path: "", sel: new Set(), mode: localStorage.getItem("fs.mode") || "grid", q: "", open: new Set(["ВУЗ", "Работа"]) };

async function viewFiles(path) {
  FS.path = path || ""; FS.sel = new Set();
  const [tree, list] = await Promise.all([GET("/api/files/tree"), GET("/api/files/list?path=" + encodeURIComponent(FS.path))]);
  view.innerHTML = `
    <div class="page-head"><h1 class="h1">Хранилище<small>Все файлы проекта по папкам: ВУЗ → предмет → тип работы, Работа → тип документа</small></h1>
      <span class="grow"></span>
      <input id="fsQ" class="search" placeholder="⌕ Поиск по именам и тексту документов…" value="${esc(FS.q)}">
    </div>
    <div class="fs">
      <aside class="fs-tree card" id="fsTree"></aside>
      <section class="fs-main">
        <div class="fs-bar">
          <div class="crumbs">${list.crumbs.map((c) => `<a href="#/files/${encodeURIComponent(c.path)}" data-drop="${esc(c.path)}">${esc(c.name)}</a>`).join("<i>/</i>")}</div>
          <span class="grow"></span>
          <button class="btn tiny" id="fsUp">⇪ ЗАГРУЗИТЬ</button>
          <button class="btn ghost tiny" id="fsMk">+ ПАПКА</button>
          <button class="btn ghost tiny" id="fsOpenDir" title="Открыть эту папку в Проводнике">▣ ПРОВОДНИК</button>
          <div class="seg small"><button data-m="grid" class="${FS.mode === "grid" ? "on" : ""}">▦</button><button data-m="list" class="${FS.mode === "list" ? "on" : ""}">☰</button></div>
        </div>
        <div class="fs-selbar" id="fsSel" hidden></div>
        <div class="fs-items ${FS.mode}" id="fsItems"></div>
      </section>
      <aside class="fs-prev card" id="fsPrev"><div class="empty-prev">Выбери файл, чтобы увидеть его здесь.<br><br>Перетащи файлы из Проводника прямо в окно — они загрузятся в текущую папку.<br><br>Файлы можно перетаскивать на папки слева.</div></aside>
    </div>`;
  drawTree(tree);
  drawItems(list.items);
  $("#fsUp").onclick = async () => uploadTo(FS.path, await pickFiles(""));
  $("#fsMk").onclick = async () => { const n = prompt("Название папки:"); if (n) { await POST("/api/files/mkdir", { path: FS.path, name: n }).catch(fail); viewFiles(FS.path); } };
  $("#fsOpenDir").onclick = () => openFile(FS.path);
  $$(".fs-bar .seg button").forEach((b) => b.onclick = () => { FS.mode = b.dataset.m; localStorage.setItem("fs.mode", FS.mode); viewFiles(FS.path); });
  const main = $(".fs-main");
  main.ondragover = (e) => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); main.classList.add("over"); } };
  main.ondragleave = (e) => { if (!main.contains(e.relatedTarget)) main.classList.remove("over"); };
  main.ondrop = (e) => { if (!e.dataTransfer.files.length) return; e.preventDefault(); main.classList.remove("over"); uploadTo(FS.path, [...e.dataTransfer.files]); };
  bindDropTargets(view);
  const q = $("#fsQ");
  q.oninput = debounce(async () => { FS.q = q.value.trim(); if (!FS.q) return viewFiles(FS.path);
    const r = await GET("/api/files/search?q=" + encodeURIComponent(FS.q)); drawItems(r, true); }, 350);
  if (FS.q) q.oninput();
}

function drawTree(t) {
  const node = (n, depth) => {
    const has = n.children.length, open = FS.open.has(n.path) || depth === 0 || FS.path.startsWith(n.path + "/") || FS.path === n.path;
    return `<div class="tn ${FS.path === n.path ? "on" : ""} ${n.name.startsWith("_") ? "trash" : ""}" style="--d:${depth}" data-p="${esc(n.path)}" data-drop="${esc(n.path)}">
      <b class="tw" data-tw="${esc(n.path)}">${has ? (open ? "▾" : "▸") : "·"}</b><span>${esc(n.name)}</span>${n.files ? `<i>${n.files}</i>` : ""}</div>
      ${has && open ? n.children.map((c) => node(c, depth + 1)).join("") : ""}`;
  };
  $("#fsTree").innerHTML = node(t, 0);
  $$("#fsTree .tn").forEach((el) => el.onclick = (e) => {
    if (e.target.dataset.tw !== undefined && e.target.textContent !== "·") {
      const p = e.target.dataset.tw; FS.open.has(p) ? FS.open.delete(p) : FS.open.add(p);
      GET("/api/files/tree").then(drawTree).then(() => bindDropTargets($("#fsTree"))); return;
    }
    location.hash = "#/files/" + encodeURIComponent(el.dataset.p);
  });
}

function drawItems(items, search) {
  const el = $("#fsItems");
  if (!items.length) { el.innerHTML = `<div class="empty-state"><div class="big">${search ? "НИЧЕГО" : "ПУСТО"}</div><p>${search ? "Попробуй другие слова" : "Перетащи сюда файлы или нажми «Загрузить»"}</p></div>`; return; }
  el.innerHTML = items.map((it) => `<div class="fi ${it.dir ? "dir" : ""}" draggable="true" data-p="${esc(it.path)}" data-d="${it.dir ? 1 : ""}" ${it.dir ? `data-drop="${esc(it.path)}"` : ""}>
      <div class="th">${it.kind === "img" ? `<img loading="lazy" src="${rawUrl(it.path)}&t=${it.ts}">` : `<b class="k k-${it.kind}">${KIND_IC[it.kind] || "▤"}</b>`}</div>
      <div class="nm" title="${esc(it.name)}">${esc(it.name)}</div>
      <div class="mt">${search ? esc(it.path.split("/").slice(0, -1).join(" / ")) : it.dir ? "папка" : fmtSize(it.size) + " · " + it.mtime}</div>
      ${it.snippet ? `<div class="sn">…${esc(it.snippet)}…</div>` : ""}</div>`).join("");
  $$(".fi", el).forEach((f) => {
    f.onclick = (e) => {
      if (e.ctrlKey || e.metaKey) { FS.sel.has(f.dataset.p) ? FS.sel.delete(f.dataset.p) : FS.sel.add(f.dataset.p); }
      else FS.sel = new Set([f.dataset.p]);
      $$(".fi", el).forEach((x) => x.classList.toggle("on", FS.sel.has(x.dataset.p)));
      selBar();
      if (!f.dataset.d && FS.sel.size === 1) preview(f.dataset.p);
    };
    f.ondblclick = () => { if (f.dataset.d) location.hash = "#/files/" + encodeURIComponent(f.dataset.p); else openFile(f.dataset.p); };
    f.ondragstart = (e) => { if (!FS.sel.has(f.dataset.p)) FS.sel = new Set([f.dataset.p]); e.dataTransfer.setData("text/neondoc-paths", JSON.stringify([...FS.sel])); };
  });
  bindDropTargets(el);
}

function bindDropTargets(root) {
  $$("[data-drop]", root).forEach((t) => {
    t.ondragover = (e) => { if (e.dataTransfer.types.includes("text/neondoc-paths")) { e.preventDefault(); t.classList.add("drop-on"); } };
    t.ondragleave = () => t.classList.remove("drop-on");
    t.ondrop = async (e) => {
      const raw = e.dataTransfer.getData("text/neondoc-paths"); if (!raw) return;
      e.preventDefault(); e.stopPropagation(); t.classList.remove("drop-on");
      try { await POST("/api/files/move", { paths: JSON.parse(raw), dest: t.dataset.drop }); toast("Перемещено"); viewFiles(FS.path); } catch (er) { fail(er); }
    };
  });
}

function selBar() {
  const b = $("#fsSel"); if (!b) return;
  b.hidden = FS.sel.size < 2;
  b.innerHTML = `<b>Выбрано: ${FS.sel.size}</b><button class="btn ghost tiny" id="sMove">↦ ПЕРЕМЕСТИТЬ</button><button class="btn danger ghost tiny" id="sDel">✕ В КОРЗИНУ</button>`;
  if (FS.sel.size < 2) return;
  $("#sMove").onclick = () => pickFromStorage(async (d) => { await POST("/api/files/move", { paths: [...FS.sel], dest: d }).catch(fail); viewFiles(FS.path); }, null, { dir: true, title: "Куда переместить" });
  $("#sDel").onclick = async () => { await POST("/api/files/delete", { paths: [...FS.sel] }).catch(fail); viewFiles(FS.path); };
}

async function uploadTo(path, files) {
  if (!files.length) return;
  const fd = new FormData(); fd.append("path", path); files.forEach((f) => fd.append("items", f));
  try { await api("POST", "/api/files/upload", fd, true); toast(`Загружено: ${files.length}`); viewFiles(path); } catch (e) { fail(e); }
}

async function preview(path) {
  const el = $("#fsPrev"); if (!el) return;
  const name = path.split("/").pop(), ext = (name.match(/\.\w+$/) || [""])[0].toLowerCase();
  const isImg = /\.(png|jpe?g|webp|gif|bmp)$/.test(ext), isPdf = ext === ".pdf", isMedia = /\.(mp3|wav|m4a|ogg|opus|flac|aac|mp4|mov|mkv|webm|avi|m4v)$/.test(ext);
  const isVideo = /\.(mp4|mov|mkv|webm|avi|m4v)$/.test(ext);
  el.innerHTML = `<div class="pv-name">${esc(name)}</div>
    <div class="pv-body">${isImg ? `<img src="${rawUrl(path)}">` : isPdf ? `<iframe src="${rawUrl(path)}"></iframe>`
      : isMedia ? (isVideo ? `<video controls src="${rawUrl(path)}"></video>` : `<audio controls src="${rawUrl(path)}"></audio>`)
      : `<pre class="pv-text" id="pvText">загрузка текста…</pre>`}</div>
    <div class="pv-acts">
      <button class="btn tiny" data-a="open">▶ ОТКРЫТЬ</button><button class="btn ghost tiny" data-a="reveal">В ПАПКЕ</button>
      <a class="btn ghost tiny" href="${rawUrl(path, 1)}" download>▼ СКАЧАТЬ</a>
      <button class="btn ghost tiny" data-a="ask">✦ СПРОСИТЬ QWEN</button>
      ${isMedia ? `<button class="btn ghost tiny" data-a="tr">♪ РАСШИФРОВАТЬ</button>` : ""}
      ${isImg ? `<button class="btn ghost tiny" data-a="an">▢ РАЗМЕТИТЬ</button>` : ""}
      ${!isImg && !isMedia ? `<span class="pv-conv">в <button class="btn ghost tiny" data-c="pdf">PDF</button><button class="btn ghost tiny" data-c="docx">WORD</button><button class="btn ghost tiny" data-c="txt">TXT</button></span>` : ""}
      <button class="btn ghost tiny" data-a="ren">✎ ИМЯ</button><button class="btn ghost tiny" data-a="mv">↦ ПЕРЕМЕСТИТЬ</button>
      <button class="btn danger ghost tiny" data-a="del">✕</button>
    </div><div id="pvRes" class="hint"></div>`;
  if ($("#pvText")) GET("/api/files/text?path=" + encodeURIComponent(path)).then((r) => { $("#pvText").textContent = r.text.slice(0, 20000) || "(нет текста)"; }).catch(() => ($("#pvText").textContent = "—"));
  const act = {
    open: () => openFile(path), reveal: () => openFile(path, true),
    ask: async () => { const id = newChatId(); await POST(`/api/chats/${id}/files/link`, { path }).catch(fail); CHAT = null; location.hash = "#/chat/" + id; },
    tr: async () => { try { const r = await POST("/api/transcripts/from-storage", { path }); location.hash = "#/transcribe/" + r.id; } catch (e) { fail(e); } },
    an: async () => { location.hash = "#/annot"; const proj = await GET("/api/annot/project?path=" + encodeURIComponent(path)).catch(() => null);
      setTimeout(() => ANNOT.view({ src: rawUrl(path), project: proj }), 50); },
    ren: async () => { const n = prompt("Новое имя:", name); if (n && n !== name) { await POST("/api/files/rename", { path, name: n }).catch(fail); viewFiles(FS.path); } },
    mv: () => pickFromStorage(async (d) => { await POST("/api/files/move", { paths: [path], dest: d }).catch(fail); viewFiles(FS.path); }, null, { dir: true, title: "Куда переместить" }),
    del: async () => { await POST("/api/files/delete", { paths: [path] }).catch(fail); toast("Перенесено в _Корзина"); viewFiles(FS.path); },
  };
  $$("[data-a]", el).forEach((b) => b.onclick = act[b.dataset.a]);
  $$("[data-c]", el).forEach((b) => b.onclick = async () => {
    try { const j = await POST("/api/files/convert", { path, format: b.dataset.c });
      watchJob(j, (r) => { if (r.status === "done" && r.result) { fileResult($("#pvRes"), r.result.path); if (location.hash.startsWith("#/files")) drawItemsRefresh(); } }); } catch (e) { fail(e); }
  });
}
const drawItemsRefresh = async () => { const l = await GET("/api/files/list?path=" + encodeURIComponent(FS.path)); drawItems(l.items); };

// ================================================================= РАСШИФРОВКА
const SPK_COLORS = ["#ff2e88", "#22e5ff", "#ffd319", "#39ff9f", "#ff7a18", "#9d4dff", "#4f8cff", "#e3622a"];
let TR = null;

async function viewTranscribe(id) {
  if (id) return viewTranscript(id);
  const [list, s] = await Promise.all([GET("/api/transcripts"), GET("/api/settings")]);
  view.innerHTML = `
    <div class="page-head"><h1 class="h1">Расшифровка<small>Аудио и видео → текст с таймкодами и участниками. Всё локально: Whisper + разделение голосов</small></h1></div>
    <div class="card glow">
      <div class="drop big-drop" id="trDrop"><div class="big">♪ ▶</div>Перетащи запись встречи, созвона, лекции: mp3, wav, m4a, ogg, mp4, mov, mkv, webm…<br>или нажми, чтобы выбрать файл</div>
      <div class="grid g4" style="margin-top:16px">
        <label class="f">ЯЗЫК<select id="trLang">${[["ru", "русский"], ["en", "английский"], ["auto", "определить сам"]].map(([k, l]) => `<option value="${k}" ${s.transcribe_language === k ? "selected" : ""}>${l}</option>`).join("")}</select></label>
        <label class="f">УЧАСТНИКОВ<select id="trSpk"><option value="0">определить сам</option>${[1, 2, 3, 4, 5, 6, 8].map((n) => `<option value="${n}">${n}</option>`).join("")}</select></label>
        <label class="f">МОДЕЛЬ WHISPER<select id="trModel">${["large-v3-turbo", "large-v3", "medium", "small"].map((x) => `<option ${x === s.whisper_model ? "selected" : ""}>${x}</option>`).join("")}</select></label>
        <label class="check" style="align-self:end;padding-bottom:10px"><input type="checkbox" id="trDia" ${s.diarize ? "checked" : ""}><b></b>Делить по участникам</label>
        <label class="f span4">СЛОВАРЬ (имена, термины, аббревиатуры — Whisper будет писать их правильно)<input id="trGl" value="${esc(s.glossary || "")}" placeholder="RPA, BPMN, OCR, фамилии участников, названия систем"></label>
      </div>
    </div>
    <div style="height:22px"></div>
    <div class="rows">${list.length ? list.map((t) => `<div class="row tr-row" data-id="${t.id}">
        <div><div class="t">${t.video ? "▶" : "♪"} ${esc(t.title)}</div><div class="s">${Object.values(t.speakers || {}).map(esc).join(", ") || "—"}</div></div>
        <div class="s">${esc(t.created)}</div>
        <div><span class="badge b-${t.status === "done" ? "done" : t.status === "error" ? "plan" : "text"}">${{ done: "готово", running: "идёт", error: "ошибка", new: "в очереди" }[t.status] || t.status}</span></div>
        <div class="m">${t.duration ? fmtTs(t.duration) : "—"}</div><div class="m">${Object.keys(t.speakers || {}).length || ""}${Object.keys(t.speakers || {}).length ? " чел." : ""}</div>
        <button class="btn danger ghost tiny" data-del="${t.id}">✕</button></div>`).join("")
      : `<div class="empty-state"><div class="big">ЗАПИСЕЙ НЕТ</div><p>Первая расшифровка скачает Whisper (~1,6 ГБ) и модели голосов (~33 МБ) — один раз.</p></div>`}</div>`;
  const dz = $("#trDrop");
  const go = async (files) => {
    if (!files.length) return;
    const opts = { language: $("#trLang").value, speakers: +$("#trSpk").value, diarize: $("#trDia").checked, model: $("#trModel").value, glossary: $("#trGl").value };
    PUT("/api/settings", { glossary: opts.glossary, transcribe_language: opts.language, diarize: opts.diarize }).catch(() => {});
    for (const f of files) {
      const fd = new FormData(); fd.append("file", f); fd.append("title", f.name.replace(/\.\w+$/, "")); fd.append("opts", JSON.stringify(opts));
      dz.innerHTML = `<span class="spin">◐</span> Загружаю ${esc(f.name)} (${fmtSize(f.size)})…`;
      try { const r = await api("POST", "/api/transcripts", fd, true);
        if (r.job && r.job.id) watchJob(r.job, () => route()); else if (r.job && r.job.error) toast(r.job.error, true);
        location.hash = "#/transcribe/" + r.id; } catch (e) { fail(e); }
    }
  };
  dz.onclick = async () => go(await pickFiles("audio/*,video/*", false));
  dz.ondragover = (e) => { e.preventDefault(); dz.classList.add("over"); };
  dz.ondragleave = () => dz.classList.remove("over");
  dz.ondrop = (e) => { e.preventDefault(); dz.classList.remove("over"); go([...e.dataTransfer.files]); };
  $$(".tr-row").forEach((r) => r.onclick = (e) => { if (!e.target.dataset.del) location.hash = "#/transcribe/" + r.dataset.id; });
  $$("[data-del]").forEach((b) => b.onclick = async (e) => { e.stopPropagation(); if (confirm("Удалить расшифровку и копию записи?")) { await DEL("/api/transcripts/" + b.dataset.del); viewTranscribe(); } });
}

async function viewTranscript(id) {
  TR = await GET("/api/transcripts/" + id);
  const works = await GET("/api/works").catch(() => []);
  const spk = Object.keys(TR.speakers || {});
  const col = (k) => SPK_COLORS[(parseInt(k.slice(1), 10) - 1) % SPK_COLORS.length];
  const running = TR.status === "running" || TR.status === "new";
  view.innerHTML = `
    <div class="page-head"><h1 class="h1 work-title"><input class="title-in" id="tTitle" value="${esc(TR.title)}"><small>${esc(TR.created)} · ${TR.duration ? fmtTs(TR.duration) : "…"} · ${TR.segments.length} реплик</small></h1>
      <span class="grow"></span><a class="btn ghost tiny" href="#/transcribe">← ВСЕ ЗАПИСИ</a>
      <button class="btn ghost tiny" id="tRerun">↻ РАСШИФРОВАТЬ ЗАНОВО</button></div>
    <div class="work tr-work">
      <div>
        <div class="card tr-player">${TR.video ? `<video id="tMedia" controls src="/api/transcripts/${id}/media"></video>` : `<audio id="tMedia" controls src="/api/transcripts/${id}/media"></audio>`}
          <div class="tr-tools"><input id="tFind" class="search" placeholder="⌕ найти в тексте"><span class="hint" id="tFound"></span><span class="grow"></span>
            <label class="check"><input type="checkbox" id="tFollow" checked><b></b>Следить за воспроизведением</label></div>
          <div class="spk-row" id="tSpk">${spk.map((k) => `<label class="spk" style="--c:${col(k)}"><b></b><input data-spk="${k}" value="${esc(TR.speakers[k])}"></label>`).join("")}
            ${spk.length ? `<span class="hint">переименуй участников — имена сразу появятся в тексте и выгрузках</span>` : ""}</div>
        </div>
        ${running ? `<div class="card"><div class="hero-big" style="font-size:14px"><span class="spin">◐</span> Идёт расшифровка — ход виден в консоли внизу</div></div>` : ""}
        ${TR.status === "error" ? `<div class="card review"><b>Расшифровка не удалась.</b> Причина — в консоли. Попробуй «Расшифровать заново» или другую модель Whisper в настройках.</div>` : ""}
        <div class="card segs" id="tSegs">${TR.segments.map((s, i) => `<div class="seg-row" data-i="${i}" style="--c:${col(s.speaker)}">
            <button class="tc-btn" data-t="${s.start}">${fmtTs(s.start)}</button>
            <select data-sp="${i}">${spk.map((k) => `<option value="${k}" ${k === s.speaker ? "selected" : ""}>${esc(TR.speakers[k])}</option>`).join("")}</select>
            <textarea class="read auto" rows="1" data-tx="${i}">${esc(s.text)}</textarea></div>`).join("") || (running ? "" : `<p class="hint">Текста нет.</p>`)}</div>
      </div>
      <aside class="rail">
        <div class="card"><div class="h2">Qwen по записи</div>
          <div class="grid">${[["summary", "Конспект"], ["protocol", "Протокол встречи"], ["questions", "Вопросы и неясности"], ["requirements", "Требования + пограничные случаи"], ["asis", "Процесс AS-IS (для BPMN)"]]
            .map(([k, l]) => `<button class="btn ghost tiny" data-ai="${k}">✦ ${l}</button>`).join("")}
            <textarea id="tCustom" rows="2" placeholder="Свой запрос: «найди, что говорили про сроки»…"></textarea>
            <button class="btn tiny" data-ai="custom">▶ СПРОСИТЬ</button>
            <button class="btn ghost tiny" id="tChat">✦ ОБСУДИТЬ В ЧАТЕ</button></div></div>
        <div class="card"><div class="h2">Выгрузить расшифровку</div>
          <div class="chips" style="gap:14px"><label class="check"><input type="checkbox" id="xTc" checked><b></b>Таймкоды</label>
            <label class="check"><input type="checkbox" id="xSp" checked><b></b>Участники</label></div>
          <label class="f" style="margin-top:10px">ПАПКА<select id="xF">${await folderOptions("Работа/Встречи и расшифровки")}</select></label>
          <div style="display:flex;gap:8px;margin-top:10px"><button class="btn tiny" data-x="docx">WORD</button><button class="btn ghost tiny" data-x="pdf">PDF</button><button class="btn ghost tiny" data-x="txt">TXT</button></div>
          <div id="xRes" class="hint" style="margin-top:8px"></div></div>
        <div class="card"><div class="h2">В работу</div>
          <p class="hint">Расшифровка ляжет во вложения работы — модель учтёт её в плане и тексте.</p>
          <select id="wSel"><option value="">выбери работу…</option>${works.map((w) => `<option value="${w.id}">${esc(w.title)}</option>`).join("")}</select>
          <button class="btn ghost tiny" id="wGo" style="margin-top:8px">◆ ДОБАВИТЬ</button></div>
        <div id="tNotes">${TR.notes.map((n, i) => `<div class="card note"><div class="card-head"><div class="h2">${esc(n.name.replace(/^\d{6}\s*/, ""))}</div><span class="grow"></span>
            <button class="btn ghost tiny" data-nx="${i}">▼</button><button class="btn ghost tiny" data-nw="${i}" title="В работу">◆</button><button class="btn danger ghost tiny" data-nd="${i}">✕</button></div>
            <div class="md">${md(n.text.replace(/^# .+\n+/, ""))}</div></div>`).join("")}</div>
      </aside>
    </div>`;
  autosizeAll(view);
  const media = $("#tMedia");
  const seek = (t) => { media.currentTime = t; media.play().catch(() => {}); };
  $$(".tc-btn").forEach((b) => b.onclick = () => seek(+b.dataset.t));
  view.addEventListener("click", (e) => { const tc = e.target.closest(".tc"); if (tc) { const p = tc.dataset.tc.split(":").map(Number); seek(p.length === 3 ? p[0] * 3600 + p[1] * 60 + p[2] : p[0] * 60 + p[1]); } });
  let lastI = -1;
  media.ontimeupdate = () => {
    const t = media.currentTime, i = TR.segments.findIndex((s, k) => t >= s.start && (k === TR.segments.length - 1 || t < TR.segments[k + 1].start));
    if (i === lastI) return; lastI = i;
    $$(".seg-row").forEach((r) => r.classList.toggle("now", +r.dataset.i === i));
    if (i >= 0 && $("#tFollow").checked) $(`.seg-row[data-i="${i}"]`).scrollIntoView({ block: "center", behavior: "smooth" });
  };
  const save = debounce(() => PUT("/api/transcripts/" + id, { title: TR.title, speakers: TR.speakers, segments: TR.segments }).catch(fail), 600);
  $("#tTitle").oninput = (e) => { TR.title = e.target.value; save(); };
  $$("[data-spk]").forEach((inp) => inp.oninput = () => { TR.speakers[inp.dataset.spk] = inp.value;
    $$(`select[data-sp] option[value="${inp.dataset.spk}"]`).forEach((o) => (o.textContent = inp.value)); save(); });
  $$("[data-sp]").forEach((sel) => sel.onchange = () => { const i = +sel.dataset.sp; TR.segments[i].speaker = sel.value;
    sel.closest(".seg-row").style.setProperty("--c", col(sel.value)); save(); });
  $$("[data-tx]").forEach((ta) => ta.oninput = () => { TR.segments[+ta.dataset.tx].text = ta.value; save(); });
  $("#tFind").oninput = debounce((e) => {
    const q = e.target.value.trim().toLowerCase(); let n = 0, first = null;
    $$(".seg-row").forEach((r) => { const hit = q && TR.segments[+r.dataset.i].text.toLowerCase().includes(q); r.classList.toggle("hit", hit); if (hit) { n++; first = first || r; } });
    $("#tFound").textContent = q ? `найдено: ${n}` : ""; if (first) first.scrollIntoView({ block: "center" });
  }, 250);
  $("#tRerun").onclick = () => {
    const m = modal(`<div class="h2">Расшифровать заново</div><div class="grid">
      <label class="f">УЧАСТНИКОВ<select id="rrS"><option value="0">определить сам</option>${[1, 2, 3, 4, 5, 6, 8].map((n) => `<option ${n === spk.length ? "selected" : ""}>${n}</option>`).join("")}</select></label>
      <label class="f">МОДЕЛЬ<select id="rrM">${["large-v3-turbo", "large-v3", "medium", "small"].map((x) => `<option>${x}</option>`).join("")}</select></label>
      <label class="check"><input type="checkbox" id="rrD" checked><b></b>Делить по участникам</label>
      <p class="hint">Правки текста и имена участников будут заменены новым результатом (имена участников S1, S2… сохранятся).</p>
      <button class="btn" id="rrGo">▶ ЗАПУСТИТЬ</button></div>`);
    $("#rrGo", m).onclick = async () => { closeModal(); try { watchJob(await POST(`/api/transcripts/${id}/run`, { speakers: +$("#rrS", m).value, model: $("#rrM", m).value, diarize: $("#rrD", m).checked }), () => route()); route(); } catch (e) { fail(e); } };
  };
  $$("[data-ai]").forEach((b) => b.onclick = async () => {
    const action = b.dataset.ai, custom = $("#tCustom").value.trim();
    if (action === "custom" && !custom) return toast("Напиши запрос", true);
    try { watchJob(await POST(`/api/transcripts/${id}/ai`, { action, custom }), () => route()); } catch (e) { fail(e); }
  });
  $("#tChat").onclick = async () => { const cid = newChatId(); await POST(`/api/chats/${cid}/files/link`, { transcript_id: id }).catch(fail); CHAT = null; location.hash = "#/chat/" + cid; };
  $$("[data-x]").forEach((b) => b.onclick = async () => {
    try { const r = await POST(`/api/transcripts/${id}/export`, { format: b.dataset.x, timecodes: $("#xTc").checked, speakers: $("#xSp").checked, folder: $("#xF").value });
      fileResult($("#xRes"), r.path); } catch (e) { fail(e); }
  });
  $("#wGo").onclick = async () => { const w = $("#wSel").value; if (!w) return toast("Выбери работу", true);
    try { await POST(`/api/transcripts/${id}/to-work`, { work_id: w }); toast("Добавлено во вложения работы"); } catch (e) { fail(e); } };
  $$("[data-nx]").forEach((b) => b.onclick = () => { const n = TR.notes[+b.dataset.nx];
    exportDialog({ title: `${TR.title} — ${n.name.replace(/^\d{6}\s*/, "")}`, text: n.text.replace(/^# .+\n+/, ""), folder: "Работа/Встречи и расшифровки" }); });
  $$("[data-nw]").forEach((b) => b.onclick = async () => { const w = $("#wSel").value; if (!w) return toast("Сначала выбери работу в блоке «В работу»", true);
    await POST(`/api/transcripts/${id}/to-work`, { work_id: w, note: TR.notes[+b.dataset.nw].name }).catch(fail); toast("Добавлено в работу"); });
  $$("[data-nd]").forEach((b) => b.onclick = async () => { await DEL(`/api/transcripts/${id}/notes/${encodeURIComponent(TR.notes[+b.dataset.nd].name)}`); route(); });
  if (running) resumeJob();
}

// ================================================================= ЧАТ
let CHAT = null;
const newChatId = () => "c" + Date.now().toString(36);
function newChat(workId) {
  const id = newChatId();
  CHAT = { id, title: "", messages: [], work_id: workId || null, files: [], think: false };
  location.hash = "#/chat/" + id;
}

async function viewChat(arg) {
  if (arg && arg.startsWith("new")) { const w = new URLSearchParams(arg.split("?")[1] || "").get("work"); return newChat(w); }
  const id = arg;
  const [chats, works, settings] = await Promise.all([GET("/api/chats"), GET("/api/works"), GET("/api/settings")]);
  if (!id) { if (chats.length) { location.hash = "#/chat/" + chats[0].id; return; } return newChat(); }
  if (!CHAT || CHAT.id !== id) { CHAT = await GET("/api/chats/" + id); CHAT.think = CHAT.think ?? settings.chat_think; }
  CHAT.id = id;
  CHAT.files = await GET(`/api/chats/${id}/files`).catch(() => []);
  view.innerHTML = `
    <div class="page-head"><h1 class="h1">Чат с Qwen<small>Прикрепляй документы, таблицы, картинки, аудио и видео — Qwen ответит по ним</small></h1></div>
    <div class="chat">
      <div class="chat-list"><button class="btn cyan" id="cNew">+ НОВЫЙ ЧАТ</button>
        <input id="cSearch" class="search" placeholder="⌕ поиск чатов">
        <div id="cItems">${chats.map((c) => `<div class="chat-item ${c.id === id ? "on" : ""}" data-id="${c.id}"><span class="t">${esc(c.title)}</span>
          <span class="d">${c.updated}</span><button class="btn danger ghost tiny" data-del="${c.id}">✕</button></div>`).join("")}
        ${chats.some((c) => c.id === id) ? "" : `<div class="chat-item on"><span class="t">Новый чат</span></div>`}</div></div>
      <div class="chat-main" id="chatMain">
        <div class="msgs" id="msgs"></div>
        <div class="attach" id="attach"></div>
        <div class="quick" id="quick"></div>
        <div class="composer">
          <textarea id="cIn" placeholder="Сообщение… Enter — отправить, Shift+Enter — новая строка. Файлы можно перетащить или вставить Ctrl+V"></textarea>
          <div class="ctl">
            <div class="ctl-row"><button class="btn" id="cSend">▶ ОТПРАВИТЬ</button><span id="cMic"></span></div>
            <div class="ctl-row">
              <button class="btn ghost tiny" id="cAtt" title="Прикрепить файл">📎 ФАЙЛ</button>
              <button class="btn ghost tiny" id="cStore" title="Из хранилища">▤</button>
              <button class="btn ghost tiny" id="cTr" title="Готовая расшифровка">♪</button>
              <label class="check tiny" title="Модель сначала подумает (медленнее, но точнее на сложных вопросах)"><input type="checkbox" id="cThink" ${CHAT.think ? "checked" : ""}><b></b>Думать</label>
            </div>
            <select id="cWork" title="Контекст"><option value="">без контекста работы</option>
              ${works.map((w) => `<option value="${w.id}" ${CHAT.work_id === w.id ? "selected" : ""}>⌁ ${esc(w.title)}</option>`).join("")}</select>
          </div>
        </div>
      </div>
    </div>`;
  $("#cMic").replaceWith(micButton(() => $("#cIn")));
  drawMsgs(); drawAttach();
  $("#cNew").onclick = () => newChat();
  $("#cSearch").oninput = (e) => { const q = e.target.value.toLowerCase(); $$(".chat-item[data-id]").forEach((c) => (c.hidden = q && !c.textContent.toLowerCase().includes(q))); };
  $$(".chat-item[data-id]").forEach((c) => c.onclick = (e) => { if (!e.target.dataset.del) location.hash = "#/chat/" + c.dataset.id; });
  $$(".chat-item [data-del]").forEach((b) => b.onclick = async () => { if (!confirm("Удалить чат вместе с файлами?")) return; await DEL("/api/chats/" + b.dataset.del); CHAT = null; location.hash = "#/chat"; });
  $("#cWork").onchange = (e) => { CHAT.work_id = e.target.value || null; saveChat(); };
  $("#cThink").onchange = (e) => { CHAT.think = e.target.checked; saveChat(); };
  $("#cAtt").onclick = async () => attachFiles(await pickFiles(""));
  $("#cStore").onclick = () => pickFromStorage(async (path) => { const r = await POST(`/api/chats/${CHAT.id}/files/link`, { path }).catch(fail); afterAttach(r); });
  $("#cTr").onclick = async () => {
    const list = (await GET("/api/transcripts")).filter((t) => t.status === "done");
    if (!list.length) return toast("Готовых расшифровок нет — сделай в разделе «Расшифровка»", true);
    const m = modal(`<div class="h2">Прикрепить расшифровку</div><div class="pick-list">${list.map((t) => `<div class="pick-it" data-t="${t.id}"><b class="k k-audio">♪</b><span>${esc(t.title)}</span><i>${fmtTs(t.duration)}</i></div>`).join("")}</div>`);
    $$("[data-t]", m).forEach((r) => r.onclick = async () => { closeModal(); afterAttach(await POST(`/api/chats/${CHAT.id}/files/link`, { transcript_id: r.dataset.t })); });
  };
  const inp = $("#cIn"), main = $("#chatMain");
  inp.onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } };
  inp.onpaste = (e) => { const fs = [...e.clipboardData.items].filter((i) => i.kind === "file").map((i) => i.getAsFile()); if (fs.length) { e.preventDefault(); attachFiles(fs.map((f, k) => f.name === "image.png" ? new File([f], `вставка_${Date.now()}_${k}.png`, { type: f.type }) : f)); } };
  main.ondragover = (e) => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); main.classList.add("over"); } };
  main.ondragleave = (e) => { if (!main.contains(e.relatedTarget)) main.classList.remove("over"); };
  main.ondrop = (e) => { e.preventDefault(); main.classList.remove("over"); attachFiles([...e.dataTransfer.files]); };
  $("#cSend").onclick = () => send();
  $("#msgs").addEventListener("click", msgAction);
  inp.focus();
  if (CHAT.files.some((f) => f.transcript_id)) resumeJob();
}

async function attachFiles(files) {
  if (!files.length) return;
  const fd = new FormData(); files.forEach((f) => fd.append("items", f));
  $("#attach").insertAdjacentHTML("beforeend", `<span class="att busy"><span class="spin">◐</span> загрузка ${files.length}…</span>`);
  try { afterAttach(await api("POST", `/api/chats/${CHAT.id}/files`, fd, true)); } catch (e) { fail(e); drawAttach(); }
}
function afterAttach(r) {
  if (!r) return;
  CHAT.files = r.files; CHAT._newImages = (CHAT._newImages || []).concat(r.files.filter((f) => f.kind === "image" && !(CHAT._seen || []).includes(f.name)).map((f) => f.name));
  CHAT._seen = r.files.map((f) => f.name);
  drawAttach(); saveChat();
  if (r.job && r.job.id) watchJob(r.job, async () => { CHAT.files = await GET(`/api/chats/${CHAT.id}/files`); drawAttach(); });
  else if (r.job && r.job.error) toast(r.job.error, true);
}
function drawAttach() {
  const el = $("#attach"); if (!el) return;
  el.innerHTML = CHAT.files.map((f) => {
    const ic = f.kind === "image" ? `<img src="/api/chats/${CHAT.id}/files/${encodeURIComponent(f.name)}">` : `<b>${f.kind === "media" || f.kind === "transcript" ? "♪" : "▤"}</b>`;
    const st = f.kind === "media" ? (f.transcript_id ? "→ текст" : "") : f.kind === "text" ? (f.chars ? f.chars.toLocaleString("ru") + " симв." : "без текста") : f.kind === "transcript" ? "расшифровка" : "картинка";
    return `<span class="att">${ic}<span class="n" title="${esc(f.name)}">${esc(f.name)}</span><i>${st}</i>${f.transcript_id ? `<a href="#/transcribe/${f.transcript_id}" title="Открыть расшифровку">↗</a>` : ""}<button data-rm="${esc(f.name)}">✕</button></span>`;
  }).join("");
  $$("[data-rm]", el).forEach((b) => b.onclick = async () => { CHAT.files = await DEL(`/api/chats/${CHAT.id}/files/${encodeURIComponent(b.dataset.rm)}`); drawAttach(); });
  // быстрые запросы
  const has = (k) => CHAT.files.some((f) => f.kind === k);
  const q = [];
  if (CHAT.files.length) q.push("Кратко перескажи прикреплённое: о чём это и что главное", "Найди в файлах всё про: ", "Составь таблицу требований по файлам");
  if (has("media") || has("transcript")) q.push("Сделай протокол встречи: решения, задачи, открытые вопросы — с таймкодами", "Кто что говорил? Позиции участников по пунктам");
  if (has("image")) q.push("Что на картинке? Опиши интерфейс и поля", "Перепиши текст с картинки");
  if (!CHAT.files.length && !CHAT.messages.length) q.push("Составь пользовательские истории и критерии приёмки для: ", "Перечисли пограничные случаи процесса: ", "Сделай черновик раздела ТЗ по ГОСТ 34 про: ");
  $("#quick").innerHTML = q.map((x) => `<span class="chip click" data-q="${esc(x)}">${esc(x.length > 46 ? x.slice(0, 44) + "…" : x)}</span>`).join("");
  $$("#quick [data-q]").forEach((c) => c.onclick = () => { const i = $("#cIn"); i.value = c.dataset.q; i.focus(); i.setSelectionRange(i.value.length, i.value.length); });
}

function drawMsgs(streaming) {
  const el = $("#msgs"); if (!el) return;
  const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  el.innerHTML = CHAT.messages.length ? CHAT.messages.map((m, i) => {
    const last = streaming && i === CHAT.messages.length - 1;
    return `<div class="msg ${m.role}" data-i="${i}">
      <div class="who">${m.role === "user" ? "ТЫ" : "QWEN"}${m.stats ? ` <span class="st">${m.stats.tokens} ток · ${m.stats.tps} ток/с</span>` : ""}</div>
      ${m.files && m.files.length ? `<div class="mfiles">${m.files.map((n) => /\.(png|jpe?g|webp|gif|bmp)$/i.test(n)
        ? `<img src="/api/chats/${CHAT.id}/files/${encodeURIComponent(n)}">` : `<span class="att mini"><b>▤</b>${esc(n)}</span>`).join("")}</div>` : ""}
      ${(m.notes || []).map((n) => `<div class="note-line">ⓘ ${esc(n)}</div>`).join("")}
      ${m.thinking ? `<details class="think" ${last && !m.content ? "open" : ""}><summary>Ход мысли${last && !m.content ? "…" : ""}</summary><div>${esc(m.thinking)}</div></details>` : ""}
      <div class="body ${last ? "cursor" : ""}">${m.role === "user" ? md(m.content) : md(m.content)}</div>
      ${m.role === "assistant" && !last && m.content ? `<div class="macts">
        <button data-act="copy">⎘ копировать</button><button data-act="exp">▼ Word / PDF / TXT</button>
        ${i === CHAT.messages.length - 1 ? `<button data-act="regen">↻ ещё раз</button>` : ""}</div>` : ""}
    </div>`;
  }).join("") : `<div class="chat-empty"><div class="big">INSERT COIN</div><p>Спроси что угодно или перетащи файлы: ТЗ, выгрузки Excel, скриншоты, записи встреч.<br>
      Аудио и видео сначала расшифруются Whisper, потом Qwen ответит по тексту.</p></div>`;
  if (nearBottom || !streaming) el.scrollTop = el.scrollHeight;
}

async function msgAction(e) {
  const b = e.target.closest("[data-act]"); if (!b) return;
  const i = +b.closest(".msg").dataset.i, m = CHAT.messages[i];
  if (b.dataset.act === "copy") { await navigator.clipboard.writeText(m.content).then(() => toast("Скопировано")).catch(() => prompt("Скопируй:", m.content)); }
  if (b.dataset.act === "exp") {
    const q = CHAT.messages.slice(0, i).reverse().find((x) => x.role === "user");
    const title = (CHAT.title || (q && q.content) || "Ответ Qwen").replace(/\s+/g, " ").slice(0, 80);
    exportDialog({ title, text: m.content });
  }
  if (b.dataset.act === "regen") { CHAT.messages.pop(); send(true); }
}

const saveChat = () => PUT("/api/chats/" + CHAT.id, { ...CHAT, files: undefined, _busy: undefined }).catch(() => {});

async function send(regen) {
  const inp = $("#cIn");
  let text = regen ? null : inp.value.trim();
  if (CHAT._busy) return;
  if (!regen) {
    const imgs = CHAT._newImages || [];
    if (!text && !imgs.length) return;
    if (!text) text = "Что на картинке?";
    inp.value = "";
    const filesNow = CHAT.files.filter((f) => !(CHAT._sentFiles || []).includes(f.name)).map((f) => f.name);
    CHAT.messages.push({ role: "user", content: text, files: filesNow, images: imgs });
    CHAT._sentFiles = CHAT.files.map((f) => f.name); CHAT._newImages = [];
    if (!CHAT.title) CHAT.title = text.slice(0, 60);
  }
  CHAT._busy = true;
  const a = { role: "assistant", content: "", thinking: "" };
  CHAT.messages.push(a);
  drawMsgs(true);
  $("#cSend").disabled = true;
  try {
    const r = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: CHAT.id, think: CHAT.think, work_id: CHAT.work_id,
        messages: CHAT.messages.slice(0, -1).map(({ role, content, images }) => ({ role, content, images })) }) });
    const reader = r.body.getReader(), dec = new TextDecoder();
    let buf = "", last = 0;
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let k;
      while ((k = buf.indexOf("\n")) >= 0) {
        const ln = buf.slice(0, k); buf = buf.slice(k + 1);
        if (!ln.trim()) continue;
        const o = JSON.parse(ln);
        if (o.c) a.content += o.c; else if (o.t) a.thinking += o.t; else if (o.n) (a.notes = a.notes || []).push(o.n); else if (o.s) a.stats = o.s;
      }
      if (Date.now() - last > 70) { drawMsgs(true); last = Date.now(); }
    }
  } catch (e) { a.content += "\n\n[ошибка: " + e.message + "]"; }
  if (!a.thinking) delete a.thinking;
  CHAT._busy = false;
  drawMsgs();
  const sb = $("#cSend"); if (sb) sb.disabled = false;
  await saveChat();
  if (!$$(".chat-item[data-id]").some((c) => c.dataset.id === CHAT.id)) viewChat(CHAT.id);
}

// ================================================================= НАСТРОЙКИ И ТЕМЫ
let UI = (() => { try { return { ...TH.DEFAULTS, ...JSON.parse(localStorage.getItem("ui.prefs") || "{}") }; } catch { return { ...TH.DEFAULTS }; } })();
const saveUI = debounce(() => PUT("/api/settings", { ui: UI }).catch(() => {}), 500);
function setUI(patch) { UI = { ...UI, ...patch }; localStorage.setItem("ui.prefs", JSON.stringify(UI)); TH.apply(UI); saveUI(); }

const THEME_INFO = {
  pixel: ["Пиксель-мир", "4 времени года × 5 времён суток. Снег, листопад, сакура, светлячки, отражения в озере, лучи солнца, северное сияние."],
  neon: ["Неон 80-х", "Синтвейв: закат в полоску, бегущая сетка, неоновые рамки и сканлинии."],
  ink: ["Тушь и спираль", "Чёрно-белая манга-графика: бумага, перо, потёки туши, медленная спираль. Красный — только для ошибок."],
  office: ["Тихий офис", "Светлая, спокойная, без анимации. Для долгой работы с текстом и созвонов с экраном."],
  graphite: ["Графит", "Тёмная и строгая, без анимации. Бережёт глаза ночью и видеокарту."],
};

function updateQuick() {
  const r = TH.resolved();
  const ic = { morning: "☀", day: "☼", evening: "☾", night: "☾", deep: "✦" }[r.time];
  $("#themeQuickIc").textContent = UI.theme === "pixel" ? ic : "◐";
  $("#themeQuickTx").textContent = UI.theme === "pixel" ? `${TH.SEASONS[r.season]} · ${TH.TIMES[r.time]}` : THEME_INFO[UI.theme][0];
  $("#logoSub").textContent = UI.theme === "pixel" ? `PIXEL WORLD // ${TH.SEASONS[r.season].toUpperCase()} // ${TH.TIMES[r.time].toUpperCase()}`
    : UI.theme === "ink" ? "ТУШЬ // ПЕРО // СПИРАЛЬ" : "LOCAL QWEN // REPORT FACTORY";
}
document.addEventListener("themechange", updateQuick);

async function viewSettings(tab = "look") {
  const s = await GET("/api/settings");
  await pollHealth();
  const tabs = [["look", "Оформление"], ["model", "Модель"], ["voice", "Голос и расшифровка"], ["files", "Файлы"]];
  view.innerHTML = `
    <div class="page-head"><h1 class="h1">Настройки<small>Всё применяется сразу. Хранится в settings.yaml рядом с программой</small></h1></div>
    <div class="tabs">${tabs.map(([k, l]) => `<a href="#/settings/${k}" class="${tab === k ? "on" : ""}">${l}</a>`).join("")}</div>
    <div id="setBody"></div>`;
  const body = $("#setBody");
  if (tab === "look") return settingsLook(body);
  if (tab === "model") {
    const v = HEALTH?.models?.length ? HEALTH.models : [s.model];
    body.innerHTML = `<div class="card"><div class="h2">Модель</div><div class="grid g3">
      <label class="f span2">АДРЕС OLLAMA<input id="sUrl" value="${esc(s.ollama_url)}"></label>
      <label class="f">МОДЕЛЬ<select id="sModel">${v.map((x) => `<option ${x === s.model ? "selected" : ""}>${esc(x)}</option>`).join("")}</select></label>
      <label class="f">КОНТЕКСТ, ТОКЕНОВ<input id="sCtx" type="number" value="${s.num_ctx}"></label>
      <label class="f">ПОПЫТОК ИСПРАВЛЕНИЯ<input id="sAtt" type="number" min="1" max="6" value="${s.max_attempts}"></label>
      <label class="f">ТЕМПЕРАТУРА ЧАТА<input id="sTemp" type="number" step="0.1" min="0" max="1.5" value="${s.chat_temperature}"></label>
      <label class="check"><input type="checkbox" id="sThink" ${s.chat_think ? "checked" : ""}><b></b>В новых чатах «Думать» включено</label>
      <label class="check"><input type="checkbox" id="sVis" ${s.vision ? "checked" : ""}><b></b>Отправлять модели картинки</label>
    </div><p class="hint">Генерация отчётов всегда идёт с temperature 0 и без «раздумий» — так результат воспроизводим. Контекст больше 32k займёт больше видеопамяти.</p></div>
    <div class="actionbar"><span class="grow"></span><button class="btn big" id="sSave">▶ СОХРАНИТЬ</button></div>`;
    $("#sSave").onclick = async () => { try { await PUT("/api/settings", { ollama_url: $("#sUrl").value, model: $("#sModel").value, num_ctx: +$("#sCtx").value,
      max_attempts: +$("#sAtt").value, chat_temperature: +$("#sTemp").value, chat_think: $("#sThink").checked, vision: $("#sVis").checked }); toast("Сохранено"); pollHealth(); } catch (e) { fail(e); } };
    return;
  }
  if (tab === "voice") {
    const v = HEALTH?.voice || {};
    body.innerHTML = `<div class="card"><div class="h2">Whisper</div><div class="grid g3">
      <label class="f">МОДЕЛЬ<select id="sWm">${["large-v3-turbo", "large-v3", "medium", "small"].map((x) => `<option ${x === s.whisper_model ? "selected" : ""}>${x}</option>`).join("")}</select></label>
      <label class="f">УСТРОЙСТВО<select id="sWd">${[["auto", "auto (GPU / Mac MLX, иначе CPU)"], ["cuda", "только GPU NVIDIA"], ["mlx", "Mac (MLX)"], ["cpu", "только CPU"]].map(([k, l]) => `<option value="${k}" ${k === s.whisper_device ? "selected" : ""}>${l}</option>`).join("")}</select></label>
      <div class="f">СОСТОЯНИЕ<div class="vt" style="color:var(--ink)">${v.state === "ready" ? "● " + esc(v.device) : v.state === "error" ? "✕ " + esc(v.error || "") : v.whisper_installed ? "не загружен" : "faster-whisper не установлен"}</div></div>
      <label class="f">ЯЗЫК РАСШИФРОВКИ<select id="sLang">${[["ru", "русский"], ["en", "английский"], ["auto", "определять"]].map(([k, l]) => `<option value="${k}" ${s.transcribe_language === k ? "selected" : ""}>${l}</option>`).join("")}</select></label>
      <label class="check" style="align-self:end"><input type="checkbox" id="sDia" ${s.diarize ? "checked" : ""}><b></b>Делить по участникам</label>
      <label class="f span3">СЛОВАРЬ ТЕРМИНОВ<input id="sGl" value="${esc(s.glossary || "")}" placeholder="RPA, OCR, BPMN, коды роботов, ФИО коллег…"></label>
    </div><div style="display:flex;gap:12px;margin-top:14px;align-items:center">
      <button class="btn ghost" id="wWarm">◆ ЗАГРУЗИТЬ WHISPER СЕЙЧАС</button><span class="hint">первый раз скачает модель (~1,6 ГБ); потом грузится за секунды</span></div></div>
    <div class="actionbar"><span class="grow"></span><button class="btn big" id="sSave">▶ СОХРАНИТЬ</button></div>`;
    $("#sSave").onclick = async () => { try { await PUT("/api/settings", { whisper_model: $("#sWm").value, whisper_device: $("#sWd").value,
      transcribe_language: $("#sLang").value, diarize: $("#sDia").checked, glossary: $("#sGl").value }); toast("Сохранено"); } catch (e) { fail(e); } };
    $("#wWarm").onclick = async () => { try { watchJob(await POST("/api/voice/warmup"), () => { pollHealth(); viewSettings("voice"); }); } catch (e) { fail(e); } };
    return;
  }
  if (tab === "files") {
    body.innerHTML = `<div class="card"><div class="h2">Хранилище</div>
      <label class="check"><input type="checkbox" id="sAuto" ${s.auto_file_works ? "checked" : ""}><b></b>Собранную работу автоматически класть в Хранилище → ВУЗ → предмет → тип</label>
      <p class="hint">Хранилище — обычная папка «Хранилище» рядом с программой. Её можно открыть в Проводнике, синхронизировать с Google Drive или Яндекс.Диском.</p>
      <div style="display:flex;gap:12px"><button class="btn ghost" id="sOpen">▣ ОТКРЫТЬ ПАПКУ</button><a class="btn ghost" href="#/files">▤ К ФАЙЛАМ</a></div></div>`;
    $("#sAuto").onchange = (e) => PUT("/api/settings", { auto_file_works: e.target.checked }).then(() => toast("Сохранено")).catch(fail);
    $("#sOpen").onclick = () => openFile("");
  }
}

function settingsLook(body) {
  const r = TH.resolved();
  const seg = (id, opts, val) => `<div class="seg" id="${id}">${opts.map(([k, l]) => `<button data-v="${k}" class="${String(val) === String(k) ? "on" : ""}">${l}</button>`).join("")}</div>`;
  body.innerHTML = `
    <div class="card"><div class="h2">Тема</div>
      <div class="themes">${Object.entries(THEME_INFO).map(([k, [n, d]]) => `<div class="theme-card ${UI.theme === k ? "on" : ""}" data-th="${k}">
        <div class="tprev tp-${k}">${k === "pixel" ? `<canvas width="320" height="180"></canvas>` : `<div class="mock"><i></i><i></i><i></i><b></b></div>`}</div>
        <div class="tname">${n}</div><div class="tdesc">${d}</div></div>`).join("")}</div></div>
    <div class="card" id="pixCard" ${UI.theme === "pixel" ? "" : "hidden"}><div class="card-head"><div class="h2">Пиксель-мир</div><span class="grow"></span>
        <button class="btn ghost tiny" id="demoDay">▶ ПРОГНАТЬ СУТКИ</button><button class="btn ghost tiny" id="demoYear">▶ ПРОГНАТЬ ГОД</button></div>
      <div class="grid g2">
        <label class="f">ВРЕМЯ ГОДА${seg("sSeason", [["auto", `Авто · сейчас ${TH.SEASONS[TH.seasonNow()].toLowerCase()}`], ...Object.entries(TH.SEASONS)], UI.season)}</label>
        <label class="f">ВРЕМЯ СУТОК${seg("sTime", [["auto", `Авто · сейчас ${TH.TIMES[TH.timeNow()].toLowerCase()}`], ...Object.entries(TH.TIMES)], UI.time)}</label>
      </div>
      <p class="hint">«Авто» по месяцу: декабрь–февраль зима, март–май весна, июнь–август лето, сентябрь–ноябрь осень. По часам: утро 5–10, день 10–17, вечер 17–21:30, ночь до часа, глубокая ночь 1–5. Можно оставить авто только для одного из двух.</p>
      <div class="scene-grid" id="sceneGrid">${Object.keys(TH.SEASONS).map((se) => Object.keys(TH.TIMES).map((ti) =>
        `<button class="sc ${r.season === se && r.time === ti ? "on" : ""}" data-se="${se}" data-ti="${ti}" title="${TH.SEASONS[se]} · ${TH.TIMES[ti]}"><canvas width="160" height="90"></canvas><span>${TH.SEASONS[se]} · ${TH.TIMES[ti]}</span></button>`).join("")).join("")}</div>
      <p class="hint">Клик по картинке закрепит этот сезон и время. Чтобы снова менялось само — выбери «Авто» выше.</p>
    </div>
    <div class="card"><div class="h2">Эффекты</div><div class="grid g2">
      <label class="f">ТРАССИРОВКА ЛУЧЕЙ <span class="hint">(пародия на RTX: свечение, лучи, блики, отражения, сияние)</span>${seg("sFx", [[0, "RTX OFF"], [1, "Мягко"], [2, "RTX ON"]], UI.fx)}</label>
      <label class="f">ЧАСТИЦЫ <span class="hint">(снег, листья, лепестки, светлячки)</span>${seg("sPart", [[0, "Нет"], [1, "Немного"], [2, "Много"]], UI.particles)}</label>
      <label class="f">СКОРОСТЬ АНИМАЦИИ <span class="vt" id="spdV">${UI.speed}×</span><input type="range" id="sSpd" min="0.25" max="3" step="0.25" value="${UI.speed}"></label>
      <label class="f">ЗАГОЛОВКИ И КНОПКИ${seg("sFont", [["pixel", "Пиксельный шрифт"], ["clean", "Обычный шрифт"]], UI.font)}</label>
      <div class="chips" style="gap:22px">
        <label class="check"><input type="checkbox" id="sMot" ${UI.motion ? "checked" : ""}><b></b>Анимация фона</label>
        <label class="check"><input type="checkbox" id="sCrt" ${UI.crt ? "checked" : ""}><b></b>CRT-сканлинии</label>
        <label class="check"><input type="checkbox" id="sBlur" ${UI.blur ? "checked" : ""}><b></b>Матовое стекло панелей</label>
      </div></div>
      <p class="hint">Фон рисуется 30 раз в секунду и почти не нагружает видеокарту, но если Qwen генерирует долго — можно выключить анимацию: картинка останется.</p></div>`;
  // превью тем
  const pc = $(".tp-pixel canvas", body); if (pc) TH.preview(pc, "pixel", r.season, r.time);
  $$(".theme-card", body).forEach((c) => c.onclick = () => { setUI({ theme: c.dataset.th }); settingsLook(body); });
  const segBind = (id, key, num) => $$(`#${id} button`, body).forEach((b) => b.onclick = () => {
    $$(`#${id} button`, body).forEach((x) => x.classList.toggle("on", x === b)); setUI({ [key]: num ? +b.dataset.v : b.dataset.v });
    if (key === "season" || key === "time") markScene(); });
  segBind("sSeason", "season"); segBind("sTime", "time"); segBind("sFx", "fx", true); segBind("sPart", "particles", true); segBind("sFont", "font");
  $("#sSpd").oninput = (e) => { $("#spdV").textContent = e.target.value + "×"; setUI({ speed: +e.target.value }); };
  $("#sMot").onchange = (e) => setUI({ motion: e.target.checked });
  $("#sCrt").onchange = (e) => setUI({ crt: e.target.checked });
  $("#sBlur").onchange = (e) => setUI({ blur: e.target.checked });
  const markScene = () => { const rr = TH.resolved(); $$("#sceneGrid .sc").forEach((b) => b.classList.toggle("on", b.dataset.se === rr.season && b.dataset.ti === rr.time)); };
  // сетка 4×5 рисуется по одной, чтобы окно не подвисало
  const scs = $$("#sceneGrid .sc", body);
  let k = 0;
  const next = () => { if (k >= scs.length || !scs[0].isConnected) return; const b = scs[k++]; TH.preview($("canvas", b), "pixel", b.dataset.se, b.dataset.ti); setTimeout(next, 16); };
  if (UI.theme === "pixel") next();
  scs.forEach((b) => b.onclick = () => { setUI({ theme: "pixel", season: b.dataset.se, time: b.dataset.ti }); settingsLook(body); });
  let demo = null;
  const runDemo = (steps) => {
    if (demo) { clearInterval(demo); demo = null; TH.demo(); return; }
    let i = 0; TH.demo(steps[0][0], steps[0][1]);
    demo = setInterval(() => { i++; if (i >= steps.length || !body.isConnected) { clearInterval(demo); demo = null; TH.demo(); return; } TH.demo(steps[i][0], steps[i][1]); }, 2600);
  };
  $("#demoDay") && ($("#demoDay").onclick = () => runDemo(Object.keys(TH.TIMES).map((t) => [TH.resolved().season, t])));
  $("#demoYear") && ($("#demoYear").onclick = () => runDemo(Object.keys(TH.SEASONS).map((se) => [se, TH.resolved().time])));
}

// ================================================================= запуск
TH.apply(UI);
$("#themeQuick").onclick = () => (location.hash = "#/settings/look");
GET("/api/settings").then((s) => { if (s.ui && Object.keys(s.ui).length) { UI = { ...TH.DEFAULTS, ...s.ui }; localStorage.setItem("ui.prefs", JSON.stringify(UI)); TH.apply(UI); } }).catch(() => {});
pollHealth();
resumeJob();
// route() — в конце wdocs.js, когда все разделы уже зарегистрированы
