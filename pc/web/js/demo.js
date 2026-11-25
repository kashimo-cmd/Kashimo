/* K13: view renderer + ?demo=<state> fixtures. K14 feeds real telemetry into KashimoView.render(). */
(function () {
  const BARS = [-60, -70, -80];
  const $ = (id) => document.getElementById(id);
  const num = (v, d) => (v === null || v === undefined ? "--" : Number(v).toFixed(d));
  const lvl = (el, l) => (l ? el.parentElement.setAttribute("data-level", l) : el.parentElement.removeAttribute("data-level"));

  const BASE = { conn: "connected", silent_ms: 0, t: {
    state: "MANUAL", latch: false, fc: 87, fl: 110, fr: 118, s: 12.4, x: 12.2, y: 0.2, yaw: 0.03, slab: 25, pan: 90, tilt: 90, led: true,
    rod: "UPRIGHT", pitch: 2, roll: 0, imu: "OK", rssi_dbm: -58, ai: "RUNNING", refusal: null },
    link: { rtt_ms: 35, loss_pct: 0 } };
  const patch = (t, link, extra) => Object.assign({}, BASE, extra, { t: Object.assign({}, BASE.t, t), link: Object.assign({}, BASE.link, link) });
  const FIXTURES = {
    "connected": patch({}, {}),
    "disconnected": patch({}, {}, { conn: "disconnected" }),
    "link-about-to-cut": patch({}, { rtt_ms: 320, loss_pct: 12 }, { silent_ms: 320 }),
    "link-lost": patch({ state: "LINK_LOST", latch: true }, {}, { silent_ms: 600 }),
    "latched": patch({ state: "STOPPED", latch: true }, {}),
    "obstacle-red": patch({ fc: 22, refusal: "front obstacle" }, {}),
    "tilt": patch({ pitch: 28, roll: -4 }, {}),
    "imu-calibrating": patch({ imu: "CALIBRATING" }, {}),
    "ai-dummy": patch({ ai: "DUMMY" }, {}),
    "led-off": patch({ led: false, ai: "PAUSED_LED" }, {}),
    "rod-moving": patch({ rod: "LIFTING" }, {}),
  };

  function banners(t, silent, conn, why) {
    const b = [];
    if (conn === "connecting") return [["info", "Connecting: waiting for the first data from the Pi."]];
    if (conn === "disconnected") return [["err", (why === "server" ? "Dashboard server" : "Pi") + " disconnected: values are stale, controls disabled."]];
    if (t.state === "LINK_LOST" || silent >= 500) b.push(["err", "LINK LOST: motors off. Press Space after the link returns."]);
    else if (silent >= 300) b.push(["warn", "Link about to cut: no message for 300 ms."]);
    if (t.latch && t.state !== "LINK_LOST") b.push(["warn", "STOP latched: drive refused. Press Space to release."]);
    if (t.fc !== null && t.fc < 30) b.push(["err", "Front obstacle under 30 cm: forward refused. S, Q and D still work."]);
    const tilt = Math.max(Math.abs(t.pitch), Math.abs(t.roll));
    if (tilt >= 35) b.push(["err", "TILT " + num(tilt, 0) + " deg: above 35. Stop and check the robot."]);
    else if (tilt >= 25) b.push(["warn", "TILT " + num(tilt, 0) + " deg: above 25."]);
    if (t.imu === "CALIBRATING") b.push(["warn", "IMU calibrating: drive refused until it is done."]);
    if (t.imu === "LOST") b.push(["err", "IMU LOST: the map stops turning."]);
    if (t.rod === "LIFTING" || t.rod === "FOLDING") b.push(["warn", "Rod moving: drive refused, head keys ignored."]);
    if (t.led === false) b.push(["info", "LED OFF: image dark, AI paused."]);
    if (t.ai === "DUMMY") b.push(["info", "AI: TEST DETECTOR, scores are not real."]);
    if (t.ai === "NO_MODEL") b.push(["info", "AI: no model loaded."]);
    if (t.refusal && !/front obstacle|STOP latched|IMU calibrating|rod moving/.test(t.refusal)) b.push(["warn", "Refused: " + t.refusal + "."]);
    return b;
  }

  function render(d) {
    const t = d.t, conn = d.conn, on = conn === "connected";
    document.body.setAttribute("data-conn", conn);
    document.body.toggleAttribute("data-nodata", t.state === "--");  // placeholder values are not stale values
    const chip = (id, text, level) => { $(id).textContent = text; lvl($(id), level); };
    chip("h-state", t.state, { MANUAL: "ok", STOPPED: "warn", LINK_LOST: "err" }[t.state]);
    chip("h-led", t.led === null ? "--" : t.led ? "ON" : "OFF", t.led === null ? "" : t.led ? "ok" : "warn");
    chip("h-rod", t.rod, t.rod === "--" ? "" : t.rod === "LIFTING" || t.rod === "FOLDING" ? "warn" : "ok");
    chip("h-ai", t.ai === "DUMMY" ? "TEST DETECTOR" : t.ai, t.ai === "--" ? "" : t.ai === "RUNNING" ? "ok" : "warn");
    chip("h-conn", on ? "Connected" : conn === "connecting" ? "Connecting" : "Disconnected", on ? "ok" : "err");
    const fc = t.fc, col = fc === null ? "none" : fc < 30 ? "red" : fc > 60 ? "green" : "orange";
    $("obstacle").setAttribute("data-color", col);
    $("front").firstChild.nodeValue = fc === null ? "--" : fc > 200 ? ">200" : num(fc, 0);
    const fl = $("front-label"); fl.textContent = { none: "NO ECHO", green: "CLEAR", orange: "CAUTION", red: "STOP" }[col];
    fl.setAttribute("data-level", { none: "", green: "ok", orange: "warn", red: "err" }[col]);
    $("fl").textContent = num(t.fl, 0); $("fr").textContent = num(t.fr, 0);
    const bars = t.rssi_dbm === null ? 0 : t.rssi_dbm >= BARS[0] ? 4 : t.rssi_dbm >= BARS[1] ? 3 : t.rssi_dbm >= BARS[2] ? 2 : 1;
    [...$("bars").children].forEach((el, i) => el.classList.toggle("on", i < bars));
    $("dbm").textContent = num(t.rssi_dbm, 0);
    $("rtt").textContent = num(d.link.rtt_ms, 0); $("loss").textContent = num(d.link.loss_pct, 0);
    $("rtt").classList.toggle("warnval", d.link.rtt_ms > 200); $("loss").classList.toggle("warnval", d.link.loss_pct > 5);
    ["pan", "tilt", "slab", "pitch", "roll"].forEach((k) => ($(k).textContent = num(t[k], 0)));
    $("s").textContent = num(t.s, 1);
    const list = banners(t, d.silent_ms, conn, d.why), key = JSON.stringify(list), ul = $("banners");
    if (ul.getAttribute("data-key") !== key) {  // rebuilt only on change: the alert region must not re-announce every 100 ms
      ul.setAttribute("data-key", key); ul.replaceChildren();
      list.forEach(([l, text]) => { const li = document.createElement("li"); li.className = "banner"; li.setAttribute("data-level", l); li.textContent = text; ul.appendChild(li); });
    }
    const stop = $("btn-stop"); stop.querySelector("span").textContent = t.latch ? "RELEASE" : "STOP";
    stop.toggleAttribute("data-latched", t.latch);
    document.querySelectorAll("button[data-code]").forEach((b) => (b.disabled = !on));
    if (document.body.hasAttribute("data-demo")) {
      $("video").setAttribute("data-state", "none");
      $("video-msg").textContent = on ? "Sample view: no video in demo mode." : "No video: the Pi is disconnected.";
    }
  }

  function sampleK15(view) {  // labelled sample path, pins and log lines for K15: never from the robot
    const say = (n, detail) => document.dispatchEvent(new CustomEvent(n, { detail }));
    const at = (h, m, sec) => new Date(2026, 10, 24, h, m, sec).getTime() / 1000;
    for (let i = 0; i <= 60; i++) {
      const f = i / 60;
      say("kashimo-telemetry", { conn: "connected", sample: true, t: { x: 0.25 + f * 11.95, y: 0.2 * Math.sin(f * 9), yaw: 0.03, s: f * 12.4, imu: "OK" } });
    }
    const ev = (id, kind, ts, x, y, slab, data) => say("kashimo-event", { t: "EVENT", id, kind, ts, s: x, x, y, slab, pan: 90, tilt: 90, data: Object.assign({ sample: true }, data) });
    ev(1, "LINK_BACK", at(14, 1, 20), 9.7, 0, 20, {});
    ev(2, "ALERT_OBSTACLE", at(14, 1, 48), 10.7, -0.1, 22, { front_cm: 24 });
    ev(3, "ALERT_DEFECT", at(14, 2, 11), 12.2, 0.2, 25, { score: 6.4 });
    ev(4, "BUMP", at(14, 0, 40), 5.8, 0.1, 12, {});
    say("kashimo-photo", { n: 1, file: null, slab: 15, ts: at(14, 0, 55), x: 7.1, y: -0.2, s: 7.3, sample: true });
    say("kashimo-telemetry", Object.assign({ sample: true }, view));
  }

  window.KashimoView = { render, fixtures: FIXTURES };
  const name = new URLSearchParams(location.search).get("demo");
  if (name !== null) {
    document.body.setAttribute("data-demo", name);
    render(FIXTURES[name] || FIXTURES.connected);
    document.querySelectorAll("button[data-code]").forEach((b) => { b.disabled = true; b.title = "Sample data: controls are off"; });
    sampleK15(FIXTURES[name] || FIXTURES.connected);
    if (!FIXTURES[name]) console.warn("unknown demo state:", name, "known:", Object.keys(FIXTURES).join(", "));
  }
})();
