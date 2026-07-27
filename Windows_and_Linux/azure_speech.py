"""Azure Speech text-to-speech support for Writing Tools."""

from __future__ import annotations

import html
import ctypes
import logging
import os
import queue
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


class _WindowsMciWavePlayer:
    """Small Windows WAV player with pause and seek support."""

    def __init__(self) -> None:
        self.alias = f"writingtoolsazure{os.getpid()}"
        self._lock = threading.RLock()
        self._open = False
        self._paused = False
        self._owner_thread_id: Optional[int] = None
        self._control_requests: queue.Queue[dict] = queue.Queue()

    def _command(self, command: str, result_size: int = 0) -> str:
        buffer = ctypes.create_unicode_buffer(result_size) if result_size else None
        error = ctypes.windll.winmm.mciSendStringW(
            command, buffer, result_size, None
        )
        if error:
            message = ctypes.create_unicode_buffer(256)
            ctypes.windll.winmm.mciGetErrorStringW(error, message, len(message))
            raise RuntimeError(f"Windows audio control failed: {message.value or error}")
        return buffer.value if buffer is not None else ""

    def play(self, audio_path: Path) -> None:
        with self._lock:
            self.stop()
            # MCI string aliases belong to the thread that opens them. All
            # later playback commands must be executed by this same thread.
            self._owner_thread_id = threading.get_ident()
            # Also close any stale alias left by an interrupted prior process.
            try:
                self._command(f"close {self.alias}")
            except Exception:
                pass
            self._command(f'open "{audio_path}" type waveaudio alias {self.alias}')
            self._open = True
            self._command(f"set {self.alias} time format milliseconds")
            self._command(f"play {self.alias}")
            self._paused = False

    def stop(self) -> None:
        with self._lock:
            is_owner = self._owner_thread_id in (None, threading.get_ident())
            if is_owner:
                # Issue cleanup commands even when our flag is stale. MCI
                # keeps playback in the system mixer independently of this
                # object's state, so skipping cleanup can leave audio running.
                for command in (
                    f"stop {self.alias}",
                    f"reset {self.alias}",
                    f"close {self.alias}",
                ):
                    try:
                        self._command(command)
                    except Exception:
                        logging.debug(
                            "Azure MCI cleanup command failed: %s",
                            command,
                            exc_info=True,
                        )
            self._open = False
            self._paused = False
            if is_owner:
                self._owner_thread_id = None
                self._finish_pending_controls_locked()

    def toggle_pause(self) -> bool:
        with self._lock:
            if not self._open:
                return False
            if self._owner_thread_id == threading.get_ident():
                return self._toggle_pause_locked()
        return bool(self._submit_control("toggle_pause", default=False))

    def seek_relative(self, milliseconds: int) -> None:
        with self._lock:
            if not self._open:
                return
            if self._owner_thread_id == threading.get_ident():
                self._seek_relative_locked(milliseconds)
                return
        self._submit_control("seek_relative", milliseconds, default=None)

    def is_finished(self) -> bool:
        with self._lock:
            self._process_control_requests_locked()
            if not self._open:
                return True
            return self._command(f"status {self.alias} mode", 64).lower() == "stopped"

    def _toggle_pause_locked(self) -> bool:
        mode = self._command(f"status {self.alias} mode", 64).lower()
        if mode == "paused" or self._paused:
            self._command(f"play {self.alias}")
            self._paused = False
            logging.info("Azure Read Aloud resumed")
        elif mode == "playing":
            self._command(f"pause {self.alias}")
            self._paused = True
            logging.info("Azure Read Aloud paused")
        return self._paused

    def _seek_relative_locked(self, milliseconds: int) -> None:
        position = int(self._command(f"status {self.alias} position", 64))
        length = int(self._command(f"status {self.alias} length", 64))
        target = max(0, min(length, position + milliseconds))
        self._command(f"seek {self.alias} to {target}")
        # MCI changes the device mode to "stopped" after seek. Restart from
        # the new position, then restore paused state when the user sought
        # while paused so the playback loop does not mistake it for EOF.
        self._command(f"play {self.alias}")
        if self._paused:
            self._command(f"pause {self.alias}")
        logging.info(
            "Azure Read Aloud seeked from %d ms to %d ms", position, target
        )

    def _submit_control(self, action: str, value=None, default=None):
        """Run a control on the MCI owner thread and return its result."""
        request = {
            "action": action,
            "value": value,
            "event": threading.Event(),
            "result": default,
            "error": None,
        }
        self._control_requests.put(request)
        if not request["event"].wait(timeout=1.0):
            logging.error("Timed out waiting for Azure playback control: %s", action)
            return default
        if request["error"] is not None:
            raise request["error"]
        return request["result"]

    def _process_control_requests_locked(self) -> None:
        """Execute button requests on the thread that opened the MCI alias."""
        while True:
            try:
                request = self._control_requests.get_nowait()
            except queue.Empty:
                return
            try:
                if not self._open:
                    request["result"] = False
                elif request["action"] == "toggle_pause":
                    request["result"] = self._toggle_pause_locked()
                elif request["action"] == "seek_relative":
                    self._seek_relative_locked(int(request["value"]))
            except Exception as exc:
                request["error"] = exc
            finally:
                request["event"].set()

    def _finish_pending_controls_locked(self) -> None:
        """Release any button handlers still waiting when playback closes."""
        while True:
            try:
                request = self._control_requests.get_nowait()
            except queue.Empty:
                return
            request["result"] = False
            request["event"].set()


class AzureSpeechService:
    """Synthesize speech through the Azure Speech REST endpoint."""

    # 24 kHz PCM needs about 48 KB/s and was badly delayed by filtered
    # corporate connections. 16 kHz retains clear speech while completing
    # more than ten times faster in measured tests on those connections.
    OUTPUT_FORMAT = "riff-16khz-16bit-mono-pcm"
    DEFAULT_REGION = "eastus"
    ENGLISH_VOICE = "en-US-JennyNeural"
    PERSIAN_VOICE = "fa-IR-DilaraNeural"
    ENGLISH_VOICES = (
        ("Ava", "en-US-AvaNeural"),
        ("Phoebe Multilingual", "en-US-PhoebeMultilingualNeural"),
        ("Phoebe Dragon HD", "en-US-Phoebe:DragonHDLatestNeural"),
        ("Ava Dragon HD", "en-US-Ava:DragonHDLatestNeural"),
        ("Emma Dragon HD", "en-US-Emma:DragonHDLatestNeural"),
        ("Andrew Dragon HD", "en-US-Andrew:DragonHDLatestNeural"),
        ("Jenny (original)", ENGLISH_VOICE),
    )
    SUPPORTED_RATES = (0.75, 1.0, 1.25, 1.5, 2.0)

    def __init__(self, config: dict) -> None:
        self.config = config
        local_app_data = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
        self.audio_dir = Path(local_app_data) / "Writing Tools" / "azure-speech"
        self._state_lock = threading.Lock()
        self._request_id = 0
        self._player = _WindowsMciWavePlayer() if sys.platform.startswith("win") else None
        self._navigation_lock = threading.Lock()
        self._active_request_id: Optional[int] = None
        self._sentences: list[str] = []
        self._sentence_index = 0
        self._requested_sentence: Optional[int] = None
        self._rate = self._normalize_rate(config.get("read_aloud_rate", 1.0))
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
        session_done = threading.Event()
        cache_lock = threading.Lock()
        audio_cache: dict[tuple[int, float], dict] = {}
        in_flight: dict[tuple[int, float], dict] = {}
        synthesis_measurements: list[dict] = []
        try:
            if not sys.platform.startswith("win"):
                raise RuntimeError("Azure Read Aloud is currently available on Windows only.")

            speech_key, region = self._credentials()
            if not speech_key:
                raise RuntimeError(
                    "Azure Speech is not configured. Add the Speech resource key in Settings > General."
                )
            if not region:
                raise RuntimeError(
                    "Azure Speech is not configured. Add the Speech resource region in Settings > General."
                )

            chunks = self._chunk_text(text)
            record["provider"] = "azure"
            record["chunk_count"] = len(chunks)
            record["voice"] = self._voice_for(text)
            record["sentence_count"] = len(chunks)
            playback_started = None
            total_audio_seconds = 0.0

            with self._navigation_lock:
                self._active_request_id = request_id
                self._sentences = chunks
                self._sentence_index = 0
                self._requested_sentence = None

            def ensure_audio(index: int, rate: float) -> Optional[dict]:
                """Synthesize once per sentence/rate and share prefetch results."""
                cache_key = (index, rate)
                with cache_lock:
                    cached = audio_cache.get(cache_key)
                    if cached is not None:
                        return cached
                    pending = in_flight.get(cache_key)
                    producer = pending is None
                    if producer:
                        pending = {
                            "event": threading.Event(),
                            "result": None,
                            "error": None,
                        }
                        in_flight[cache_key] = pending

                if producer:
                    rate_token = int(round(rate * 100))
                    audio_path = self.audio_dir / (
                        f"read-aloud-{os.getpid()}-{request_id}-{index}-{rate_token}.wav"
                    )
                    synthesis_started = time.perf_counter()
                    try:
                        request_metrics = self._synthesize(
                            chunks[index],
                            speech_key,
                            region,
                            audio_path,
                            self._voice_for(text),
                            rate=rate,
                        )
                        result = {
                            "path": audio_path,
                            "duration": self._audio_duration(audio_path),
                            "synthesis_ms": self._elapsed_ms(synthesis_started),
                            "request_metrics": request_metrics,
                        }
                        with cache_lock:
                            synthesis_measurements.append(result)
                            if session_done.is_set():
                                try:
                                    audio_path.unlink(missing_ok=True)
                                except OSError:
                                    logging.debug(
                                        "Could not remove canceled Azure prefetch audio",
                                        exc_info=True,
                                    )
                            else:
                                audio_cache[cache_key] = result
                            pending["result"] = result
                    except Exception as exc:
                        pending["error"] = exc
                    finally:
                        pending["event"].set()
                else:
                    while not pending["event"].wait(timeout=0.1):
                        if not self._is_current(request_id):
                            return None

                if pending["error"] is not None:
                    raise pending["error"]
                return pending["result"]

            def prefetch(index: int, rate: float) -> None:
                if index >= len(chunks):
                    return
                thread = threading.Thread(
                    target=ensure_audio,
                    args=(index, rate),
                    daemon=True,
                    name=f"WritingToolsAzurePrefetch{index}",
                )
                thread.start()

            self._notify(status_callback, "Connecting to Azure Speech...")
            index = 0
            while index < len(chunks):
                if not self._is_current(request_id):
                    return
                with self._navigation_lock:
                    self._sentence_index = index
                    rate = self._rate

                self._notify(
                    status_callback,
                    f"Preparing sentence {index + 1} of {len(chunks)}...",
                )
                audio = ensure_audio(index, rate)
                if audio is None:
                    return
                request_metrics = audio["request_metrics"]
                record["azure_headers_ms"] = request_metrics["headers_ms"]
                record["azure_download_ms"] = request_metrics["download_ms"]

                if not self._is_current(request_id):
                    return
                with self._navigation_lock:
                    requested = self._requested_sentence
                    current_rate = self._rate
                    if requested is not None:
                        self._requested_sentence = None
                if requested is not None or current_rate != rate:
                    index = requested if requested is not None else index
                    continue

                total_audio_seconds += audio["duration"]
                self._player.play(audio["path"])
                if playback_started is None:
                    playback_started = time.perf_counter()
                    record["first_chunk_synthesis_ms"] = audio["synthesis_ms"]
                    record["time_to_audio_ms"] = self._elapsed_ms(started)
                prefetch(index + 1, rate)
                self._notify(
                    status_callback,
                    f"Reading with Azure Speech (sentence {index + 1} of {len(chunks)})...",
                )
                while self._is_current(request_id) and not self._player.is_finished():
                    time.sleep(0.05)
                self._player.stop()

                with self._navigation_lock:
                    requested = self._requested_sentence
                    self._requested_sentence = None
                index = requested if requested is not None else index + 1

            if self._is_current(request_id):
                with cache_lock:
                    record["synthesis_ms"] = round(
                        sum(item["synthesis_ms"] for item in synthesis_measurements),
                        2,
                    )
                record["audio_seconds"] = round(total_audio_seconds, 3)
                record["read_aloud_rate"] = self.get_rate()
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
            session_done.set()
            if self._player is not None:
                self._player.stop()
            with self._navigation_lock:
                if self._active_request_id == request_id:
                    self._active_request_id = None
                    self._sentences = []
                    self._requested_sentence = None
            with cache_lock:
                cached_paths = [item["path"] for item in audio_cache.values()]
            for audio_path in cached_paths:
                try:
                    audio_path.unlink(missing_ok=True)
                except OSError:
                    logging.debug(
                        "Could not remove temporary Azure audio: %s",
                        audio_path,
                        exc_info=True,
                    )
            record["outcome"] = outcome
            record["total_ms"] = self._elapsed_ms(started)
            self.metrics.append(record)

    def stop(self) -> None:
        with self._state_lock:
            self._request_id += 1
        with self._navigation_lock:
            self._active_request_id = None
            self._sentences = []
            self._requested_sentence = None
        if self._player is not None:
            self._player.stop()
        if sys.platform.startswith("win"):
            try:
                import winsound

                winsound.PlaySound(None, 0)
            except Exception:
                logging.debug("No active Azure Read Aloud playback", exc_info=True)

    def toggle_pause(self) -> bool:
        return self._player.toggle_pause() if self._player is not None else False

    def previous_sentence(self) -> None:
        self._move_sentence(-1)

    def next_sentence(self) -> None:
        self._move_sentence(1)

    def _move_sentence(self, delta: int) -> None:
        should_interrupt = False
        with self._navigation_lock:
            if self._active_request_id is None or not self._sentences:
                return
            target = self._sentence_index + delta
            target = max(0, min(len(self._sentences) - 1, target))
            if delta > 0 and target == self._sentence_index:
                return
            self._requested_sentence = target
            should_interrupt = True
        if should_interrupt and self._player is not None:
            self._player.stop()

    def get_rate(self) -> float:
        with self._navigation_lock:
            return self._rate

    def set_rate(self, rate: float) -> float:
        normalized = self._normalize_rate(rate)
        should_interrupt = False
        with self._navigation_lock:
            if normalized == self._rate:
                return self._rate
            self._rate = normalized
            if self._active_request_id is not None and self._sentences:
                self._requested_sentence = self._sentence_index
                should_interrupt = True
        if should_interrupt and self._player is not None:
            self._player.stop()
        return normalized

    def test_connection(self, key: str, region: str, voice: Optional[str] = None) -> None:
        """Synthesize and play the selected voice, raising on any connection error."""
        if not sys.platform.startswith("win"):
            raise RuntimeError("Azure Read Aloud is currently available on Windows only.")
        key = key.strip()
        region = region.strip() or self.DEFAULT_REGION
        if not key:
            raise RuntimeError("Enter an Azure Speech resource key first.")

        import winsound

        output_path = self.audio_dir / "connection-test.wav"
        selected_voice = self._normalize_english_voice(voice)
        voice_name = next(
            (name for name, voice_id in self.ENGLISH_VOICES if voice_id == selected_voice),
            "selected voice",
        )
        self._synthesize(
            f"Hello. This is {voice_name}. This is how I will sound when reading English text.",
            key,
            region,
            output_path,
            selected_voice,
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

    def _synthesize(
        self,
        text: str,
        key: str,
        region: str,
        output_path: Path,
        voice: str,
        rate: float = 1.0,
    ) -> dict[str, float]:
        rate_percent = int(round((self._normalize_rate(rate) - 1.0) * 100))
        prosody_rate = f"{rate_percent:+d}%"
        ssml = (
            '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            'xml:lang="en-US">'
            f'<voice name="{html.escape(voice)}"><prosody rate="{prosody_rate}">'
            f"{html.escape(text)}</prosody></voice>"
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
        request_started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                headers_received = time.perf_counter()
                audio = response.read()
                download_finished = time.perf_counter()
                output_path.write_bytes(audio)
                return {
                    "headers_ms": round((headers_received - request_started) * 1000, 2),
                    "download_ms": round((download_finished - headers_received) * 1000, 2),
                }
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Azure Speech request failed ({exc.code}): {detail or exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Could not reach Azure Speech: {exc.reason}") from exc

    def _voice_for(self, text: str) -> str:
        persian = sum("\u0600" <= char <= "\u06ff" for char in text)
        latin = sum(char.isascii() and char.isalpha() for char in text)
        if persian > latin:
            return self.PERSIAN_VOICE
        settings = self.config.get("azure_speech", {})
        return self._normalize_english_voice(settings.get("voice"))

    @classmethod
    def _normalize_english_voice(cls, voice: Optional[str]) -> str:
        supported = {voice_id for _, voice_id in cls.ENGLISH_VOICES}
        return voice if voice in supported else cls.ENGLISH_VOICE

    @staticmethod
    def _chunk_text(text: str) -> list[str]:
        """Split text into sentence units for exact back/forward controls."""
        cleaned = " ".join(text.split())
        if not cleaned:
            return []
        sentences = [
            match.group(0).strip()
            for match in re.finditer(
                r'.+?(?:[.!?\u061f]+(?:["\u201d\u2019)\]]+)?(?=\s|$)|$)',
                cleaned,
            )
            if match.group(0).strip()
        ]
        return sentences or [cleaned]

    @classmethod
    def _normalize_rate(cls, rate) -> float:
        try:
            requested = float(rate)
        except (TypeError, ValueError):
            requested = 1.0
        return min(cls.SUPPORTED_RATES, key=lambda value: abs(value - requested))

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
