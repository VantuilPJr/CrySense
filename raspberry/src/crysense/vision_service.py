from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

JPEG_MARKER = 0xFF
JPEG_START = 0xD8
JPEG_END = 0xD9
MAX_JPEG_BYTES = 3 * 1024 * 1024


def _number(name: str, default: float) -> float:
    value = os.getenv(name)
    return default if value in (None, "") else float(value)


def _normalized_labels(value: str) -> tuple[str, ...]:
    return tuple(item.strip().lower() for item in value.split(",") if item.strip())


def _risk_zone(value: str) -> tuple[float, float, float, float] | None:
    if not value.strip():
        return None
    try:
        return _risk_zone_values(value.split(","))
    except ValueError as exc:
        raise ValueError("CRYSENSE_VISION_RISK_ZONE deve ser x1,y1,x2,y2 entre 0 e 1.") from exc


def _risk_zone_values(values: object) -> tuple[float, float, float, float]:
    try:
        x1, y1, x2, y2 = (float(item) for item in values)
    except (TypeError, ValueError) as exc:
        raise ValueError("A zona de risco deve conter quatro valores numéricos.") from exc
    if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
        raise ValueError("A zona de risco deve estar entre 0 e 1 e ter x1<x2, y1<y2.")
    return x1, y1, x2, y2


@dataclass(frozen=True)
class VisionConfig:
    pi_url: str
    model_source: str
    image_size: int
    confidence_threshold: float
    interval_seconds: float
    report_interval_seconds: float
    consecutive_frames: int
    risk_labels: tuple[str, ...]
    risk_zone: tuple[float, float, float, float] | None
    token: str

    @classmethod
    def from_env(cls) -> VisionConfig:
        pi_url = os.getenv("CRYSENSE_PI_URL", "http://192.168.15.51:8080").rstrip("/")
        # Um nome de modelo oficial, como ``yolo11n.pt``, é aceito pelo
        # Ultralytics e baixado no computador na primeira execução. Um caminho
        # absoluto para um modelo treinado continua funcionando da mesma forma.
        model = os.getenv("CRYSENSE_VISION_MODEL", "yolo11n.pt").strip() or "yolo11n.pt"
        return cls(
            pi_url=pi_url,
            model_source=model,
            image_size=int(_number("CRYSENSE_VISION_IMAGE_SIZE", 320)),
            confidence_threshold=_number("CRYSENSE_VISION_CONFIDENCE", 0.55),
            interval_seconds=max(0.1, _number("CRYSENSE_VISION_INTERVAL", 0.5)),
            report_interval_seconds=max(0.5, _number("CRYSENSE_VISION_REPORT_INTERVAL", 0.5)),
            consecutive_frames=max(1, int(_number("CRYSENSE_VISION_CONSECUTIVE", 3))),
            risk_labels=_normalized_labels(os.getenv("CRYSENSE_VISION_RISK_LABELS", "climb,escape_risk")),
            risk_zone=_risk_zone(os.getenv("CRYSENSE_VISION_RISK_ZONE", "")),
            token=os.getenv("CRYSENSE_VISION_TOKEN", "").strip(),
        )


@dataclass(frozen=True)
class Detection:
    label: str
    confidence: float
    box: tuple[float, float, float, float]


@dataclass(frozen=True)
class SafetyDecision:
    alert: bool
    label: str | None
    confidence: float | None
    detail: str


class SafetyEvaluator:
    """Converte detecções YOLO em alerta após persistência em quadros consecutivos."""

    def __init__(self, config: VisionConfig) -> None:
        self.config = config
        self._consecutive = 0
        self._risk_zone = config.risk_zone

    def set_risk_zone(self, zone: tuple[float, float, float, float] | None) -> None:
        if zone != self._risk_zone:
            self._risk_zone = zone
            self._consecutive = 0

    def evaluate(self, detections: list[Detection], width: int, height: int) -> SafetyDecision:
        candidate = self._find_candidate(detections, width, height)
        self._consecutive = self._consecutive + 1 if candidate else 0
        if candidate and self._consecutive >= self.config.consecutive_frames:
            return SafetyDecision(True, candidate.label, candidate.confidence, "Padrão visual de risco confirmado; verifique o berço.")
        if candidate:
            return SafetyDecision(False, candidate.label, candidate.confidence, f"Confirmando possível risco ({self._consecutive}/{self.config.consecutive_frames}).")
        if not self._risk_zone and not self.config.risk_labels:
            return SafetyDecision(False, None, None, "Configure rótulos de risco ou uma zona de saída para habilitar alertas.")
        return SafetyDecision(False, None, None, "Nenhum padrão visual de risco detectado.")

    def _find_candidate(self, detections: list[Detection], width: int, height: int) -> Detection | None:
        explicit = [item for item in detections if item.label.lower() in self.config.risk_labels]
        if explicit:
            return max(explicit, key=lambda item: item.confidence)
        if not self._risk_zone:
            return None
        zone = self._risk_zone
        zone_pixels = (zone[0] * width, zone[1] * height, zone[2] * width, zone[3] * height)
        persons = [item for item in detections if item.label.lower() in {"person", "baby", "bebê"}]
        in_zone = [item for item in persons if _intersects(item.box, zone_pixels)]
        if not in_zone:
            return None
        selected = max(in_zone, key=lambda item: item.confidence)
        return Detection("near_exit_zone", selected.confidence, selected.box)


def _intersects(first: tuple[float, float, float, float], second: tuple[float, float, float, float]) -> bool:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    return right > left and bottom > top


def _mjpeg_jpegs(url: str) -> Iterator[bytes]:
    request = urllib.request.Request(url, headers={"Accept": "multipart/x-mixed-replace"})
    with urllib.request.urlopen(request, timeout=30) as response:
        frame = bytearray()
        previous = -1
        collecting = False
        while True:
            chunk = response.read(8_192)
            if not chunk:
                return
            for value in chunk:
                if not collecting:
                    if previous == JPEG_MARKER and value == JPEG_START:
                        frame = bytearray((JPEG_MARKER, JPEG_START))
                        collecting = True
                else:
                    frame.append(value)
                    if len(frame) > MAX_JPEG_BYTES:
                        frame.clear()
                        collecting = False
                    elif previous == JPEG_MARKER and value == JPEG_END:
                        yield bytes(frame)
                        frame.clear()
                        collecting = False
                previous = value


class VisionRunner:
    def __init__(self, config: VisionConfig) -> None:
        self.config = config
        self.evaluator = SafetyEvaluator(config)
        self._model = None
        self._next_zone_sync_at = 0.0

    def run_forever(self) -> None:
        self._load_model()
        self._send_report("starting", False, None, None, "Modelo visual carregado; conectando à câmera.")
        next_inference_at = 0.0
        last_report_at = 0.0
        previous_alert = False
        stream_url = f"{self.config.pi_url}/api/camera/stream"

        while True:
            try:
                for jpeg in _mjpeg_jpegs(stream_url):
                    now = time.monotonic()
                    if now >= self._next_zone_sync_at:
                        self._sync_risk_zone()
                        self._next_zone_sync_at = now + 1.0
                    if now < next_inference_at:
                        continue
                    next_inference_at = now + self.config.interval_seconds
                    frame = self._decode_jpeg(jpeg)
                    if frame is None:
                        continue
                    detections = self._detect(frame)
                    decision = self.evaluator.evaluate(detections, frame.shape[1], frame.shape[0])
                    changed = decision.alert != previous_alert
                    if changed or now - last_report_at >= self.config.report_interval_seconds:
                        self._send_report(
                            "monitoring",
                            decision.alert,
                            decision.label,
                            decision.confidence,
                            decision.detail,
                            self._display_detections(detections, frame.shape[1], frame.shape[0]),
                        )
                        last_report_at = now
                        previous_alert = decision.alert
            except KeyboardInterrupt:
                return
            except Exception as exc:
                self._send_report("error", False, None, None, f"Falha no serviço visual: {str(exc)[:180]}")
                print(f"[visão] {exc}", file=sys.stderr)
                time.sleep(2)

    def _load_model(self) -> None:
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError('Instale as dependências da visão com: pip install -e ".[vision]"') from exc
        try:
            self._model = YOLO(self.config.model_source)
        except Exception as exc:
            raise RuntimeError(
                f"Não foi possível carregar o modelo YOLO '{self.config.model_source}'. "
                "Para o modelo padrão, deixe o computador conectado à internet na primeira execução."
            ) from exc

    def _sync_risk_zone(self) -> None:
        """Lê a zona desenhada no painel; falhas não interrompem a visão."""
        request = urllib.request.Request(f"{self.config.pi_url}/api/vision/config")
        try:
            with urllib.request.urlopen(request, timeout=1.5) as response:
                payload = json.loads(response.read())
            values = payload.get("risk_zone")
            self.evaluator.set_risk_zone(None if values is None else _risk_zone_values(values))
        except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError):
            return

    @staticmethod
    def _decode_jpeg(jpeg: bytes):
        import cv2

        return cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)

    def _detect(self, frame) -> list[Detection]:
        results = self._model(frame, imgsz=self.config.image_size, conf=self.config.confidence_threshold, verbose=False)
        result = results[0]
        boxes = result.boxes
        if boxes is None:
            return []
        names = result.names
        detections = []
        for box in boxes:
            class_id = int(box.cls[0].item())
            label = str(names[class_id] if isinstance(names, list) else names.get(class_id, class_id))
            x1, y1, x2, y2 = (float(value) for value in box.xyxy[0].tolist())
            detections.append(Detection(label, float(box.conf[0].item()), (x1, y1, x2, y2)))
        return detections

    @staticmethod
    def _display_detections(detections: list[Detection], width: int, height: int) -> list[dict]:
        labels = {"person", "baby", "bebê", "infant"}
        visible = []
        for detection in detections:
            if detection.label.lower() not in labels:
                continue
            x1, y1, x2, y2 = detection.box
            box = (
                max(0.0, min(1.0, x1 / width)),
                max(0.0, min(1.0, y1 / height)),
                max(0.0, min(1.0, x2 / width)),
                max(0.0, min(1.0, y2 / height)),
            )
            if box[0] < box[2] and box[1] < box[3]:
                visible.append({"label": detection.label, "confidence": detection.confidence, "box": box})
        return sorted(visible, key=lambda item: item["confidence"], reverse=True)[:8]

    def _send_report(
        self,
        state: str,
        alert: bool,
        label: str | None,
        confidence: float | None,
        detail: str,
        detections: list[dict] | None = None,
    ) -> None:
        payload = json.dumps(
            {
                "state": state,
                "alert": alert,
                "label": label,
                "confidence": confidence,
                "detail": detail,
                "timestamp": datetime.now(UTC).isoformat(),
                "detections": detections or [],
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.config.token:
            headers["X-CrySense-Vision-Token"] = self.config.token
        request = urllib.request.Request(f"{self.config.pi_url}/api/vision/report", data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=5):
                pass
        except urllib.error.URLError as exc:
            print(f"[visão] não foi possível atualizar o Raspberry: {exc}", file=sys.stderr)


def main() -> None:
    config = VisionConfig.from_env()
    try:
        VisionRunner(config).run_forever()
    except KeyboardInterrupt:
        return
    except Exception as exc:
        print(f"[visão] inicialização interrompida: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
