from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from sys import platform


@dataclass(frozen=True)
class CameraStatus:
    running: bool
    width: int
    height: int
    fps: int
    rotation_degrees: float
    source: str | None
    error: str | None
    frames: int
    last_frame_at: str | None
    frame_age_seconds: float | None


class CameraService:
    """Captura UVC em thread e expõe o último JPEG para transmissão MJPEG local."""

    def __init__(
        self, index: int, width: int, height: int, fps: int, device: str | None = None, rotation_degrees: float = 0
    ) -> None:
        self.index = index
        self.device = device
        self.width = width
        self.height = height
        self.fps = fps
        self.rotation_degrees = rotation_degrees % 360
        self.error: str | None = None
        self.source: str | None = None
        self._jpeg: bytes | None = None
        self._lock = threading.Condition()
        self._capture_lock = threading.Lock()
        self._capture = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._frames = 0
        self._last_frame_at: str | None = None
        self._last_frame_monotonic: float | None = None

    @property
    def running(self) -> bool:
        with self._lock:
            last_frame = self._last_frame_monotonic
            has_jpeg = self._jpeg is not None
        fresh = last_frame is not None and time.monotonic() - last_frame <= 3
        return bool(self._thread and self._thread.is_alive() and has_jpeg and fresh and self.error is None)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="crysense-camera", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._capture_lock:
            capture = self._capture
        if capture is not None:
            capture.release()
        with self._lock:
            self._lock.notify_all()
        if self._thread:
            self._thread.join(timeout=3)
        self._jpeg = None

    def status(self) -> CameraStatus:
        with self._lock:
            last_frame_monotonic = self._last_frame_monotonic
            frame_age = None if last_frame_monotonic is None else round(time.monotonic() - last_frame_monotonic, 2)
            frames = self._frames
            last_frame_at = self._last_frame_at
        return CameraStatus(
            self.running,
            self.width,
            self.height,
            self.fps,
            self.rotation_degrees,
            self.source,
            self.error,
            frames,
            last_frame_at,
            frame_age,
        )

    def _sources(self) -> list[int | str]:
        sources: list[int | str] = []
        if self.device:
            sources.append(self.device)
        # O índice /dev/videoN muda quando drivers do Pi ou a webcam reiniciam.
        # O symlink index0 identifica o fluxo de vídeo da webcam UVC de forma estável.
        sources.extend(str(path) for path in sorted(Path("/dev/v4l/by-id").glob("*-video-index0")))
        sources.append(self.index)
        return list(dict.fromkeys(sources))

    @staticmethod
    def _open_capture(cv2, source: int | str):
        backend = cv2.CAP_V4L2 if platform.startswith("linux") else cv2.CAP_ANY
        return cv2.VideoCapture(source, backend)

    def _configure_capture(self, cv2, capture) -> None:
        # Esta webcam fornece somente YUYV. Um buffer reduzido evita que o
        # painel mostre imagens antigas quando a rede está mais lenta.
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV"))
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        capture.set(cv2.CAP_PROP_FPS, self.fps)

    def _rotate_frame(self, cv2, frame):
        """Gira no sentido horário; 90, 180 e 270 preservam toda a imagem."""
        angle = self.rotation_degrees
        if angle == 0:
            return frame
        if angle == 90:
            return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        if angle == 180:
            return cv2.rotate(frame, cv2.ROTATE_180)
        if angle == 270:
            return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

        height, width = frame.shape[:2]
        transform = cv2.getRotationMatrix2D((width / 2, height / 2), -angle, 1)
        return cv2.warpAffine(frame, transform, (width, height), borderMode=cv2.BORDER_REPLICATE)

    def mjpeg_frames(self):
        previous: bytes | None = None
        while not self._stop.is_set():
            with self._lock:
                self._lock.wait_for(
                    lambda previous=previous: (
                        self._jpeg is not None and self._jpeg != previous
                    ) or self._stop.is_set(),
                    timeout=3,
                )
                jpeg = self._jpeg
            if not jpeg:
                continue
            previous = jpeg
            yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n"

    def _run(self) -> None:
        try:
            import cv2

            delay = 1.0 / max(1, self.fps)
            while not self._stop.is_set():
                capture = None
                for source in self._sources():
                    candidate = self._open_capture(cv2, source)
                    self._configure_capture(cv2, candidate)
                    if candidate.isOpened():
                        capture = candidate
                        self.source = str(source)
                        break
                    candidate.release()
                if capture is None:
                    self.source = None
                    self.error = "webcam UVC não abriu; nova tentativa em 2 s"
                    self._stop.wait(2)
                    continue

                with self._capture_lock:
                    self._capture = capture
                self.error = None
                next_frame_due = time.monotonic()
                while not self._stop.is_set():
                    ok, frame = capture.read()
                    if not ok:
                        self.error = "falha ao capturar quadro da webcam; reconectando"
                        break
                    frame = self._rotate_frame(cv2, frame)
                    ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 78])
                    if ok:
                        with self._lock:
                            self._jpeg = encoded.tobytes()
                            self._frames += 1
                            self._last_frame_at = datetime.now(UTC).isoformat()
                            self._last_frame_monotonic = time.monotonic()
                            self._lock.notify_all()
                    next_frame_due = max(next_frame_due + delay, time.monotonic())
                    self._stop.wait(max(0, next_frame_due - time.monotonic()))
                with self._capture_lock:
                    if self._capture is capture:
                        self._capture = None
                capture.release()
                if self.error:
                    self._stop.wait(1)
        except Exception as exc:
            self.error = str(exc)
