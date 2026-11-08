
import time
import json
import queue
import threading
from urllib.request import urlopen
import customtkinter as ctk
import pyautogui
from bridge import start_bridge, send_command
from sync_logging import get_logger

log = get_logger("desktop")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

app = ctk.CTk()
app.title("NeuroLearn")
app.geometry("680x590")
app.resizable(False, False)

running = False
focused = True
unfocused_start = 0
unfocused_seconds = 0
pending_rewind = 0

# Flask is the source of truth for UI focus text.
STATUS_URL = "http://127.0.0.1:5001/api/status"
network_events = queue.Queue(maxsize=2)
stop_network = threading.Event()
current_status = "waiting"
current_display = "Waiting for EEG"
last_live_revision = None
last_log_status = None
last_connection_status = None


def _send_network_event(item):
    try:
        network_events.put_nowait(item)
    except queue.Full:
        try:
            network_events.get_nowait()
        except queue.Empty:
            pass
        network_events.put_nowait(item)


def _poll_server():
    # Networking stays off the Tkinter main thread.
    while not stop_network.is_set():
        try:
            with urlopen(STATUS_URL, timeout=1.0) as response:
                state = json.load(response)
            _send_network_event(("state", state))
        except (OSError, ValueError) as exc:
            _send_network_event(("error", str(exc)))
        stop_network.wait(0.3)


def _process_network_events():
    global current_status, current_display, last_live_revision, last_log_status, last_connection_status
    newest = None
    try:
        while True:
            newest = network_events.get_nowait()
    except queue.Empty:
        pass

    if newest:
        kind, payload = newest
        if kind == "error":
            if last_connection_status != "offline":
                log.error("SERVER OFFLINE | %s", payload)
                last_connection_status = "offline"
            connection_label.configure(
                text="Flask server: OFFLINE (run status_server.py)",
                text_color="#FF3366"
            )
            current_status = "waiting"
            current_display = "Server offline"
            last_live_revision = None
        elif not payload.get("live"):
            if last_connection_status != "waiting":
                log.warning("SERVER ONLINE but EEG data STALE / WAITING for test.py")
                last_connection_status = "waiting"
            connection_label.configure(
                text="Flask server: ONLINE | EEG: waiting for test.py",
                text_color="#FFB86C"
            )
            current_status = "waiting"
            current_display = "Waiting for EEG"
            last_live_revision = None
        else:
            if last_connection_status != "live":
                log.info("SERVER ONLINE | EEG LIVE")
                last_connection_status = "live"
            connection_label.configure(
                text="Flask server: ONLINE | EEG: LIVE",
                text_color="#55D6A0"
            )
            status = payload.get("status", "waiting")
            if status not in ("focused", "pending", "unfocused"):
                status = "waiting"
            current_display = payload.get("display", status)
            current_status = status
            if status != last_log_status:
                log.info("DISPLAY UPDATED | revision=%s status=%s text=%r", payload.get("revision"), status, current_display)
                last_log_status = status
            # Update distraction tracking on status TRANSITIONS only.
            # Pending and Alert are both displayed as unfocused states.
            revision = payload.get("revision")
            if revision != last_live_revision:
                last_live_revision = revision
                if running:
                    if status in ("pending", "unfocused"):
                        set_unfocused()
                    elif status == "focused":
                        set_focused()
        update_screen()

    app.after(100, _process_network_events)


def update_screen():
    # Always mirror the status from test.py, whether a session has started or not.
    colors = {
        "focused": "#55D6A0",
        "pending": "#FFB86C",
        "unfocused": "#FF3366",
        "waiting": "white",
    }
    status_label.configure(text=current_display, text_color=colors[current_status])
    seconds_label.configure(text=f"{unfocused_seconds} seconds")


def start_session():
    global running, focused, unfocused_seconds, pending_rewind
    running = True
    log.info("SESSION STARTED | current EEG status=%s", current_status)
    focused = True
    unfocused_seconds = 0
    pending_rewind = 0
    start_button.configure(state="disabled")
    message_label.configure(text="Session started. Monitoring EEG from test.py.")
    send_command("discard")
    if current_status in ("pending", "unfocused"):
        set_unfocused()
    update_screen()


def set_unfocused():
    global focused, unfocused_start, unfocused_seconds
    if not running or not focused:
        return
    focused = False
    log.info("TRACKING distraction started")
    unfocused_start = time.monotonic()
    unfocused_seconds = 0
    send_command("distracted")
    message_label.configure(text="Unfocused detected. Tracking time...")
    update_screen()


def set_focused():
    global focused, unfocused_seconds, pending_rewind
    if not running or focused:
        return
    unfocused_seconds = int((time.monotonic() - unfocused_start) // 5) * 5
    if unfocused_seconds >= 10:
        pending_rewind = unfocused_seconds
        message_label.configure(
            text=f"You may have missed {pending_rewind} seconds. Rewind?"
        )
        rewind_button.configure(state="normal")
        continue_button.configure(state="normal")
    else:
        message_label.configure(text="Short distraction. No rewind needed.")
        send_command("discard")
    focused = True
    log.info("TRACKING distraction ended | seconds=%s", unfocused_seconds)
    send_command("focused")
    unfocused_seconds = 0
    update_screen()


def simulate_unfocused():
    # Demonstrates session behavior, but cannot overwrite the live EEG label.
    if not running:
        message_label.configure(text="Click Start Session first.")
        return
    set_unfocused()


def simulate_focused():
    if not running:
        message_label.configure(text="Click Start Session first.")
        return
    set_focused()


def update_timer():
    global unfocused_seconds
    if running and not focused:
        unfocused_seconds = int((time.monotonic() - unfocused_start) // 5) * 5
        update_screen()
    app.after(250, update_timer)


def continue_lecture():
    global pending_rewind
    pending_rewind = 0
    rewind_button.configure(state="disabled")
    continue_button.configure(state="disabled")
    message_label.configure(text="Continuing without rewinding.")
    send_command("discard")


def send_rewind(seconds):
    original_speed = float(speed_var.get().replace("x", ""))

    # Rewind the video
    presses = max(1, seconds // 5)
    pyautogui.press("left", presses=presses, interval=0.2)

    # Don't slow down below 0.25x
    if original_speed <= 0.25:
        return

    # Slow down by 0.25x
    pyautogui.hotkey("shift", ",")

    slower_speed = original_speed - 0.25

    # Calculate how long replay should take
    replay_time = (presses * 5) / slower_speed

    # Restore the original speed
    app.after(int(replay_time * 1000),lambda: pyautogui.hotkey("shift", "."))

def rewind_lecture():
    global pending_rewind

    seconds = pending_rewind
    if seconds == 0:
        return

    pending_rewind = 0
    rewind_button.configure(state="disabled")
    continue_button.configure(state="disabled")
    message_label.configure(
        text="Switch to your video using Alt+Tab. Rewinding in 5 seconds!"
    )

    send_command("rewind")
    app.after(5000, lambda: send_rewind(seconds))


header = ctk.CTkLabel(
    app,
    text="NeuroLearn",
    font=ctk.CTkFont(size=34, weight="bold")
)
header.pack(pady=(24, 3))

subtitle = ctk.CTkLabel(
    app,
    text="EEG lecture companion | Flask live sync",
    text_color="#9EAFC6"
)
subtitle.pack(pady=(0, 8))

connection_label = ctk.CTkLabel(
    app, text="Flask server: connecting...", text_color="#FFB86C"
)
connection_label.pack(pady=(0, 8))

card = ctk.CTkFrame(app, corner_radius=16)
card.pack(fill="x", padx=32, pady=8)

status_heading = ctk.CTkLabel(
    card,
    text="ATTENTION STATUS",
    font=ctk.CTkFont(size=13, weight="bold")
)
status_heading.pack(pady=(20, 4))

status_label = ctk.CTkLabel(
    card,
    text="Session not started",
    font=ctk.CTkFont(size=25, weight="bold")
)
status_label.pack()

seconds_heading = ctk.CTkLabel(
    card,
    text="Current possible distraction",
    text_color="#9EAFC6"
)
seconds_heading.pack(pady=(12, 2))

seconds_label = ctk.CTkLabel(
    card,
    text="0 seconds",
    font=ctk.CTkFont(size=25, weight="bold")
)
seconds_label.pack(pady=(0, 20))

start_button = ctk.CTkButton(
    app,
    text="Start Session",
    height=40,
    width=180,
    command=start_session
)
start_button.pack(pady=(10, 18))

button_row = ctk.CTkFrame(app, fg_color="transparent")
button_row.pack(pady=(0, 16))

unfocused_button = ctk.CTkButton(
    button_row,
    text="Simulate Unfocused",
    width=190,
    height=40,
    fg_color="#B45B31",
    hover_color="#944522",
    command=simulate_unfocused
)
unfocused_button.pack(side="left", padx=8)

focused_button = ctk.CTkButton(
    button_row,
    text="Simulate Focused",
    width=190,
    height=40,
    fg_color="#247F62",
    hover_color="#1D624C",
    command=simulate_focused
)
focused_button.pack(side="left", padx=8)

prompt_card = ctk.CTkFrame(app, corner_radius=16)
prompt_card.pack(fill="x", padx=32, pady=5)

message_label = ctk.CTkLabel(
    prompt_card,
    text="Start a session to begin.",
    wraplength=550
)
message_label.pack(pady=(16, 10), padx=15)

prompt_buttons = ctk.CTkFrame(
    prompt_card,
    fg_color="transparent"
)
prompt_buttons.pack(pady=(0, 15))

rewind_button = ctk.CTkButton(
    prompt_buttons,
    text="Rewind Lecture",
    width=170,
    command=rewind_lecture,
    state="disabled"
)
rewind_button.pack(side="left", padx=8)

continue_button = ctk.CTkButton(
    prompt_buttons,
    text="Continue",
    width=140,
    fg_color="#4B5563",
    hover_color="#374151",
    command=continue_lecture,
    state="disabled"
)
continue_button.pack(side="left", padx=8)

speed_var = ctk.StringVar(value="1.75x")

speed_menu = ctk.CTkOptionMenu(
    app,
    values=["0.5x", "0.75x", "1x", "1.25x",
            "1.5x", "1.75x", "2x"],
    variable=speed_var
)

speed_menu.pack(pady=10)

def on_close():
    stop_network.set()
    app.destroy()

app.protocol("WM_DELETE_WINDOW", on_close)
update_timer()
start_bridge()
log.info("DESKTOP STARTING | polling %s", STATUS_URL)
threading.Thread(target=_poll_server, daemon=True).start()
_process_network_events()
app.mainloop()