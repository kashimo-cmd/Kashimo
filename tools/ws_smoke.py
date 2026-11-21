"""K03 smoke test: connect to a Pi (real or fake), drive forward, print telemetry. Exit 0 if s changed."""
import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import websockets  # noqa: E402

from common import constants as C  # noqa: E402
from common import protocol as P  # noqa: E402


def control(seq, fwd=0, turn=0):
    return P.encode(P.Control(seq=seq, ts=time.time(), drive=P.DriveCmd(fwd=fwd, turn=turn), head=P.HeadCmd(pan=0, tilt=0)))


def show(t):
    fc = "--" if t.fc is None else f"{t.fc:.0f}"
    print(f"{t.state:8} imu={t.imu:11} s={t.s:6.3f} x={t.x:6.3f} y={t.y:6.3f} yaw={t.yaw:6.1f} front={fc:>4} cm "
          f"slab={t.slab} rssi={t.rssi_dbm:.0f} refusal={t.refusal}")


async def run(url, seconds, fwd, turn):
    seq, first, last, tel = 0, None, None, None
    async with websockets.connect(url) as ws:
        seq += 1
        await ws.send(P.encode(P.Sync(seq=seq, ts=time.time(), since_id=0)))
        start, driving_from, shown = time.monotonic(), None, 0.0
        while True:
            now = time.monotonic()
            if driving_from is None and tel is not None and tel.imu != "CALIBRATING":
                driving_from = now  # IMU ready: start the timed drive
            if driving_from is not None and now - driving_from > seconds:
                break
            if driving_from is None and now - start > 10:
                print("FAIL: IMU never became ready")
                return 1
            seq += 1
            await ws.send(control(seq, *((fwd, turn) if driving_from is not None else (0, 0))))
            try:
                while True:
                    msg = P.decode(await asyncio.wait_for(ws.recv(), C.HEARTBEAT_S))
                    if isinstance(msg, P.Telemetry):
                        tel = msg
                        first = first if first is not None and driving_from else (msg if driving_from else None)
                        last = msg
                        if now - shown >= 0.5:
                            shown = now
                            show(msg)
                    elif isinstance(msg, P.Event):
                        print(f"EVENT {msg.id} {msg.kind} s={msg.s} slab={msg.slab} data={msg.data}")
            except asyncio.TimeoutError:
                pass
        await ws.send(control(seq + 1))
    if first is None or last is None:
        print("FAIL: no telemetry")
        return 1
    moved = abs(last.s - first.s) > 0.01 or abs(last.yaw - first.yaw) > 1.0
    print(f"{'OK' if moved else 'FAIL'}: s {first.s:.3f} -> {last.s:.3f}, yaw {first.yaw:.1f} -> {last.yaw:.1f}")
    return 0 if moved else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=f"ws://127.0.0.1:{C.WS_PORT}/ws")
    ap.add_argument("--seconds", type=float, default=3.0, help="how long to drive")
    ap.add_argument("--fwd", type=int, default=1, choices=(-1, 0, 1))
    ap.add_argument("--turn", type=int, default=0, choices=(-1, 0, 1))
    a = ap.parse_args()
    try:
        sys.exit(asyncio.run(run(a.url, a.seconds, a.fwd, a.turn)))
    except (OSError, websockets.WebSocketException) as exc:
        sys.exit(f"FAIL: cannot talk to {a.url}: {exc}")
