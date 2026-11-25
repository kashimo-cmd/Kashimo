/* K14 keys: rules of 4.6 and 5.4. Pure part first (tested in Node), DOM binding last. */
(function (root) {
  "use strict";
  const KEY_MAP = { KeyW: "FORWARD", KeyS: "BACKWARD", KeyA: "LEFT", KeyD: "RIGHT", ArrowLeft: "HEAD_LEFT", ArrowRight: "HEAD_RIGHT",
    ArrowUp: "HEAD_UP", ArrowDown: "HEAD_DOWN", KeyH: "HEAD_HOME", KeyL: "LED", Enter: "PHOTO", KeyP: "SCREENSHOT", KeyR: "ROD", Space: "STOP" };
  const HELD_KEYS = new Set(["KeyW", "KeyS", "KeyA", "KeyD", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"]);
  const KEY_TO_CMD = { KeyH: "HEAD_HOME", KeyL: "LED", KeyR: "ROD", Space: "STOP" };
  const BLOCKED_DEFAULTS = new Set(["Space", "Enter", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"]);
  const HEARTBEAT_MS = 100, ROD_HOLD_MS = 1000;
  // Sign of each held key. Left Q = -1 and head keys that grow the angle = +1 follow fake_pi (CHECK ON PI: head directions, K07).
  const AXIS = { KeyW: ["fwd", 1], KeyS: ["fwd", -1], KeyA: ["turn", -1], KeyD: ["turn", 1],
    ArrowRight: ["pan", 1], ArrowLeft: ["pan", -1], ArrowUp: ["tilt", 1], ArrowDown: ["tilt", -1] };
  const KINDS = { Enter: "photo", KeyP: "shot", KeyR: "rod", Space: "stop" };

  function control(held) {
    const a = { fwd: 0, turn: 0, pan: 0, tilt: 0 };
    for (const code of held) a[AXIS[code][0]] += AXIS[code][1];  // opposite keys add up to 0: Z+S and Q+D cancel
    return { drive: { fwd: a.fwd, turn: a.turn }, head: { pan: a.pan, tilt: a.tilt } };
  }

  function createState() {
    const held = new Set();
    return {
      down: (c) => { if (HELD_KEYS.has(c)) held.add(c); },
      up: (c) => held.delete(c),
      clear: () => held.clear(),
      has: (c) => held.has(c),
      control: () => control(held),
      driving: () => ["KeyW", "KeyS", "KeyA", "KeyD"].some((c) => held.has(c)),
    };
  }

  const classify = (code) => (!Object.hasOwn(KEY_MAP, code) ? null : HELD_KEYS.has(code) ? "held" : KINDS[code] || "cmd");
  const stopCmd = (latch) => (latch ? "START" : "STOP");

  function createRodHold(holdMs) {
    const ms = holdMs || ROD_HOLD_MS;
    let t0 = null, fired = false;
    return {
      start(now) { if (t0 === null) { t0 = now; fired = false; } },
      cancel() { t0 = null; fired = false; },
      active: () => t0 !== null,
      tick(now) {
        if (t0 === null) return { progress: 0, fired: false };
        const progress = Math.min(1, (now - t0) / ms);
        const fire = progress >= 1 && !fired;
        if (fire) fired = true;
        return { progress, fired: fire };
      },
    };
  }

  /* o: doc, win, enabled(), onCmd(name), onHeld(), getLatch(), onPhoto(), onShot(), onRefused(text), now?, raf? */
  function bind(o) {
    const doc = o.doc, win = o.win;
    const now = o.now || (() => win.performance.now());
    const raf = o.raf || ((f) => win.requestAnimationFrame(f));
    const state = createState(), rod = createRodHold(), down = new Set();
    const each = (code, f) => doc.querySelectorAll('[data-code="' + code + '"]').forEach(f);
    const lit = (code, on) => each(code, (b) => (on ? b.setAttribute("data-pressed", "") : b.removeAttribute("data-pressed")));
    const ring = (p, on) => each("KeyR", (b) => {
      b.style.setProperty("--hold", String(p));
      if (on) b.setAttribute("data-holding", p >= 1 ? "done" : ""); else b.removeAttribute("data-holding");
    });

    function tick() {
      const r = rod.tick(now());
      ring(r.progress, rod.active());
      if (r.fired) o.onCmd("ROD");
      if (rod.active() && r.progress < 1) raf(tick);
    }

    function press(code) {
      const kind = classify(code);
      if (!kind || down.has(code) || !o.enabled()) return;
      down.add(code);
      lit(code, true);
      if (kind === "held") { state.down(code); o.onHeld(); }
      else if (kind === "cmd") o.onCmd(KEY_TO_CMD[code]);
      else if (kind === "stop") o.onCmd(stopCmd(o.getLatch()));
      else if (kind === "photo") o.onPhoto();
      else if (kind === "shot") o.onShot();
      else if (state.driving()) o.onRefused("Rod refused: stop first.");
      else { rod.start(now()); tick(); }
    }

    function release(code) {
      if (!down.delete(code)) return;
      lit(code, false);
      if (state.has(code)) { state.up(code); o.onHeld(); }
      if (code === "KeyR") { rod.cancel(); ring(0, false); }
    }

    function releaseAll() {
      const codes = [...down];
      state.clear();
      down.clear();
      rod.cancel();
      codes.forEach((c) => lit(c, false));
      ring(0, false);
      if (codes.length) o.onHeld();
    }

    const mapped = (e) => Object.hasOwn(KEY_MAP, e.code);
    const typing = (e) => /^(INPUT|TEXTAREA|SELECT)$/.test((e.target && e.target.tagName) || "");
    doc.addEventListener("keydown", (e) => {
      if (!mapped(e) || typing(e) || e.ctrlKey || e.metaKey || e.altKey) return;  // Ctrl+R, Ctrl+P and friends stay the browser's
      if (BLOCKED_DEFAULTS.has(e.code)) e.preventDefault();  // no scroll, no click on a focused button
      if (!e.repeat) press(e.code);
    });
    doc.addEventListener("keyup", (e) => {
      if (!mapped(e) || typing(e)) return;
      if (BLOCKED_DEFAULTS.has(e.code)) e.preventDefault();
      release(e.code);
    });
    win.addEventListener("blur", releaseAll);
    doc.addEventListener("visibilitychange", () => { if (doc.visibilityState === "hidden") releaseAll(); });

    doc.querySelectorAll("button[data-code]").forEach((b) => {
      const code = b.getAttribute("data-code");
      b.addEventListener("pointerdown", (e) => {
        if (e.pointerType === "mouse" && e.button !== 0) return;
        e.preventDefault();
        try { b.setPointerCapture(e.pointerId); } catch (_) { /* not capturable: pointerup still arrives */ }
        press(code);
      });
      ["pointerup", "pointercancel", "lostpointercapture"].forEach((n) => b.addEventListener(n, () => release(code)));
      ["click", "contextmenu"].forEach((n) => b.addEventListener(n, (e) => e.preventDefault()));
    });

    return { state, press, release, releaseAll, tick };
  }

  const api = { KEY_MAP, HELD_KEYS, KEY_TO_CMD, BLOCKED_DEFAULTS, HEARTBEAT_MS, ROD_HOLD_MS, AXIS, control, createState, classify, stopCmd, createRodHold, bind };
  root.KashimoKeys = api;
  if (typeof module === "object" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
