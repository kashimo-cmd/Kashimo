import { createRequire } from "node:module";
const sent = [];
globalThis.setTimeout = globalThis.setInterval = () => 0;
const require = createRequire(import.meta.url);
const K = require("../pc/web/js/keys.js"), L = require("../pc/web/js/link.js");
class WS { constructor() { this.readyState = 1; } send(t) { sent.push(t); } }
const link = L.create({ url: "ws://x/ws", WebSocket: WS });
link.connect();
link.state.wsOpen = true;
link.send({ t: "SYNC", seq: 1, ts: Date.now() / 1000, since_id: 0 });
const keys = ["KeyW", "KeyS", "KeyA", "KeyD", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"];
for (let m = 0; m < 256; m += 1) link.control(K.control(keys.filter((_, i) => m & (1 << i))));
for (const c of ["HEAD_HOME", "LED", "ROD", "STOP", "START"]) link.cmd(c);
console.log(JSON.stringify(sent));
