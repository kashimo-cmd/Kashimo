/* K15 log: alerts and events list, latest first, with the picture viewer (design K15). Pure model first (tested in Node), DOM last.
   Keys: Enter and Space belong to the robot (K14), so a row or pin is opened by click, touch, or V. */
(function (root) {
  "use strict";
  const MAX_ITEMS = 500;
  const num = (v) => typeof v === "number" && Number.isFinite(v);
  const two = (n) => String(n).padStart(2, "0");
  const fmtTime = (ts) => { const d = new Date(ts * 1000); return two(d.getHours()) + ":" + two(d.getMinutes()) + ":" + two(d.getSeconds()); };
  const alertUrl = (p) => (typeof p === "string" && p ? "/alerts/" + encodeURIComponent(p.split("/").pop()) : null);

  function describe(it) {  // { text, mark }: mark picks the shape and colour of the row, same as the map pin
    const d = it.data || {}, tag = d.sample ? " (sample)" : "";
    switch (it.kind) {
      case "ALERT_DEFECT": return { mark: "alert", text: "Defect" + (num(d.score) ? ", score " + d.score.toFixed(1) : "") + (d.class ? ", " + d.class : "") + (d.delayed ? ", sent late" : "") + tag };
      case "ALERT_OBSTACLE": return { mark: "obstacle", text: "Obstacle ahead" + (num(d.front_cm) ? ", " + Math.round(d.front_cm) + " cm" : "") + tag };
      case "ALERT_ROD": return { mark: "alert", text: "Rod did not finish its move" + tag };
      case "ALERT_TILT": {
        const deg = num(d.pitch) && num(d.roll) ? Math.max(Math.abs(d.pitch), Math.abs(d.roll)) : num(d.deg) ? d.deg : null;
        return { mark: "alert", text: "Tilt over the limit" + (deg === null ? "" : ", " + Math.round(deg) + " deg") + tag };
      }
      case "BUMP": return { mark: "bump", text: "Bump" + (num(d.g) ? ", " + d.g.toFixed(1) + " g" : "") + tag };
      case "LINK_LOST": return { mark: "link-lost", text: "Link lost, motors off" + tag };
      case "LINK_BACK": return { mark: "link-back", text: "Link back, STOP stays latched until Space" + tag };
      case "PHOTO": return { mark: "photo", text: "Photo " + it.n + " saved" + tag };
      default: return { mark: "", text: String(it.kind) + tag };
    }
  }

  const hasPicture = (it) => !(it.data && it.data.sample) && ((it.kind === "ALERT_DEFECT" && !!(it.data && (it.data.frame || it.data.heat))) || (it.kind === "PHOTO" && !!it.file));

  function images(it, run) {  // [{ label, url }]; empty when the location is not known
    const d = it.data || {};
    if (!hasPicture(it)) return [];
    if (it.kind === "ALERT_DEFECT") return [{ label: "Frame", url: alertUrl(d.frame) }, { label: "Heatmap", url: alertUrl(d.heat) }].filter((i) => i.url);
    if (!run) return [];
    return [{ label: "Photo", url: "/runs/" + encodeURIComponent(run) + "/" + it.file.split("/").map(encodeURIComponent).join("/") }];
  }

  const fromEvent = (m) => ({ key: "e" + m.id, kind: m.kind, ts: m.ts, slab: m.slab, x: m.x, y: m.y, s: m.s, pan: m.pan, tilt: m.tilt, data: m.data || {} });
  const fromPhoto = (p) => ({ key: "p" + p.n, kind: "PHOTO", ts: p.ts, slab: p.slab, x: p.x, y: p.y, s: p.s, n: p.n, file: p.file, data: p.sample ? { sample: true } : {} });

  function createLog() {
    let items = [], order = 0;
    const byKey = new Map();
    const newest = (a, b) => b.ts - a.ts || b.order - a.order;
    return {
      add(it) {
        if (byKey.has(it.key)) return false;
        it.order = ++order;
        byKey.set(it.key, it);
        items.push(it);
        if (items.length > MAX_ITEMS) { items.sort(newest); byKey.delete(items.pop().key); }
        return true;
      },
      get: (key) => byKey.get(key),
      sorted: () => items.slice().sort(newest),
      size: () => items.length,
    };
  }

  function init(doc) {
    const body = doc.getElementById("log-body"), dlg = doc.getElementById("viewer");
    if (!body) return null;
    const model = createLog(), empty = body.firstElementChild ? body.firstElementChild.cloneNode(true) : null;
    let run = "", selected = null, raf = false;
    const el = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
    const pick = (key) => doc.dispatchEvent(new CustomEvent("kashimo-select", { detail: { key, open: true } }));

    function row(it) {
      const d = describe(it), tr = el("tr");
      tr.setAttribute("data-key", it.key);
      tr.tabIndex = 0;
      tr.setAttribute("aria-keyshortcuts", "V");
      tr.title = hasPicture(it) ? "Click or press V to open the picture" : "Click or press V to mark it on the map";
      if (it.key === selected) tr.setAttribute("data-selected", "");
      [fmtTime(it.ts), Number.isInteger(it.slab) ? two(it.slab) : "--"].forEach((c) => { const td = el("td", "", c); td.title = c; tr.appendChild(td); });
      const ev = el("td", "ev", d.text);
      ev.setAttribute("data-mark", d.mark);
      ev.title = d.text;
      if (hasPicture(it)) ev.appendChild(el("span", "pic", "picture"));
      tr.appendChild(ev);
      tr.addEventListener("click", () => pick(it.key));
      tr.addEventListener("keydown", (e) => { if (e.code === "KeyV" && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); pick(it.key); } });
      return tr;
    }

    function render() {
      raf = false;
      body.replaceChildren();
      if (!model.size()) { if (empty) body.appendChild(empty); return; }
      model.sorted().forEach((it) => body.appendChild(row(it)));
    }
    const later = () => { if (!raf) { raf = true; (root.requestAnimationFrame || ((f) => setTimeout(f, 16)))(render); } };

    function openViewer(it) {
      if (!dlg) return;
      const d = describe(it), imgs = images(it, run);
      doc.getElementById("viewer-title").textContent = d.text;
      const meta = [Number.isInteger(it.slab) ? "Slab " + two(it.slab) : null, fmtTime(it.ts), num(it.s) ? "path " + it.s.toFixed(1) + " m" : null,
        num(it.pan) && num(it.tilt) ? "pan " + Math.round(it.pan) + ", tilt " + Math.round(it.tilt) : null].filter(Boolean).join("  |  ");
      doc.getElementById("viewer-meta").textContent = meta;
      const vb = doc.getElementById("viewer-body");
      vb.replaceChildren();
      if (!imgs.length) vb.appendChild(el("p", "dim", "No picture: its location is not known yet."));
      imgs.forEach((i) => {
        const fig = el("figure"), cap = el("figcaption", "label", i.label), note = el("p", "dim", "Loading picture..."), img = el("img");
        img.alt = i.label + ": " + d.text;
        img.hidden = true;
        img.onload = () => { img.hidden = false; note.remove(); };
        img.onerror = () => { note.textContent = "Picture not available: the Pi or the file cannot be reached."; };
        img.src = i.url;
        fig.append(cap, note, img);
        vb.appendChild(fig);
      });
      if (typeof dlg.showModal === "function") { if (!dlg.open) dlg.showModal(); } else dlg.setAttribute("open", "");
      dlg.focus();  // not on the Close button: Enter is the robot's photo key
    }

    if (dlg) {
      const close = () => (typeof dlg.close === "function" ? dlg.close() : dlg.removeAttribute("open"));
      doc.getElementById("viewer-close").addEventListener("click", close);
      dlg.addEventListener("click", (e) => { if (e.target === dlg) close(); });
      dlg.addEventListener("keydown", (e) => { if (e.code === "KeyV" && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); close(); } });
    }

    doc.addEventListener("kashimo-event", (e) => { if (model.add(fromEvent(e.detail))) later(); });
    doc.addEventListener("kashimo-photo", (e) => { if (model.add(fromPhoto(e.detail))) later(); });
    doc.addEventListener("kashimo-config", (e) => { if (e.detail && e.detail.run) run = e.detail.run; });
    doc.addEventListener("kashimo-select", (e) => {
      selected = e.detail.key;
      const it = model.get(selected);
      body.querySelectorAll("tr[data-key]").forEach((tr) => {
        const on = tr.getAttribute("data-key") === selected;
        tr.toggleAttribute("data-selected", on);
        if (on && tr.scrollIntoView) tr.scrollIntoView({ block: "nearest" });
      });
      if (it && e.detail.open && hasPicture(it)) openViewer(it);
    });
    return { model, render };
  }

  const api = { MAX_ITEMS, fmtTime, describe, hasPicture, images, fromEvent, fromPhoto, createLog, init };
  root.KashimoLog = api;
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root.document) api.instance = init(root.document);
})(typeof window !== "undefined" ? window : globalThis);
