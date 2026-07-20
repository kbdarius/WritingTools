"""Microsoft Word Read Aloud integration for Writing Tools."""

import ctypes
import logging
import sys
import threading
from typing import Callable, Optional


StatusCallback = Optional[Callable[[str], None]]
ErrorCallback = Optional[Callable[[str], None]]


class WordSpeechService:
    """Read text with an isolated Microsoft Word instance on Windows."""

    SW_MINIMIZE = 6
    WM_CLOSE = 0x0010
    PROCESS_TERMINATE = 0x0001
    SYNCHRONIZE = 0x00100000
    WAIT_TIMEOUT = 0x00000102

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._word_hwnd = None
        self._word_pid = None
        self._stop_requested = False

    def speak(
        self,
        text: str,
        status_callback: StatusCallback = None,
        error_callback: ErrorCallback = None,
        metrics_context: Optional[dict] = None,
    ) -> None:
        """Create a temporary document and run Word's Read Aloud command."""
        del metrics_context  # Kept for parity with LocalSpeechService.speak.
        if not sys.platform.startswith("win"):
            self._error(error_callback, "Microsoft Word Read Aloud is available on Windows only.")
            return

        word = None
        document = None
        pythoncom = None
        pid = None
        try:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            self.stop()
            with self._lock:
                self._stop_requested = False
                self._stop_event.clear()

            self._notify(status_callback, "Starting Microsoft Word...")
            # DispatchEx guarantees cleanup cannot close Word windows the user
            # already had open.
            word = win32com.client.DispatchEx("Word.Application")
            word.DisplayAlerts = 0
            word.Visible = True
            document = word.Documents.Add()
            document.Content.Text = text
            document.Content.Select()
            word.Activate()

            hwnd = int(word.ActiveWindow.Hwnd)
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            with self._lock:
                self._word_hwnd = hwnd
                self._word_pid = int(pid.value)
                stopped = self._stop_requested
            if stopped:
                return

            self._notify(status_callback, "Reading selected text with Microsoft Word.")

            # ExecuteMso blocks until playback ends. Minimize from a timer
            # after the command starts, without making a cross-thread COM call.
            minimize_timer = threading.Timer(
                0.75,
                lambda: ctypes.windll.user32.ShowWindow(hwnd, self.SW_MINIMIZE),
            )
            minimize_timer.daemon = True
            minimize_timer.start()
            word.CommandBars.ExecuteMso("ReadAloud")

            # Word exposes no completion event for Read Aloud. Keep the
            # temporary document alive for a conservative duration that also
            # covers slow playback speeds; Stop/Escape ends the wait at once.
            word_count = max(1, len(text.split()))
            estimated_seconds = max(8.0, min(3600.0, word_count / 1.25 + 5.0))
            self._stop_event.wait(estimated_seconds)

            with self._lock:
                stopped = self._stop_requested
            if not stopped:
                self._notify(status_callback, "Read Aloud finished.")
        except ImportError:
            self._error(
                error_callback,
                "Microsoft Word support is missing from this Writing Tools installation.",
            )
        except Exception as exc:
            logging.error("Microsoft Word Read Aloud failed: %s", exc, exc_info=True)
            with self._lock:
                stopped = self._stop_requested
            if not stopped:
                self._error(
                    error_callback,
                    "Microsoft Word could not start Read Aloud. Make sure desktop Word is installed and activated.",
                )
        finally:
            with self._lock:
                self._word_hwnd = None
                pid = self._word_pid
                self._word_pid = None
            if document is not None:
                try:
                    document.Close(0)
                except Exception:
                    logging.debug("Word temporary document was already closed", exc_info=True)
            if word is not None:
                try:
                    word.Quit()
                except Exception:
                    logging.debug("Word Read Aloud instance was already closed", exc_info=True)
            self._ensure_process_exited(pid)
            if pythoncom is not None:
                pythoncom.CoUninitialize()

    def stop(self) -> None:
        """Stop playback by closing only the isolated Word window we own."""
        with self._lock:
            self._stop_requested = True
            hwnd = self._word_hwnd
            self._stop_event.set()
        if hwnd:
            ctypes.windll.user32.PostMessageW(hwnd, self.WM_CLOSE, 0, 0)

    def _ensure_process_exited(self, pid: Optional[int]) -> None:
        """Terminate only our DispatchEx process if Word refuses to quit."""
        if not pid:
            return
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(
            self.PROCESS_TERMINATE | self.SYNCHRONIZE,
            False,
            pid,
        )
        if not handle:
            return
        try:
            if kernel32.WaitForSingleObject(handle, 3000) == self.WAIT_TIMEOUT:
                logging.warning("Force-closing unresponsive Word Read Aloud process %s", pid)
                kernel32.TerminateProcess(handle, 0)
        finally:
            kernel32.CloseHandle(handle)

    @staticmethod
    def _notify(callback: StatusCallback, message: str) -> None:
        logging.info("Word Read Aloud: %s", message)
        if callback:
            callback(message)

    @staticmethod
    def _error(callback: ErrorCallback, message: str) -> None:
        if callback:
            callback(message)
