import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const L = createRequire(import.meta.url)("../pc/web/js/log.js");
const ev = (id, kind, ts, data) => L.fromEvent({ id, kind, ts, slab: 7, x: 1, y: 0, s: 1, pan: 90, tilt: 90, data });

test("describe: one plain line per event kind", () => {
  const d = (kind, data) => L.describe(ev(1, kind, 1, data));
  assert.deepEqual(d("ALERT_DEFECT", { score: 6.44, class: "cut" }), { mark: "alert", text: "Defect, score 6.4, cut" });
  assert.equal(d("ALERT_DEFECT", {}).text, "Defect");
  assert.equal(d("ALERT_OBSTACLE", { front_cm: 24.4 }).text, "Obstacle ahead, 24 cm");
  assert.equal(d("ALERT_TILT", { pitch: 28, roll: -31 }).text, "Tilt over the limit, 31 deg");
  assert.equal(d("ALERT_ROD", {}).text, "Rod did not finish its move");
  assert.equal(d("BUMP", {}).mark, "bump");
  assert.equal(d("LINK_LOST", {}).mark, "link-lost");
  assert.equal(d("LINK_BACK", {}).mark, "link-back");
  assert.equal(d("ALERT_DEFECT", { sample: true }).text, "Defect (sample)");
  assert.equal(L.describe(L.fromPhoto({ n: 3, ts: 1, slab: 2 })).text, "Photo 3 saved");
});

test("log: latest first, no duplicates, bounded", () => {
  const log = L.createLog();
  assert.equal(log.add(ev(1, "BUMP", 10, {})), true);
  assert.equal(log.add(ev(1, "BUMP", 10, {})), false);
  log.add(ev(2, "BUMP", 30, {}));
  log.add(ev(3, "BUMP", 20, {}));
  log.add(L.fromPhoto({ n: 1, ts: 30, slab: 1 }));  // same second as event 2, arrived later
  assert.deepEqual(log.sorted().map((i) => i.key), ["p1", "e2", "e3", "e1"]);
  const big = L.createLog();
  for (let i = 1; i <= L.MAX_ITEMS + 20; i++) big.add(ev(i, "BUMP", i, {}));
  assert.equal(big.size(), L.MAX_ITEMS);
  assert.equal(big.get("e1"), undefined);
  assert.ok(big.get("e" + (L.MAX_ITEMS + 20)));
});

test("images: defect frame and heatmap from /alerts, photo from the run folder, nothing for samples", () => {
  const d = ev(4, "ALERT_DEFECT", 1, { frame: "/alerts/000004.jpg", heat: "/alerts/000004_heat.jpg" });
  assert.deepEqual(L.images(d, "").map((i) => [i.label, i.url]), [["Frame", "/alerts/000004.jpg"], ["Heatmap", "/alerts/000004_heat.jpg"]]);
  assert.equal(L.images(ev(5, "ALERT_DEFECT", 1, { frame: "../../etc/x.jpg" }), "")[0].url, "/alerts/x.jpg");  // only the file name is kept
  const p = L.fromPhoto({ n: 1, ts: 1, slab: 3, file: "photos/photo_0001_nopos.jpg" });
  assert.equal(L.images(p, "2026-11-25_10-00")[0].url, "/runs/2026-11-25_10-00/photos/photo_0001_nopos.jpg");
  assert.deepEqual(L.images(p, ""), []);
  assert.equal(L.hasPicture(p), true);
  assert.equal(L.hasPicture(ev(6, "BUMP", 1, {})), false);
  assert.equal(L.hasPicture(ev(7, "ALERT_DEFECT", 1, { sample: true, frame: "/alerts/1.jpg" })), false);
});

test("fmtTime is HH:MM:SS", () => {
  assert.match(L.fmtTime(1764000000.4), /^\d\d:\d\d:\d\d$/);
});
