import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const K = createRequire(import.meta.url)("../pc/web/js/keys.js");
const py = readFileSync(new URL("../common/constants.py", import.meta.url), "utf8");
const names = (re) => [...py.match(re)[1].matchAll(/"(\w+)"/g)].map((m) => m[1]);
const pairs = (re) => Object.fromEntries([...py.match(re)[1].matchAll(/"(\w+)": "(\w+)"/g)].map((m) => [m[1], m[2]]));

function rig() {
  const doc = Object.assign(new EventTarget(), { visibilityState: "visible", querySelectorAll: () => [] });
  const win = new EventTarget();
  const log = { cmds: [], held: 0, photo: 0, shot: 0, refused: [] };
  const st = { t: 0, latch: false, on: true };
  const kb = K.bind({ doc, win, now: () => st.t, raf: () => {}, enabled: () => st.on, onCmd: (c) => log.cmds.push(c), onHeld: () => log.held++,
    getLatch: () => st.latch, onPhoto: () => log.photo++, onShot: () => log.shot++, onRefused: (m) => log.refused.push(m) });
  const key = (type, code, extra = {}) => {
    const e = Object.assign(new Event(type, { cancelable: true }), { code, repeat: false, ctrlKey: false, metaKey: false, altKey: false }, extra);
    doc.dispatchEvent(e);
    return e;
  };
  return { doc, win, kb, log, st, key };
}

test("tables match common/constants.py", () => {
  assert.deepEqual(K.KEY_MAP, pairs(/KEY_MAP = \{([^}]*)\}/));
  assert.deepEqual([...K.HELD_KEYS].sort(), names(/HELD_KEYS = frozenset\(\s*\[([^\]]*)\]/).sort());
  assert.deepEqual(K.KEY_TO_CMD, pairs(/KEY_TO_CMD = \{([^}]*)\}/));
  assert.deepEqual([...K.BLOCKED_DEFAULTS].sort(), names(/BLOCKED_DEFAULTS = frozenset\(\[([^\]]*)\]/).sort());
  assert.equal(K.HEARTBEAT_MS, Number(py.match(/HEARTBEAT_S = ([\d.]+)/)[1]) * 1000);
  assert.equal(K.ROD_HOLD_MS, Number(py.match(/ROD_HOLD_S = ([\d.]+)/)[1]) * 1000);
  assert.equal(Object.keys(K.KEY_MAP).length, 14);
});

test("every key has one class, unknown keys none", () => {
  const got = Object.fromEntries(Object.keys(K.KEY_MAP).map((c) => [c, K.classify(c)]));
  assert.equal(Object.values(got).filter((k) => k === "held").length, 8);
  assert.deepEqual([got.Enter, got.KeyP, got.KeyR, got.Space, got.KeyH, got.KeyL], ["photo", "shot", "rod", "stop", "cmd", "cmd"]);
  assert.equal(K.classify("KeyX"), null);
  assert.equal(K.classify("toString"), null);
});

test("held keys become axes, opposite keys cancel", () => {
  const c = (...codes) => K.control(codes);
  assert.deepEqual(c(), { drive: { fwd: 0, turn: 0 }, head: { pan: 0, tilt: 0 } });
  assert.deepEqual(c("KeyW"), { drive: { fwd: 1, turn: 0 }, head: { pan: 0, tilt: 0 } });
  assert.deepEqual(c("KeyS", "KeyA"), { drive: { fwd: -1, turn: -1 }, head: { pan: 0, tilt: 0 } });
  assert.deepEqual(c("KeyW", "KeyD").drive, { fwd: 1, turn: 1 });
  assert.deepEqual(c("KeyW", "KeyS").drive, { fwd: 0, turn: 0 });
  assert.deepEqual(c("KeyA", "KeyD").drive, { fwd: 0, turn: 0 });
  assert.deepEqual(c("ArrowRight", "ArrowUp").head, { pan: 1, tilt: 1 });
  assert.deepEqual(c("ArrowLeft", "ArrowRight", "ArrowDown").head, { pan: 0, tilt: -1 });
});

test("STOP key toggles on the latch", () => {
  assert.equal(K.stopCmd(false), "STOP");
  assert.equal(K.stopCmd(true), "START");
});

test("rod hold fires once at 1 s, release resets", () => {
  const h = K.createRodHold();
  assert.deepEqual(h.tick(0), { progress: 0, fired: false });
  h.start(100);
  h.start(500);  // a second start does not move the origin
  assert.equal(h.tick(599).fired, false);
  assert.equal(h.tick(599).progress, 0.499);
  assert.deepEqual(h.tick(1100), { progress: 1, fired: true });
  assert.equal(h.tick(1600).fired, false);
  h.cancel();
  h.start(2000);
  assert.equal(h.tick(2999).fired, false);
  assert.equal(h.tick(3000).fired, true);
});

test("keyboard: hold, release, auto-repeat, blur", () => {
  const r = rig();
  r.key("keydown", "KeyW");
  r.key("keydown", "KeyW", { repeat: true });
  r.key("keydown", "KeyD");
  assert.deepEqual(r.kb.state.control().drive, { fwd: 1, turn: 1 });
  assert.equal(r.log.held, 2);
  r.key("keyup", "KeyW");
  assert.deepEqual(r.kb.state.control().drive, { fwd: 0, turn: 1 });
  r.win.dispatchEvent(new Event("blur"));
  assert.deepEqual(r.kb.state.control(), { drive: { fwd: 0, turn: 0 }, head: { pan: 0, tilt: 0 } });
  r.key("keydown", "KeyW");
  r.doc.visibilityState = "hidden";
  r.doc.dispatchEvent(new Event("visibilitychange"));
  assert.equal(r.kb.state.control().drive.fwd, 0);
});

test("keyboard: one-shot keys fire once per press, STOP uses the latch", () => {
  const r = rig();
  r.key("keydown", "KeyL"); r.key("keydown", "KeyL", { repeat: true }); r.key("keyup", "KeyL");
  r.key("keydown", "KeyH"); r.key("keyup", "KeyH");
  r.key("keydown", "Space"); r.key("keyup", "Space");
  r.st.latch = true;
  r.key("keydown", "Space"); r.key("keyup", "Space");
  r.key("keydown", "Enter"); r.key("keyup", "Enter");
  r.key("keydown", "KeyP"); r.key("keyup", "KeyP");
  assert.deepEqual(r.log.cmds, ["LED", "HEAD_HOME", "STOP", "START"]);
  assert.deepEqual([r.log.photo, r.log.shot], [1, 1]);
});

test("keyboard: Space, Enter and arrows never reach the page, Ctrl combos do", () => {
  const r = rig();
  for (const code of K.BLOCKED_DEFAULTS) {
    assert.equal(r.key("keydown", code).defaultPrevented, true, code);
    assert.equal(r.key("keyup", code).defaultPrevented, true, code);
  }
  assert.equal(r.key("keydown", "KeyW").defaultPrevented, false);
  const base = [r.log.photo, r.log.shot, r.log.cmds.length];
  assert.equal(r.key("keydown", "KeyR", { ctrlKey: true }).defaultPrevented, false);
  r.key("keydown", "KeyP", { ctrlKey: true });
  assert.deepEqual([r.log.photo, r.log.shot, r.log.cmds.length], base);  // Ctrl+R and Ctrl+P do nothing here
});

test("keyboard: works whatever the layout says (only event.code counts)", () => {
  const r = rig();
  r.key("keydown", "KeyW", { key: "\u0635" });
  assert.equal(r.kb.state.control().drive.fwd, 1);
});

test("keyboard: nothing is accepted while disabled", () => {
  const r = rig();
  r.st.on = false;
  r.key("keydown", "KeyW"); r.key("keydown", "KeyL");
  assert.equal(r.kb.state.control().drive.fwd, 0);
  assert.deepEqual(r.log.cmds, []);
});

test("rod key: refused while driving, otherwise ROD after the hold", () => {
  const r = rig();
  r.key("keydown", "KeyW");
  r.key("keydown", "KeyR");
  assert.equal(r.log.refused.length, 1);
  r.key("keyup", "KeyR"); r.key("keyup", "KeyW");
  r.st.t = 1000;
  r.key("keydown", "KeyR");
  r.st.t = 1999; r.kb.tick();
  assert.deepEqual(r.log.cmds, []);
  r.st.t = 2000; r.kb.tick(); r.kb.tick();
  assert.deepEqual(r.log.cmds, ["ROD"]);
  r.key("keyup", "KeyR");
  r.st.t = 3000;
  r.key("keydown", "KeyR");
  r.st.t = 3500; r.key("keyup", "KeyR");
  r.st.t = 4500; r.kb.tick();
  assert.deepEqual(r.log.cmds, ["ROD"]);  // released at 0.5 s: no second command
});
