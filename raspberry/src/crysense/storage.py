from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from .pipeline import CryEvent


class Storage:
    def __init__(self, database_path: Path) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(database_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.connection:
            self.connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    label TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    trigger_confidence REAL NOT NULL,
                    scores_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sensor_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    temperature REAL,
                    humidity REAL,
                    pressure REAL
                );
                CREATE TABLE IF NOT EXISTS vision_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    label TEXT NOT NULL,
                    confidence REAL,
                    detail TEXT
                );
                CREATE TABLE IF NOT EXISTS vision_configuration (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    risk_zone_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def close(self) -> None:
        self.connection.close()

    def add_event(self, event: CryEvent) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT INTO events(timestamp, label, confidence, trigger_confidence, scores_json) VALUES (?, ?, ?, ?, ?)",
                (event.timestamp, event.label, event.confidence, event.trigger_confidence, json.dumps(event.scores)),
            )

    def recent_events(self, limit: int = 50) -> list[dict]:
        limit = max(1, min(int(limit), 200))
        with self.lock:
            rows = self.connection.execute(
                "SELECT timestamp, label, confidence, trigger_confidence, scores_json FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {
                "timestamp": row["timestamp"],
                "label": row["label"],
                "confidence": row["confidence"],
                "trigger_confidence": row["trigger_confidence"],
                "scores": json.loads(row["scores_json"]),
            }
            for row in rows
        ]

    def add_sensor_sample(self, timestamp: str, temperature: float | None, humidity: float | None, pressure: float | None) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT INTO sensor_samples(timestamp, temperature, humidity, pressure) VALUES (?, ?, ?, ?)",
                (timestamp, temperature, humidity, pressure),
            )

    def add_vision_event(self, timestamp: str, label: str, confidence: float | None, detail: str | None) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT INTO vision_events(timestamp, label, confidence, detail) VALUES (?, ?, ?, ?)",
                (timestamp, label, confidence, detail),
            )

    def recent_vision_events(self, limit: int = 50) -> list[dict]:
        limit = max(1, min(int(limit), 200))
        with self.lock:
            rows = self.connection.execute(
                "SELECT timestamp, label, confidence, detail FROM vision_events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {
                "timestamp": row["timestamp"],
                "label": row["label"],
                "confidence": row["confidence"],
                "detail": row["detail"],
            }
            for row in rows
        ]

    def vision_risk_zone(self) -> tuple[float, float, float, float] | None:
        with self.lock:
            row = self.connection.execute(
                "SELECT risk_zone_json FROM vision_configuration WHERE id = 1"
            ).fetchone()
        if row is None:
            return None
        try:
            values = tuple(float(value) for value in json.loads(row["risk_zone_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        return values if len(values) == 4 else None

    def set_vision_risk_zone(self, zone: tuple[float, float, float, float], updated_at: str) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO vision_configuration(id, risk_zone_json, updated_at)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET risk_zone_json = excluded.risk_zone_json, updated_at = excluded.updated_at
                """,
                (json.dumps(zone), updated_at),
            )

    def clear_vision_risk_zone(self) -> None:
        with self.lock, self.connection:
            self.connection.execute("DELETE FROM vision_configuration WHERE id = 1")
