/* K14 app: live data into KashimoView, keys and buttons into commands. With ?demo=<state> nothing live runs. */
(function () {
  "use strict";
  const params = new URLSearchParams(location.search);
  if (params.has("demo")) return;
  const $ = (id) => document.getElementById(id);
  const K = window.KashimoKeys, L = window.KashimoLink, V = window.KashimoVideo, view = window.KashimoView;
  const EMPTY = { state: "--", latch: false, fc: null, fl: null, fr: null, s: null, slab: null, pan: null, tilt: null, led: null,
    rod: "--", pitch: null, roll: null, imu: "--", rssi_dbm: null, ai: "--", refusal: null };
  const LABEL = { photo: "Photo", screenshot: "Screenshot" };
  let cur = null, wasOn = false, optimistic = null, msgTimer = 0, last = null;  // last = newest saved file, relative to the run folder
  const busy = {};

  const link = L.create({
    url: (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws",
    onEvent: (m) => document.dispatchEvent(new CustomEvent("kashimo-event", { detail: m })),  // K15 log and map listen here
  });

  function flash(text, level) {
    const el = $("action-msg");
    el.textContent = text;
    el.title = text;  // clamped to 3 lines in the panel, the tooltip has it all
    el.setAttribute("data-level", level || "");
    clearTimeout(msgTimer);
    if (level !== "err") msgTimer = setTimeout(() => { el.textContent = ""; el.removeAttribute("data-level"); }, 8000);
  }

  const pageRect = () => {  // this page in screen pixels, so the server crops the screenshot to it (browser zoom must be 100 %)
    const dpr = window.devicePixelRatio || 1, side = (window.outerWidth - window.innerWidth) / 2;
    return { x: Math.round((window.screenX + side) * dpr), y: Math.round((window.screenY + window.outerHeight - window.innerHeight - side) * dpr),
      w: Math.round(window.innerWidth * dpr), h: Math.round(window.innerHeight * dpr) };
  };
  const JSON_POST = { "Content-Type": "application/json" };

  async function capture(kind) {  // "saved" is shown only after the server confirms the file
    if (busy[kind]) return;
    busy[kind] = true;
    flash("Saving " + LABEL[kind].toLowerCase() + "...", "");
    const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), 10000);
    try {
      const opts = { method: "POST", signal: ctl.signal };
      if (kind === "screenshot") Object.assign(opts, { headers: JSON_POST, body: JSON.stringify({ region: pageRect() }) });
      const r = await fetch("/api/" + kind, opts);
      const b = await r.json().catch(() => ({}));
      if (r.ok && b.ok) {
        last = b.file;
        $("btn-show").disabled = false;
        if (kind === "photo") document.dispatchEvent(new CustomEvent("kashimo-photo", { detail: { n: b.n, file: b.file, slab: b.slab, ts: Date.now() / 1000, x: cur && cur.t ? cur.t.x : null, y: cur && cur.t ? cur.t.y : null, s: cur && cur.t ? cur.t.s : null } }));  // K15 pin: position from the last telemetry shown
        const slab = Number.isInteger(b.slab) ? " (slab " + String(b.slab).padStart(2, "0") + ")" : "";
        flash("Saved: " + LABEL[kind].toLowerCase() + " " + b.n + ", " + String(b.file).split("/").pop() + slab, "ok");
      } else flash("Failed: " + LABEL[kind].toLowerCase() + " not saved. " + (b.error || "server answered " + r.status), "err");
    } catch (e) {
      flash("Failed: " + LABEL[kind].toLowerCase() + " not saved. " + (e.name === "AbortError" ? "The server took over 10 s." : "Dashboard server unreachable."), "err");
    } finally {
      clearTimeout(timer);
      busy[kind] = false;
    }
  }

  async function showFile() {  // opens the file manager on the newest photo or screenshot
    if (!last) return;
    try {
      const r = await fetch("/api/reveal", { method: "POST", headers: JSON_POST, body: JSON.stringify({ file: last }) });
      const b = await r.json().catch(() => ({}));
      if (r.ok && b.ok) flash("Opened the folder of " + last.split("/").pop(), "ok");
      else flash("Failed: could not open the folder. " + (b.error || "server answered " + r.status), "err");
    } catch (e) {
      flash("Failed: could not open the folder. Dashboard server unreachable.", "err");
    }
  }
  $("btn-show").addEventListener("click", showFile);

  const latch = () => (optimistic && performance.now() < optimistic.until ? optimistic.value : !!(cur && cur.t && cur.t.latch));
  const kb = K.bind({
    doc: document, win: window,
    enabled: () => !!cur && cur.conn === "connected",
    onCmd: (c) => {
      if (c === "STOP" || c === "START") optimistic = { value: c === "STOP", until: performance.now() + 400 };  // a fast second press must undo, not repeat
      link.cmd(c);
    },
    onHeld: () => link.control(kb.state.control()),  // key change goes out at once, the 100 ms heartbeat repeats it
    getLatch: latch,
    onPhoto: () => capture("photo"),
    onShot: () => capture("screenshot"),
    onRefused: (t) => flash(t, "warn"),
  });

  function tick() {
    cur = link.view();
    const on = cur.conn === "connected";
    if (wasOn && !on) kb.releaseAll();
    wasOn = on;
    view.render(Object.assign({}, cur, { t: cur.t || EMPTY }));
    document.dispatchEvent(new CustomEvent("kashimo-telemetry", { detail: cur }));  // K15 map
  }

  async function startVideo() {
    for (;;) {
      try {
        const st = await (await fetch("/api/status")).json();
        const v = st.video || {};
        document.dispatchEvent(new CustomEvent("kashimo-config", { detail: st }));  // K15: gallery size, run folder
        const mode = params.get("video") || v.mode;
        const vid = V.create({
          mode, whep: v.whep_url, mjpeg: v.mjpeg_url, video: $("cam"), img: $("cam-img"),
          onState: (s) => {
            $("video").setAttribute("data-state", s.state === "live" ? "live" : "none");
            $("video-msg").textContent = s.text;
            const tag = $("video-tag");
            tag.textContent = s.tag;
            if (s.tag) tag.removeAttribute("hidden"); else tag.setAttribute("hidden", "");
          },
        });
        window.addEventListener("pagehide", () => vid.stop());
        vid.start();
        return;
      } catch (_) {
        $("video-msg").textContent = "No video yet: waiting for the dashboard server.";
        await new Promise((ok) => setTimeout(ok, 1000));
      }
    }
  }

  link.start(() => kb.state.control());
  setInterval(tick, 100);
  tick();
  startVideo();
  window.KashimoApp = { link, kb, capture, showFile };
})();
