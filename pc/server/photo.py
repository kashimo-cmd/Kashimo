"""Photo: newest frame of the video stream, saved as photo_0001_slab07_d12.4m_p090_t090.jpg (design 5.3)."""
import os
import threading
import time

import cv2

os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")  # RTSP over TCP, like the Pi side
OPEN_MS = 5000


class NoFrame(RuntimeError):
    """No fresh frame: stream missing or stalled."""


class FrameGrabber:
    """Keeps one reader on the stream (RTSP or MJPEG) and holds the newest frame. Starts at the first photo."""

    def __init__(self, url, max_age=2.0, wait=4.0):
        self.url, self.max_age, self.wait = url, max_age, wait
        self.frame, self.stamp = None, 0.0
        self.lock, self.stop, self.thread = threading.Lock(), threading.Event(), None

    def _run(self):
        while not self.stop.is_set():
            params = [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, OPEN_MS, cv2.CAP_PROP_READ_TIMEOUT_MSEC, OPEN_MS]
            cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG, params)
            while not self.stop.is_set() and cap.isOpened():
                ok, frame = cap.read()
                if not ok:
                    break
                with self.lock:
                    self.frame, self.stamp = frame, time.monotonic()
            cap.release()
            self.stop.wait(1.0)

    def latest(self):
        """Newest frame (BGR array). Raises NoFrame when there is none or it is older than max_age."""
        if not self.url:
            raise NoFrame("no video url in config (video.rtsp_url / video.mjpeg_url)")
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
        end = time.monotonic() + self.wait
        while self.frame is None and time.monotonic() < end:
            time.sleep(0.05)
        with self.lock:
            frame, age = self.frame, time.monotonic() - self.stamp
        if frame is None:
            raise NoFrame(f"no frame from {self.url} after {self.wait:.0f} s")
        if age > self.max_age:
            raise NoFrame(f"stream stalled, newest frame is {age:.1f} s old")
        return frame

    def close(self):
        self.stop.set()
        if self.thread is not None:
            self.thread.join(1.0)


def file_name(n, src):
    """src = Telemetry (slab s pan tilt) or None."""
    if src is None:
        return f"photo_{n:04d}_nopos.jpg"
    return f"photo_{n:04d}_slab{src.slab:02d}_d{src.s:.1f}m_p{round(src.pan):03d}_t{round(src.tilt):03d}.jpg"


def save(frame, folder, n, src):
    """Write the JPEG and confirm it exists and is not empty. Returns its path."""
    path = folder / file_name(n, src)
    if not cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95]) or path.stat().st_size == 0:
        raise OSError(f"could not write {path.name}")
    return path
