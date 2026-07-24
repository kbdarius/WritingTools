"""Azure Speech text-to-speech support for Writing Tools."""

from __future__ import annotations

import html
import logging
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Callable, Optional

from speech_metrics import SpeechMetricsRecorder


StatusCallback = Optional[Callable[[str], None]]
ErrorCallback = Optional[Callable[[str], None]]


class AzureSpeechService:
    """Synthesize speech through the Azure Speech REST endpoint."""

    OUTPUT_FORMAT = "riff-24khz-16bit-mono-pcm"
    DEFAULT_REGION = "eastus"
    ENGLISH_VOICE = "en-US-JennyNeural"
    PERSIAN_VOICE = "fa-IR-DilaraNeural"

    def __init__(self, config: dict) -> None:
        self.config = config
        local_app_data = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
        self.audio_dir = Path(local_app_data) / "Writing Tools" / "azure-speech"
        self._state_lock = threading.Lock()
        self._request_id = 0
        self.metrics = SpeechMetricsRecorder()

    def speak(
        self,
        text: str,
        status_callback: StatusCallback = None,
        error_callback: ErrorCallback = None,
        metrics_context: Optional[dict] = None,
    ) -> None:
        request_id = self._begin_request()
        started = time.perf_counter()
        record = self.metrics.new_record(text, metrics_context)
        outcome = "canceled"
        try:
            if not sys.platform.startswith("win"):
                raise RuntimeError("Azure Read Aloud is currently available on Windows only.")

            key, region = self._credentials()
            if not key:
                raise RuntimeError(
                    "Azure Speech is not configured. Add the Speech resource key in Settings > General."
                )
            if not region:
                raise RuntimeError(
                    "Azure Speech is not configured. Add the Speech resource region in Settings > General."
                )

            import winsound

            chunks = self._chunk_text(text)
            record["provider"] = "azure"
            record["chunk_count"] = len(chunks)
            record["voice"] = self._voice_for(text)
            playback_started = None
            total_synthesis_ms = 0.0
            total_audio_seconds = 0.0

            self._notify(status_callback, "Connecting to Azure Speech...")
            for index, chunk in enumerate(chunks):
                if not self._is_current(request_id):
                    return
                self._notify(status_callback, f"Preparing part {index + 1} of {len(chunks)}...")
                synthesis_started = time.perf_counter()
                audio_path = self.audio_dir / f"read-aloud-{index % 2}.wav"
                self._synthesize(chunk, key, region, audio_path, self._voice_for(text))
                chunk_synthesis_ms = self._elapsed_ms(synthesis_started)
                total_synthesis_ms += chunk_synthesis_ms

                if not self._is_current(request_id):
                    return
                audio_seconds = self._audio_duration(audio_path)
                total_audio_seconds += audio_seconds
                winsound.PlaySound(
                    str(audio_path),
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
                )
                if playback_started is None:
                    playback_started = time.perf_counter()
                    record["first_chunk_synthesis_ms"] = chunk_synthesis_ms
                    record["time_to_audio_ms"] = self._elapsed_ms(started)
                self._notify(status_callback, f"Reading part {index + 1} of {len(chunks)}...")
                deadline = time.monotonic() + audio_seconds
                while self._is_current(request_id) and time.monotonic() < deadline:
                    time.sleep(0.05)

            if self._is_current(request_id):
                record["synthesis_ms"] = round(total_synthesis_ms, 2)
                record["audio_seconds"] = round(total_audio_seconds, 3)
                record["outcome"] = "completed"
                outcome = "completed"
                self._notify(status_callback, "Read Aloud finished.")
        except Exception as exc:
            outcome = "error"
            record["error_type"] = type(exc).__name__
            logging.error("Azure Read Aloud failed: %s", exc, exc_info=True)
            if self._is_current(request_id) and error_callback:
                error_callback(str(exc))
        finally:
            record["outcome"] = outcome
            record["total_ms"] = self._elapsed_ms(started)
            self.metrics.append(record)

    def stop(self) -> None:
        with self._state_lock:
            self._request_id += 1
        if sys.platform.startswith("win"):
            try:
                import winsound

                winsound.PlaySound(None, 0)
            except Exception:
                logging.debug("No active Azure Read Aloud playback", exc_info=True)

    def test_connection(self, key: str, region: str) -> None:
        """Synthesize and play a short sample, raising on any connection error."""
        if not sys.platform.startswith("win"):
            raise RuntimeError("Azure Read Aloud is currently available on Windows only.")
        key = key.strip()
        region = region.strip() or self.DEFAULT_REGION
        if not key:
            raise RuntimeError("Enter an Azure Speech resource key first.")

        import winsound

        output_path = self.audio_dir / "connection-test.wav"
        self._synthesize(
            "Azure Speech is connected and working.",
            key,
            region,
            output_path,
            self.ENGLISH_VOICE,
        )
        winsound.PlaySound(
            str(output_path),
            # Playback is synchronous when SND_ASYNC is omitted. Python 3.11
            # does not expose a separate SND_SYNC constant.
            winsound.SND_FILENAME | winsound.SND_NODEFAULT,
        )

    def _credentials(self) -> tuple[str, str]:
        settings = self.config.get("azure_speech", {})
        key = settings.get("key", "") or os.environ.get("AZURE_SPEECH_KEY", "")
        region = settings.get("region", "") or os.environ.get("AZURE_SPEECH_REGION", "")
        return key.strip(), (region.strip() or self.DEFAULT_REGION)

    def _synthesize(self, text: str, key: str, region: str, output_path: Path, voice: str) -> None:
        ssml = (
            '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            'xml:lang="en-US">'
            f'<voice name="{html.escape(voice)}">{html.escape(text)}</voice>'
            "</speak>"
        ).encode("utf-8")
        request = urllib.request.Request(
            f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
            data=ssml,
            headers={
                "Accept": "audio/wav",
                "Content-Type": "application/ssml+xml",
                "Ocp-Apim-Subscription-Key": key,
                "X-Microsoft-OutputFormat": self.OUTPUT_FORMAT,
                "User-Agent": "WritingTools/AzureReadAloud",
            },
            method="POST",
        )
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                output_path.write_bytes(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Azure Speech request failed ({exc.code}): {detail or exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Could not reach Azure Speech: {exc.reason}") from exc

    @classmethod
    def _voice_for(cls, text: str) -> str:
        persian = sum("\u0600" <= char <= "\u06ff" for char in text)
        latin = sum(char.isascii() and char.isalpha() for char in text)
        return cls.PERSIAN_VOICE if persian > latin else cls.ENGLISH_VOICE

    @staticmethod
    def _chunk_text(text: str, target_chars: int = 240, max_chars: int = 500) -> list[str]:
        cleaned = " ".join(text.split())
        if not cleaned:
            return []
        sentences = re.split(r"(?<=[.!?\u061f\u061b])\s+", cleaned)
        pieces: list[str] = []
        for sentence in sentences:
            remaining = sentence.strip()
            while len(remaining) > max_chars:
                split_at = remaining.rfind(" ", 0, max_chars + 1)
                if split_at < target_chars // 2:
                    split_at = max_chars
                pieces.append(remaining[:split_at].strip())
                remaining = remaining[split_at:].strip()
            if remaining:
                pieces.append(remaining)
        chunks: list[str] = []
        current = ""
        for piece in pieces:
            candidate = f"{current} {piece}".strip()
            if current and len(candidate) > target_chars:
                chunks.append(current)
                current = piece
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks

    def _begin_request(self) -> int:
        self.stop()
        with self._state_lock:
            self._request_id += 1
            return self._request_id

    def _is_current(self, request_id: int) -> bool:
        with self._state_lock:
            return request_id == self._request_id

    def _audio_duration(self, audio_path: Path) -> float:
        with wave.open(str(audio_path), "rb") as wav_file:
            frame_rate = wav_file.getframerate()
            return wav_file.getnframes() / frame_rate if frame_rate else 0.0

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return round((time.perf_counter() - started) * 1000, 2)

    @staticmethod
    def _notify(callback: StatusCallback, message: str) -> None:
        logging.info("Azure Read Aloud: %s", message)
        if callback:
            callback(message)
