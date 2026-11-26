"""aiohttp server: /ws (design 4.5), static /alerts/, internal endpoints for the AI worker (127.0.0.1 only)."""
from __future__ import annotations

import asyncio
import logging
import signal
import time

from aiohttp import WSMsgType, web

from common import constants as C
from common import protocol as P

log = logging.getLogger("kashimo.ws")
LOCAL = ("127.0.0.1", "::1")
SLOW_S = 2.0  # rssi, cpu and recording checks may block, so they run in a thread
SEND_TIMEOUT_S = 0.25  # a client that cannot take a message in this time is dropped, the 50 ms loop never waits longer

CTRL, HUB = web.AppKey("ctrl"), web.AppKey("hub")


class Hub:
    """The connected dashboards and the one place that writes to them."""

    def __init__(self, ctrl):
        self.ctrl, self.clients, self._lock = ctrl, set(), asyncio.Lock()

    async def _send(self, ws, text: str) -> None:
        try:
            await asyncio.wait_for(ws.send_str(text), SEND_TIMEOUT_S)
        except Exception:
            self.clients.discard(ws)
            ws.force_close()  # it must reconnect and SYNC, not keep sending heartbeats into a dead pipe

    async def flush(self) -> None:
        """Send everything the controller queued to every client (dropped when nobody listens)."""
        async with self._lock:
            while self.ctrl.outbox:
                msg = self.ctrl.outbox.popleft()
                if not self.clients:
                    continue
                try:
                    text = P.encode(msg)
                except P.ProtocolError:
                    log.exception("message not sent")
                    continue
                for ws in list(self.clients):
                    await self._send(ws, text)

    async def replay(self, ws, since_id: int) -> None:
        """SYNC: stored events with an id above since_id, to this client only."""
        async with self._lock:
            for ev in self.ctrl.events.since(since_id):
                await self._send(ws, P.encode(ev))


is_local = lambda remote: remote in LOCAL  # noqa: E731


def _guard(request) -> None:
    if not is_local(request.remote):
        raise web.HTTPForbidden(text="internal endpoint: 127.0.0.1 only")


async def ws_handler(request):
    ctrl, hub = request.app[CTRL], request.app[HUB]
    ws = web.WebSocketResponse(max_msg_size=64 * 1024)
    await ws.prepare(request)
    hub.clients.add(ws)
    try:
        async for m in ws:
            if m.type != WSMsgType.TEXT:
                continue
            try:
                msg = P.decode(m.data)
            except P.ProtocolError as exc:
                log.warning("ignored bad message: %s", exc)  # a bad CONTROL does not feed the watchdog
                continue
            if isinstance(msg, P.Control):
                ctrl.on_control(msg)
            elif isinstance(msg, P.Cmd):
                ctrl.on_cmd(msg.cmd)
            elif isinstance(msg, P.Sync):
                await hub.flush()
                await hub.replay(ws, msg.since_id)
            await hub.flush()
    finally:
        hub.clients.discard(ws)
    return ws


async def internal_state(request):
    _guard(request)
    return web.json_response(request.app[CTRL].internal_state())


async def _body(request) -> dict:
    try:
        body = await request.json()
    except ValueError:
        raise web.HTTPBadRequest(text="body is not JSON") from None
    if not isinstance(body, dict):
        raise web.HTTPBadRequest(text="body must be an object")
    return body


async def internal_event(request):
    """AI worker posts {"data": {score, frame, heat, detector}} (kind ALERT_DEFECT, the only kind it may post)."""
    _guard(request)
    body = await _body(request)
    if body.get("kind", "ALERT_DEFECT") != "ALERT_DEFECT":
        raise web.HTTPBadRequest(text="only ALERT_DEFECT may be posted")
    try:
        ev = request.app[CTRL].post_defect(body.get("data"))
    except P.ProtocolError as exc:
        raise web.HTTPBadRequest(text=str(exc)) from None
    await request.app[HUB].flush()
    return web.json_response({"id": ev.id})


async def internal_ai_status(request):
    _guard(request)
    body = await _body(request)
    try:
        request.app[CTRL].set_ai_status(body.get("ai"), body.get("ai_ms", 0.0))
    except P.ProtocolError as exc:
        raise web.HTTPBadRequest(text=str(exc)) from None
    return web.json_response({"ok": True})


def make_app(ctrl) -> web.Application:
    app = web.Application()
    app[CTRL], app[HUB] = ctrl, Hub(ctrl)
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/internal/state", internal_state)
    app.router.add_post("/internal/event", internal_event)
    app.router.add_post("/internal/ai_status", internal_ai_status)
    ctrl.alerts_dir.mkdir(parents=True, exist_ok=True)
    app.router.add_static("/alerts", ctrl.alerts_dir, show_index=False)
    return app


async def start(ctrl, host: str, port: int):
    """Listen on host:port. Returns (runner, hub); call runner.cleanup() to stop."""
    app = make_app(ctrl)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    return runner, app[HUB]


async def every(period: float, fn, ctrl, after=None) -> None:
    """Run fn(dt, now) on a drift-free schedule. An error cuts the motors and latches, the loop keeps running."""
    last = nxt = time.monotonic()
    errors = 0
    while True:
        nxt += period
        now = time.monotonic()
        dt, last = min(max(now - last, 0.0), 0.2), now
        try:
            fn(dt, now)
        except Exception:
            errors += 1
            if errors <= 3 or errors % 100 == 0:
                log.exception("loop error %d", errors)
            ctrl.fail_safe()
        if after:
            await after()
        wait = nxt - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        else:
            nxt = time.monotonic()  # fell behind: do not burst
            await asyncio.sleep(0)


async def slow_loop(ctrl) -> None:
    while True:
        try:
            await asyncio.to_thread(ctrl.read_slow)
        except Exception:
            log.exception("read_slow failed")
        await asyncio.sleep(SLOW_S)


async def serve(ctrl, host: str, port: int, stop: asyncio.Event | None = None,
                ready: asyncio.Event | None = None) -> None:
    """Run the controller until stop is set (SIGINT or SIGTERM when stop is None)."""
    stop = stop or asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError, ValueError):
            pass  # Windows: Ctrl+C raises KeyboardInterrupt in main()
    runner, hub = await start(ctrl, host, port)
    ctrl.sensors.start()
    tasks = [asyncio.create_task(every(C.LOOP_S, ctrl.step, ctrl, hub.flush)),
             asyncio.create_task(every(1.0 / C.IMU_RATE, ctrl.imu_step, ctrl)), asyncio.create_task(slow_loop(ctrl))]
    log.info("controller on ws://%s:%s/ws (%s)", host, port, ctrl.hw.mode)
    if ready:
        ready.set()
    try:
        await stop.wait()
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await runner.cleanup()
        ctrl.close()
