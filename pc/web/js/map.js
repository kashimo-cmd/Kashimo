/* K15 map: top-down SVG of the gallery, robot path and pins (design K15, 5.6). Pure model first (tested in Node), DOM last. */
(function (root) {
  "use strict";
  const DEF = { width_m: 2.0, length_m: 30, slab_width_m: 0.5 };
  const MAX_PATH = 6000, MIN_STEP = 0.02, RESET_DROP_M = 0.5, PAD = { l: 12, r: 12, t: 20, b: 22 };
  const num = (v) => typeof v === "number" && Number.isFinite(v);
  const PIN_KIND = { ALERT_DEFECT: "alert", ALERT_ROD: "alert", ALERT_TILT: "alert", ALERT_OBSTACLE: "obstacle", BUMP: "bump", PHOTO: "photo" };
  const PIN_TEXT = { photo: "Photo", alert: "Alert", obstacle: "Obstacle", bump: "Bump" };
  const GLYPH = { photo: "\u25CF", alert: "\u25B2", obstacle: "\u25A0", bump: "\u25C6" };
  const pinKind = (kind) => PIN_KIND[kind] || null;

  function addPoint(path, x, y) {  // keeps the path light: 2 cm steps, halved when it passes MAX_PATH
    const p = path[path.length - 1];
    if (p && Math.hypot(x - p.x, y - p.y) < MIN_STEP) return false;
    path.push({ x, y });
    if (path.length > MAX_PATH) {
      const keep = path.filter((_, i) => i % 2 === 0);
      if (keep[keep.length - 1] !== path[path.length - 1]) keep.push(path[path.length - 1]);
      path.splice(0, path.length, ...keep);
    }
    return true;
  }

  function createModel(cfg) {
    const m = { g: Object.assign({}, DEF, cfg), path: [], pins: new Map(), hole: null, last: null, conn: "connecting", sample: false, selected: null };

    m.update = (v) => {  // v = { conn, t, sample? } -> true when something to redraw changed
      let changed = m.conn !== v.conn || m.sample !== !!v.sample;
      m.conn = v.conn;
      m.sample = !!v.sample;
      const t = v.t, l = m.last;
      if (!t || !num(t.x) || !num(t.y)) return changed;
      if (l && num(t.s) && num(l.s) && t.s < l.s - RESET_DROP_M) { m.path = []; m.hole = null; changed = true; }  // the Pi restarted: new run
      if (!m.hole) m.hole = num(t.s) && t.s < 0.1 ? { x: t.x, y: t.y, exact: true } : { x: 0, y: 0, exact: false };
      const now = { x: t.x, y: t.y, yaw: num(t.yaw) ? t.yaw : null, s: num(t.s) ? t.s : null, imu: t.imu || null };
      if (!l || ["x", "y", "yaw", "s", "imu"].some((k) => l[k] !== now[k])) changed = true;
      m.last = now;
      if (addPoint(m.path, now.x, now.y)) changed = true;
      return changed;
    };

    m.addPin = (p) => {  // p = { key, kind, x, y, slab }
      const pin = pinKind(p.kind);
      if (!pin || !num(p.x) || !num(p.y) || m.pins.has(p.key)) return false;
      m.pins.set(p.key, Object.assign({}, p, { pin }));
      return true;
    };

    m.stats = () => m.last && { path: m.last.s, direct: Math.hypot(m.last.x - m.hole.x, m.last.y - m.hole.y), holeExact: m.hole.exact };

    m.badges = () => {  // [level, text, tooltip]
      const b = [], l = m.last;
      if (m.sample) b.push(["warn", "SAMPLE", "Sample data: not the robot."]);
      if (!l) return b;
      if (m.conn !== "connected") b.push(["warn", "STALE", "The Pi is not connected: position frozen at the last value."]);
      if (l.imu === "LOST") b.push(["err", "IMU LOST", "Heading is frozen: the map stops turning."]);
      else {
        if (l.imu === "CALIBRATING") b.push(["warn", "IMU CALIBRATING", "Heading is not valid until calibration ends."]);
        b.push(["warn", "HEADING UNCERTAIN", "Heading comes from the gyro alone and drifts. Treat y as a sketch."]);
      }
      if (Math.abs(l.y) > m.g.width_m / 2) b.push(["warn", "OUTSIDE OUTLINE", "The estimated y is outside the gallery width: gyro drift."]);
      return b;
    };

    m.bounds = () => {  // the nominal gallery always fits, plus everything that was measured
      const w = m.g.width_m / 2, b = { x0: 0, x1: m.g.length_m, y0: -w, y1: w };
      const grow = (p) => { if (p) { b.x0 = Math.min(b.x0, p.x); b.x1 = Math.max(b.x1, p.x); b.y0 = Math.min(b.y0, p.y); b.y1 = Math.max(b.y1, p.y); } };
      m.path.forEach(grow); m.pins.forEach(grow); grow(m.hole); grow(m.last);
      return b;
    };
    return m;
  }

  /* World (x right, y up, metres) to pixels. 1 SVG unit = 1 px, so text and strokes keep their size. */
  function fit(b, W, H, pad) {
    const dx = Math.max(b.x1 - b.x0, 0.5), dy = Math.max(b.y1 - b.y0, 0.5);
    const aw = Math.max(W - pad.l - pad.r, 1), ah = Math.max(H - pad.t - pad.b, 1), k = Math.min(aw / dx, ah / dy);
    const ox = pad.l + (aw - dx * k) / 2 - b.x0 * k, oy = pad.t + (ah + dy * k) / 2 + b.y0 * k;
    return { k, X: (x) => ox + x * k, Y: (y) => oy - y * k };
  }

  function slabLabels(k, slabW, length) {  // every 5th slab, thinned to every 10th, 20th... when the labels would touch
    let step = 5;
    while (k * slabW * step < 36) step *= 2;
    const n = Math.floor(length / slabW + 1e-9), out = [];
    for (let i = step; i <= n; i += step) out.push({ n: i, x: (i - 0.5) * slabW });
    return out;
  }

  const SVG = "http://www.w3.org/2000/svg";
  function create(o) {
    const doc = o.doc, el = o.el, model = createModel(o.gallery);
    const h = (tag, attrs, parent, text) => {
      const n = doc.createElement(tag);
      Object.entries(attrs || {}).forEach(([k, v]) => n.setAttribute(k, v));
      if (text !== undefined) n.textContent = text;
      if (parent) parent.appendChild(n);
      return n;
    };
    const s = (tag, attrs, parent) => {
      const n = doc.createElementNS(SVG, tag);
      Object.entries(attrs || {}).forEach(([k, v]) => n.setAttribute(k, v));
      if (parent) parent.appendChild(n);
      return n;
    };
    el.replaceChildren();
    el.classList.remove("empty");
    el.classList.add("mapbox");
    const badges = h("ul", { class: "map-badges", "aria-label": "Map warnings" }, el);
    const view = h("div", { class: "map-view" }, el);
    const svg = s("svg", { class: "map-svg", role: "group", "aria-label": "Top view of the gallery, the robot path and the pins" }, view);
    h("p", { class: "map-empty" }, view, "No position yet. The path appears when the Pi sends telemetry.");
    const stats = h("div", { class: "map-stats" }, el);
    const sp = h("span", {}, stats), sd = h("span", {}, stats);
    h("span", { class: "label" }, sp, "Path "); const pathEl = h("span", { class: "num", id: "map-path" }, sp, "--"); sp.append(" m");
    h("span", { class: "label" }, sd, "To hole "); const directEl = h("span", { class: "num", id: "map-direct" }, sd, "--"); sd.append(" m");
    const legend = h("div", { class: "map-legend label", "aria-label": "Pin legend" }, el);
    Object.keys(PIN_TEXT).forEach((k) => { const i = h("span", { "data-pin": k }, legend); h("i", { "aria-hidden": "true" }, i, GLYPH[k]); i.append(PIN_TEXT[k]); });
    h("span", {}, legend, "Numbers: slab");

    let dirty = false, badgeKey = "";
    const mark = () => { if (!dirty) { dirty = true; (root.requestAnimationFrame || ((f) => setTimeout(f, 16)))(draw); } };
    const pick = (key) => doc.dispatchEvent(new CustomEvent("kashimo-select", { detail: { key, open: true } }));

    const gStatic = s("g", { "aria-hidden": "true" }, svg), pathEl2 = s("polyline", { class: "m-path", "aria-hidden": "true" }, svg);
    const robotEl = s("g", { "aria-hidden": "true" }, svg), gPins = s("g", {}, svg), pinEls = new Map();
    let selShown = null;

    function makePin(p) {  // created once and then only moved: a click must never land on an element that is being replaced
      const label = PIN_TEXT[p.pin] + (Number.isInteger(p.slab) ? ", slab " + String(p.slab).padStart(2, "0") : "");
      const n = s("g", { class: "m-pin", "data-kind": p.pin, "data-key": p.key, role: "button", tabindex: "0",
        "aria-label": label + ". Click or press V to open.", "aria-keyshortcuts": "V" }, gPins);
      s("title", {}, n).textContent = label;
      s("circle", { class: "hit", r: 11 }, n);
      s("circle", { class: "m-ring", r: 10 }, n);
      if (p.pin === "photo") s("circle", { class: "m-shape", r: 5 }, n);
      else if (p.pin === "obstacle") s("rect", { class: "m-shape", x: -5, y: -5, width: 10, height: 10 }, n);
      else s("polygon", { class: "m-shape", points: p.pin === "alert" ? "0,-6 6,5 -6,5" : "0,-6 6,0 0,6 -6,0" }, n);
      n.addEventListener("click", () => pick(p.key));
      n.addEventListener("keydown", (e) => { if (e.code === "KeyV" && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); pick(p.key); } });
      pinEls.set(p.key, n);
      return n;
    }

    function draw() {
      dirty = false;
      const g = model.g, w = g.width_m / 2, st = model.stats(), b = model.badges();
      view.setAttribute("data-has", model.last || model.pins.size ? "1" : "0");
      pathEl.textContent = st && st.path !== null ? st.path.toFixed(1) : "--";
      directEl.textContent = st ? (st.holeExact ? "" : "~") + st.direct.toFixed(1) : "--";
      directEl.title = st && !st.holeExact ? "The hole is assumed at the origin: the dashboard joined after the robot had moved." : "";
      const key = JSON.stringify(b);
      if (key !== badgeKey) {
        badgeKey = key;
        badges.replaceChildren();
        b.forEach(([lv, text, tip]) => h("li", { class: "map-badge", "data-level": lv, title: tip }, badges, text));
      }
      const r = svg.getBoundingClientRect(), W = Math.round(r.width), H = Math.round(r.height);
      svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
      gStatic.replaceChildren();
      if (W < 40 || H < 24) return;
      const f = fit(model.bounds(), W, H, PAD), X = f.X, Y = f.Y, top = Y(w), bottom = Y(-w);
      s("rect", { class: "m-gallery", x: X(0), y: top, width: g.length_m * f.k, height: g.width_m * f.k }, gStatic);
      const n = Math.floor(g.length_m / g.slab_width_m + 1e-9);
      if (f.k * g.slab_width_m >= 3) for (let i = 0; i <= n; i++) s("line", { class: "m-tick", x1: X(i * g.slab_width_m), x2: X(i * g.slab_width_m), y1: bottom, y2: bottom + 4 }, gStatic);
      slabLabels(f.k, g.slab_width_m, g.length_m).forEach((l) => { s("text", { class: "m-text", x: X(l.x), y: bottom + 16 }, gStatic).textContent = l.n; });
      if (model.hole) {
        s("line", { class: "m-hole", x1: X(model.hole.x), x2: X(model.hole.x), y1: top - 4, y2: bottom }, gStatic);
        s("text", { class: "m-text start", x: X(model.hole.x) + 4, y: top - 6 }, gStatic).textContent = "HOLE";
      }
      pathEl2.setAttribute("points", model.path.length > 1 ? model.path.map((p) => X(p.x).toFixed(1) + "," + Y(p.y).toFixed(1)).join(" ") : "");
      robotEl.replaceChildren();
      if (model.last) {
        const at = `translate(${X(model.last.x).toFixed(1)} ${Y(model.last.y).toFixed(1)})`;
        if (model.last.yaw === null) s("circle", { class: "m-robot", r: 5, transform: at }, robotEl);
        else s("polygon", { class: "m-robot", points: "9,0 -6,6 -6,-6", transform: at + ` rotate(${(-model.last.yaw * 180 / Math.PI).toFixed(1)})` }, robotEl);
      }
      model.pins.forEach((p) => {
        const n = pinEls.get(p.key) || makePin(p);
        n.setAttribute("transform", `translate(${X(p.x).toFixed(1)} ${Y(p.y).toFixed(1)})`);
        n.toggleAttribute("data-selected", model.selected === p.key);
      });
      if (selShown !== model.selected) {  // the selected pin goes on top, only when the selection changes
        selShown = model.selected;
        const sel = pinEls.get(selShown);
        if (sel) gPins.appendChild(sel);
      }
    }

    doc.addEventListener("kashimo-telemetry", (e) => { if (model.update(e.detail)) mark(); });
    doc.addEventListener("kashimo-event", (e) => { const m = e.detail; if (model.addPin({ key: "e" + m.id, kind: m.kind, x: m.x, y: m.y, slab: m.slab })) mark(); });
    doc.addEventListener("kashimo-photo", (e) => { const p = e.detail; if (model.addPin({ key: "p" + p.n, kind: "PHOTO", x: p.x, y: p.y, slab: p.slab })) mark(); });
    doc.addEventListener("kashimo-config", (e) => { if (e.detail && e.detail.gallery) { Object.assign(model.g, e.detail.gallery); mark(); } });
    doc.addEventListener("kashimo-select", (e) => { model.selected = e.detail.key; mark(); });
    if (root.ResizeObserver) new root.ResizeObserver(mark).observe(view);
    root.addEventListener("resize", mark);
    mark();
    return { model, draw };
  }

  const api = { DEF, PIN_KIND, pinKind, addPoint, createModel, fit, slabLabels, create };
  root.KashimoMap = api;
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root.document && root.document.getElementById("map")) api.instance = create({ doc: root.document, el: root.document.getElementById("map") });
})(typeof window !== "undefined" ? window : globalThis);
