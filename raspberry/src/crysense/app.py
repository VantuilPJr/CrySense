from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from secrets import compare_digest
from threading import Event, Lock, Thread
from time import monotonic
from typing import Literal

from fastapi import FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from .audio_runtime import AudioRuntime, PinkNoisePlayer
from .camera import CameraService
from .hardware import BME280, TFT, DisplaySnapshot, read_network_status, reading_dict
from .models import AudioClassifier
from .pipeline import CryEvent, TwoStagePipeline
from .settings import Settings
from .storage import Storage
from .uploaded_audio import MAX_UPLOAD_BYTES, analyze_uploaded_wav
from .vision_state import VisionState


class VisionDetection(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    confidence: float = Field(ge=0, le=1)
    box: tuple[float, float, float, float]


class VisionReport(BaseModel):
    state: Literal["starting", "monitoring", "error"] = "monitoring"
    alert: bool = False
    label: str | None = Field(default=None, max_length=80)
    confidence: float | None = Field(default=None, ge=0, le=1)
    detail: str | None = Field(default=None, max_length=240)
    timestamp: str | None = Field(default=None, max_length=64)
    detections: list[VisionDetection] = Field(default_factory=list, max_length=8)


class VisionZoneUpdate(BaseModel):
    risk_zone: tuple[float, float, float, float] | None


AUDIO_UPLOAD = File(...)


def _validate_risk_zone(zone: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = zone
    if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
        raise HTTPException(status_code=422, detail="A zona deve estar entre 0 e 1 e ter x1<x2 e y1<y2.")
    return zone


def _validate_detection_box(box: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = box
    if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
        raise HTTPException(status_code=422, detail="A caixa visual deve estar entre 0 e 1 e ter x1<x2 e y1<y2.")
    return box


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    static_dir = Path(__file__).with_name("static")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        settings.models_dir.mkdir(parents=True, exist_ok=True)
        storage = Storage(settings.data_dir / "crysense.db")
        trigger = AudioClassifier(settings.trigger_model_path, ("cry", "noise"), seconds=1.0)
        type_classifier = AudioClassifier(settings.type_model_path, ("colic", "hunger"), seconds=6.0)
        trigger.load()
        type_classifier.load()
        speaker = PinkNoisePlayer(settings.audio_output_device, settings.audio_output_channels)
        tft = TFT(settings.enable_tft)
        sensor = BME280(settings.enable_sensor)
        vision = VisionState(settings.vision_status_timeout)
        app.state.display_event_until = 0.0

        sensor_cache_lock = Lock()
        sensor_cache = sensor.read()
        sensor_cache_at = monotonic()
        network_cache_lock = Lock()
        network_cache = read_network_status()
        network_cache_at = monotonic()

        def latest_sensor_reading():
            nonlocal sensor_cache, sensor_cache_at
            now = monotonic()
            with sensor_cache_lock:
                if now - sensor_cache_at >= 5:
                    sensor_cache = sensor.read()
                    sensor_cache_at = now
                return sensor_cache

        def latest_network_reading():
            nonlocal network_cache, network_cache_at
            now = monotonic()
            with network_cache_lock:
                if now - network_cache_at >= 5:
                    network_cache = read_network_status()
                    network_cache_at = now
                return network_cache

        def handle_event(event: CryEvent) -> None:
            storage.add_event(event)
            app.state.display_event_until = monotonic() + 15
            if event.label == "colic":
                speaker.play(60)
                tft.show("CÓLICA", f"{event.confidence:.0%}\nRuído ativo", (150, 50, 60))
            else:
                speaker.stop()
                tft.show("FOME", f"{event.confidence:.0%}\nPrecisa mamar", (160, 110, 35))

        pipeline = TwoStagePipeline(
            trigger,
            type_classifier,
            trigger_threshold=settings.trigger_threshold,
            type_threshold=settings.type_threshold,
            type_margin=settings.type_margin,
            on_event=handle_event,
        )
        def update_monitor_display() -> None:
            if monotonic() < app.state.display_event_until:
                return
            accent = (25, 125, 155)
            if not audio.listening:
                status = "MICROFONE INATIVO"
                detail = audio.error or ("Inicializando captura" if audio.running else "Aguardando microfone")
                accent = (215, 137, 42)
            elif pipeline.phase == "error":
                status = "ERRO NA IA"
                detail = pipeline.last_error or "Falha ao analisar o audio"
                accent = (190, 67, 72)
            elif pipeline.phase == "capturing_type_audio":
                status = "ANALISANDO CHORO"
                detail = "Identificando fome ou colica"
                accent = (221, 133, 42)
            elif pipeline.last_trigger and pipeline.last_trigger.label == "cry":
                status = "CHORO DETECTADO"
                detail = f"IA 1 {pipeline.last_trigger.confidence:.0%} - confirmando"
                accent = (221, 133, 42)
            else:
                status = "MONITORANDO"
                detail = "IA pronta e escutando"
            tft.show_dashboard(
                DisplaySnapshot(
                    status=status,
                    detail=detail,
                    network=latest_network_reading(),
                    sensor=latest_sensor_reading(),
                    audio_level=audio.level_rms,
                    camera_running=camera.running,
                    accent=accent,
                )
            )

        audio = AudioRuntime(
            pipeline,
            input_device=settings.audio_input_device,
            input_channels=settings.audio_input_channels,
            input_channel=settings.audio_input_channel,
        )
        camera = CameraService(
            settings.camera_index,
            settings.camera_width,
            settings.camera_height,
            settings.camera_fps,
            device=settings.camera_device,
            rotation_degrees=settings.camera_rotation,
        )
        if settings.enable_camera:
            camera.start()
        if settings.enable_audio and trigger.ready and type_classifier.ready:
            audio.start()

        display_stop = Event()
        display_thread: Thread | None = None

        def display_loop() -> None:
            while not display_stop.wait(1):
                update_monitor_display()

        if tft.ready:
            update_monitor_display()
            display_thread = Thread(target=display_loop, name="crysense-display", daemon=True)
            display_thread.start()

        app.state.settings = settings
        app.state.storage = storage
        app.state.pipeline = pipeline
        app.state.audio = audio
        app.state.camera = camera
        app.state.sensor = sensor
        app.state.latest_sensor_reading = latest_sensor_reading
        app.state.latest_network_reading = latest_network_reading
        app.state.tft = tft
        app.state.speaker = speaker
        app.state.vision = vision
        app.state.handle_event = handle_event
        try:
            yield
        finally:
            display_stop.set()
            if display_thread:
                display_thread.join(timeout=2)
            audio.stop()
            speaker.stop()
            camera.stop()
            storage.close()

    app = FastAPI(title="CrySense", version="0.1.0", lifespan=lifespan)

    @app.get("/api/health")
    def health() -> dict:
        pipeline: TwoStagePipeline = app.state.pipeline
        return {"ok": True, "trigger_ready": pipeline.trigger.ready, "type_ready": pipeline.type_classifier.ready}

    @app.get("/api/status")
    def status() -> dict:
        sensor_reading = app.state.latest_sensor_reading()
        network_reading = app.state.latest_network_reading()
        if sensor_reading.error is None:
            app.state.storage.add_sensor_sample(
                sensor_reading.timestamp, sensor_reading.temperature, sensor_reading.humidity, sensor_reading.pressure
            )
        return {
            "ok": True,
            "pipeline": app.state.pipeline.status(),
            "audio": {
                "running": app.state.audio.running,
                "listening": app.state.audio.listening,
                "sample_rate": app.state.audio.capture_sample_rate,
                "input_channels": app.state.audio.input_channels,
                "level_rms": app.state.audio.level_rms,
                "level_peak": app.state.audio.level_peak,
                "last_frame_at": app.state.audio.last_frame_at,
                "error": app.state.audio.error,
            },
            "camera": asdict(app.state.camera.status()),
            "vision": app.state.vision.snapshot(),
            "sensor": reading_dict(sensor_reading),
            "network": asdict(network_reading),
            "tft_error": app.state.tft.error,
        }

    @app.get("/api/events")
    def events(limit: int = Query(50, ge=1, le=200)) -> dict:
        return {"events": app.state.storage.recent_events(limit)}

    @app.get("/api/vision/events")
    def vision_events(limit: int = Query(50, ge=1, le=200)) -> dict:
        return {"events": app.state.storage.recent_vision_events(limit)}

    @app.get("/api/vision/config")
    def vision_config() -> dict:
        return {"risk_zone": app.state.storage.vision_risk_zone()}

    @app.put("/api/vision/config")
    def update_vision_config(update: VisionZoneUpdate) -> dict:
        if update.risk_zone is None:
            app.state.storage.clear_vision_risk_zone()
            return {"ok": True, "risk_zone": None}
        zone = _validate_risk_zone(update.risk_zone)
        app.state.storage.set_vision_risk_zone(zone, datetime.now(UTC).isoformat())
        return {"ok": True, "risk_zone": zone}

    @app.get("/api/config")
    def config() -> dict:
        settings: Settings = app.state.settings
        return {
            "trigger_threshold": settings.trigger_threshold,
            "type_threshold": settings.type_threshold,
            "type_margin": settings.type_margin,
            "camera": {
                "width": settings.camera_width,
                "height": settings.camera_height,
                "fps": settings.camera_fps,
                "rotation_degrees": settings.camera_rotation,
            },
            "vision": {"configured": True, "requires_token": bool(settings.vision_token)},
        }

    @app.post("/api/audio/analyze")
    async def analyze_audio(audio: UploadFile = AUDIO_UPLOAD) -> dict:
        filename = audio.filename or "audio.wav"
        accepted_media_types = {"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"}
        if not filename.lower().endswith(".wav") and (audio.content_type or "").lower() not in accepted_media_types:
            await audio.close()
            raise HTTPException(status_code=415, detail="Envie um arquivo WAV PCM (.wav).")
        payload = await audio.read(MAX_UPLOAD_BYTES + 1)
        await audio.close()
        if len(payload) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="O arquivo deve ter no máximo 12 MB.")
        try:
            result, event = analyze_uploaded_wav(
                payload,
                filename if filename.lower().endswith(".wav") else "audio.wav",
                app.state.pipeline.trigger,
                app.state.pipeline.type_classifier,
                app.state.settings.trigger_threshold,
                app.state.settings.type_threshold,
                app.state.settings.type_margin,
            )
            if event is not None:
                app.state.handle_event(event)
            return result
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/vision/report")
    def vision_report(
        report: VisionReport,
        token: str | None = Header(default=None, alias="X-CrySense-Vision-Token"),
    ) -> dict:
        settings: Settings = app.state.settings
        if settings.vision_token and not compare_digest(token or "", settings.vision_token):
            raise HTTPException(status_code=401, detail="Token da visão inválido.")
        timestamp = report.timestamp or datetime.now(UTC).isoformat()
        new_alert = app.state.vision.update(
            state=report.state,
            alert=report.alert,
            label=report.label,
            confidence=report.confidence,
            detail=report.detail,
            updated_at=timestamp,
            detections=[
                {
                    "label": detection.label,
                    "confidence": detection.confidence,
                    "box": _validate_detection_box(detection.box),
                }
                for detection in report.detections
            ],
        )
        if new_alert:
            app.state.storage.add_vision_event(timestamp, report.label or "risco_visual", report.confidence, report.detail)
            app.state.display_event_until = monotonic() + 15
            app.state.tft.show("RISCO VISUAL", (report.detail or report.label or "Verifique o berço")[:45], (180, 55, 45))
        return {"ok": True, "vision": app.state.vision.snapshot()}

    @app.get("/api/camera/stream")
    def camera_stream():
        if not app.state.camera.running:
            raise HTTPException(status_code=503, detail=app.state.camera.error or "webcam indisponível")
        return StreamingResponse(
            app.state.camera.mjpeg_frames(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/")
    def dashboard() -> FileResponse:
        return FileResponse(static_dir / "index.html", headers={"Cache-Control": "no-store, max-age=0"})

    return app


app = create_app()


def main() -> None:
    import uvicorn

    runtime_settings = Settings.from_env()
    uvicorn.run("crysense.app:app", host=runtime_settings.host, port=runtime_settings.port, reload=False)


if __name__ == "__main__":
    main()
