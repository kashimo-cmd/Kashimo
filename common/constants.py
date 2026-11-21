"""Frozen constants of design section 4.3, ports of 4.5, key map of 4.6."""

OBSTACLE_CM = 30
DRIVE_SPEED = 0.25  # m/s

LOOP_S = 0.05
TELEM_HZ = 10
HEARTBEAT_S = 0.1
WATCHDOG_S = 0.5
WARN_S = 0.3

HEAD_RATE = 40  # deg/s
HOME_RATE = 60  # deg/s
INIT_HEAD_RATE = 30  # deg/s, 5.1 step 1
REST = (90, 90)  # (pan, tilt)
FOLD_POSE = None  # measured on the prototype (CHECK ON PI)

ROD_RATE = 30  # deg/s
ROD_TIMEOUT = 5.0  # s
ROD_HOLD_S = 1.0  # PC side

IMU_RATE = 100  # Hz
GYRO_CAL_S = 3.0

SNAP_STRAIGHT = 1.0  # m, no turn above SNAP_NO_TURN_DPS
SNAP_NO_TURN_DPS = 3.0
SNAP_WINDOW = 25  # deg, snap is OFF by default (5.6)

TILT_WARN = 25  # deg
TILT_ALERT = 35  # deg
BUMP_G = 0.5  # g above rest

STANDSTILL_GYRO_DPS = 1.0
STANDSTILL_ACCEL_G = 0.03
STANDSTILL_NO_COUNT_S = 1.0

# Front distance colours [EST]
FRONT_GREEN_ABOVE = 60  # cm
FRONT_MAX_CM = 200  # above this the dashboard shows ">200"; None shows "--"

# Link strength [EST]
LINK_BARS_DBM = (-60, -70, -80)  # 4, 3, 2 bars; worse = 1
DELAY_WARN_MS = 200
LOSS_WARN_PCT = 5

WS_PORT = 8765
WHEP_PORT = 8889
RTSP_PORT = 8554
DASHBOARD_PORT = 8080

# Physical key positions (event.code) -> function, section 4.6
KEY_MAP = {
    "KeyW": "FORWARD",
    "KeyS": "BACKWARD",
    "KeyA": "LEFT",
    "KeyD": "RIGHT",
    "ArrowLeft": "HEAD_LEFT",
    "ArrowRight": "HEAD_RIGHT",
    "ArrowUp": "HEAD_UP",
    "ArrowDown": "HEAD_DOWN",
    "KeyH": "HEAD_HOME",
    "KeyL": "LED",
    "Enter": "PHOTO",
    "KeyP": "SCREENSHOT",
    "KeyR": "ROD",
    "Space": "STOP",
}
HELD_KEYS = frozenset(
    ["KeyW", "KeyS", "KeyA", "KeyD", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"]
)  # sent every HEARTBEAT_S as CONTROL
KEY_TO_CMD = {"KeyH": "HEAD_HOME", "KeyL": "LED", "KeyR": "ROD", "Space": "STOP"}  # one-shot CMD
BLOCKED_DEFAULTS = frozenset(["Space", "Enter", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"])


def front_colour(cm):
    """Colour of the big front readout: none (no echo), green, orange, red."""
    if cm is None:
        return "none"
    if cm < OBSTACLE_CM:
        return "red"
    return "green" if cm > FRONT_GREEN_ABOVE else "orange"


def link_bars(rssi_dbm):
    """Signal bars 1..4 from dBm."""
    for bars, floor in zip((4, 3, 2), LINK_BARS_DBM):
        if rssi_dbm >= floor:
            return bars
    return 1
