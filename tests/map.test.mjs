import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const M = createRequire(import.meta.url)("../pc/web/js/map.js");
const tel = (x, y, s, extra) => ({ conn: "connected", t: Object.assign({ x, y, s, yaw: 0, imu: "OK" }, extra) });

test("pinKind: four pin kinds, link events have no pin", () => {
  assert.deepEqual(["ALERT_DEFECT", "ALERT_ROD", "ALERT_TILT", "ALERT_OBSTACLE", "BUMP", "PHOTO"].map(M.pinKind), ["alert", "alert", "alert", "obstacle", "bump", "photo"]);
  assert.equal(M.pinKind("LINK_LOST"), null);
  assert.equal(M.pinKind("LINK_BACK"), null);
});

test("addPoint: 2 cm steps, bounded length, last point kept", () => {
  const p = [];
  assert.equal(M.addPoint(p, 0, 0), true);
  assert.equal(M.addPoint(p, 0.01, 0), false);
  assert.equal(M.addPoint(p, 0.05, 0), true);
  const q = [];
  for (let i = 0; i < 20000; i++) M.addPoint(q, i * 0.05, 0);
  assert.ok(q.length <= 6000 && q[q.length - 1].x === 19999 * 0.05);
});

test("model: path length, straight distance to the hole, exact hole", () => {
  const m = M.createModel();
  m.update(tel(0.25, 0, 0));
  m.update(tel(3.25, 4, 7));
  const st = m.stats();
  assert.deepEqual([st.path, st.direct, st.holeExact], [7, 5, true]);
});

test("model: joining mid-run puts the hole at the origin and says so", () => {
  const m = M.createModel();
  m.update(tel(3, 4, 6));
  assert.deepEqual([m.stats().direct, m.stats().holeExact], [5, false]);
});

test("model: Pi restart (s drops) starts a new path, pins stay", () => {
  const m = M.createModel();
  m.update(tel(0.25, 0, 0)); m.update(tel(5, 0, 4.75));
  m.addPin({ key: "e1", kind: "BUMP", x: 3, y: 0, slab: 7 });
  m.update(tel(0.25, 0, 0));
  assert.equal(m.path.length, 1);
  assert.equal(m.pins.size, 1);
});

test("model: update reports changes only when something changed", () => {
  const m = M.createModel();
  assert.equal(m.update(tel(1, 0, 1)), true);
  assert.equal(m.update(tel(1, 0, 1)), false);
  assert.equal(m.update({ conn: "disconnected", t: m.last }), true);
  assert.equal(m.update({ conn: "connecting", t: null }), true);
  assert.equal(m.last.x, 1);  // no telemetry yet in this view: the last position stays
});

test("pins: bad coordinates, unknown kind and repeats are refused", () => {
  const m = M.createModel();
  assert.equal(m.addPin({ key: "e1", kind: "ALERT_DEFECT", x: 1, y: 0 }), true);
  assert.equal(m.addPin({ key: "e1", kind: "ALERT_DEFECT", x: 1, y: 0 }), false);
  assert.equal(m.addPin({ key: "e2", kind: "LINK_LOST", x: 1, y: 0 }), false);
  assert.equal(m.addPin({ key: "e3", kind: "BUMP", x: null, y: 0 }), false);
});

test("badges: sample, stale, imu, heading, outside", () => {
  const m = M.createModel({ width_m: 2 });
  assert.deepEqual(m.badges(), []);
  m.update(tel(1, 0, 1));
  assert.deepEqual(m.badges().map((b) => b[1]), ["HEADING UNCERTAIN"]);
  m.update(Object.assign(tel(1, 1.5, 1), { sample: true, conn: "disconnected" }));
  assert.deepEqual(m.badges().map((b) => b[1]), ["SAMPLE", "STALE", "HEADING UNCERTAIN", "OUTSIDE OUTLINE"]);
  m.update(tel(1, 0, 1, { imu: "LOST" }));
  assert.deepEqual(m.badges().map((b) => b[1]), ["IMU LOST"]);
  m.update(tel(1, 0, 1, { imu: "CALIBRATING" }));
  assert.deepEqual(m.badges().map((b) => b[1]), ["IMU CALIBRATING", "HEADING UNCERTAIN"]);
});

test("bounds always hold the nominal gallery and grow with the data", () => {
  const m = M.createModel({ width_m: 2, length_m: 30 });
  assert.deepEqual(m.bounds(), { x0: 0, x1: 30, y0: -1, y1: 1 });
  m.update(tel(31, 4, 31));
  assert.deepEqual(m.bounds(), { x0: 0, x1: 31, y0: -1, y1: 4 });
});

test("fit: y points up, the box is centred, nothing leaves the pad", () => {
  const pad = { l: 10, r: 10, t: 20, b: 20 }, f = M.fit({ x0: 0, x1: 30, y0: -1, y1: 1 }, 300, 100, pad);
  assert.ok(Math.abs(f.k - 9.333) < 0.01);
  assert.ok(f.Y(1) < f.Y(-1));
  assert.ok(Math.abs(f.X(0) - 10) < 1e-9 && Math.abs(f.X(30) - 290) < 1e-9);
  assert.ok(Math.abs((f.Y(1) + f.Y(-1)) / 2 - 50) < 1e-9);
});

test("slabLabels: every 5th slab, thinned when crowded", () => {
  assert.deepEqual(M.slabLabels(100, 0.5, 5).map((l) => l.n), [5, 10]);
  assert.equal(M.slabLabels(100, 0.5, 5)[0].x, 2.25);
  assert.deepEqual(M.slabLabels(9.3, 0.5, 30).map((l) => l.n), [10, 20, 30, 40, 50, 60]);
});
