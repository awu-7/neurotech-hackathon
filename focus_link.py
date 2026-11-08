"""Background LSL focus-stream receiver shared by NeuroLearn desktop GUIs.

NeuroPawnFocus is published by test.py: int32 [1] = focused, [0] = unfocused.
All Tk widget updates must take place on the main thread (poll ``messages`` with after()).
"""
import queue
import threading
import time


class FocusReceiver:
    def __init__(self, stream_name="NeuroPawnFocus"):
        self.stream_name = stream_name
        self.messages = queue.Queue(maxsize=256)
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="EEGFocusReceiver")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _emit(self, kind, value):
        try:
            self.messages.put_nowait((kind, value))
        except queue.Full:
            try:
                self.messages.get_nowait()
            except queue.Empty:
                pass
            self.messages.put_nowait((kind, value))

    def drain(self):
        """Read pending messages on the Tk main thread."""
        out = []
        while True:
            try:
                out.append(self.messages.get_nowait())
            except queue.Empty:
                return out

    def _run(self):
        try:
            from pylsl import StreamInlet, resolve_byprop
        except Exception as exc:
            self._emit("error", f"pylsl unavailable: {exc}")
            return

        while not self._stop.is_set():
            try:
                matches = resolve_byprop("name", self.stream_name, timeout=1.0)
                if not matches:
                    self._emit("connection", False)
                    continue
                inlet = StreamInlet(matches[0], max_buflen=3)
                self._emit("connection", True)
                last_sample_at = time.monotonic()
                while not self._stop.is_set():
                    sample, _ = inlet.pull_sample(timeout=0.5)
                    if sample is None:
                        if time.monotonic() - last_sample_at > 3.0:
                            self._emit("connection", False)
                            break
                        continue
                    last_sample_at = time.monotonic()
                    try:
                        state = int(sample[0])
                    except (TypeError, ValueError, IndexError):
                        continue
                    if state in (0, 1):
                        self._emit("state", bool(state))
                inlet.close_stream()
            except Exception as exc:
                self._emit("connection", False)
                self._emit("error", str(exc))
                self._stop.wait(1.0)
