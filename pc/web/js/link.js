/* K14 link: browser WebSocket to the PC server (relay of 4.5), 100 ms heartbeat, reconnect, view model for KashimoView. */
(function (root) {
  "use strict";
  const HEARTBEAT_MS = 100, STALE_MS = 2000, RETRY_MS = [500, 1000, 2000];

  function buildView(s, now) {
    const silent = s.tel ? Math.max(0, Math.round(now - s.telAt)) : 0;
    let conn = "connected", why = null;
    if (!s.wsOpen) { conn = s.everOpen ? "disconnected" : "connecting"; why = "server"; }
    else if (s.pi === null || (s.pi && !s.tel)) conn = "connecting";
    else if (!s.pi || silent >= STALE_MS) { conn = "disconnected"; why = "pi"; }
    const l = (s.tel && s.tel.link) || {};
    const val = (v) => (v === undefined ? null : v);
    return { conn, why, silent_ms: silent, t: s.tel, link: { rtt_ms: val(l.rtt_ms), loss_pct: val(l.loss_pct) } };
  }

  /* o: url, onEvent(m), WebSocket?, now?, wall? */
  function create(o) {
    const WS = o.WebSocket || root.WebSocket;
    const clock = o.now || (() => root.performance.now());
    const wall = o.wall || (() => Date.now() / 1000);
    const s = { wsOpen: false, everOpen: false, pi: null, tel: null, telAt: 0, seq: 0, lastEvent: 0 };
    const seen = new Set();
    let ws = null, tries = 0;

    const send = (m) => {
      if (!ws || ws.readyState !== 1) return false;
      ws.send(JSON.stringify(m));
      return true;
    };
    const msg = (t, extra) => Object.assign({ t, seq: ++s.seq, ts: wall() }, extra);

    function handle(text) {
      let m;
      try { m = JSON.parse(text); } catch (_) { return; }
      if (!m || typeof m !== "object") return;
      if (m.t === "LINK") s.pi = !!m.pi;
      else if (m.t === "TELEMETRY") { s.tel = m; s.telAt = clock(); }
      else if (m.t === "EVENT" && !seen.has(m.id)) {  // a replay after reconnect repeats old events
        seen.add(m.id);
        s.lastEvent = Math.max(s.lastEvent, m.id);
        if (o.onEvent) o.onEvent(m);
      }
    }

    function connect() {
      try { ws = new WS(o.url); } catch (_) { ws = null; setTimeout(connect, RETRY_MS[2]); return; }
      ws.onopen = () => { s.wsOpen = s.everOpen = true; tries = 0; send(msg("SYNC", { since_id: s.lastEvent })); };
      ws.onmessage = (e) => handle(e.data);
      ws.onerror = () => {};  // onclose follows
      ws.onclose = () => { s.wsOpen = false; s.pi = null; ws = null; setTimeout(connect, RETRY_MS[Math.min(tries++, 2)]); };
    }

    const link = {
      state: s, connect, handle, send,
      control: (c) => send(msg("CONTROL", { drive: c.drive, head: c.head })),
      cmd: (name) => send(msg("CMD", { cmd: name })),
      view: () => buildView(s, clock()),
      start(getControl) {
        connect();
        setInterval(() => { if (s.wsOpen) link.control(getControl()); }, HEARTBEAT_MS);
      },
    };
    return link;
  }

  const api = { HEARTBEAT_MS, STALE_MS, buildView, create };
  root.KashimoLink = api;
  if (typeof module === "object" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
