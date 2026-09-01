from dataclasses import replace

from crysense.hardware import (
    TFT,
    DisplaySnapshot,
    NetworkReading,
    SensorReading,
    read_network_status,
)


class FakeDisplay:
    def __init__(self, *, width: int = 128, height: int = 160, rotation: int = 90) -> None:
        self.width = width
        self.height = height
        self.rotation = rotation
        self.images = []

    def image(self, frame) -> None:
        self.images.append(frame.copy())


def dashboard_snapshot(*, connected: bool = True) -> DisplaySnapshot:
    return DisplaySnapshot(
        status="Monitorando",
        detail="IA pronta e escutando",
        network=NetworkReading(
            connected=connected,
            interface="wlan0",
            ip_address="192.168.15.51" if connected else None,
            ssid="Feira Maker" if connected else None,
        ),
        sensor=SensorReading(
            timestamp="2026-09-01T12:00:00+00:00",
            temperature=26.8,
            humidity=63.0,
            pressure=917.0,
        ),
        audio_level=0.035,
        camera_running=True,
    )


def test_dashboard_renders_landscape_status_cards() -> None:
    tft = TFT(False)
    image = tft.render_dashboard(dashboard_snapshot(), (160, 128))

    assert image.mode == "RGB"
    assert image.size == (160, 128)
    assert image.getpixel((2, 2)) == (35, 111, 141)
    assert image.getpixel((8, 110)) == (24, 164, 125)


def test_dashboard_handles_missing_network_and_sensor_values() -> None:
    tft = TFT(False)
    snapshot = replace(
        dashboard_snapshot(connected=False),
        sensor=SensorReading("2026-09-01T12:00:00+00:00", None, None, None, "sensor indisponivel"),
        audio_level=99,
        camera_running=False,
    )

    image = tft.render_dashboard(snapshot, (160, 128))

    assert image.size == (160, 128)
    assert image.getpixel((8, 110)) == (224, 143, 45)


def test_tft_avoids_duplicate_frames_and_respects_rotation() -> None:
    tft = TFT(False)
    fake = FakeDisplay()
    tft.display = fake
    snapshot = dashboard_snapshot()

    tft.show_dashboard(snapshot)
    tft.show_dashboard(snapshot)
    tft.show_dashboard(replace(snapshot, audio_level=0.08))

    assert len(fake.images) == 2
    assert all(image.size == (160, 128) for image in fake.images)

    portrait = FakeDisplay(width=128, height=160, rotation=0)
    tft.display = portrait
    tft.show_dashboard(replace(snapshot, status="Inicializando"))
    assert portrait.images[0].size == (128, 160)


def test_alert_has_priority_layout_and_supports_long_text() -> None:
    tft = TFT(False)
    image = tft.render_alert(
        "Colica",
        "Choro classificado com alta confianca. Verifique o bebe e acompanhe os sinais.",
        (190, 67, 72),
        (160, 128),
    )

    assert image.size == (160, 128)
    assert image.getpixel((2, 2)) == (190, 67, 72)


def test_network_status_identifies_fallback_access_point(monkeypatch) -> None:
    monkeypatch.setattr("crysense.hardware._interface_ipv4", lambda _interface: "10.42.0.1")
    monkeypatch.setattr("crysense.hardware._wifi_ssid", lambda _interface: "CrySense-Setup")

    reading = read_network_status()

    assert reading.connected is True
    assert reading.access_point is True
    assert reading.ip_address == "10.42.0.1"
