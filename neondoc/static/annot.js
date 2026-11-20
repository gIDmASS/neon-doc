/* NEON.DOC — «Разметка»: редактор скриншотов для ТЗ, инструкций и отчётов.
 * Все пометки — объекты: их можно выделить, подвинуть, перекрасить, удалить, а проект — сохранить
 * рядом с картинкой (.annot.json) и открыть потом снова.
 */
"use strict";

const ANNOT = (() => {
  const FONTS = [["Arial", "Arial"], ["Segoe UI", "Segoe UI"], ["Times New Roman", "Times New Roman"], ["Georgia", "Georgia"],
    ["Consolas", "Consolas"], ["Verdana", "Verdana"], ["Trebuchet MS", "Trebuchet MS"], ["Impact", "Impact"],
    ["Comic Sans MS", "Comic Sans MS"], ["Pixel", "Пиксельный"], ["VT", "Терминал VT323"]];
  const COLORS = ["#e01e1e", "#ff7a18", "#ffd319", "#2ecc40", "#00a8e8", "#1f3f6f", "#9d4dff", "#ff2e88", "#111111", "#ffffff"];
  const PRESETS = {
    "ТЗ (DM)": { color: "#e01e1e", width: 5, badge: 40, font: "Arial", size: 26, fill: "none", shadow: false, badgeShape: "round" },
    "Маркер": { color: "#ffd319", width: 18, badge: 34, font: "Segoe UI", size: 22, fill: "none", shadow: false, badgeShape: "round" },
    "Синий акцент": { color: "#00a8e8", width: 4, badge: 36, font: "Segoe UI", size: 22, fill: "soft", shadow: true, badgeShape: "round" },
    "Строгий": { color: "#111111", width: 3, badge: 32, font: "Times New Roman", size: 22, fill: "none", shadow: false, badgeShape: "square" },
  };
  const TOOLS = [
    ["select", "↖", "Выбор и перемещение", "V"], ["rectnum", "▣¹", "Рамка + номер", "R"], ["rect", "▢", "Рамка", "F"],
    ["ellipse", "◯", "Овал", "E"], ["arrow", "➜", "Стрелка", "A"], ["line", "╱", "Линия", "L"], ["pen", "✎", "Карандаш", "P"],
    ["marker", "▬", "Маркер (полупрозрачный)", "H"], ["text", "T", "Текст", "T"], ["num", "①", "Номер", "N"],
    ["callout", "💬", "Выноска с текстом", "K"], ["blur", "▦", "Скрыть (пиксели)", "B"], ["spot", "◐", "Прожектор: затемнить всё остальное", "S"],
    ["crop", "⌗", "Обрезка", "C"]];

  let S = null;   // состояние редактора

  function fresh() {
    const st = JSON.parse(localStorage.getItem("annot.style") || "null") || { ...PRESETS["ТЗ (DM)"], opacity: 1, bold: true, italic: false, textBg: "none" };
    return { img: null, imgSrc: null, items: [], crop: null, k: 2, pad: true, padColor: "#ffffff", tool: "rectnum", style: st,
      next: 1, sel: null, hist: [], redo: [], drag: null, zoom: "fit", name: "", legend: {} };
  }

  // ------------------------------------------------------------------ геометрия
  const P = () => (S.pad ? 30 : 0);
  const V = () => S.crop || { x: 0, y: 0, w: S.img.width, h: S.img.height };
  const toCv = (x, y) => { const c = V(); return [(x - c.x) * S.k + P(), (y - c.y) * S.k + P()]; };
  function toImg(e, cv) {
    const r = cv.getBoundingClientRect(), sx = cv.width / r.width, c = V();
    return { x: c.x + ((e.clientX - r.left) * sx - P()) / S.k, y: c.y + ((e.clientY - r.top) * sx - P()) / S.k };
  }
  const norm = (a) => ({ ...a, x: Math.min(a.x, a.x + a.w), y: Math.min(a.y, a.y + a.h), w: Math.abs(a.w), h: Math.abs(a.h) });
  function bbox(it) {
    if (it.pts) { const xs = it.pts.map((p) => p[0]), ys = it.pts.map((p) => p[1]);
      return { x: Math.min(...xs), y: Math.min(...ys), w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys) }; }
    if (it.t === "num") { const r = it.st.badge / S.k / 2; return { x: it.x - r, y: it.y - r, w: r * 2, h: r * 2 }; }
    if (it.t === "text") { const m = measureText(it); return { x: it.x, y: it.y, w: m.w / S.k, h: m.h / S.k }; }
    return { x: it.x, y: it.y, w: it.w, h: it.h };
  }
  function hit(it, p) {
    const b = bbox(it), pad = 6 / S.k;
    if (it.t === "arrow" || it.t === "line") {
      const [a, c] = it.pts, dx = c[0] - a[0], dy = c[1] - a[1], L = dx * dx + dy * dy || 1;
      const u = Math.max(0, Math.min(1, ((p.x - a[0]) * dx + (p.y - a[1]) * dy) / L));
      return Math.hypot(a[0] + u * dx - p.x, a[1] + u * dy - p.y) < (it.st.width / S.k) + pad;
    }
    if ((it.t === "rect" || it.t === "rectnum") && it.st.fill === "none") {
      const inX = p.x > b.x - pad && p.x < b.x + b.w + pad, inY = p.y > b.y - pad && p.y < b.y + b.h + pad;
      const nearEdge = Math.abs(p.x - b.x) < pad * 2 || Math.abs(p.x - b.x - b.w) < pad * 2 || Math.abs(p.y - b.y) < pad * 2 || Math.abs(p.y - b.y - b.h) < pad * 2;
      const nearBadge = it.n != null && Math.hypot(p.x - b.x, p.y - b.y) < it.st.badge / S.k;
      return (inX && inY && nearEdge) || nearBadge;
    }
    return p.x > b.x - pad && p.x < b.x + b.w + pad && p.y > b.y - pad && p.y < b.y + b.h + pad;
  }

  // ------------------------------------------------------------------ отрисовка
  let mctx = null;
  function measureText(it) {
    mctx = mctx || document.createElement("canvas").getContext("2d");
    mctx.font = fontOf(it.st);
    const lines = (it.text || " ").split("\n");
    const w = Math.max(...lines.map((l) => mctx.measureText(l || " ").width)) + (it.st.textBg !== "none" || it.t === "callout" ? 20 : 0);
    const h = lines.length * it.st.size * 1.25 + (it.st.textBg !== "none" || it.t === "callout" ? 12 : 0);
    return { w, h, lines };
  }
  const fontOf = (st) => `${st.italic ? "italic " : ""}${st.bold ? "bold " : ""}${st.size}px "${st.font}", Arial, sans-serif`;
  function rr(ctx, x, y, w, h, r) { ctx.beginPath(); ctx.roundRect(x, y, w, h, Math.max(0, Math.min(r, h / 2, w / 2))); }
  function shadow(ctx, st) { if (st.shadow) { ctx.shadowColor = "rgba(0,0,0,.35)"; ctx.shadowBlur = 8; ctx.shadowOffsetY = 3; } }
  function noShadow(ctx) { ctx.shadowColor = "transparent"; ctx.shadowBlur = 0; ctx.shadowOffsetY = 0; }

  function badge(ctx, n, bx, by, st) {
    const H = st.badge, t = String(n);
    ctx.font = `bold ${Math.round(H * .65)}px "${st.font}", Arial, sans-serif`;
    const w = Math.max(H, ctx.measureText(t).width + H * .45);
    const rad = st.badgeShape === "square" ? 4 : st.badgeShape === "rounded" ? H * .28 : H / 2;
    shadow(ctx, st);
    ctx.fillStyle = "#fff"; rr(ctx, bx - 3, by - 3, w + 6, H + 6, rad + 3); ctx.fill(); noShadow(ctx);
    ctx.fillStyle = st.color; rr(ctx, bx, by, w, H, rad); ctx.fill();
    ctx.fillStyle = light(st.color) ? "#111" : "#fff"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(t, bx + w / 2, by + H / 2 + 1);
    return w;
  }
  const light = (h) => { const c = h.replace("#", ""); const n = parseInt(c.length === 3 ? [...c].map((x) => x + x).join("") : c, 16);
    return ((n >> 16) * .299 + ((n >> 8) & 255) * .587 + (n & 255) * .114) > 170; };
  const fillOf = (st) => st.fill === "solid" ? st.color : st.fill === "soft" ? st.color + "33" : null;

  function drawItem(ctx, it, src) {
    const st = it.st;
    ctx.save();
    ctx.globalAlpha = st.opacity ?? 1;
    ctx.lineCap = ctx.lineJoin = "round";
    if (it.t === "blur") {
      const b = norm(it), [L, T] = toCv(b.x, b.y), [R, B] = toCv(b.x + b.w, b.y + b.h);
      const px = Math.max(6, Math.round(st.width * 2.4));
      const tmp = document.createElement("canvas"); tmp.width = Math.max(1, (R - L) / px); tmp.height = Math.max(1, (B - T) / px);
      const tc = tmp.getContext("2d"); tc.drawImage(src, L, T, R - L, B - T, 0, 0, tmp.width, tmp.height);
      ctx.imageSmoothingEnabled = false; ctx.drawImage(tmp, 0, 0, tmp.width, tmp.height, L, T, R - L, B - T);
    } else if (it.t === "rect" || it.t === "rectnum" || it.t === "ellipse") {
      const b = norm(it), [L, T] = toCv(b.x, b.y), [R, B] = toCv(b.x + b.w, b.y + b.h), o = st.width / 2 + 1;
      ctx.strokeStyle = st.color; ctx.lineWidth = st.width; shadow(ctx, st);
      if (it.t === "ellipse") { ctx.beginPath(); ctx.ellipse((L + R) / 2, (T + B) / 2, (R - L) / 2 + o, (B - T) / 2 + o, 0, 0, 7); }
      else { ctx.beginPath(); ctx.rect(L - o, T - o, R - L + o * 2, B - T + o * 2); }
      const f = fillOf(st); if (f) { ctx.fillStyle = f; ctx.fill(); }
      ctx.stroke();
    } else if (it.t === "arrow" || it.t === "line") {
      const [a, b] = it.pts.map((p) => toCv(p[0], p[1]));
      ctx.strokeStyle = ctx.fillStyle = st.color; ctx.lineWidth = st.width; shadow(ctx, st);
      const ang = Math.atan2(b[1] - a[1], b[0] - a[0]), head = it.t === "arrow" ? Math.max(14, st.width * 3.2) : 0;
      ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0] - Math.cos(ang) * head * .7, b[1] - Math.sin(ang) * head * .7); ctx.stroke();
      if (head) { ctx.beginPath(); ctx.moveTo(b[0], b[1]);
        ctx.lineTo(b[0] - Math.cos(ang - .42) * head, b[1] - Math.sin(ang - .42) * head);
        ctx.lineTo(b[0] - Math.cos(ang + .42) * head, b[1] - Math.sin(ang + .42) * head); ctx.closePath(); ctx.fill(); }
    } else if (it.t === "pen" || it.t === "marker") {
      ctx.strokeStyle = st.color; ctx.lineWidth = it.t === "marker" ? Math.max(st.width, 12) : st.width;
      if (it.t === "marker") { ctx.globalAlpha = .38; ctx.globalCompositeOperation = "multiply"; ctx.lineCap = "square"; }
      ctx.beginPath(); it.pts.forEach((p, i) => { const [x, y] = toCv(p[0], p[1]); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); ctx.stroke();
    } else if (it.t === "text" || it.t === "callout") {
      const m = measureText(it), [x, y] = toCv(it.x, it.y);
      const boxed = it.t === "callout" || st.textBg !== "none";
      if (it.t === "callout" && it.tail) {   // хвостик выноски к точке
        const [tx, ty] = toCv(it.tail[0], it.tail[1]);
        ctx.fillStyle = st.textBg === "color" ? st.color : "#fff"; ctx.strokeStyle = st.color; ctx.lineWidth = 2; shadow(ctx, st);
        ctx.beginPath(); ctx.moveTo(x + m.w * .3, y + m.h / 2); ctx.lineTo(tx, ty); ctx.lineTo(x + m.w * .55, y + m.h / 2); ctx.closePath(); ctx.fill(); ctx.stroke();
      }
      if (boxed) {
        shadow(ctx, st);
        ctx.fillStyle = st.textBg === "color" ? st.color : st.textBg === "dark" ? "#111" : "#fff";
        rr(ctx, x, y, m.w, m.h, 8); ctx.fill(); noShadow(ctx);
        ctx.strokeStyle = st.color; ctx.lineWidth = it.t === "callout" ? 2.5 : 0; if (it.t === "callout") ctx.stroke();
      }
      ctx.font = fontOf(st); ctx.textBaseline = "top"; ctx.textAlign = "left";
      ctx.fillStyle = st.textBg === "color" ? (light(st.color) ? "#111" : "#fff") : st.textBg === "dark" ? "#fff" : st.color;
      if (!boxed && st.shadow) { ctx.strokeStyle = "#fff"; ctx.lineWidth = 4; m.lines.forEach((l, i) => ctx.strokeText(l, x, y + i * st.size * 1.25)); }
      m.lines.forEach((l, i) => ctx.fillText(l, x + (boxed ? 10 : 0), y + (boxed ? 6 : 0) + i * st.size * 1.25));
    }
    ctx.restore();
  }

  function render(cv, tmp, forExport) {
    if (!S.img) return;
    const c = V(), ctx = cv.getContext("2d");
    cv.width = Math.round(c.w * S.k + 2 * P()); cv.height = Math.round(c.h * S.k + 2 * P());
    ctx.fillStyle = S.padColor; ctx.fillRect(0, 0, cv.width, cv.height);
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(S.img, c.x, c.y, c.w, c.h, P(), P(), c.w * S.k, c.h * S.k);
    const all = tmp ? S.items.concat([tmp]) : S.items;
    // сначала «скрыть», потом прожектор, потом остальное
    const base = document.createElement("canvas"); base.width = cv.width; base.height = cv.height; base.getContext("2d").drawImage(cv, 0, 0);
    all.filter((i) => i.t === "blur").forEach((i) => drawItem(ctx, i, base));
    const spots = all.filter((i) => i.t === "spot");
    if (spots.length) {
      ctx.save(); ctx.beginPath(); ctx.rect(0, 0, cv.width, cv.height);
      spots.forEach((s) => { const b = norm(s), [L, T] = toCv(b.x, b.y), [R, B] = toCv(b.x + b.w, b.y + b.h); ctx.roundRect(L - 6, T - 6, R - L + 12, B - T + 12, 10); });
      ctx.fillStyle = `rgba(0,0,0,${.55 * (spots[0].st.opacity ?? 1)})`; ctx.fill("evenodd"); ctx.restore();
    }
    all.filter((i) => !["blur", "spot", "crop", "num"].includes(i.t)).forEach((i) => drawItem(ctx, i));
    // номера — поверх всего, без наложения друг на друга
    const placed = [];
    for (const it of all) {
      if (it.n == null) continue;
      let bx, by;
      if (it.t === "num") { const [X, Y] = toCv(it.x, it.y); bx = X - it.st.badge / 2; by = Y - it.st.badge / 2; }
      else { const b = norm(it), [L, T] = toCv(b.x, b.y); bx = L - it.st.badge * .55; by = T - it.st.badge * .55; }
      bx = Math.max(2, bx); by = Math.max(2, by);
      for (const q of placed) if (Math.abs(q[0] - bx) < it.st.badge && Math.abs(q[1] - by) < it.st.badge) bx = q[0] + it.st.badge + 6;
      placed.push([bx, by]);
      ctx.save(); ctx.globalAlpha = it.st.opacity ?? 1; badge(ctx, it.n, bx, by, it.st); ctx.restore();
    }
    if (tmp && tmp.t === "crop") {
      const b = norm(tmp), [L, T] = toCv(b.x, b.y), [R, B] = toCv(b.x + b.w, b.y + b.h);
      ctx.save(); ctx.fillStyle = "rgba(0,0,0,.45)"; ctx.beginPath(); ctx.rect(0, 0, cv.width, cv.height); ctx.rect(L, T, R - L, B - T); ctx.fill("evenodd");
      ctx.setLineDash([8, 6]); ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; ctx.strokeRect(L, T, R - L, B - T); ctx.restore();
    }
    if (!forExport && S.sel != null && S.items[S.sel]) {   // рамка выделения и ручки
      const b = bbox(S.items[S.sel]), [L, T] = toCv(b.x, b.y), [R, B] = toCv(b.x + b.w, b.y + b.h);
      ctx.save(); ctx.setLineDash([6, 4]); ctx.strokeStyle = "#00a8e8"; ctx.lineWidth = 1.5; ctx.strokeRect(L - 8, T - 8, R - L + 16, B - T + 16);
      ctx.setLineDash([]); ctx.fillStyle = "#fff"; ctx.strokeStyle = "#00a8e8";
      handles(S.items[S.sel]).forEach(([hx, hy]) => { const [x, y] = toCv(hx, hy); ctx.beginPath(); ctx.rect(x - 6, y - 6, 12, 12); ctx.fill(); ctx.stroke(); });
      ctx.restore();
    }
  }
  function handles(it) {
    if (it.t === "arrow" || it.t === "line") return it.pts.map((p) => [p[0], p[1]]);
    if (["rect", "rectnum", "ellipse", "blur", "spot"].includes(it.t)) { const b = norm(it); return [[b.x, b.y], [b.x + b.w, b.y], [b.x, b.y + b.h], [b.x + b.w, b.y + b.h]]; }
    if (it.t === "callout" && it.tail) return [it.tail];
    return [];
  }

  // ------------------------------------------------------------------ история
  const snap = () => { S.hist.push(JSON.stringify({ items: S.items, crop: S.crop, next: S.next, legend: S.legend })); if (S.hist.length > 150) S.hist.shift(); S.redo = []; };
  function undo() { const h = S.hist.pop(); if (!h) return; S.redo.push(JSON.stringify({ items: S.items, crop: S.crop, next: S.next, legend: S.legend }));
    Object.assign(S, JSON.parse(h)); S.sel = null; redraw(); }
  function redoF() { const h = S.redo.pop(); if (!h) return; S.hist.push(JSON.stringify({ items: S.items, crop: S.crop, next: S.next, legend: S.legend }));
    Object.assign(S, JSON.parse(h)); S.sel = null; redraw(); }

  // ------------------------------------------------------------------ интерфейс
  let root, cv;
  function redraw(tmp) { if (!S.img) return; render(cv, tmp); applyZoom(); drawLayers(); }
  function applyZoom() {
    if (S.zoom === "fit") { cv.style.width = ""; cv.style.maxWidth = "100%"; }
    else { cv.style.maxWidth = "none"; cv.style.width = cv.width * S.zoom + "px"; }
  }

  function html() {
    const st = S.style;
    return `
    <div class="page-head"><h1 class="h1">Разметка<small>Скриншоты для ТЗ, инструкций и отчётов: рамки, номера, стрелки, выноски, скрытие данных</small></h1>
      <span class="grow"></span>
      <button class="btn ghost tiny" id="anOpen">⇪ ОТКРЫТЬ</button>
      <button class="btn ghost tiny" id="anFromStore">▤ ИЗ ХРАНИЛИЩА</button>
      <button class="btn ghost tiny" id="anPaste">⎘ ИЗ БУФЕРА</button>
    </div>
    <div class="annot">
      <div class="an-tools card">
        ${TOOLS.map(([k, ic, tt, key]) => `<button class="an-tool ${S.tool === k ? "on" : ""}" data-tool="${k}" title="${tt} (${key})"><b>${ic}</b><span>${tt.split(":")[0]}</span><i>${key}</i></button>`).join("")}
      </div>
      <div class="an-stage">
        <div class="an-bar">
          <span class="lbl">№</span><input id="anNext" type="number" min="1" value="${S.next}" style="width:64px">
          <button class="btn ghost tiny" id="anUndo" title="Ctrl+Z">↶</button><button class="btn ghost tiny" id="anRedo" title="Ctrl+Y">↷</button>
          <button class="btn ghost tiny" id="anRenum" title="Пронумеровать заново по порядку">1→2→3</button>
          <button class="btn ghost tiny" id="anUncrop">СБРОС ОБРЕЗКИ</button>
          <button class="btn ghost tiny" id="anClear">ОЧИСТИТЬ</button>
          <span class="grow"></span>
          <span class="lbl">Масштаб</span>
          <select id="anK"><option value="1" ${S.k === 1 ? "selected" : ""}>×1</option><option value="2" ${S.k === 2 ? "selected" : ""}>×2</option><option value="3" ${S.k === 3 ? "selected" : ""}>×3</option></select>
          <label class="check"><input type="checkbox" id="anPad" ${S.pad ? "checked" : ""}><b></b>Поля 30 px</label>
          <input type="color" id="anPadC" value="${S.padColor}" title="Цвет полей">
          <select id="anZoom"><option value="fit">Вписать</option><option value="0.5">50%</option><option value="1">100%</option></select>
        </div>
        <div class="an-canvas" id="anWrap">
          <div class="an-drop" id="anDrop"><div class="big">ВСТАВЬ СКРИНШОТ</div><p><b>Ctrl+V</b>, перетащи файл сюда или открой из хранилища.<br>
            Тяни мышью по картинке — появится рамка с номером, как на рисунках в ТЗ.</p></div>
          <canvas id="anCv" hidden></canvas>
          <textarea id="anText" class="an-text" hidden></textarea>
        </div>
      </div>
      <div class="an-side">
        <div class="card"><div class="h2">Стиль</div>
          <div class="chips" id="anPresets">${Object.keys(PRESETS).map((p) => `<span class="chip click" data-preset="${p}">${p}</span>`).join("")}
            ${Object.keys(JSON.parse(localStorage.getItem("annot.presets") || "{}")).map((p) => `<span class="chip click mine" data-preset="${esc(p)}">★ ${esc(p)}</span>`).join("")}</div>
          <div class="an-colors">${COLORS.map((c) => `<button data-color="${c}" style="--c:${c}" class="${st.color === c ? "on" : ""}"></button>`).join("")}
            <input type="color" id="anColor" value="${st.color}" title="Свой цвет"></div>
          <label class="f">ТОЛЩИНА <span class="vt" id="anWv">${st.width}</span><input type="range" id="anW" min="1" max="24" value="${st.width}"></label>
          <label class="f">НОМЕР, РАЗМЕР <span class="vt" id="anBv">${st.badge}</span><input type="range" id="anB" min="20" max="80" value="${st.badge}"></label>
          <div class="grid g2">
            <label class="f">ФОРМА НОМЕРА<select id="anBs">${[["round", "круг"], ["rounded", "скруглённый"], ["square", "квадрат"]].map(([k, l]) => `<option value="${k}" ${st.badgeShape === k ? "selected" : ""}>${l}</option>`).join("")}</select></label>
            <label class="f">ЗАЛИВКА<select id="anFill">${[["none", "нет"], ["soft", "полупрозрачная"], ["solid", "сплошная"]].map(([k, l]) => `<option value="${k}" ${st.fill === k ? "selected" : ""}>${l}</option>`).join("")}</select></label>
          </div>
          <label class="f">ШРИФТ<select id="anFont">${FONTS.map(([k, l]) => `<option value="${k}" ${st.font === k ? "selected" : ""} style="font-family:'${k}'">${l}</option>`).join("")}</select></label>
          <div class="grid g2">
            <label class="f">РАЗМЕР ТЕКСТА<input type="number" id="anSize" min="10" max="120" value="${st.size}"></label>
            <label class="f">ФОН ТЕКСТА<select id="anTbg">${[["none", "нет"], ["white", "белый"], ["color", "цвет"], ["dark", "тёмный"]].map(([k, l]) => `<option value="${k}" ${st.textBg === k ? "selected" : ""}>${l}</option>`).join("")}</select></label>
          </div>
          <div class="chips" style="gap:16px">
            <label class="check"><input type="checkbox" id="anBold" ${st.bold ? "checked" : ""}><b></b>Жирный</label>
            <label class="check"><input type="checkbox" id="anIt" ${st.italic ? "checked" : ""}><b></b>Курсив</label>
            <label class="check"><input type="checkbox" id="anSh" ${st.shadow ? "checked" : ""}><b></b>Тень</label>
          </div>
          <label class="f">ПРОЗРАЧНОСТЬ<input type="range" id="anOp" min="20" max="100" value="${Math.round((st.opacity ?? 1) * 100)}"></label>
          <button class="btn ghost tiny" id="anSavePreset">★ СОХРАНИТЬ КАК ПРЕСЕТ</button>
          <p class="hint">Если что-то выделено, стиль меняется у него.</p>
        </div>
        <div class="card"><div class="card-head"><div class="h2">Слои и легенда</div><span class="grow"></span>
          <button class="btn ghost tiny" id="anLegendCopy" title="Скопировать «1 — …» для текста ТЗ">⎘ ЛЕГЕНДА</button></div>
          <div id="anLayers" class="an-layers"></div></div>
        <div class="card"><div class="h2">Сохранить</div>
          <label class="f">ИМЯ ФАЙЛА<input id="anName" value="${esc(S.name)}" placeholder="например: Рисунок 12 — форма входа"></label>
          <div class="grid g2" style="margin-top:10px">
            <button class="btn" id="anSave">▼ PNG</button><button class="btn ghost" id="anCopy">⎘ В БУФЕР</button>
          </div>
          <label class="f" style="margin-top:12px">ПАПКА В ХРАНИЛИЩЕ<select id="anFolder"></select></label>
          <button class="btn ghost" id="anStore" style="margin-top:8px;width:100%;justify-content:center">▤ В ХРАНИЛИЩЕ (+ проект для правки)</button>
          <div class="grid g2" style="margin-top:12px">
            <select id="anWork"><option value="">в работу…</option></select><input id="anFig" placeholder="id рисунка">
          </div>
          <button class="btn ghost" id="anToWork" style="margin-top:8px;width:100%;justify-content:center">◆ РИСУНКОМ В РАБОТУ</button>
        </div>
      </div>
    </div>`;
  }

  function drawLayers() {
    const el = $("#anLayers");
    if (!el) return;
    const names = { rect: "Рамка", rectnum: "Рамка №", ellipse: "Овал", arrow: "Стрелка", line: "Линия", pen: "Карандаш", marker: "Маркер",
      text: "Текст", num: "Номер", callout: "Выноска", blur: "Скрыто", spot: "Прожектор" };
    el.innerHTML = S.items.length ? S.items.map((it, i) => ({ it, i })).reverse().map(({ it, i }) => `
      <div class="an-layer ${S.sel === i ? "on" : ""}" data-i="${i}">
        <i style="background:${it.st.color}"></i><span>${names[it.t] || it.t}${it.n != null ? " " + it.n : ""}${it.text ? " · " + esc(it.text.slice(0, 18)) : ""}</span>
        ${it.n != null ? `<input data-leg="${it.n}" placeholder="что это (для легенды)" value="${esc(S.legend[it.n] || "")}">` : ""}
        <button data-up="${i}" title="Выше">▲</button><button data-del="${i}" title="Удалить">✕</button></div>`).join("")
      : `<p class="hint">Пока пусто. Пометки появятся здесь — у каждого номера можно подписать, что он обозначает, и скопировать легенду в ТЗ.</p>`;
    $$(".an-layer", el).forEach((r) => r.onclick = (e) => { if (e.target.closest("button,input")) return; S.sel = +r.dataset.i; redraw(); });
    $$("[data-del]", el).forEach((b) => b.onclick = () => { snap(); S.items.splice(+b.dataset.del, 1); S.sel = null; redraw(); });
    $$("[data-up]", el).forEach((b) => b.onclick = () => { const i = +b.dataset.up; if (i < S.items.length - 1) { snap(); [S.items[i], S.items[i + 1]] = [S.items[i + 1], S.items[i]]; S.sel = i + 1; redraw(); } });
    $$("[data-leg]", el).forEach((inp) => inp.oninput = () => { S.legend[inp.dataset.leg] = inp.value; });
  }

  function loadImage(src, project) {
    const im = new Image();
    im.onload = () => {
      S.img = im; S.imgSrc = src; S.items = []; S.crop = null; S.hist = []; S.redo = []; S.next = 1; S.sel = null; S.legend = {};
      if (project) { S.items = project.items || []; S.crop = project.crop || null; S.next = project.next || 1; S.legend = project.legend || {};
        S.k = project.k || S.k; S.pad = project.pad ?? S.pad; }
      $("#anDrop").hidden = true; cv.hidden = false; $("#anNext").value = S.next; redraw();
    };
    im.src = src;
  }
  const fileToURL = (f) => new Promise((res) => { const r = new FileReader(); r.onload = () => res(r.result); r.readAsDataURL(f); });

  function setStyle(patch) {
    Object.assign(S.style, patch);
    localStorage.setItem("annot.style", JSON.stringify(S.style));
    if (S.sel != null && S.items[S.sel]) { snap(); Object.assign(S.items[S.sel].st, patch); }
    redraw();
  }
  function syncStyleInputs() {
    const st = S.style;
    $("#anColor").value = st.color; $("#anW").value = st.width; $("#anWv").textContent = st.width; $("#anB").value = st.badge; $("#anBv").textContent = st.badge;
    $("#anBs").value = st.badgeShape; $("#anFill").value = st.fill; $("#anFont").value = st.font; $("#anSize").value = st.size; $("#anTbg").value = st.textBg;
    $("#anBold").checked = st.bold; $("#anIt").checked = st.italic; $("#anSh").checked = st.shadow; $("#anOp").value = Math.round((st.opacity ?? 1) * 100);
    $$(".an-colors [data-color]").forEach((b) => b.classList.toggle("on", b.dataset.color === st.color));
  }

  function pngData() { const out = document.createElement("canvas"); render(out, null, true); return out; }
  function nextNum() { return Math.max(1, parseInt($("#anNext").value, 10) || 1); }
  function bumpNum() { S.next = nextNum() + 1; $("#anNext").value = S.next; }

  // ------------------------------------------------------------------ текстовый ввод поверх холста
  function editText(it, isNew) {
    const ta = $("#anText"), r = cv.getBoundingClientRect(), wrap = $("#anWrap").getBoundingClientRect(), sc = r.width / cv.width;
    const [x, y] = toCv(it.x, it.y);
    ta.hidden = false; ta.value = it.text || "";
    Object.assign(ta.style, { left: r.left - wrap.left + $("#anWrap").scrollLeft + x * sc + "px", top: r.top - wrap.top + $("#anWrap").scrollTop + y * sc + "px",
      font: fontOf({ ...it.st, size: it.st.size * sc }), color: it.st.color });
    ta.focus();
    const done = () => {
      ta.onblur = null; ta.hidden = true;
      const v = ta.value.replace(/\s+$/, "");
      if (!v) { if (!isNew) { snap(); S.items.splice(S.items.indexOf(it), 1); } }
      else { if (isNew) { snap(); S.items.push(it); } else snap(); it.text = v; S.sel = S.items.indexOf(it); }
      redraw();
    };
    ta.onblur = done;
    ta.onkeydown = (e) => { if (e.key === "Escape") { ta.value = isNew ? "" : it.text; ta.blur(); } if (e.key === "Enter" && (e.ctrlKey || !e.shiftKey && it.t === "text" && false)) ta.blur(); };
  }

  // ------------------------------------------------------------------ мышь
  function bind() {
    cv.addEventListener("mousedown", (e) => {
      if (!S.img || e.button !== 0) return;
      const p = toImg(e, cv), st = { ...S.style };
      if (S.tool === "select") {
        // ручки выделенного
        if (S.sel != null) {
          const hs = handles(S.items[S.sel]);
          const hi = hs.findIndex(([hx, hy]) => Math.hypot(hx - p.x, hy - p.y) < 10 / S.k);
          if (hi >= 0) { snap(); S.drag = { mode: "handle", hi, p0: p }; return; }
        }
        let found = null;
        for (let i = S.items.length - 1; i >= 0; i--) if (hit(S.items[i], p)) { found = i; break; }
        S.sel = found;
        if (found != null) {
          snap(); S.drag = { mode: "move", p0: p, orig: JSON.parse(JSON.stringify(S.items[found])) };
          Object.assign(S.style, S.items[found].st); syncStyleInputs();
        }
        redraw(); return;
      }
      if (S.tool === "num") { snap(); S.items.push({ t: "num", x: p.x, y: p.y, n: nextNum(), st }); bumpNum(); S.sel = S.items.length - 1; redraw(); return; }
      if (S.tool === "text") { editText({ t: "text", x: p.x, y: p.y, text: "", st }, true); return; }
      if (S.tool === "callout") { S.drag = { mode: "callout", p0: p, st }; return; }
      if (S.tool === "pen" || S.tool === "marker") { S.drag = { mode: "draw", it: { t: S.tool, pts: [[p.x, p.y]], st } }; return; }
      S.drag = { mode: "shape", p0: p, st };
    });
    cv.addEventListener("dblclick", (e) => {
      if (!S.img) return;
      const p = toImg(e, cv);
      for (let i = S.items.length - 1; i >= 0; i--) { const it = S.items[i];
        if ((it.t === "text" || it.t === "callout") && hit(it, p)) { editText(it, false); return; } }
    });
    addEventListener("mousemove", (e) => {
      if (!S || !S.drag || !cv.isConnected) return;
      const p = toImg(e, cv), d = S.drag;
      if (d.mode === "move") {
        const it = S.items[S.sel], dx = p.x - d.p0.x, dy = p.y - d.p0.y, o = d.orig;
        if (o.pts) it.pts = o.pts.map(([x, y]) => [x + dx, y + dy]); else { it.x = o.x + dx; it.y = o.y + dy; }
        if (o.tail) it.tail = [o.tail[0] + dx, o.tail[1] + dy];
        redraw(); return;
      }
      if (d.mode === "handle") {
        const it = S.items[S.sel];
        if (it.pts) it.pts[d.hi] = [p.x, p.y];
        else if (it.t === "callout") it.tail = [p.x, p.y];
        else { const b = norm(it), corners = [[b.x + b.w, b.y + b.h], [b.x, b.y + b.h], [b.x + b.w, b.y], [b.x, b.y]], [ax, ay] = corners[d.hi];
          Object.assign(it, { x: Math.min(ax, p.x), y: Math.min(ay, p.y), w: Math.abs(p.x - ax), h: Math.abs(p.y - ay) }); }
        redraw(); return;
      }
      if (d.mode === "draw") { d.it.pts.push([p.x, p.y]); redraw(d.it); return; }
      const r = { x: Math.min(d.p0.x, p.x), y: Math.min(d.p0.y, p.y), w: Math.abs(p.x - d.p0.x), h: Math.abs(p.y - d.p0.y), st: d.st };
      if (S.tool === "arrow" || S.tool === "line") { redraw({ t: S.tool, pts: [[d.p0.x, d.p0.y], [p.x, p.y]], st: d.st }); return; }
      if (d.mode === "callout") { redraw({ t: "arrow", pts: [[d.p0.x, d.p0.y], [p.x, p.y]], st: { ...d.st, width: 2 } }); return; }
      redraw({ ...r, t: S.tool === "rectnum" ? "rectnum" : S.tool, n: S.tool === "rectnum" ? nextNum() : undefined });
    });
    addEventListener("mouseup", (e) => {
      if (!S || !S.drag || !cv.isConnected) return;
      const d = S.drag; S.drag = null;
      const p = toImg(e, cv);
      if (d.mode === "move" || d.mode === "handle") { redraw(); return; }
      if (d.mode === "draw") { if (d.it.pts.length > 1) { snap(); S.items.push(d.it); } redraw(); return; }
      if (d.mode === "callout") {   // выноска: тянем от точки, на которую указываем, к месту текста
        editText({ t: "callout", x: p.x, y: p.y, tail: [d.p0.x, d.p0.y], text: "", st: d.st }, true); return;
      }
      const r = { x: Math.min(d.p0.x, p.x), y: Math.min(d.p0.y, p.y), w: Math.abs(p.x - d.p0.x), h: Math.abs(p.y - d.p0.y) };
      if (S.tool === "arrow" || S.tool === "line") {
        if (Math.hypot(p.x - d.p0.x, p.y - d.p0.y) < 4) { redraw(); return; }
        snap(); S.items.push({ t: S.tool, pts: [[d.p0.x, d.p0.y], [p.x, p.y]], st: d.st }); redraw(); return;
      }
      if (r.w < 3 || r.h < 3) { redraw(); return; }
      snap();
      if (S.tool === "crop") {
        const x = Math.max(0, r.x), y = Math.max(0, r.y);
        S.crop = { x, y, w: Math.min(S.img.width, r.x + r.w) - x, h: Math.min(S.img.height, r.y + r.h) - y };
      } else {
        const it = { t: S.tool, ...r, st: d.st };
        if (S.tool === "rectnum") { it.n = nextNum(); bumpNum(); }
        S.items.push(it); S.sel = S.items.length - 1;
      }
      redraw();
    });
  }

  function keys(e) {
    if (!S || !cv || !cv.isConnected || !S.img) return;
    if (e.target.matches("input,textarea,select")) return;
    const k = e.key.toLowerCase();
    if ((e.ctrlKey || e.metaKey) && k === "z") { e.preventDefault(); e.shiftKey ? redoF() : undo(); return; }
    if ((e.ctrlKey || e.metaKey) && k === "y") { e.preventDefault(); redoF(); return; }
    if ((e.ctrlKey || e.metaKey) && k === "d" && S.sel != null) { e.preventDefault(); snap(); const c = JSON.parse(JSON.stringify(S.items[S.sel]));
      if (c.pts) c.pts = c.pts.map(([x, y]) => [x + 12, y + 12]); else { c.x += 12; c.y += 12; } if (c.n != null) { c.n = nextNum(); bumpNum(); }
      S.items.push(c); S.sel = S.items.length - 1; redraw(); return; }
    if ((k === "delete" || k === "backspace") && S.sel != null) { e.preventDefault(); snap(); S.items.splice(S.sel, 1); S.sel = null; redraw(); return; }
    if (k.startsWith("arrow") && S.sel != null) { e.preventDefault(); const it = S.items[S.sel], st = (e.shiftKey ? 10 : 1) / S.k;
      const dx = k === "arrowleft" ? -st : k === "arrowright" ? st : 0, dy = k === "arrowup" ? -st : k === "arrowdown" ? st : 0;
      if (it.pts) it.pts = it.pts.map(([x, y]) => [x + dx, y + dy]); else { it.x += dx; it.y += dy; } redraw(); return; }
    if (k === "escape") { S.sel = null; redraw(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const t = TOOLS.find((x) => x[3].toLowerCase() === k);
    if (t) setTool(t[0]);
  }
  function setTool(t) { S.tool = t; $$(".an-tool").forEach((b) => b.classList.toggle("on", b.dataset.tool === t)); cv.style.cursor = t === "select" ? "default" : "crosshair"; }

  async function view(opts = {}) {
    if (!S) S = fresh();
    view.el = view.el || null;
    $("#view").innerHTML = html();
    root = $("#view"); cv = $("#anCv");
    bind();
    if (S.img) { $("#anDrop").hidden = true; cv.hidden = false; redraw(); }
    setTool(S.tool);
    // загрузка
    const open = async (f) => { if (f && f.type.startsWith("image/")) { S.name = f.name.replace(/\.\w+$/, ""); $("#anName").value = S.name; loadImage(await fileToURL(f)); } };
    $("#anOpen").onclick = async () => open((await pickFiles("image/*", false))[0]);
    $("#anPaste").onclick = async () => {
      try { const items = await navigator.clipboard.read();
        for (const it of items) { const t = it.types.find((x) => x.startsWith("image/")); if (t) { loadImage(URL.createObjectURL(await it.getType(t))); return; } }
        toast("В буфере нет картинки", true);
      } catch { toast("Нажми Ctrl+V прямо на этой странице", true); }
    };
    $("#anFromStore").onclick = () => pickFromStorage(async (path) => {
      const proj = await GET("/api/annot/project?path=" + encodeURIComponent(path)).catch(() => null);
      S.name = path.split("/").pop().replace(/\.\w+$/, ""); $("#anName").value = S.name;
      loadImage("/api/files/raw?path=" + encodeURIComponent(path), proj);
      if (proj) toast("Открыт проект разметки — пометки можно править");
    }, (it) => it.dir || it.kind === "img");
    const wrap = $("#anWrap");
    wrap.ondragover = (e) => e.preventDefault();
    wrap.ondrop = (e) => { e.preventDefault(); open(e.dataTransfer.files[0]); };
    if (opts.src) loadImage(opts.src, opts.project);
    // панель
    $$(".an-tool").forEach((b) => b.onclick = () => setTool(b.dataset.tool));
    $("#anNext").oninput = (e) => (S.next = nextNum());
    $("#anUndo").onclick = undo; $("#anRedo").onclick = redoF;
    $("#anRenum").onclick = () => { snap(); let n = 1; const leg = {}; S.items.forEach((it) => { if (it.n != null) { if (S.legend[it.n]) leg[n] = S.legend[it.n]; it.n = n++; } });
      S.legend = leg; S.next = n; $("#anNext").value = n; redraw(); };
    $("#anUncrop").onclick = () => { snap(); S.crop = null; redraw(); };
    $("#anClear").onclick = () => { if (!S.items.length || confirm("Удалить все пометки?")) { snap(); S.items = []; S.next = 1; S.legend = {}; $("#anNext").value = 1; redraw(); } };
    $("#anK").onchange = (e) => { S.k = +e.target.value; redraw(); };
    $("#anPad").onchange = (e) => { S.pad = e.target.checked; redraw(); };
    $("#anPadC").oninput = (e) => { S.padColor = e.target.value; redraw(); };
    $("#anZoom").onchange = (e) => { S.zoom = e.target.value === "fit" ? "fit" : +e.target.value; applyZoom(); };
    $$("[data-preset]").forEach((c) => c.onclick = () => {
      const mine = JSON.parse(localStorage.getItem("annot.presets") || "{}");
      setStyle({ ...(PRESETS[c.dataset.preset] || mine[c.dataset.preset]) }); syncStyleInputs();
    });
    $("#anSavePreset").onclick = () => { const n = prompt("Название пресета:"); if (!n) return;
      const mine = JSON.parse(localStorage.getItem("annot.presets") || "{}"); mine[n] = { ...S.style }; localStorage.setItem("annot.presets", JSON.stringify(mine)); view(); };
    $$(".an-colors [data-color]").forEach((b) => b.onclick = () => { setStyle({ color: b.dataset.color }); syncStyleInputs(); });
    $("#anColor").oninput = (e) => setStyle({ color: e.target.value });
    $("#anW").oninput = (e) => { $("#anWv").textContent = e.target.value; setStyle({ width: +e.target.value }); };
    $("#anB").oninput = (e) => { $("#anBv").textContent = e.target.value; setStyle({ badge: +e.target.value }); };
    $("#anBs").onchange = (e) => setStyle({ badgeShape: e.target.value });
    $("#anFill").onchange = (e) => setStyle({ fill: e.target.value });
    $("#anFont").onchange = (e) => setStyle({ font: e.target.value });
    $("#anSize").oninput = (e) => setStyle({ size: +e.target.value || 22 });
    $("#anTbg").onchange = (e) => setStyle({ textBg: e.target.value });
    $("#anBold").onchange = (e) => setStyle({ bold: e.target.checked });
    $("#anIt").onchange = (e) => setStyle({ italic: e.target.checked });
    $("#anSh").onchange = (e) => setStyle({ shadow: e.target.checked });
    $("#anOp").oninput = (e) => setStyle({ opacity: +e.target.value / 100 });
    $("#anName").oninput = (e) => (S.name = e.target.value);
    $("#anLegendCopy").onclick = async () => {
      const nums = [...new Set(S.items.filter((i) => i.n != null).map((i) => i.n))].sort((a, b) => a - b);
      if (!nums.length) return toast("Нет номеров", true);
      const txt = nums.map((n) => `${n} – ${S.legend[n] || "…"}`).join(";\n") + ".";
      await navigator.clipboard.writeText(txt).then(() => toast("Легенда скопирована — вставь под рисунком в ТЗ")).catch(() => prompt("Скопируй:", txt));
    };
    // сохранение
    $("#anSave").onclick = () => { if (!S.img) return; pngData().toBlob((b) => { const a = document.createElement("a"); a.href = URL.createObjectURL(b);
      a.download = (S.name || "разметка_" + new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")) + ".png"; a.click(); }); };
    $("#anCopy").onclick = () => { if (!S.img) return; pngData().toBlob(async (b) => {
      try { await navigator.clipboard.write([new ClipboardItem({ "image/png": b })]); toast("Скопировано — Ctrl+V в Word или Telegram"); }
      catch { toast("Не дал буфер обмена — сохрани PNG", true); } }); };
    const folders = await GET("/api/files/folders").catch(() => []);
    $("#anFolder").innerHTML = folders.map((f) => `<option ${f === "Работа/Скриншоты" ? "selected" : ""}>${esc(f)}</option>`).join("");
    const works = await GET("/api/works").catch(() => []);
    $("#anWork").innerHTML = `<option value="">в работу…</option>` + works.map((w) => `<option value="${w.id}">${esc(w.title)}</option>`).join("");
    if (opts.work) $("#anWork").value = opts.work;
    if (opts.fig) $("#anFig").value = opts.fig;
    const project = () => ({ items: S.items, crop: S.crop, next: S.next, legend: S.legend, k: S.k, pad: S.pad });
    $("#anStore").onclick = async () => {
      if (!S.img) return;
      try { const r = await POST("/api/annot/save", { png: pngData().toDataURL("image/png"), folder: $("#anFolder").value, name: S.name, project: project() });
        toast("Сохранено: " + r.path); } catch (e) { fail(e); }
    };
    $("#anToWork").onclick = async () => {
      const w = $("#anWork").value, f = $("#anFig").value.trim();
      if (!S.img) return; if (!w) return toast("Выбери работу", true);
      if (!/^[a-z0-9_\-]+$/.test(f)) return toast("id рисунка: латиница, цифры, _ и -", true);
      try { await POST("/api/annot/save", { png: pngData().toDataURL("image/png"), work_id: w, fig_id: f }); toast(`Рисунок ${f} добавлен в работу`); } catch (e) { fail(e); }
    };
  }
  document.addEventListener("keydown", keys);
  document.addEventListener("paste", (e) => {
    if (!cv || !cv.isConnected || !location.hash.startsWith("#/annot")) return;
    for (const i of e.clipboardData.items) if (i.type.startsWith("image/")) { const f = i.getAsFile(); fileToURL(f).then((u) => loadImage(u)); S.name = ""; break; }
  });

  return { view, reset() { S = null; } };
})();
