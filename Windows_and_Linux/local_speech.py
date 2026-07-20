"""Offline Kokoro text-to-speech support for Writing Tools."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import sys
import threading
import time
import urllib.request
import wave
from pathlib import Path
from typing import Callable, Optional

from speech_metrics import SpeechMetricsRecorder


StatusCallback = Optional[Callable[[str], None]]
ErrorCallback = Optional[Callable[[str], None]]


class LocalSpeechService:
    """Lazily synthesize English with Sarah and Persian with Amir."""

    MODEL_NAME = "kokoro-v1.0.int8.onnx"
    VOICES_NAME = "voices-v1.0.bin"
    MODEL_URL = (
        "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
        "model-files-v1.0/kokoro-v1.0.int8.onnx"
    )
    VOICES_URL = (
        "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
        "model-files-v1.0/voices-v1.0.bin"
    )
    MODEL_SHA256 = "6e742170d309016e5891a994e1ce1559c702a2ccd0075e67ef7157974f6406cb"
    VOICES_SHA256 = "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d"
    PERSIAN_MODEL_NAME = "fa_IR-amir-medium.onnx"
    PERSIAN_CONFIG_NAME = "fa_IR-amir-medium.onnx.json"
    PERSIAN_MODEL_URL = (
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
        "fa/fa_IR/amir/medium/fa_IR-amir-medium.onnx"
    )
    PERSIAN_CONFIG_URL = PERSIAN_MODEL_URL + ".json"
    PERSIAN_MODEL_SHA256 = "fb815380d969ea372b0b21b0de14421f58fe481047e153e69685d079b6e1a9d1"
    PERSIAN_CONFIG_SHA256 = "75f918a3bf0f57a9179abe725af529f2a5c79d6c899e2a84aec76c685d5dfb9a"

    def __init__(self) -> None:
        local_app_data = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
        self.data_dir = Path(local_app_data) / "Writing Tools" / "kokoro"
        self.audio_path = self.data_dir / "read-aloud.wav"
        self._kokoro_engine = None
        self._piper_engine = None
        self._engine_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._request_id = 0
        self._english_files_verified = False
        self._persian_files_verified = False
        self.metrics = SpeechMetricsRecorder()

    @property
    def model_path(self) -> Path:
        return self.data_dir / self.MODEL_NAME

    @property
    def voices_path(self) -> Path:
        return self.data_dir / self.VOICES_NAME

    @property
    def persian_model_path(self) -> Path:
        return self.data_dir / self.PERSIAN_MODEL_NAME

    @property
    def persian_config_path(self) -> Path:
        return self.data_dir / self.PERSIAN_CONFIG_NAME

    def speak(
        self,
        text: str,
        status_callback: StatusCallback = None,
        error_callback: ErrorCallback = None,
        metrics_context: Optional[dict] = None,
    ) -> None:
        """Generate and asynchronously play ``text``; newest request wins."""
        request_id = self._begin_request()
        started = time.perf_counter()
        record = self.metrics.new_record(text, metrics_context)
        record.update({
            "english_engine_warm": self._kokoro_engine is not None,
            "persian_engine_warm": self._piper_engine is not None,
            "english_files_verified": self._english_files_verified,
            "persian_files_verified": self._persian_files_verified,
        })
        outcome = "canceled"
        try:
            if not sys.platform.startswith("win"):
                raise RuntimeError("Local Read Aloud is currently available on Windows only.")

            # Emit before waiting for the engine lock. If background warm-up
            # is still finishing, the user immediately sees useful feedback.
            self._notify(status_callback, "Preparing local voice...")
            queue_started = time.perf_counter()
            with self._engine_lock:
                record["engine_queue_ms"] = self._elapsed_ms(queue_started)
                if not self._is_current(request_id):
                    return
                detection_started = time.perf_counter()
                use_persian = self._is_predominantly_persian(text)
                record["language_detection_ms"] = self._elapsed_ms(detection_started)
                record["language"] = "fa" if use_persian else "en"
                files_started = time.perf_counter()
                if use_persian:
                    self._ensure_persian_files(status_callback)
                    record["file_check_ms"] = self._elapsed_ms(files_started)
                    if not self._is_current(request_id):
                        return
                    engine_started = time.perf_counter()
                    self._ensure_piper_engine(status_callback)
                    record["engine_prepare_ms"] = self._elapsed_ms(engine_started)
                    if not self._is_current(request_id):
                        return
                    self._notify(status_callback, "Preparing Amir's Persian voice…")
                    voice_name = "Amir"
                else:
                    self._ensure_english_files(status_callback)
                    record["file_check_ms"] = self._elapsed_ms(files_started)
                    if not self._is_current(request_id):
                        return
                    engine_started = time.perf_counter()
                    self._ensure_kokoro_engine(status_callback)
                    record["engine_prepare_ms"] = self._elapsed_ms(engine_started)
                    if not self._is_current(request_id):
                        return
                    self._notify(status_callback, "Preparing Sarah's English voice…")
                    voice_name = "Sarah"
                record["voice"] = voice_name
                if not self._is_current(request_id):
                    return

                import winsound

                chunks = self._chunk_text(text)
                record["chunk_count"] = len(chunks)
                record["chunk_characters"] = [len(chunk) for chunk in chunks]
                synthesis_total_ms = 0.0
                audio_total_seconds = 0.0
                playback_started = None
                previous_deadline = None

                for index, chunk in enumerate(chunks):
                    if not self._is_current(request_id):
                        return

                    chunk_path = self.data_dir / f"read-aloud-{index % 2}.wav"
                    self._notify(
                        status_callback,
                        f"Preparing part {index + 1} of {len(chunks)} with {voice_name}...",
                    )
                    synthesis_started = time.perf_counter()
                    if use_persian:
                        self._synthesize_persian(chunk, chunk_path)
                    else:
                        samples, sample_rate = self._kokoro_engine.create(
                            chunk,
                            voice="af_sarah",
                            speed=1.0,
                            lang="en-us",
                        )
                        self._write_wave(samples, sample_rate, chunk_path)
                    chunk_synthesis_ms = self._elapsed_ms(synthesis_started)
                    synthesis_total_ms += chunk_synthesis_ms

                    # Synthesize the next part while the current part is playing,
                    # then wait only for any playback time that remains.
                    if previous_deadline is not None:
                        while self._is_current(request_id) and time.monotonic() < previous_deadline:
                            time.sleep(0.05)
                        if not self._is_current(request_id):
                            return

                    audio_seconds = self._audio_duration(chunk_path)
                    audio_total_seconds += audio_seconds
                    winsound.PlaySound(
                        str(chunk_path),
                        winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
                    )
                    if index == 0:
                        record["first_chunk_synthesis_ms"] = chunk_synthesis_ms
                        record["time_to_audio_ms"] = self._elapsed_ms(started)
                        playback_started = time.perf_counter()
                    self._notify(
                        status_callback,
                        f"Reading part {index + 1} of {len(chunks)} with {voice_name}.",
                    )
                    previous_deadline = time.monotonic() + audio_seconds

                record["synthesis_ms"] = round(synthesis_total_ms, 2)
                record["audio_seconds"] = round(audio_total_seconds, 3)
                if previous_deadline is not None:
                    while self._is_current(request_id) and time.monotonic() < previous_deadline + 0.15:
                        time.sleep(0.05)
                if self._is_current(request_id):
                    if playback_started is not None:
                        record["playback_ms"] = self._elapsed_ms(playback_started)
                    outcome = "completed"
                    self._notify(status_callback, "Read Aloud finished.")
        except Exception as exc:
            outcome = "error"
            record["error_type"] = type(exc).__name__
            logging.error("Local Read Aloud failed: %s", exc, exc_info=True)
            if self._is_current(request_id) and error_callback:
                error_callback(str(exc))
        finally:
            record["outcome"] = outcome
            record["total_ms"] = self._elapsed_ms(started)
            self.metrics.append(record)

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return round((time.perf_counter() - started) * 1000, 2)

    def warm_up_english(self) -> None:
        """Load cached Sarah resources in the background without downloading."""
        if not sys.platform.startswith("win"):
            return
        if not self.model_path.exists() or not self.voices_path.exists():
            return

        try:
            with self._engine_lock:
                if not self._english_files_verified:
                    if (
                        self._sha256(self.model_path) != self.MODEL_SHA256
                        or self._sha256(self.voices_path) != self.VOICES_SHA256
                    ):
                        logging.warning("Skipping Sarah warm-up because cached files failed verification")
                        return
                    self._english_files_verified = True
                self._ensure_kokoro_engine(None)
                logging.info("Read Aloud: Sarah's local voice is warmed and ready")
        except Exception:
            # Warm-up is opportunistic. A normal button click still reports a
            # user-visible error and can repair/download files if necessary.
            logging.warning("Read Aloud background warm-up failed", exc_info=True)

    def stop(self) -> None:
        """Cancel pending output and stop Windows WAV playback."""
        with self._state_lock:
            self._request_id += 1
        if sys.platform.startswith("win"):
            try:
                import winsound

                winsound.PlaySound(None, 0)
            except Exception:
                logging.debug("No active Read Aloud playback to stop", exc_info=True)

    def _begin_request(self) -> int:
        self.stop()
        with self._state_lock:
            self._request_id += 1
            return self._request_id

    def _is_current(self, request_id: int) -> bool:
        with self._state_lock:
            return request_id == self._request_id

    def _ensure_english_files(self, status_callback: StatusCallback) -> None:
        if self._english_files_verified:
            return
        self.data_dir.mkdir(parents=True, exist_ok=True)
        downloads = (
            (self.model_path, self.MODEL_URL, self.MODEL_SHA256, "voice model (92 MB)"),
            (self.voices_path, self.VOICES_URL, self.VOICES_SHA256, "voice data (28 MB)"),
        )
        for path, url, expected_hash, label in downloads:
            if path.exists() and self._sha256(path) == expected_hash:
                continue
            self._notify(status_callback, f"Downloading Kokoro {label}; this happens only once…")
            partial_path = path.with_suffix(path.suffix + ".part")
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "WritingTools/ReadAloud"})
                with urllib.request.urlopen(request, timeout=60) as response, partial_path.open("wb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                if self._sha256(partial_path) != expected_hash:
                    raise RuntimeError(f"The downloaded Kokoro {label} failed its integrity check.")
                os.replace(partial_path, path)
            finally:
                if partial_path.exists():
                    partial_path.unlink()
        self._english_files_verified = True

    def _ensure_persian_files(self, status_callback: StatusCallback) -> None:
        if self._persian_files_verified:
            return
        self.data_dir.mkdir(parents=True, exist_ok=True)
        downloads = (
            (
                self.persian_model_path,
                self.PERSIAN_MODEL_URL,
                self.PERSIAN_MODEL_SHA256,
                "Amir Persian voice model (64 MB)",
            ),
            (
                self.persian_config_path,
                self.PERSIAN_CONFIG_URL,
                self.PERSIAN_CONFIG_SHA256,
                "Amir Persian voice configuration",
            ),
        )
        for path, url, expected_hash, label in downloads:
            if path.exists() and self._sha256(path) == expected_hash:
                continue
            self._notify(status_callback, f"Downloading {label}; this happens only once…")
            partial_path = path.with_suffix(path.suffix + ".part")
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "WritingTools/ReadAloud"})
                with urllib.request.urlopen(request, timeout=60) as response, partial_path.open("wb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                if self._sha256(partial_path) != expected_hash:
                    raise RuntimeError(f"The downloaded {label} failed its integrity check.")
                os.replace(partial_path, path)
            finally:
                if partial_path.exists():
                    partial_path.unlink()
        self._persian_files_verified = True

    def _ensure_kokoro_engine(self, status_callback: StatusCallback) -> None:
        if self._kokoro_engine is not None:
            return
        self._notify(status_callback, "Loading Sarah's local voice for the first time…")
        try:
            from kokoro_onnx import Kokoro
        except ImportError as exc:
            raise RuntimeError(
                "The local speech component is missing. Reinstall Writing Tools or run "
                "'pip install kokoro-onnx==0.5.0'."
            ) from exc
        self._kokoro_engine = Kokoro(str(self.model_path), str(self.voices_path))

    def _ensure_piper_engine(self, status_callback: StatusCallback) -> None:
        if self._piper_engine is not None:
            return
        self._notify(status_callback, "Loading Amir's local Persian voice for the first time…")
        try:
            from piper import PiperVoice
        except ImportError as exc:
            raise RuntimeError(
                "The Persian speech component is missing. Reinstall Writing Tools or run "
                "'pip install piper-tts==1.5.0'."
            ) from exc
        self._piper_engine = PiperVoice.load(
            self.persian_model_path,
            config_path=self.persian_config_path,
        )

    def _synthesize_persian(self, text: str, output_path: Optional[Path] = None) -> None:
        with wave.open(str(output_path or self.audio_path), "wb") as wav_file:
            self._piper_engine.synthesize_wav(text, wav_file)

    @staticmethod
    def _chunk_text(text: str, target_chars: int = 140, max_chars: int = 200) -> list[str]:
        """Split on sentence/word boundaries for faster first audio."""
        cleaned = " ".join(text.split())
        if not cleaned:
            return []

        sentences = re.split(r"(?<=[.!?\u061f\u061b])\s+", cleaned)
        pieces = []
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

        chunks = []
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

    @staticmethod
    def _is_predominantly_persian(text: str) -> bool:
        """Route Arabic-script selections to Amir when they dominate Latin text."""
        persian_count = sum(
            "\u0600" <= char <= "\u06ff"
            or "\u0750" <= char <= "\u077f"
            or "\ufb50" <= char <= "\ufdff"
            or "\ufe70" <= char <= "\ufeff"
            for char in text
        )
        latin_count = sum(
            ("A" <= char <= "Z") or ("a" <= char <= "z")
            for char in text
        )
        return persian_count > latin_count

    def _write_wave(
        self,
        samples,
        sample_rate: int,
        output_path: Optional[Path] = None,
    ) -> None:
        import numpy as np

        pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
        with wave.open(str(output_path or self.audio_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm.tobytes())

    def _audio_duration(self, audio_path: Optional[Path] = None) -> float:
        with wave.open(str(audio_path or self.audio_path), "rb") as wav_file:
            frame_rate = wav_file.getframerate()
            if not frame_rate:
                return 0.0
            return wav_file.getnframes() / frame_rate

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _notify(callback: StatusCallback, message: str) -> None:
        logging.info("Read Aloud: %s", message)
        if callback:
            callback(message)
