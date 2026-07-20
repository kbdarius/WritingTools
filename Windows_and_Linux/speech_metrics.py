"""Small, local-only performance records for Read Aloud estimation."""

from __future__ import annotations

import json
import os
import platform
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from version import APP_VERSION


class SpeechMetricsRecorder:
    """Append privacy-preserving JSONL records with bounded retention."""

    MAX_RECORDS = 500
    COMPACT_AFTER_BYTES = 512 * 1024

    def __init__(self) -> None:
        local_app_data = os.environ.get("LOCALAPPDATA") or str(Path.home())
        self.path = Path(local_app_data) / "Writing Tools" / "read-aloud-metrics.jsonl"
        self.csv_path = Path(local_app_data) / "Writing Tools" / "read-aloud-metrics.csv"
        self._lock = threading.Lock()

    @staticmethod
    def describe_text(text: str) -> dict:
        """Return useful shape data without retaining any selected content."""
        return {
            "characters": len(text),
            "words": len(re.findall(r"\b\w+\b", text, flags=re.UNICODE)),
            "lines": text.count("\n") + 1,
            "digits": sum(char.isdigit() for char in text),
            "symbols": sum(
                not char.isalnum() and not char.isspace()
                for char in text
            ),
            "latin_letters": sum(
                ("A" <= char <= "Z") or ("a" <= char <= "z")
                for char in text
            ),
            "arabic_script": sum(
                "\u0600" <= char <= "\u06ff"
                or "\u0750" <= char <= "\u077f"
                or "\ufb50" <= char <= "\ufdff"
                or "\ufe70" <= char <= "\ufeff"
                for char in text
            ),
        }

    def new_record(self, text: str, context: dict | None = None) -> dict:
        now_utc = datetime.now(timezone.utc)
        record = {
            "schema": 1,
            "timestamp_utc": now_utc.isoformat(),
            "collection_date_utc": now_utc.date().isoformat(),
            "collection_datetime_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S"),
            "collection_date": now_utc.astimezone().date().isoformat(),
            "collection_datetime": now_utc.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
            "app_version": APP_VERSION,
            "cpu_threads": os.cpu_count(),
            "architecture": platform.machine(),
            **self.describe_text(text),
        }
        if context:
            record.update(context)
        return record

    def append(self, record: dict) -> None:
        """Write one record and compact old entries when the file is large."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            encoded = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
            with self._lock:
                with self.path.open("a", encoding="utf-8") as output:
                    output.write(encoded + "\n")
                if self.path.stat().st_size > self.COMPACT_AFTER_BYTES:
                    lines = self.path.read_text(encoding="utf-8").splitlines()
                    retained = lines[-self.MAX_RECORDS :]
                    self.path.write_text(
                        "\n".join(retained) + ("\n" if retained else ""),
                        encoding="utf-8",
                    )
                self._append_csv(record)
        except Exception:
            # Metrics must never break or delay Read Aloud.
            return

    def _append_csv(self, record: dict) -> None:
        if not record:
            return

        # Keep a simple table-friendly view for manual review.
        # Header is written once, then rows are appended.
        existing = self.csv_path.exists()
        header_fields = sorted(record.keys())
        with self.csv_path.open("a", encoding="utf-8", newline="") as output:
            if not existing:
                output.write(",".join(header_fields) + "\n")
            output.write(
                ",".join(self._csv_escape(str(record.get(name, ""))) for name in header_fields)
                + "\n"
            )

    @staticmethod
    def _csv_escape(value: str) -> str:
        if "," in value or "\n" in value or "\"" in value:
            escaped = value.replace('"', '""')
            return f'"{escaped}"'
        return value
