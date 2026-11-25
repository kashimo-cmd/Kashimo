import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const timers = [];
globalThis.setTimeout = (f, ms) => { timers.push({ f, ms, kind: "timeout" }); return timers.length; };
globalThis.setInterval = (f, ms) => { timers.push({ f, ms, kind: "interval" }); return timers.length; };
const L = createRequire(import.meta.url)("../pc/web/js/link.js");

class FakeWS {
  constructor(url) { this.url = url; this.readyState = 0; this.sent = []; FakeWS.last = this; }
  send(t) { this.sent.push(JSON.parse(t)); }
  open() { this.readyState = 1; this.onopen(); }
  recv(m) { this.onmessage({ data: typeof m === "string" ? m : JSON.stringify(m) }); }
  drop() { this.readyState = 3; this.onclose(); }
}
const TEL = { t: "TELEMETRY", state: "MANUAL", latch: false, link: { rtt_ms: 35, loss_pct: 0, pi: true } };
const mk = () => {
  const clock = { t: 1000 }, events = [];
  const link = L.create({ url: "ws://x/ws", WebSocket: FakeWS, now: () => clock.t, wall: () => 1.5, onEvent: (m) => events.push(m) });
  return { link, clock, events };
};

test("buildView: every connection state", () => {
  const base = { wsOpen: true, everOpen: true, pi: true, tel: TEL, telAt: 1000 };
  const v = (s, now = 1000) => L.buildView(Object.assign({}, base, s), now);
  assert.equal(v({}).conn, "connected");
  assert.deepEqual([v({}, 1350).conn, v({}, 1350).silent_ms], ["connected", 350]);
  assert.deepEqual([v({}, 3000).conn, v({}, 3000).why], ["disconnected", "pi"]);
  assert.deepEqual([v({ pi: false }).conn, v({ pi: false }).why], ["disconnected", "pi"]);
  assert.equal(v({ pi: null }).conn, "connecting");
  assert.equal(v({ tel: null }).conn, "connecting");
  assert.deepEqual([v({ wsOpen: false }).conn, v({ wsOpen: false }).why], ["disconnected", "server"]);
  assert.equal(v({ wsOpen: false, everOpen: false }).conn, "connecting");
  assert.deepEqual(v({}).link, { rtt_ms: 35, loss_pct: 0 });
  assert.deepEqual(v({ tel: { t: "TELEMETRY" } }).link, { rtt_ms: null, loss_pct: null });
});

test("open sends SYNC, LINK and TELEMETRY make it connected", () => {
  const { link, clock } = mk();
  link.connect();
  assert.equal(link.view().conn, "connecting");
  FakeWS.last.open();
  assert.deepEqual(FakeWS.last.sent, [{ t: "SYNC", seq: 1, ts: 1.5, since_id: 0 }]);
  FakeWS.last.recv({ t: "LINK", pi: true });
  FakeWS.last.recv(TEL);
  assert.equal(link.view().conn, "connected");
  clock.t += 2500;
  assert.equal(link.view().conn, "disconnected");
  FakeWS.last.recv({ t: "LINK", pi: false });
  FakeWS.last.recv("not json");
  FakeWS.last.recv("[1]");
  assert.equal(link.view().why, "pi");
});

test("CONTROL and CMD wire shape, sequence numbers rise", () => {
  const { link } = mk();
  assert.equal(link.control({ drive: { fwd: 0, turn: 0 }, head: { pan: 0, tilt: 0 } }), false);  // closed socket: nothing sent
  link.connect(); FakeWS.last.open();
  link.control({ drive: { fwd: 1, turn: -1 }, head: { pan: 0, tilt: 1 } });
  link.cmd("LED");
  assert.deepEqual(FakeWS.last.sent.slice(1), [
    { t: "CONTROL", seq: 3, ts: 1.5, drive: { fwd: 1, turn: -1 }, head: { pan: 0, tilt: 1 } },
    { t: "CMD", seq: 4, ts: 1.5, cmd: "LED" }]);
});

test("heartbeat runs every 100 ms with the keys of the moment", () => {
  const { link } = mk();
  let c = { drive: { fwd: 1, turn: 0 }, head: { pan: 0, tilt: 0 } };
  link.start(() => c);
  const beat = timers.filter((t) => t.kind === "interval").pop();
  assert.equal(beat.ms, 100);
  beat.f();  // socket not open yet: silent
  FakeWS.last.open();
  beat.f();
  c = { drive: { fwd: 0, turn: 0 }, head: { pan: 0, tilt: 0 } };
  beat.f();
  const sent = FakeWS.last.sent.filter((m) => m.t === "CONTROL");
  assert.deepEqual(sent.map((m) => m.drive.fwd), [1, 0]);
});

test("events are delivered once, reconnect asks for the rest and backs off", () => {
  const { link, events } = mk();
  link.connect(); FakeWS.last.open();
  for (const id of [1, 2, 2, 3, 1]) FakeWS.last.recv({ t: "EVENT", id, kind: "BUMP" });
  assert.deepEqual(events.map((e) => e.id), [1, 2, 3]);
  const before = timers.length;
  FakeWS.last.drop();
  assert.equal(link.view().conn, "disconnected");
  assert.equal(timers[before].ms, 500);
  timers[before].f();
  FakeWS.last.open();
  assert.equal(FakeWS.last.sent[0].since_id, 3);
  FakeWS.last.drop(); timers[timers.length - 1].f(); FakeWS.last.drop();
  FakeWS.last.open && FakeWS.last.drop();
  assert.ok(timers[timers.length - 1].ms <= 2000);
});
