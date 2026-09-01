from __future__ import annotations

import socket
import struct
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any


@dataclass(frozen=True)
class SensorReading:
    timestamp: str
    temperature: float | None
    humidity: float | None
    pressure: float | None
    error: str | None = None


@dataclass(frozen=True)
class NetworkReading:
    connected: bool
    interface: str
    ip_address: str | None
    ssid: str | None = None
    access_point: bool = False
    error: str | None = None


@dataclass(frozen=True)
class DisplaySnapshot:
    status: str
    detail: str
    network: NetworkReading
    sensor: SensorReading
    audio_level: float | None = None
    camera_running: bool = False
    accent: tuple[int, int, int] = (25, 125, 155)
    crying_baby: bool = False
    animation_frame: int = 0


def _interface_ipv4(interface: str) -> str | None:
    """Obtém o IPv4 da interface sem depender de um acesso à internet."""
    try:
        import fcntl

        request = struct.pack("256s", interface.encode("utf-8")[:15])
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            response = fcntl.ioctl(connection.fileno(), 0x8915, request)
        return socket.inet_ntoa(response[20:24])
    except (ImportError, OSError, ValueError):
        return None


def _wifi_ssid(interface: str) -> str | None:
    commands = (
        ("iwgetid", interface, "--raw"),
        ("nmcli", "-g", "GENERAL.CONNECTION", "device", "show", interface),
    )
    for command in commands:
        try:
            result = subprocess.run(command, capture_output=True, check=False, text=True, timeout=1)
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue
        value = result.stdout.strip().splitlines()
        if result.returncode == 0 and value and value[0] not in {"", "--"}:
            return value[0]
    return None


def read_network_status(interface: str = "wlan0") -> NetworkReading:
    ip_address = _interface_ipv4(interface)
    ssid = _wifi_ssid(interface) if ip_address else None
    operstate_path = Path("/sys/class/net") / interface / "operstate"
    try:
        operstate = operstate_path.read_text(encoding="utf-8").strip().lower()
    except OSError:
        operstate = "unknown"
    connected = bool(ip_address) and operstate != "down"
    access_point = bool(
        connected
        and (
            (ssid or "").casefold() == "crysense-setup".casefold()
            or (ip_address or "").startswith("10.42.")
        )
    )
    return NetworkReading(
        connected=connected,
        interface=interface,
        ip_address=ip_address,
        ssid=ssid,
        access_point=access_point,
        error=None if connected else f"{interface} sem IPv4",
    )


class BME280:
    """BME280 no I2C padrão do Pi: GPIO2/SDA físico 3 e GPIO3/SCL físico 5."""

    def __init__(self, enabled: bool) -> None:
        self.sensor: Any | None = None
        self.error: str | None = None
        self._lock = Lock()
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
            with self._lock:
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
        self._font_cache: dict[tuple[int, bool], Any] = {}
        self._last_frame_key: object | None = None
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

    @property
    def ready(self) -> bool:
        return self.display is not None and self.error is None

    def _image_size(self) -> tuple[int, int]:
        if self.display is None:
            return (160, 128)
        if self.display.rotation in (90, 270):
            return (self.display.height, self.display.width)
        return (self.display.width, self.display.height)

    def _font(self, size: int, *, bold: bool = False) -> Any:
        from PIL import ImageFont

        key = (size, bold)
        if key in self._font_cache:
            return self._font_cache[key]
        filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
        candidates = (
            filename,
            f"/usr/share/fonts/truetype/dejavu/{filename}",
            f"/usr/share/fonts/dejavu/{filename}",
        )
        for candidate in candidates:
            try:
                font = ImageFont.truetype(candidate, size)
                self._font_cache[key] = font
                return font
            except OSError:
                continue
        font = ImageFont.load_default()
        self._font_cache[key] = font
        return font

    @staticmethod
    def _fit_text(draw: Any, text: str, font: Any, max_width: int) -> str:
        value = " ".join(text.replace("\n", " ").split())
        if draw.textbbox((0, 0), value, font=font)[2] <= max_width:
            return value
        suffix = "..."
        while value and draw.textbbox((0, 0), value + suffix, font=font)[2] > max_width:
            value = value[:-1]
        return value.rstrip() + suffix if value else suffix

    @classmethod
    def _wrapped_lines(cls, draw: Any, text: str, font: Any, max_width: int, max_lines: int = 2) -> list[str]:
        lines: list[str] = []
        for paragraph in text.splitlines() or [text]:
            current = ""
            for word in paragraph.split():
                candidate = f"{current} {word}".strip()
                if not current or draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
                    current = candidate
                else:
                    lines.append(current)
                    current = word
                    if len(lines) == max_lines:
                        break
            if current and len(lines) < max_lines:
                lines.append(current)
            if len(lines) == max_lines:
                break
        if lines and len(" ".join(lines)) < len(" ".join(text.split())):
            lines[-1] = cls._fit_text(draw, lines[-1] + "...", font, max_width)
        return lines or [""]

    @staticmethod
    def _draw_wifi(draw: Any, center: tuple[int, int], color: tuple[int, int, int]) -> None:
        x, y = center
        for radius in (3, 6, 9):
            draw.arc((x - radius, y - radius, x + radius, y + radius), 215, 325, fill=color, width=2)
        draw.ellipse((x - 1, y + 4, x + 1, y + 6), fill=color)

    @staticmethod
    def _draw_crying_baby(draw: Any, box: tuple[int, int, int, int], animation_frame: int = 0) -> None:
        """Desenha um rosto vetorial para não depender de fontes de emoji."""
        left, top, right, bottom = box
        width = right - left
        height = bottom - top
        center_x = left + width // 2
        center_y = top + height // 2
        frame = animation_frame % 2
        skin = (255, 218, 181)
        outline = (104, 73, 67)
        hair = (113, 79, 60)
        tear = (55, 157, 219)
        mouth = (111, 48, 59)

        ear_radius = max(2, width // 11)
        draw.ellipse(
            (left - ear_radius + 2, center_y - ear_radius, left + ear_radius + 2, center_y + ear_radius),
            fill=skin,
            outline=outline,
        )
        draw.ellipse(
            (right - ear_radius - 2, center_y - ear_radius, right + ear_radius - 2, center_y + ear_radius),
            fill=skin,
            outline=outline,
        )
        draw.ellipse((left, top, right, bottom), fill=skin, outline=outline, width=2)

        hair_y = top + max(3, height // 7)
        draw.arc((center_x - 9, top - 2, center_x + 2, hair_y + 7), 185, 345, fill=hair, width=2)
        draw.arc((center_x - 1, top - 1, center_x + 9, hair_y + 7), 195, 350, fill=hair, width=2)

        eye_y = center_y - max(1, height // 12)
        eye_offset = max(5, width // 5)
        draw.line((center_x - eye_offset - 3, eye_y - 1, center_x - eye_offset, eye_y + 1), fill=outline, width=2)
        draw.line((center_x - eye_offset, eye_y + 1, center_x - eye_offset + 3, eye_y - 1), fill=outline, width=2)
        draw.line((center_x + eye_offset - 3, eye_y - 1, center_x + eye_offset, eye_y + 1), fill=outline, width=2)
        draw.line((center_x + eye_offset, eye_y + 1, center_x + eye_offset + 3, eye_y - 1), fill=outline, width=2)

        mouth_width = max(6, width // 5)
        mouth_top = center_y + max(4, height // 7)
        draw.ellipse(
            (center_x - mouth_width // 2, mouth_top, center_x + mouth_width // 2, mouth_top + max(7, height // 4)),
            fill=mouth,
            outline=outline,
        )
        draw.arc(
            (center_x - mouth_width // 2 + 1, mouth_top + 2, center_x + mouth_width // 2 - 1, mouth_top + max(6, height // 5)),
            10,
            170,
            fill=(244, 132, 139),
            width=1,
        )

        tear_top = eye_y + 3
        for index, x in enumerate((center_x - eye_offset, center_x + eye_offset)):
            length = max(5, height // 5) + (2 if (index + frame) % 2 == 0 else 0)
            draw.line((x, tear_top, x, tear_top + length), fill=tear, width=2)
            draw.ellipse((x - 2, tear_top + length - 1, x + 2, tear_top + length + 3), fill=tear)

    def render_dashboard(self, snapshot: DisplaySnapshot, image_size: tuple[int, int] | None = None) -> Any:
        from PIL import Image, ImageDraw

        width, height = image_size or self._image_size()
        image = Image.new("RGB", (width, height), (242, 248, 252))
        draw = ImageDraw.Draw(image)
        title_font = self._font(13, bold=True)
        status_font = self._font(10, bold=True)
        value_font = self._font(12, bold=True)
        small_font = self._font(8)
        tiny_font = self._font(7)

        header = (35, 111, 141)
        card = (255, 255, 255)
        border = (211, 229, 237)
        text = (38, 65, 78)
        muted = (92, 119, 130)
        good = (24, 164, 125)
        warning = (224, 143, 45)

        draw.rectangle((0, 0, width, 19), fill=header)
        draw.text((7, 2), "CrySense", fill="white", font=title_font)
        wifi_color = good if snapshot.network.connected else (190, 205, 212)
        self._draw_wifi(draw, (width - 34, 8), wifi_color)
        wifi_text = "AP" if snapshot.network.access_point else ("ON" if snapshot.network.connected else "OFF")
        draw.text((width - 20, 5), wifi_text, fill="white", font=tiny_font)

        draw.rounded_rectangle((4, 23, width - 5, 60), radius=7, fill=card, outline=border)
        draw.rounded_rectangle((4, 23, 8, 60), radius=2, fill=snapshot.accent)
        status = self._fit_text(draw, snapshot.status.upper(), status_font, width - 66)
        draw.text((13, 27), status, fill=text, font=status_font)
        detail = self._fit_text(draw, snapshot.detail, small_font, width - 67)
        draw.text((13, 42), detail, fill=muted, font=small_font)

        if snapshot.crying_baby:
            self._draw_crying_baby(
                draw,
                (width - 49, 25, width - 13, 58),
                animation_frame=snapshot.animation_frame,
            )
        else:
            level = max(0.0, min(float(snapshot.audio_level or 0.0), 0.10))
            meter = level / 0.10
            meter_x, meter_y, meter_width = width - 52, 43, 42
            draw.text((meter_x, 27), f"MIC {level:.0%}", fill=muted, font=tiny_font)
            draw.rounded_rectangle(
                (meter_x, meter_y, meter_x + meter_width, meter_y + 6), radius=3, fill=(225, 237, 241)
            )
            if meter > 0:
                fill_width = max(3, round(meter_width * meter))
                meter_color = good if meter < 0.75 else warning
                draw.rounded_rectangle(
                    (meter_x, meter_y, meter_x + fill_width, meter_y + 6), radius=3, fill=meter_color
                )

        sensor_y, sensor_bottom = 64, 101
        gap = 3
        sensor_width = (width - 8 - gap * 2) // 3
        sensor_values = (
            ("TEMP", "--.-°" if snapshot.sensor.temperature is None else f"{snapshot.sensor.temperature:.1f}°"),
            ("UMIDADE", "--%" if snapshot.sensor.humidity is None else f"{snapshot.sensor.humidity:.0f}%"),
            ("PRESSAO", "----" if snapshot.sensor.pressure is None else f"{snapshot.sensor.pressure:.0f}"),
        )
        for index, (label, value) in enumerate(sensor_values):
            left = 4 + index * (sensor_width + gap)
            right = width - 5 if index == 2 else left + sensor_width
            draw.rounded_rectangle((left, sensor_y, right, sensor_bottom), radius=6, fill=card, outline=border)
            draw.text((left + 5, sensor_y + 4), label, fill=muted, font=tiny_font)
            draw.text((left + 5, sensor_y + 16), value, fill=text, font=value_font)
            if index == 2 and snapshot.sensor.pressure is not None:
                draw.text((right - 17, sensor_y + 26), "hPa", fill=muted, font=tiny_font)

        dot_color = good if snapshot.network.connected else warning
        draw.ellipse((6, 108, 11, 113), fill=dot_color)
        if snapshot.network.access_point:
            network_label = "REDE CRYSENSE"
        elif snapshot.network.connected:
            network_label = snapshot.network.ssid or "WIFI CONECTADO"
        else:
            network_label = "SEM WIFI"
        draw.text((14, 105), self._fit_text(draw, network_label, tiny_font, width - 61), fill=text, font=tiny_font)
        ip_label = snapshot.network.ip_address or "IP indisponivel"
        draw.text((6, 116), self._fit_text(draw, ip_label, tiny_font, width - 53), fill=muted, font=tiny_font)
        camera_color = good if snapshot.camera_running else (170, 188, 196)
        draw.ellipse((width - 45, 108, width - 40, 113), fill=camera_color)
        draw.text((width - 37, 105), "CAM", fill=text, font=tiny_font)
        return image

    def render_alert(
        self,
        title: str,
        detail: str,
        color: tuple[int, int, int],
        image_size: tuple[int, int] | None = None,
        *,
        crying_baby: bool = False,
        animation_frame: int = 0,
    ) -> Any:
        from PIL import Image, ImageDraw

        width, height = image_size or self._image_size()
        image = Image.new("RGB", (width, height), (249, 252, 253))
        draw = ImageDraw.Draw(image)
        header_font = self._font(11, bold=True)
        title_font = self._font(19, bold=True)
        detail_font = self._font(10)
        small_font = self._font(8, bold=True)
        draw.rectangle((0, 0, width, 21), fill=color)
        draw.text((7, 3), "CrySense", fill="white", font=header_font)
        draw.text((width - 46, 5), "ALERTA", fill="white", font=small_font)
        draw.rounded_rectangle((7, 29, width - 8, height - 10), radius=10, fill="white", outline=color, width=2)
        text_width = width - 84 if crying_baby else width - 28
        fitted_title = self._fit_text(draw, title.upper(), title_font, text_width)
        draw.text((14, 37), fitted_title, fill=color, font=title_font)
        lines = self._wrapped_lines(draw, detail, detail_font, text_width, max_lines=3)
        draw.multiline_text((14, 66), "\n".join(lines), fill=(45, 65, 75), font=detail_font, spacing=3)
        if crying_baby:
            self._draw_crying_baby(
                draw,
                (width - 58, 34, width - 15, 77),
                animation_frame=animation_frame,
            )
        draw.text((14, height - 25), "VERIFIQUE O BEBE", fill=color, font=small_font)
        return image

    def _present(self, image: Any, frame_key: object) -> None:
        if self.display is None or frame_key == self._last_frame_key:
            return
        try:
            with self._lock:
                self.display.image(image)
                self._last_frame_key = frame_key
        except Exception as exc:
            self.error = str(exc)

    def show_dashboard(self, snapshot: DisplaySnapshot) -> None:
        if self.display is None:
            return
        image = self.render_dashboard(snapshot)
        self._present(image, ("dashboard", snapshot))

    def show(
        self,
        title: str,
        detail: str,
        color: tuple[int, int, int] = (30, 90, 180),
        *,
        crying_baby: bool = False,
        animation_frame: int = 0,
    ) -> None:
        if self.display is None:
            return
        try:
            frame = animation_frame % 2 if crying_baby else 0
            image = self.render_alert(
                title,
                detail,
                color,
                crying_baby=crying_baby,
                animation_frame=frame,
            )
            self._present(image, ("alert", title, detail, color, crying_baby, frame))
        except Exception as exc:
            self.error = str(exc)


def reading_dict(reading: SensorReading) -> dict:
    return asdict(reading)
