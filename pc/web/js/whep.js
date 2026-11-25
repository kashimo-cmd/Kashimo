/* K14 video: WHEP (WebRTC from MediaMTX) with an MJPEG mode and fallback. One source at a time. */
(function (root) {
  "use strict";
  const GATHER_MS = 1500, STALL_MS = 3000, RETRY_MS = [1000, 2000, 3000], FALLBACK_AFTER = 3;

  const absolute = (base, loc) => new URL(loc, base).href;

  /* o: mode "webrtc"|"mjpeg", whep, mjpeg, video, img, onState({state, text, tag}), state = connecting|live|retry|failed */
  function create(o) {
    let stopped = true, pc = null, session = null, tries = 0, timer = 0, live = false, everLive = false, lastT = -1, lastAt = 0;
    const say = (state, text, tag) => o.onState({ state, text, tag: tag || "" });
    const show = (el, on) => { if (on) el.removeAttribute("hidden"); else el.setAttribute("hidden", ""); };

    function teardown() {
      const c = pc;
      pc = null;
      live = false;
      if (session) { fetch(session, { method: "DELETE" }).catch(() => {}); session = null; }
      if (c) { c.onconnectionstatechange = null; c.close(); }
      o.video.srcObject = null;
    }

    function mjpeg(fallback) {
      if (stopped) return;
      const tag = fallback ? "MJPEG fallback" : "MJPEG";
      show(o.video, false);
      show(o.img, true);
      say("connecting", "Connecting video...", tag);
      o.img.onload = () => { tries = 0; say("live", "", tag); };
      o.img.onerror = () => {
        if (stopped) return;
        say("retry", "Video lost, retrying...", tag);
        timer = setTimeout(() => mjpeg(fallback), RETRY_MS[Math.min(tries++, 2)]);
      };
      o.img.src = o.mjpeg + (o.mjpeg.includes("?") ? "&" : "?") + "t=" + Date.now();
    }

    function lost(text) {
      clearTimeout(timer);
      teardown();
      if (stopped) return;
      tries++;
      if (!everLive && tries >= FALLBACK_AFTER && o.mjpeg) { mjpeg(true); return; }  // never worked: try MJPEG; once it has worked keep retrying WebRTC
      say("retry", text + ", retrying...", "WebRTC");
      timer = setTimeout(attempt, RETRY_MS[Math.min(tries - 1, 2)]);
    }

    async function whep() {
      show(o.img, false);
      show(o.video, true);
      say("connecting", "Connecting video...", "WebRTC");
      const conn = new RTCPeerConnection({ iceServers: [] });  // LAN only, works offline
      pc = conn;
      conn.addTransceiver("video", { direction: "recvonly" });
      conn.ontrack = (e) => {
        o.video.srcObject = e.streams[0];
        try { e.receiver.jitterBufferTarget = 0; } catch (_) { /* not supported: default buffer */ }
      };
      conn.onconnectionstatechange = () => { if (pc === conn && (conn.connectionState === "failed" || conn.connectionState === "closed")) lost("Video lost"); };
      await conn.setLocalDescription(await conn.createOffer());
      await new Promise((done) => {
        if (conn.iceGatheringState === "complete") { done(); return; }
        const t = setTimeout(done, GATHER_MS);
        conn.onicegatheringstatechange = () => { if (conn.iceGatheringState === "complete") { clearTimeout(t); done(); } };
      });
      const r = await fetch(o.whep, { method: "POST", headers: { "Content-Type": "application/sdp" }, body: conn.localDescription.sdp });
      if (r.status !== 201 && r.status !== 200) throw new Error("server answered " + r.status);
      const loc = r.headers.get("Location");
      session = loc ? absolute(o.whep, loc) : null;
      const sdp = await r.text();
      if (pc !== conn) { conn.close(); return; }  // stopped meanwhile
      await conn.setRemoteDescription({ type: "answer", sdp });
    }

    async function attempt() {
      if (stopped) return;
      try { await whep(); } catch (e) { lost("No video: " + ((e && e.message) || "error")); }
    }

    o.video.addEventListener("playing", () => { live = everLive = true; tries = 0; lastT = -1; lastAt = Date.now(); say("live", "", "WebRTC"); });
    setInterval(() => {  // a frozen picture must not look live
      if (!live) return;
      const q = o.video.getVideoPlaybackQuality && o.video.getVideoPlaybackQuality();
      const t = q ? q.totalVideoFrames : o.video.currentTime;  // currentTime keeps running on a MediaStream without frames
      if (t !== lastT) { lastT = t; lastAt = Date.now(); } else if (Date.now() - lastAt > STALL_MS) lost("Video stalled");
    }, 1000);

    return {
      start() {
        stopped = false;
        if (o.mode === "mjpeg" && o.mjpeg) mjpeg(false);
        else if (o.whep) attempt();
        else say("failed", "No video source in the configuration.");
      },
      stop() { stopped = true; clearTimeout(timer); teardown(); o.img.removeAttribute("src"); },
    };
  }

  const api = { absolute, create };
  root.KashimoVideo = api;
  if (typeof module === "object" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
