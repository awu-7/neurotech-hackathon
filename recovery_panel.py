"""Tk recovery panel; HTTP work runs outside the UI thread."""
import json
import queue
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import customtkinter as ctk


class RecoveryPanel(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.events = queue.Queue()
        self.request_lock = threading.Lock()
        self.items = {}
        self.closed = threading.Event()
        self.selected = ctk.StringVar(value="No captured intervals")
        ctk.CTkLabel(self, text="AI Lecture Recovery").pack(pady=4)
        self.menu = ctk.CTkOptionMenu(self, variable=self.selected, values=[self.selected.get()], command=self.render)
        self.menu.pack(fill="x", padx=12)
        self.button = ctk.CTkButton(self, text="Explain What I Missed", command=self.explain, state="disabled")
        self.button.pack(pady=6)
        self.clear_button = ctk.CTkButton(self, text="Clear Recovery History", command=self.clear_history,
                                         fg_color="#4B5563", hover_color="#374151")
        self.clear_button.pack(pady=(0, 4))
        ctk.CTkLabel(self, text="Clears saved timestamps and explanations for all videos.",
                     text_color="#9EAFC6").pack()
        self.output = ctk.CTkTextbox(self, height=150, wrap="word")
        self.output.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.render()
        threading.Thread(target=self.poll, daemon=True).start()
        self.after(150, self.drain)

    def api(self, suffix="", post=False, method=None):
        req = Request("http://127.0.0.1:5001/api/distractions" + suffix,
                      data=b"{}" if post else None,
                      headers={"Content-Type": "application/json"}, method=method)
        try:
            with urlopen(req, timeout=3) as response:
                return json.load(response)
        except HTTPError as exc:
            raise RuntimeError(json.load(exc).get("error", str(exc))) from exc

    def poll(self):
        while not self.closed.is_set():
            try:
                with self.request_lock:
                    self.events.put(("items", self.api()["items"]))
            except (OSError, ValueError, RuntimeError) as exc:
                self.events.put(("error", f"Recovery server unavailable: {exc}"))
            self.closed.wait(2)

    def explain(self):
        record = self.items.get(self.selected.get())
        if not record:
            return
        self.button.configure(state="disabled")
        self.show("Requesting explanation...")
        def worker():
            try:
                with self.request_lock:
                    self.api("/" + record["id"] + "/explain", post=True)
                    self.events.put(("items", self.api()["items"]))
            except (OSError, ValueError, RuntimeError) as exc:
                self.events.put(("error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def clear_history(self):
        self.clear_button.configure(state="disabled")
        self.show("Clearing recovery history...")
        def worker():
            try:
                # Serialize with reads so an older poll cannot restore deleted items.
                with self.request_lock:
                    self.api(method="DELETE")
                    self.events.put(("items", []))
            except (OSError, ValueError, RuntimeError) as exc:
                self.events.put(("error", f"Could not clear recovery history: {exc}"))
            finally:
                self.events.put(("clear_finished", None))
        threading.Thread(target=worker, daemon=True).start()

    def show(self, text):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.configure(state="disabled")

    def render(self, *_):
        row = self.items.get(self.selected.get())
        self.button.configure(state="normal" if row and row["status"] in ("ready", "error") else "disabled")
        if not row:
            self.show("Play a YouTube lecture with the extension loaded. Start a session, then return to focus after a distraction. Select a captured interval here.")
        else:
            self.show(row.get("explanation") or row.get("error") or
                      ("Generating explanation..." if row["status"] == "generating" else "Interval saved. Click Explain What I Missed."))

    def drain(self):
        if self.closed.is_set():
            return
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "clear_finished":
                    self.clear_button.configure(state="normal")
                elif kind == "error":
                    self.show(value)
                    self.button.configure(state="normal" if self.items else "disabled")
                else:
                    self.items = {f"{r['video_id']} | {r['start']:.1f}-{r['end']:.1f}s | {r['id'][:8]}": r for r in value}
                    labels = list(self.items) or ["No captured intervals"]
                    self.menu.configure(values=labels)
                    if self.selected.get() not in labels:
                        self.selected.set(labels[0])
                    self.render()
        except queue.Empty:
            pass
        self.after(150, self.drain)
