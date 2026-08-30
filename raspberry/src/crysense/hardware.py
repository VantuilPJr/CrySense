from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any


@dataclass(frozen=True)
class SensorReading:
    timestamp: str
    temperature: float | None
    humidity: float | None
    pressure: float | None
    error: str | None = None


class BME280:
    """BME280 no I2C padrão do Pi: GPIO2/SDA físico 3 e GPIO3/SCL físico 5."""

    def __init__(self, enabled: bool) -> None:
        self.sensor: Any | None = None
        self.error: str | None = None
        if not enabled:
            return
        try:
            import adafruit_bme280.basic as adafruit_bme280
            import board

            self.sensor = adafruit_bme280.Adafruit_BME280_I2C(board.I2C(), address=0x76)
        except Exception as exc:
            self.error = str(exc)

    def read(self) -> SensorReading:
        timestamp = datetime.now(UTC).isoformat()
        if self.sensor is None:
            return SensorReading(timestamp, None, None, None, self.error or "BME280 desabilitado")
        try:
            return SensorReading(
                timestamp,
                round(float(self.sensor.temperature), 2),
                round(float(self.sensor.relative_humidity), 2),
                round(float(self.sensor.pressure), 2),
            )
        except Exception as exc:
            return SensorReading(timestamp, None, None, None, str(exc))


class TFT:
    """TFT SPI ST7735: CE0/GPIO8, RST/GPIO24, DC/GPIO25 e LED/GPIO23 opcional."""

    def __init__(self, enabled: bool) -> None:
        self.display: Any | None = None
        self.backlight: Any | None = None
        self.error: str | None = None
        self._lock = Lock()
        if not enabled:
            return
        try:
            import board
            import digitalio
            from adafruit_rgb_display import st7735

            spi = board.SPI()
            self.display = st7735.ST7735R(
                spi,
                cs=digitalio.DigitalInOut(board.CE0),
                dc=digitalio.DigitalInOut(board.D25),
                rst=digitalio.DigitalInOut(board.D24),
                width=128,
                height=160,
                rotation=90,
                baudrate=24_000_000,
            )
            self.backlight = digitalio.DigitalInOut(board.D23)
            self.backlight.switch_to_output(value=True)
        except Exception as exc:
            self.error = str(exc)

    def show(self, title: str, detail: str, color: tuple[int, int, int] = (30, 90, 180)) -> None:
        if self.display is None:
            return
        try:
            from PIL import Image, ImageDraw, ImageFont

            with self._lock:
                # O driver gira a imagem internamente; a imagem de entrada precisa
                # usar as dimensões invertidas quando a rotação é 90° ou 270°.
                if self.display.rotation in (90, 270):
                    image_size = (self.display.height, self.display.width)
                else:
                    image_size = (self.display.width, self.display.height)
                image = Image.new("RGB", image_size, color)
                draw = ImageDraw.Draw(image)
                font = ImageFont.load_default()
                draw.text((8, 12), "CrySense", fill="white", font=font)
                draw.text((8, 48), title[:20], fill="white", font=font)
                draw.multiline_text((8, 75), detail[:80], fill="white", font=font, spacing=4)
                self.display.image(image)
        except Exception as exc:
            self.error = str(exc)


def reading_dict(reading: SensorReading) -> dict:
    return asdict(reading)
