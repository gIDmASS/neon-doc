/* NEON.DOC — темы оформления и живые фоны.
 *
 *  neon      Неон 80-х (синтвейв: сетка, закат, звёзды)
 *  ink       Тушь и спираль (бумага, перо, потёки туши, вьющаяся спираль — своя графика)
 *  pixel     Пиксель-мир: 4 сезона × 5 времён суток, живые частицы и «пародия на RTX»
 *  office    Тихий офис (светлая, без анимации — для долгой работы с текстом)
 *  graphite  Графит (тёмная, без анимации)
 *
 * Пиксельная сцена рисуется в буфер 320×180 и растягивается без сглаживания, а свет (bloom, лучи,
 * блики, отражения, туман, северное сияние) — поверх, на полноразмерном холсте. Отсюда и «RTX».
 */
"use strict";

const TH = (() => {
  // ------------------------------------------------------------------ утилиты цвета
  const hex = (h) => { h = h.replace("#", ""); if (h.length === 3) h = [...h].map((c) => c + c).join("");
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]; };
  const rgb = (c, a) => a == null ? `rgb(${c[0] | 0},${c[1] | 0},${c[2] | 0})` : `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`;
  const toHex = (c) => "#" + c.map((x) => Math.max(0, Math.min(255, Math.round(x))).toString(16).padStart(2, "0")).join("");
  const mix = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
  const C = (h) => (typeof h === "string" ? hex(h) : h);
  function rng(seed) { return () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

  // ------------------------------------------------------------------ время суток и сезон
  const TIMES = { morning: "Утро", day: "День", evening: "Вечер", night: "Ночь", deep: "Глубокая ночь" };
  const SEASONS = { winter: "Зима", spring: "Весна", summer: "Лето", autumn: "Осень" };
  function timeNow(d = new Date()) {
    const h = d.getHours() + d.getMinutes() / 60;
    return h >= 5 && h < 10 ? "morning" : h >= 10 && h < 17 ? "day" : h >= 17 && h < 21.5 ? "evening" : h >= 21.5 || h < 1 ? "night" : "deep";
  }
  function seasonNow(d = new Date()) {
    const m = d.getMonth();
    return m === 11 || m <= 1 ? "winter" : m <= 4 ? "spring" : m <= 7 ? "summer" : "autumn";
  }
  // как далеко зашли внутри отрезка суток (0..1) — солнце и луна двигаются плавно
  function timeProgress(time, d = new Date()) {
    const h = d.getHours() + d.getMinutes() / 60;
    const r = { morning: [5, 10], day: [10, 17], evening: [17, 21.5], night: [21.5, 25], deep: [1, 5] }[time];
    let x = h < r[0] && time === "night" ? h + 24 : h;
    return Math.max(0, Math.min(1, (x - r[0]) / (r[1] - r[0])));
  }

  // ------------------------------------------------------------------ палитры пиксель-мира
  const SKY = {
    morning: { top: "#5b78c4", mid: "#e9a3a8", hz: "#ffd9a8", light: 0.9, sun: "#ffd27a", body: "sun" },
    day:     { top: "#3d8ae0", mid: "#7ec0f3", hz: "#d4ecff", light: 1.0, sun: "#fff4c0", body: "sun" },
    evening: { top: "#33275f", mid: "#b8477a", hz: "#ff9348", light: 0.72, sun: "#ff8a3d", body: "sun" },
    night:   { top: "#0a0f30", mid: "#18224f", hz: "#343c78", light: 0.42, sun: "#e8ecff", body: "moon" },
    deep:    { top: "#020309", mid: "#060a20", hz: "#101838", light: 0.26, sun: "#cdd6ff", body: "moon" },
  };
  const SEASON_TINT = { winter: ["#c4d8ff", 0.16], spring: ["#ffc6dc", 0.08], summer: ["#fff1b8", 0.04], autumn: ["#ffb26a", 0.12] };
  const ACCENT = {
    winter: { pink: "#3a9cff", cyan: "#7fe1ff", violet: "#8a7dff", yellow: "#ffe08a", green: "#5fe0c0", orange: "#7fb2ff" },
    spring: { pink: "#ff5f9e", cyan: "#4fd18b", violet: "#b78cff", yellow: "#ffd95e", green: "#6fdc6f", orange: "#ff8fb8" },
    summer: { pink: "#24b35a", cyan: "#22b8e6", violet: "#6f7bff", yellow: "#ffc928", green: "#39d98a", orange: "#ffae2a" },
    autumn: { pink: "#e3622a", cyan: "#e3a72f", violet: "#b5546d", yellow: "#ffc93c", green: "#a6c23b", orange: "#ff8a18" },
  };

  // ------------------------------------------------------------------ CSS-переменные тем
  const BASE_NEON = {
    "--bg": "#0b0118", "--bg2": "#140628", "--panel": "rgba(26,8,52,.82)", "--panel-solid": "#1a0834", "--line": "#3b1c66",
    "--pink": "#ff2e88", "--hot": "#ff4fa3", "--cyan": "#22e5ff", "--violet": "#9d4dff", "--yellow": "#ffd319",
    "--orange": "#ff7a18", "--green": "#39ff9f", "--ink": "#f4ecff", "--text": "#ece6f7", "--muted": "#a594c7", "--dim": "#6f5c95",
    "--hi": "#ffffff", "--on-accent": "#ffffff", "--on-cyan": "#0b0118", "--paper": "#ffffff", "--field": "#0e0320",
    "--field2": "#120427", "--bubble": "#150530", "--code-bg": "#07010f", "--side-top": "#12032a",
    "--side-bg": "linear-gradient(180deg,#12032a 0%,#0b0118 70%)", "--stripe1": "#1d0a3a", "--stripe2": "#170730",
    "--led-off": "#4a3466", "--console-bg": "rgba(7,1,15,.96)", "--scrim": "rgba(5,0,12,.78)",
  };
  const VARS = {
    neon: BASE_NEON,
    ink: {
      "--bg": "#efe8d8", "--bg2": "#e7dfcc", "--panel": "rgba(250,246,236,.93)", "--panel-solid": "#faf6ec", "--line": "#1b1814",
      "--pink": "#161311", "--hot": "#2a2521", "--cyan": "#161311", "--violet": "#4b443c", "--yellow": "#8c5a00",
      "--orange": "#3a332d", "--green": "#2f5d2f", "--ink": "#0e0c0a", "--text": "#1d1a17", "--muted": "#5d554c", "--dim": "#8f867b",
      "--hi": "#0e0c0a", "--on-accent": "#faf6ec", "--on-cyan": "#faf6ec", "--paper": "#ffffff", "--field": "#fffdf7",
      "--field2": "#fffdf7", "--bubble": "#fffdf7", "--code-bg": "#f4efe3", "--side-top": "#e9e1cf",
      "--side-bg": "linear-gradient(180deg,#ebe3d1,#efe8d8)", "--stripe1": "#e3dbc8", "--stripe2": "#ece5d4",
      "--led-off": "#c9c0ae", "--console-bg": "rgba(244,239,227,.98)", "--scrim": "rgba(30,26,22,.55)", "--alert": "#b3121b",
    },
    office: {
      "--bg": "#f3f5f9", "--bg2": "#e9edf4", "--panel": "rgba(255,255,255,.97)", "--panel-solid": "#ffffff", "--line": "#d9dfe8",
      "--pink": "#2563eb", "--hot": "#3b82f6", "--cyan": "#0f766e", "--violet": "#7c3aed", "--yellow": "#b45309",
      "--orange": "#1d4ed8", "--green": "#15803d", "--ink": "#111827", "--text": "#1f2937", "--muted": "#6b7280", "--dim": "#9ca3af",
      "--hi": "#111827", "--on-accent": "#ffffff", "--on-cyan": "#ffffff", "--paper": "#ffffff", "--field": "#ffffff",
      "--field2": "#fbfcfe", "--bubble": "#f6f8fb", "--code-bg": "#f3f4f6", "--side-top": "#ffffff",
      "--side-bg": "#ffffff", "--stripe1": "#eef1f6", "--stripe2": "#f6f8fb", "--led-off": "#d1d5db",
      "--console-bg": "rgba(255,255,255,.98)", "--scrim": "rgba(17,24,39,.45)",
    },
    graphite: {
      "--bg": "#141619", "--bg2": "#1a1d21", "--panel": "rgba(29,32,38,.97)", "--panel-solid": "#1d2026", "--line": "#2d323b",
      "--pink": "#4f8cff", "--hot": "#6aa0ff", "--cyan": "#38bdf8", "--violet": "#a78bfa", "--yellow": "#fbbf24",
      "--orange": "#3b76f6", "--green": "#34d399", "--ink": "#f3f4f6", "--text": "#e5e7eb", "--muted": "#9ca3af", "--dim": "#6b7280",
      "--hi": "#f9fafb", "--on-accent": "#ffffff", "--on-cyan": "#0b1220", "--paper": "#ffffff", "--field": "#16181d",
      "--field2": "#181b20", "--bubble": "#22262d", "--code-bg": "#101215", "--side-top": "#17191d",
      "--side-bg": "#17191d", "--stripe1": "#22262d", "--stripe2": "#1c1f25", "--led-off": "#3a3f48",
      "--console-bg": "rgba(16,18,21,.98)", "--scrim": "rgba(0,0,0,.6)",
    },
  };

  function pixelVars(season, time) {
    const a = ACCENT[season], sky = SKY[time];
    const light = time === "morning" || time === "day";
    const dk = (h, t) => toHex(mix(hex(h), [24, 22, 40], t));
    const tint = hex(SEASON_TINT[season][0]);
    if (light) {
      return {
        "--bg": toHex(mix(hex(sky.hz), tint, .2)), "--bg2": "#fff7ec", "--panel": "rgba(255,251,244,.86)", "--panel-solid": "#fffaf2",
        "--line": toHex(mix(hex(a.pink), [60, 50, 70], .45)) + "66",
        "--pink": a.pink, "--hot": a.pink, "--cyan": dk(a.cyan, .45), "--violet": dk(a.violet, .25), "--yellow": dk(a.yellow, .5),
        "--orange": a.orange, "--green": dk(a.green, .45), "--ink": "#1e1b2c", "--text": "#26233a", "--muted": "#615b74", "--dim": "#9a94a8",
        "--hi": "#1b1830", "--on-accent": "#ffffff", "--on-cyan": "#ffffff", "--paper": "#ffffff", "--field": "rgba(255,255,255,.92)",
        "--field2": "rgba(255,255,255,.85)", "--bubble": "rgba(255,255,255,.92)", "--code-bg": "#f4efe6",
        "--side-top": "#fff7ec", "--side-bg": "rgba(255,250,242,.82)", "--stripe1": "#f2e9da", "--stripe2": "#f8f1e5",
        "--led-off": "#d6cfc3", "--console-bg": "rgba(255,250,242,.97)", "--scrim": "rgba(30,26,50,.45)",
      };
    }
    const deep = toHex(mix(hex(sky.top), [0, 0, 0], .35));
    return {
      "--bg": deep, "--bg2": toHex(mix(hex(sky.mid), [0, 0, 0], .5)), "--panel": `rgba(${mix(hex(sky.top), [10, 10, 24], .45).map(Math.round)},.80)`,
      "--panel-solid": toHex(mix(hex(sky.top), [10, 10, 24], .4)), "--line": toHex(mix(hex(a.pink), hex(sky.top), .55)),
      "--pink": a.pink, "--hot": a.pink, "--cyan": a.cyan, "--violet": a.violet, "--yellow": a.yellow, "--orange": a.orange,
      "--green": a.green, "--ink": "#f3f1ff", "--text": "#e9e8f6", "--muted": "#aeb0cf", "--dim": "#737796",
      "--hi": "#ffffff", "--on-accent": "#ffffff", "--on-cyan": deep, "--paper": "#ffffff",
      "--field": "rgba(6,8,22,.72)", "--field2": "rgba(6,8,22,.6)", "--bubble": "rgba(10,12,30,.82)", "--code-bg": "rgba(0,0,0,.45)",
      "--side-top": deep, "--side-bg": `linear-gradient(180deg, ${toHex(mix(hex(sky.top), [0, 0, 0], .25))}d9, ${deep}e6)`,
      "--stripe1": toHex(mix(hex(sky.top), [0, 0, 0], .2)), "--stripe2": toHex(mix(hex(sky.top), [0, 0, 0], .35)),
      "--led-off": "#3b3f5c", "--console-bg": "rgba(4,6,18,.95)", "--scrim": "rgba(0,0,10,.65)",
    };
  }

  // ------------------------------------------------------------------ состояние
  const DEFAULTS = { theme: "pixel", season: "auto", time: "auto", fx: 2, particles: 2, motion: true, crt: false,
    font: "pixel", blur: true, speed: 1 };
  let P = { ...DEFAULTS };
  let cur = { theme: null, season: null, time: null };
  const canvas = document.createElement("canvas"), over = document.createElement("canvas");
  canvas.id = "scene"; over.id = "sceneFx";
  let scene = null, raf = 0, lastFrame = 0, forced = null;

  function resolved() {
    return {
      season: forced?.season || (P.season === "auto" ? seasonNow() : P.season),
      time: forced?.time || (P.time === "auto" ? timeNow() : P.time),
    };
  }

  function apply(prefs) {
    if (prefs) P = { ...DEFAULTS, ...prefs };
    if (!canvas.isConnected) { document.body.prepend(over); document.body.prepend(canvas); }
    const { season, time } = resolved();
    const b = document.body;
    b.dataset.theme = P.theme;
    b.dataset.season = season;
    b.dataset.time = time;
    b.dataset.mode = P.theme === "pixel" ? (time === "morning" || time === "day" ? "light" : "dark")
      : P.theme === "office" || P.theme === "ink" ? "light" : "dark";
    b.classList.toggle("clean-fonts", P.font === "clean" || P.theme === "office" || P.theme === "graphite");
    b.classList.toggle("ink-fonts", P.theme === "ink");
    b.classList.toggle("no-crt", !(P.crt && (P.theme === "neon" || P.theme === "pixel")));
    b.classList.toggle("no-blur", !P.blur);
    const vars = P.theme === "pixel" ? pixelVars(season, time) : VARS[P.theme] || VARS.neon;
    const root = document.documentElement.style;
    for (const [k, v] of Object.entries(vars)) root.setProperty(k, v);
    if (!vars["--alert"]) root.setProperty("--alert", vars["--pink"]);
    const key = P.theme + "/" + season + "/" + time + "/" + P.particles + "/" + P.fx;
    if (key !== cur.key) {
      cur = { theme: P.theme, season, time, key };
      canvas.classList.add("fade");
      setTimeout(() => { buildScene(); canvas.classList.remove("fade"); }, scene ? 350 : 0);
    }
    loop();
    document.dispatchEvent(new CustomEvent("themechange", { detail: { ...P, season, time } }));
  }

  function buildScene() {
    const { season, time } = resolved();
    scene = P.theme === "pixel" ? new PixelScene(season, time) : P.theme === "neon" ? new NeonScene() : P.theme === "ink" ? new InkScene() : null;
    resize();
    if (!scene) { canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height); over.getContext("2d").clearRect(0, 0, over.width, over.height); }
    else scene.frame(performance.now() / 1000, true);
  }

  function resize() {
    const W = innerWidth, H = innerHeight;
    if (scene && scene.lowres) { canvas.width = scene.w; canvas.height = scene.h; canvas.classList.add("pix"); }
    else { canvas.width = W; canvas.height = H; canvas.classList.remove("pix"); }
    over.width = Math.round(W * Math.min(devicePixelRatio || 1, 1.5)); over.height = Math.round(H * Math.min(devicePixelRatio || 1, 1.5));
    if (scene) { scene.resize && scene.resize(); scene.frame(performance.now() / 1000, true); }
  }
  addEventListener("resize", () => { clearTimeout(resize.t); resize.t = setTimeout(resize, 120); });

  function loop() {
    cancelAnimationFrame(raf);
    const step = (now) => {
      raf = requestAnimationFrame(step);
      if (!scene || document.hidden) return;
      if (!P.motion) return;
      if (now - lastFrame < 1000 / 30) return;   // 30 кадров/с достаточно и бережёт GPU для Qwen
      lastFrame = now;
      scene.frame(now / 1000 * P.speed, false);
    };
    raf = requestAnimationFrame(step);
  }
  // раз в минуту: не сменилось ли время суток или сезон
  setInterval(() => { if (P.season === "auto" || P.time === "auto") apply(); }, 60000);

  // ================================================================== ПИКСЕЛЬ-МИР
  class PixelScene {
    constructor(season, time) {
      this.lowres = true; this.w = 320; this.h = 180;
      this.season = season; this.time = time; this.sky = SKY[time];
      this.r = rng(season.length * 97 + time.length * 13 + 7);
      this.bg = document.createElement("canvas"); this.bg.width = this.w; this.bg.height = this.h;
      this.fg = document.createElement("canvas"); this.fg.width = this.w; this.fg.height = this.h;
      this.horizon = 118; this.lake = [118, 148];
      this.parts = []; this.smoke = []; this.lights = []; this.stars = []; this.shoot = null;
      this.night = time === "night" || time === "deep";
      this.dusk = time === "evening" || time === "morning";
      this.build();
    }
    // свет: умножаем на освещённость и подкрашиваем ночью в синий
    L(c, k = 1) {
      c = C(c);
      const l = this.sky.light * k;
      let o = [c[0] * l, c[1] * l, c[2] * l];
      if (this.night) o = mix(o, [30, 40, 90], this.time === "deep" ? .38 : .25);
      if (this.time === "evening") o = mix(o, [255, 120, 70], .12);
      if (this.time === "morning") o = mix(o, [255, 190, 170], .08);
      const t = SEASON_TINT[this.season];
      return mix(o, mix(hex(t[0]), o, .5), t[1] * .5);
    }
    sunPos() {
      const p = timeProgress(this.time);
      const tbl = { morning: [40 + p * 70, 104 - p * 40], day: [120 + p * 130, 34 + Math.abs(p - .3) * 20],
        evening: [220 + p * 60, 70 + p * 46], night: [240 - p * 60, 30 + p * 6], deep: [120 - p * 50, 26 + p * 14] }[this.time];
      return { x: tbl[0], y: tbl[1] };
    }
    build() {
      const { w, h, r } = this;
      const b = this.bg.getContext("2d"), f = this.fg.getContext("2d");
      b.imageSmoothingEnabled = f.imageSmoothingEnabled = false;
      const sky = this.sky, tint = SEASON_TINT[this.season];
      const top = mix(hex(sky.top), hex(tint[0]), tint[1]), mid = mix(hex(sky.mid), hex(tint[0]), tint[1]), hz = mix(hex(sky.hz), hex(tint[0]), tint[1]);
      // небо полосами с дизерингом — как в 16-битных играх
      for (let y = 0; y < this.horizon; y++) {
        const t = y / this.horizon;
        const c = t < .55 ? mix(top, mid, t / .55) : mix(mid, hz, (t - .55) / .45);
        const band = Math.floor(t * 18) / 18, c2 = band < .55 ? mix(top, mid, band / .55) : mix(mid, hz, (band - .55) / .45);
        for (let x = 0; x < w; x++) { b.fillStyle = rgb((x + y) % 2 ? c : c2); b.fillRect(x, y, 1, 1); }
      }
      // звёзды
      if (this.night || this.time === "evening") {
        const n = this.time === "deep" ? 160 : this.time === "night" ? 90 : 20;
        for (let i = 0; i < n; i++) this.stars.push({ x: r() * w | 0, y: r() * (this.horizon - 20) | 0, p: r() * 6, s: r() < .1 ? 2 : 1 });
        if (this.time === "deep") {   // Млечный Путь
          for (let i = 0; i < 700; i++) { const t = r(); const x = t * w, y = 10 + t * 50 + (r() - .5) * 22;
            b.fillStyle = rgb([190, 200, 255], .05 + r() * .12); b.fillRect(x | 0, y | 0, 1, 1); }
        }
      }
      // солнце / луна
      const sp = this.sunPos(); this.sp = sp;
      if (sky.body === "sun") {
        const R = this.time === "day" ? 9 : 12;
        for (let y = -R; y <= R; y++) for (let x = -R; x <= R; x++) {
          const d = Math.hypot(x, y);
          if (d <= R) { b.fillStyle = rgb(mix(hex(sky.sun), [255, 255, 255], d < R - 3 ? .35 : 0)); b.fillRect(sp.x + x | 0, sp.y + y | 0, 1, 1); }
        }
        if (this.time === "evening") for (let k = 0; k < 4; k++) { b.fillStyle = rgb(hex(sky.mid)); b.fillRect(sp.x - R | 0, sp.y + 3 + k * 3 | 0, R * 2 + 1, 1); }
      } else {
        const R = 7;
        for (let y = -R; y <= R; y++) for (let x = -R; x <= R; x++) {
          const d = Math.hypot(x, y), d2 = Math.hypot(x + 4, y - 2);
          if (d <= R && d2 > R - .5) { b.fillStyle = rgb(mix([240, 240, 255], [190, 200, 240], (x + R) / (2 * R) * .5)); b.fillRect(sp.x + x | 0, sp.y + y | 0, 1, 1); }
        }
      }
      // облака
      this.clouds = [];
      const nc = this.night ? 3 : this.time === "day" ? 6 : 5;
      for (let i = 0; i < nc; i++) this.clouds.push({ x: r() * w, y: 12 + r() * 50, s: .6 + r() * .9, v: .02 + r() * .05, seed: r() * 1000 });
      // горы (две гряды)
      const ridge = (base, amp, rough, col, snowLine) => {
        // высоты: сумма синусов со случайными фазами + шум — горы без повторяющегося рисунка
        const ph = [r() * 6, r() * 6, r() * 6, r() * 6];
        const hgt = [];
        let n = 0;
        for (let x = 0; x < w; x++) {
          n += (r() - .5) * rough * .35; n *= .92;
          const y = base - amp * (.55 * Math.sin(x / 47 + ph[0]) + .3 * Math.sin(x / 21 + ph[1]) + .15 * Math.sin(x / 9 + ph[2]) + .6) + n;
          hgt.push(y);
        }
        for (let x = 0; x < w; x++) {
          const slope = (hgt[Math.min(w - 1, x + 2)] - hgt[Math.max(0, x - 2)]) / 4;   // наклон по 5 столбцам — без полос
          for (let yy = hgt[x] | 0; yy < this.horizon + 2; yy++) {
            let c = this.L(col, .92 + (yy - hgt[x]) / 140);
            if (snowLine && yy - hgt[x] < snowLine * (1 + Math.sin(x * .3) * .4)) c = this.L(this.season === "winter" ? "#f4f8ff" : "#e9eef9", 1.05);
            if (!this.night) c = mix(c, slope > 0 ? hex(sky.sun) : [20, 20, 50], Math.min(.18, Math.abs(slope) * .25));
            b.fillStyle = rgb(c); b.fillRect(x, yy, 1, 1);
          }
        }
        return hgt;
      };
      const far = { winter: "#8fa3cf", spring: "#8e9ac9", summer: "#7f95c2", autumn: "#9b8aa9" }[this.season];
      const near = { winter: "#6e86b8", spring: "#5f8a76", summer: "#4f7f5a", autumn: "#8a6a4a" }[this.season];
      this.ridgeFar = ridge(84, 26, 3.2, far, this.season === "winter" ? 14 : this.season === "summer" ? 0 : 5);
      this.ridgeNear = ridge(106, 12, 2.2, near, this.season === "winter" ? 8 : 0);
      // туман у подножия
      for (let y = this.horizon - 14; y < this.horizon; y++) { b.fillStyle = rgb(hz, (y - this.horizon + 14) / 14 * .35); b.fillRect(0, y, w, 1); }

      // ---- передний план (отдельный буфер — его не отражаем)
      const groundY = this.lake[1];
      const g1 = { winter: "#eef3ff", spring: "#6cc06a", summer: "#3f9a3a", autumn: "#b98c3b" }[this.season];
      const g2 = { winter: "#c9d6f0", spring: "#4c9e52", summer: "#2f7a2c", autumn: "#8d6a2b" }[this.season];
      // берег
      for (let x = 0; x < w; x++) {
        const sh = groundY - 2 + Math.round(Math.sin(x / 9) * 1.5 + Math.sin(x / 23) * 2);
        for (let y = sh; y < h; y++) {
          const d = (y - sh) / (h - sh);
          let c = this.L(mix(hex(g1), hex(g2), Math.min(1, d * 1.3 + (r() < .2 ? .15 : 0))));
          f.fillStyle = rgb(c); f.fillRect(x, y, 1, 1);
        }
        f.fillStyle = rgb(this.L(this.season === "winter" ? "#ffffff" : mix(hex(g1), [255, 255, 255], .25)));
        f.fillRect(x, sh, 1, 1);
      }
      // тропинка к дому
      for (let y = groundY + 4; y < h; y++) {
        const cx = 186 - (y - groundY) * 1.4, hw = 2 + (y - groundY) * .35;
        f.fillStyle = rgb(this.L(this.season === "winter" ? "#d7def0" : "#c8a874"));
        f.fillRect(cx - hw | 0, y, hw * 2 | 0, 1);
      }
      // цветы/листья на земле
      for (let i = 0; i < 160; i++) {
        const x = r() * w | 0, y = groundY + 4 + r() * (h - groundY - 4) | 0;
        const c = { winter: ["#ffffff", "#dfe8ff"], spring: ["#ff8fc0", "#ffe36e", "#ffffff", "#b58cff"], summer: ["#ffe14e", "#ff6b6b", "#ffffff"],
          autumn: ["#e35b26", "#f2a33a", "#a8321e", "#ffd25a"] }[this.season];
        f.fillStyle = rgb(this.L(c[i % c.length])); f.fillRect(x, y, 1, 1);
      }
      // деревья
      const tree = (x, y, s, kind) => {
        const trunk = this.L("#5a3d2a");
        if (kind === "pine") {
          f.fillStyle = rgb(trunk); f.fillRect(x - 1, y - 4 * s, 2, 4 * s);
          for (let k = 0; k < 4; k++) {
            const wy = y - 4 * s - k * 5 * s, ww = (8 - k * 1.6) * s;
            for (let yy = 0; yy < 6 * s; yy++) {
              const half = ww * (yy / (6 * s));
              for (let xx = -half; xx <= half; xx++) {
                let c = this.L(this.season === "winter" ? "#2f5a52" : "#24563c", 1 - (xx + half) / (half * 2 + 1) * .25);
                if (this.season === "winter" && (yy < 2 || r() < .25)) c = this.L("#f4f8ff");
                f.fillStyle = rgb(c); f.fillRect(x + xx | 0, wy - 6 * s + yy | 0, 1, 1);
              }
            }
          }
        } else {
          f.fillStyle = rgb(trunk); f.fillRect(x - 1, y - 10 * s, 2, 10 * s);
          if (this.season === "winter") {   // голые ветки со снегом
            for (let k = 0; k < 6; k++) { const a = -Math.PI / 2 + (k - 2.5) * .45, L = (6 + r() * 5) * s;
              for (let t = 0; t < L; t++) { f.fillStyle = rgb(t < L - 1 ? trunk : this.L("#ffffff")); f.fillRect(x + Math.cos(a) * t | 0, y - 9 * s + Math.sin(a) * t | 0, 1, 1); } }
            return;
          }
          const pal = { spring: ["#ffb7d5", "#ff8fc0", "#ffe0ee", "#fff"], summer: ["#3fa34d", "#2e8a3c", "#5cc062", "#247530"],
            autumn: ["#e35b26", "#f2a33a", "#ffd25a", "#b8401f"] }[this.season];
          const R = 8 * s;
          for (let yy = -R; yy <= R; yy++) for (let xx = -R * 1.2; xx <= R * 1.2; xx++) {
            const d = Math.hypot(xx / 1.2, yy) + (r() - .5) * 2.5;
            if (d < R) {
              const lit = (-xx - yy) / (R * 2);   // свет слева сверху
              f.fillStyle = rgb(this.L(pal[(r() * pal.length) | 0], 1 + lit * .35));
              f.fillRect(x + xx | 0, y - 12 * s + yy | 0, 1, 1);
            }
          }
        }
      };
      const kinds = this.season === "winter" ? ["pine", "pine", "bare"] : this.season === "summer" ? ["round", "pine", "round"] : ["round", "round", "pine"];
      const treesAt = [[18, 1.2], [44, .9], [70, 1.4], [255, 1.1], [282, 1.5], [306, .9], [120, .8]];
      treesAt.forEach(([x, s], i) => tree(x, groundY + 10 + (i % 3) * 4, s, kinds[i % kinds.length]));
      // дом
      const hx = 172, hy = groundY + 6;
      const wall = this.L(this.season === "autumn" ? "#a8653a" : "#b97a4b"), wall2 = this.L("#8a5532");
      f.fillStyle = rgb(wall); f.fillRect(hx, hy - 20, 30, 20);
      f.fillStyle = rgb(wall2); f.fillRect(hx + 22, hy - 20, 8, 20);
      for (let k = 0; k < 14; k++) { f.fillStyle = rgb(this.L(this.season === "winter" ? "#f4f8ff" : "#7a2f2f", k < 2 && this.season === "winter" ? 1 : .95));
        f.fillRect(hx - 3 + k, hy - 20 - k, 36 - k * 2, 1); }
      f.fillStyle = rgb(this.L("#5b4a45")); f.fillRect(hx + 22, hy - 34, 4, 10);
      this.chimney = { x: hx + 24, y: hy - 35 };
      f.fillStyle = rgb(this.L("#4a2e1e")); f.fillRect(hx + 12, hy - 10, 6, 10);
      const lit = this.night || this.time === "evening";
      [[hx + 4, hy - 15], [hx + 22, hy - 15]].forEach(([x, y]) => {
        f.fillStyle = rgb(lit ? [255, 205, 110] : this.L("#9fc7ff", 1.1)); f.fillRect(x, y, 5, 5);
        f.fillStyle = rgb(this.L("#3b2a20")); f.fillRect(x + 2, y, 1, 5); f.fillRect(x, y + 2, 5, 1);
        if (lit) this.lights.push({ x: x + 2.5, y: y + 2.5, r: 28, c: [255, 190, 90], k: .55 });
      });
      // фонари
      [[150, groundY + 16], [214, groundY + 18]].forEach(([x, y]) => {
        f.fillStyle = rgb(this.L("#2b2b33")); f.fillRect(x, y - 14, 1, 14); f.fillRect(x - 1, y - 15, 3, 1);
        f.fillStyle = rgb(lit ? [255, 236, 170] : this.L("#e0e4ec")); f.fillRect(x - 1, y - 18, 3, 3);
        if (lit) this.lights.push({ x: x + .5, y: y - 16.5, r: 36, c: [255, 220, 140], k: .7, pool: true, py: y });
      });
      // снеговик зимой, скворечник летом — мелочи, которые приятно заметить
      if (this.season === "winter") { [[5, 0], [4, -8], [3, -14]].forEach(([R, dy]) => { for (let yy = -R; yy <= R; yy++) for (let xx = -R; xx <= R; xx++)
        if (Math.hypot(xx, yy) <= R) { f.fillStyle = rgb(this.L("#f8fbff", 1 - (xx + yy) / 40)); f.fillRect(232 + xx, groundY + 20 + dy + yy, 1, 1); } });
        f.fillStyle = rgb(this.L("#ff7a18")); f.fillRect(234, groundY + 6, 2, 1); }

      // данные для отражения
      this.bgData = b.getImageData(0, 0, w, h);
      this.buf = document.createElement("canvas"); this.buf.width = w; this.buf.height = h;
      this.water = this.buf.getContext("2d").createImageData(w, this.lake[1] - this.lake[0]);
      // частицы
      const n = [0, 70, 170][P.particles] * (this.season === "winter" ? 1.4 : 1);
      for (let i = 0; i < n; i++) this.parts.push(this.newPart(true));
      if (this.season === "summer" && (this.night || this.time === "evening"))
        for (let i = 0; i < [0, 18, 40][P.particles]; i++) this.parts.push({ k: "fly", x: r() * w, y: 100 + r() * 70, p: r() * 6, v: .2 + r() * .4 });
    }
    newPart(init) {
      const r = Math.random, w = this.w, h = this.h;
      const base = { x: r() * w, y: init ? r() * h : -4, z: .5 + r() * .8, p: r() * 6 };
      if (this.season === "winter") return { ...base, k: "snow", v: .15 + r() * .35 };
      if (this.season === "autumn") return { ...base, k: "leaf", v: .18 + r() * .25, c: ["#e35b26", "#f2a33a", "#ffd25a", "#b8401f", "#c97a2a"][r() * 5 | 0] };
      if (this.season === "spring") return { ...base, k: "petal", v: .12 + r() * .2, c: ["#ffb7d5", "#ffd3e6", "#ffffff"][r() * 3 | 0] };
      return { ...base, k: this.night ? "dust" : "pollen", v: .03 + r() * .06, c: "#fff6c8" };
    }
    frame(t, _init, offscreen) {
      const { w, h } = this;
      const bc = this.buf.getContext("2d");
      bc.putImageData(this.bgData, 0, 0);
      // мерцание звёзд
      for (const s of this.stars) {
        const a = .5 + .5 * Math.sin(t * 2 + s.p);
        bc.fillStyle = `rgba(255,255,255,${.25 + a * .75})`; bc.fillRect(s.x, s.y, s.s, s.s);
        if (s.s > 1 && a > .9) { bc.fillRect(s.x - 1, s.y, 4, 1); bc.fillRect(s.x, s.y - 1, 1, 4); }
      }
      // падающая звезда
      if (this.time === "deep" || this.time === "night") {
        if (!this.shoot && Math.random() < .004) this.shoot = { x: 60 + Math.random() * 200, y: 10 + Math.random() * 30, l: 0 };
        if (this.shoot) { const s = this.shoot; s.l += 3;
          for (let k = 0; k < 10; k++) { bc.fillStyle = `rgba(255,255,255,${1 - k / 10})`; bc.fillRect(s.x + s.l - k * 2, s.y + (s.l - k * 2) * .4, 1, 1); }
          if (s.l > 70) this.shoot = null; }
      }
      // облака
      for (const c of this.clouds) {
        c.x += c.v; if (c.x > w + 40) c.x = -40;
        const rr = rng(c.seed | 0);
        const col = this.night ? [60, 70, 120] : this.time === "evening" ? [255, 170, 150] : this.time === "morning" ? [255, 225, 220] : [255, 255, 255];
        for (let k = 0; k < 7; k++) {
          const ox = (rr() - .5) * 30 * c.s, oy = (rr() - .5) * 6 * c.s, R = (5 + rr() * 6) * c.s;
          for (let yy = -R; yy <= R; yy++) { const half = Math.sqrt(R * R - yy * yy) * 1.6;
            bc.fillStyle = rgb(mix(col, [0, 0, 0], yy > 0 ? .12 : 0), this.night ? .45 : .85);
            bc.fillRect(c.x + ox - half | 0, c.y + oy + yy | 0, half * 2 | 0, 1); }
        }
      }
      // отражение в озере (зимой — лёд)
      const [L0, L1] = this.lake, src = bc.getImageData(0, 0, w, L0), wd = this.water.data, sd = src.data;
      const frozen = this.season === "winter";
      const wc = frozen ? [205, 222, 245] : this.season === "autumn" ? [40, 70, 90] : [30, 80, 120];
      const wl = this.L(wc);
      for (let y = 0; y < L1 - L0; y++) {
        const sy = Math.max(0, L0 - 1 - Math.round(y * 1.7));
        const amp = frozen ? 0 : (P.fx ? .6 + y * .09 : 0);
        const off = Math.round(Math.sin(y * .9 + t * 2.2) * amp + Math.sin(y * .31 - t * 1.3) * amp * .5);
        const k = frozen ? .55 : .35 + y / (L1 - L0) * .2;
        for (let x = 0; x < w; x++) {
          const sx = Math.min(w - 1, Math.max(0, x + off)), si = (sy * w + sx) * 4, di = (y * w + x) * 4;
          wd[di] = sd[si] * (1 - k) + wl[0] * k; wd[di + 1] = sd[si + 1] * (1 - k) + wl[1] * k; wd[di + 2] = sd[si + 2] * (1 - k) + wl[2] * k; wd[di + 3] = 255;
          if (!frozen && P.fx && (x * 7 + y * 13 + (t * 9 | 0)) % 97 === 0) { wd[di] += 40; wd[di + 1] += 40; wd[di + 2] += 40; }
        }
      }
      bc.putImageData(this.water, 0, L0);
      if (frozen && P.fx) for (let i = 0; i < 6; i++) {   // искры на льду
        const x = (Math.sin(t * .7 + i * 17) * .5 + .5) * w | 0, y = L0 + 3 + ((i * 37) % (L1 - L0 - 6));
        bc.fillStyle = `rgba(255,255,255,${.5 + .5 * Math.sin(t * 6 + i)})`; bc.fillRect(x, y, 1, 1);
      }
      bc.drawImage(this.fg, 0, 0);
      // дым из трубы
      if (this.season !== "summer" || this.night) {
        if (Math.random() < .3) this.smoke.push({ x: this.chimney.x, y: this.chimney.y, a: .55, s: 1 });
        for (const s of this.smoke) { s.y -= .25; s.x += .12 + Math.sin(t + s.y * .1) * .08; s.a -= .006; s.s += .02;
          bc.fillStyle = `rgba(${this.night ? "150,155,180" : "235,235,240"},${Math.max(0, s.a)})`; bc.fillRect(s.x | 0, s.y | 0, s.s + 1 | 0, s.s + 1 | 0); }
        this.smoke = this.smoke.filter((s) => s.a > 0);
      }
      // частицы
      const wind = Math.sin(t * .3) * .25 + (this.season === "autumn" ? .25 : .05);
      for (const p of this.parts) {
        if (p.k === "fly") {
          p.x += Math.sin(t * p.v + p.p) * .3; p.y += Math.cos(t * p.v * 1.3 + p.p) * .2;
          const a = .5 + .5 * Math.sin(t * 3 + p.p);
          bc.fillStyle = `rgba(230,255,120,${a})`; bc.fillRect(p.x | 0, p.y | 0, 1, 1);
          continue;
        }
        p.y += p.v * p.z; p.x += (wind + Math.sin(t * 1.5 + p.p) * (p.k === "leaf" ? .45 : .2)) * p.z;
        if (p.y > h + 3 || p.x > w + 6 || p.x < -6) Object.assign(p, this.newPart(false), { x: p.x < -6 ? w : Math.random() * w });
        if (p.k === "snow") { bc.fillStyle = `rgba(255,255,255,${.6 + p.z * .3})`; bc.fillRect(p.x | 0, p.y | 0, p.z > 1 ? 2 : 1, p.z > 1 ? 2 : 1); }
        else if (p.k === "leaf") { bc.fillStyle = rgb(this.L(p.c)); const fl = Math.sin(t * 4 + p.p) > 0;
          bc.fillRect(p.x | 0, p.y | 0, fl ? 2 : 1, fl ? 1 : 2); }
        else if (p.k === "petal") { bc.fillStyle = rgb(this.L(p.c, 1.1)); bc.fillRect(p.x | 0, p.y | 0, Math.sin(t * 3 + p.p) > 0 ? 2 : 1, 1); }
        else { bc.fillStyle = `rgba(255,250,210,${.25 + .35 * Math.sin(t + p.p)})`; bc.fillRect(p.x | 0, p.y | 0, 1, 1); }
      }
      if (offscreen) return;
      const ctx = canvas.getContext("2d");
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(this.buf, 0, 0);
      this.fx(t);
    }
    // ------------- «RTX»: всё, что светится, — на полноразмерном холсте поверх пикселей
    map(x, y) {
      const W = over.width, H = over.height, s = Math.max(W / this.w, H / this.h);
      return [(W - this.w * s) / 2 + x * s, (H - this.h * s) / 2 + y * s, s];
    }
    fx(t) {
      const o = over.getContext("2d"), W = over.width, H = over.height;
      o.clearRect(0, 0, W, H);
      if (!P.fx) return;
      const hi = P.fx >= 2;
      o.globalCompositeOperation = "screen";
      const [sx, sy, s] = this.map(this.sp.x, this.sp.y);
      const sun = hex(this.sky.sun);
      // свечение солнца / луны
      const glowR = (this.sky.body === "sun" ? (this.time === "day" ? 90 : 140) : 70) * s / 4;
      let g = o.createRadialGradient(sx, sy, 0, sx, sy, glowR * (1 + .03 * Math.sin(t * 1.3)));
      g.addColorStop(0, rgb(sun, this.sky.body === "sun" ? .75 : .4)); g.addColorStop(.25, rgb(sun, .25)); g.addColorStop(1, rgb(sun, 0));
      o.fillStyle = g; o.fillRect(0, 0, W, H);
      // солнечные лучи сквозь атмосферу (утро/вечер — сильнее)
      if (this.sky.body === "sun" && hi) {
        const n = 9, k = this.time === "day" ? .05 : .11;
        for (let i = 0; i < n; i++) {
          const a = Math.PI / 2 + (i - n / 2) * .16 + Math.sin(t * .15 + i) * .03;
          const len = H * 1.4, wdt = .045 + (i % 3) * .015;
          o.beginPath(); o.moveTo(sx, sy);
          o.lineTo(sx + Math.cos(a - wdt) * len, sy + Math.sin(a - wdt) * len);
          o.lineTo(sx + Math.cos(a + wdt) * len, sy + Math.sin(a + wdt) * len); o.closePath();
          const lg = o.createLinearGradient(sx, sy, sx + Math.cos(a) * len, sy + Math.sin(a) * len);
          lg.addColorStop(0, rgb(sun, k * (.6 + .4 * Math.sin(t * .7 + i * 2)))); lg.addColorStop(1, rgb(sun, 0));
          o.fillStyle = lg; o.fill();
        }
        // блики объектива
        const cx = W / 2, cy = H / 2;
        [[.35, 18, .18], [.6, 9, .22], [1.25, 30, .1], [1.6, 12, .16]].forEach(([d, r, a], i) => {
          const fx = sx + (cx - sx) * d, fy = sy + (cy - sy) * d;
          const fg = o.createRadialGradient(fx, fy, 0, fx, fy, r * s / 3);
          const col = i % 2 ? [120, 200, 255] : [255, 180, 120];
          fg.addColorStop(0, rgb(col, a)); fg.addColorStop(.7, rgb(col, a * .4)); fg.addColorStop(1, rgb(col, 0));
          o.fillStyle = fg; o.fillRect(fx - r * s, fy - r * s, r * s * 2, r * s * 2);
        });
      }
      // окна, фонари: свечение + световое пятно на земле (это и есть «глобальное освещение»)
      for (const l of this.lights) {
        const [lx, ly] = this.map(l.x, l.y), fl = 1 + Math.sin(t * 9 + l.x) * .04 + (Math.random() - .5) * .03;
        const lg = o.createRadialGradient(lx, ly, 0, lx, ly, l.r * s / 3 * fl);
        lg.addColorStop(0, rgb(l.c, l.k)); lg.addColorStop(.3, rgb(l.c, l.k * .35)); lg.addColorStop(1, rgb(l.c, 0));
        o.fillStyle = lg; o.fillRect(lx - l.r * s, ly - l.r * s, l.r * s * 2, l.r * s * 2);
        if (l.pool && hi) { const [px, py] = this.map(l.x, l.py); o.save(); o.translate(px, py); o.scale(1, .3);
          const pg = o.createRadialGradient(0, 0, 0, 0, 0, 22 * s / 2); pg.addColorStop(0, rgb(l.c, .35)); pg.addColorStop(1, rgb(l.c, 0));
          o.fillStyle = pg; o.fillRect(-30 * s, -30 * s, 60 * s, 60 * s); o.restore(); }
      }
      // светлячки — с ореолом
      for (const p of this.parts) if (p.k === "fly") {
        const [fx, fy] = this.map(p.x, p.y), a = .5 + .5 * Math.sin(t * 3 + p.p);
        const fg = o.createRadialGradient(fx, fy, 0, fx, fy, 3 * s); fg.addColorStop(0, `rgba(220,255,120,${.55 * a})`); fg.addColorStop(1, "rgba(220,255,120,0)");
        o.fillStyle = fg; o.fillRect(fx - 3 * s, fy - 3 * s, 6 * s, 6 * s);
      }
      // северное сияние зимней ночью
      if (this.season === "winter" && this.night && hi) {
        for (let band = 0; band < 3; band++) {
          o.beginPath();
          for (let x = 0; x <= W; x += 12) {
            const y = H * (.12 + band * .05) + Math.sin(x / 160 + t * .25 + band) * H * .04 + Math.sin(x / 47 + t * .6) * H * .01;
            x ? o.lineTo(x, y) : o.moveTo(x, y);
          }
          o.lineTo(W, 0); o.lineTo(0, 0); o.closePath();
          const ag = o.createLinearGradient(0, 0, 0, H * .3);
          const col = band === 1 ? [140, 120, 255] : [80, 255, 170];
          ag.addColorStop(0, rgb(col, 0)); ag.addColorStop(.7, rgb(col, .07 + .04 * Math.sin(t * .5 + band))); ag.addColorStop(1, rgb(col, 0));
          o.fillStyle = ag; o.fill();
        }
      }
      o.globalCompositeOperation = "source-over";
      // утренний туман над озером
      if (this.time === "morning" && hi) {
        const [, ly0] = this.map(0, this.lake[0] - 8), [, ly1] = this.map(0, this.lake[1]);
        for (let i = 0; i < 3; i++) {
          const yy = ly0 + (ly1 - ly0) * (i / 3), off = (t * 12 * (i + 1)) % W;
          const fg = o.createLinearGradient(0, yy - 30, 0, yy + 30);
          fg.addColorStop(0, "rgba(255,245,240,0)"); fg.addColorStop(.5, "rgba(255,245,240,.13)"); fg.addColorStop(1, "rgba(255,245,240,0)");
          o.fillStyle = fg; o.fillRect(-off, yy - 30, W * 2, 60);
        }
      }
      // крупные хлопья «у камеры» — ощущение глубины
      if (this.season === "winter" && P.particles >= 2 && hi) {
        if (!this.bokeh) this.bokeh = Array.from({ length: 14 }, () => ({ x: Math.random(), y: Math.random(), r: 3 + Math.random() * 7, v: .0006 + Math.random() * .001, p: Math.random() * 6 }));
        for (const b of this.bokeh) { b.y += b.v; b.x += Math.sin(t + b.p) * .0004; if (b.y > 1.05) { b.y = -.05; b.x = Math.random(); }
          const bx = b.x * W, by = b.y * H, bg = o.createRadialGradient(bx, by, 0, bx, by, b.r * 2);
          bg.addColorStop(0, "rgba(255,255,255,.55)"); bg.addColorStop(.5, "rgba(255,255,255,.18)"); bg.addColorStop(1, "rgba(255,255,255,0)");
          o.fillStyle = bg; o.fillRect(bx - b.r * 2, by - b.r * 2, b.r * 4, b.r * 4); }
      }
      // виньетка
      const vg = o.createRadialGradient(W / 2, H / 2, Math.min(W, H) * .35, W / 2, H / 2, Math.max(W, H) * .75);
      vg.addColorStop(0, "rgba(0,0,0,0)"); vg.addColorStop(1, `rgba(0,0,${this.night ? 20 : 0},${this.night ? .45 : .22})`);
      o.fillStyle = vg; o.fillRect(0, 0, W, H);
    }
  }

  // ================================================================== НЕОН
  class NeonScene {
    constructor() { this.lowres = false; this.st = Array.from({ length: 140 }, () => ({ x: Math.random(), y: Math.random() * .55, p: Math.random() * 6, s: Math.random() < .15 ? 2 : 1 })); }
    frame(t) {
      const c = canvas.getContext("2d"), W = canvas.width, H = canvas.height;
      const g = c.createLinearGradient(0, 0, 0, H);
      g.addColorStop(0, "#07010f"); g.addColorStop(.55, "#1a0533"); g.addColorStop(1, "#0b0118");
      c.fillStyle = g; c.fillRect(0, 0, W, H);
      for (const s of this.st) { c.fillStyle = `rgba(255,255,255,${.3 + .5 * (.5 + .5 * Math.sin(t * 1.5 + s.p))})`; c.fillRect(s.x * W, s.y * H, s.s, s.s); }
      // солнце в полоску
      const hz = H * .62, sx = W * .62, R = Math.min(W, H) * .2;
      const sg = c.createLinearGradient(0, hz - R, 0, hz);
      sg.addColorStop(0, "#ffd319"); sg.addColorStop(.5, "#ff7a18"); sg.addColorStop(1, "#ff2e88");
      c.save(); c.beginPath(); c.arc(sx, hz, R, Math.PI, 0); c.clip(); c.fillStyle = sg; c.fillRect(sx - R, hz - R, R * 2, R);
      c.fillStyle = "#1a0533";
      for (let k = 0; k < 7; k++) { const y = hz - R * .45 + k * R * .085 + ((t * 8) % (R * .085)); c.fillRect(sx - R, y, R * 2, 2 + k * .9); }
      c.restore();
      // горы-каркас
      c.strokeStyle = "rgba(157,77,255,.55)"; c.lineWidth = 1.2; c.beginPath();
      for (let x = 0; x <= W; x += 18) { const y = hz - Math.abs(Math.sin(x / 140) * 60 + Math.sin(x / 57) * 22); x ? c.lineTo(x, y) : c.moveTo(x, y); }
      c.stroke();
      // бегущая сетка
      c.fillStyle = "#0b0118"; c.fillRect(0, hz, W, H - hz);
      c.strokeStyle = "rgba(255,46,136,.55)"; c.lineWidth = 1;
      const off = (t * .35) % 1;
      for (let i = 0; i < 26; i++) { const k = (i + off) / 26, y = hz + Math.pow(k, 2.2) * (H - hz); c.globalAlpha = .25 + k * .75;
        c.beginPath(); c.moveTo(0, y); c.lineTo(W, y); c.stroke(); }
      c.globalAlpha = 1;
      for (let i = -24; i <= 24; i++) { c.beginPath(); c.moveTo(W / 2 + i * 14, hz); c.lineTo(W / 2 + i * W * .09, H); c.stroke(); }
      const o = over.getContext("2d"); o.clearRect(0, 0, over.width, over.height);
      if (P.fx) { const k = over.width / W, gg = o.createRadialGradient(sx * k, hz * k, 0, sx * k, hz * k, R * 2.4 * k);
        gg.addColorStop(0, "rgba(255,80,140,.35)"); gg.addColorStop(1, "rgba(255,80,140,0)"); o.fillStyle = gg; o.fillRect(0, 0, over.width, over.height); }
    }
  }

  // ================================================================== ТУШЬ И СПИРАЛЬ (своя графика)
  class InkScene {
    constructor() {
      this.lowres = false;
      this.paper = null;
      this.drips = Array.from({ length: 9 }, (_, i) => ({ x: .06 + i * .11 + Math.random() * .04, L: 20 + Math.random() * 70, w: 2 + Math.random() * 3, p: Math.random() * 6 }));
      this.specks = Array.from({ length: 40 }, () => ({ x: Math.random(), y: Math.random(), r: .5 + Math.random() * 2.2, v: .00004 + Math.random() * .0001 }));
    }
    resize() { this.paper = null; }
    makePaper(W, H) {
      const p = document.createElement("canvas"); p.width = W; p.height = H; const c = p.getContext("2d");
      c.fillStyle = "#efe8d8"; c.fillRect(0, 0, W, H);
      const img = c.getImageData(0, 0, W, H), d = img.data;
      for (let i = 0; i < d.length; i += 4) { const n = (Math.random() - .5) * 14; d[i] += n; d[i + 1] += n; d[i + 2] += n * .9; }
      c.putImageData(img, 0, 0);
      // штриховка по краям
      c.strokeStyle = "rgba(20,17,15,.06)"; c.lineWidth = 1;
      for (let i = 0; i < 220; i++) { const x = Math.random() * W, y = H - Math.random() * H * .18; c.beginPath(); c.moveTo(x, y); c.lineTo(x + 26, y - 26); c.stroke(); }
      // засохший цветок в углу — тонкое перо
      const fx = W - 120, fy = H - 40;
      c.strokeStyle = "rgba(20,17,15,.55)"; c.lineWidth = 1.1; c.beginPath(); c.moveTo(fx, fy);
      c.bezierCurveTo(fx - 10, fy - 70, fx + 30, fy - 120, fx - 20, fy - 170); c.stroke();
      for (let k = 0; k < 7; k++) { const a = Math.PI * .9 + k * .28, L = 26 + Math.random() * 14; c.beginPath();
        c.moveTo(fx - 20, fy - 170); c.quadraticCurveTo(fx - 20 + Math.cos(a) * L * .6, fy - 170 + Math.sin(a) * L * .2, fx - 20 + Math.cos(a) * L, fy - 170 + Math.abs(Math.sin(a)) * L);
        c.stroke(); }
      [[fx + 6, fy - 60, -1], [fx + 12, fy - 100, 1]].forEach(([x, y, d]) => { c.beginPath(); c.moveTo(x, y);
        c.quadraticCurveTo(x + 22 * d, y + 4, x + 30 * d, y + 26); c.quadraticCurveTo(x + 10 * d, y + 18, x, y); c.stroke(); });
      return p;
    }
    frame(t) {
      const c = canvas.getContext("2d"), W = canvas.width, H = canvas.height;
      if (!this.paper || this.paper.width !== W) this.paper = this.makePaper(W, H);
      c.drawImage(this.paper, 0, 0);
      // спираль — дрожащая линия пера, медленно закручивается
      const cx = W * .82, cy = H * .3, turns = 7, R = Math.min(W, H) * .32;
      c.save(); c.translate(cx, cy); c.rotate(t * .05);
      for (let pass = 0; pass < 2; pass++) {
        c.beginPath(); c.strokeStyle = pass ? "rgba(20,17,15,.10)" : "rgba(20,17,15,.16)"; c.lineWidth = pass ? 3 : 1.1;
        for (let a = 0; a < turns * Math.PI * 2; a += .05) {
          const r = (a / (turns * Math.PI * 2)) * R, j = Math.sin(a * 17 + pass * 3) * .8;
          const x = Math.cos(a) * (r + j), y = Math.sin(a) * (r + j);
          a ? c.lineTo(x, y) : c.moveTo(x, y);
        }
        c.stroke();
      }
      c.restore();
      // потёки туши сверху: медленно стекают и подсыхают
      c.fillStyle = "rgba(14,12,10,.85)";
      c.fillRect(0, 0, W, 3);
      for (const d of this.drips) {
        const L = d.L * (.75 + .25 * Math.sin(t * .2 + d.p)), x = d.x * W, w = d.w;
        c.beginPath(); c.moveTo(x - w * 2, 0);
        c.bezierCurveTo(x - w, L * .4, x - w * .6, L * .8, x - w * .5, L);
        c.arc(x, L, w * .9, Math.PI, 0, true);
        c.bezierCurveTo(x + w * .6, L * .8, x + w, L * .4, x + w * 2, 0); c.fill();
      }
      for (const s of this.specks) { s.y += s.v; if (s.y > 1) s.y = 0; c.beginPath(); c.arc(s.x * W, s.y * H, s.r, 0, 7); c.fillStyle = "rgba(14,12,10,.12)"; c.fill(); }
      over.getContext("2d").clearRect(0, 0, over.width, over.height);
    }
  }

  // ------------------------------------------------------------------ превью для окна настроек
  function preview(cv, theme, season, time) {
    const saveP = P, ctx = cv.getContext("2d");
    P = { ...P, theme, fx: 2, particles: 2 };
    const tmp = { s: null };
    try {
      if (theme === "pixel") {
        const sc = new PixelScene(season, time);
        sc.frame(3, true, true);   // только во внутренний буфер
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(sc.buf, 0, 0, cv.width, cv.height);
        const sp = sc.sp, sx = sp.x / 320 * cv.width, sy = sp.y / 180 * cv.height;
        const g = ctx.createRadialGradient(sx, sy, 0, sx, sy, cv.width * .25);
        g.addColorStop(0, rgb(hex(SKY[time].sun), .5)); g.addColorStop(1, rgb(hex(SKY[time].sun), 0));
        ctx.globalCompositeOperation = "screen"; ctx.fillStyle = g; ctx.fillRect(0, 0, cv.width, cv.height); ctx.globalCompositeOperation = "source-over";
        tmp.s = sc;
      }
    } finally { P = saveP; }
    return tmp.s;
  }

  return { apply, preview, timeNow, seasonNow, TIMES, SEASONS, DEFAULTS, get prefs() { return { ...P }; },
    resolved, demo(season, time) { forced = season || time ? { season, time } : null; apply(); } };
})();
