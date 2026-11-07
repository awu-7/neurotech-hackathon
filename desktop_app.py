
import time
import customtkinter as ctk
import pyautogui

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

app = ctk.CTk()
app.title("NeuroLearn")
app.geometry("680x540")
app.resizable(False, False)

running = False
focused = True
unfocused_start = 0
unfocused_seconds = 0
pending_rewind = 0


def update_screen():
    if not running:
        status_label.configure(text="Session not started", text_color="white")
    elif focused:
        status_label.configure(text="Focused", text_color="#55D6A0")
    else:
        status_label.configure(text="Possibly distracted", text_color="#FFB86C")

    seconds_label.configure(text=f"{unfocused_seconds} seconds")


def start_session():
    global running, focused, unfocused_seconds, pending_rewind
    running = True
    focused = True
    unfocused_seconds = 0
    pending_rewind = 0
    start_button.configure(state="disabled")
    message_label.configure(text="Session started. Try the demo buttons below.")
    update_screen()


def simulate_unfocused():
    global focused, unfocused_start, unfocused_seconds

    if not running:
        message_label.configure(text="Click Start Session first.")
        return

    if focused:
        focused = False
        unfocused_start = time.monotonic()
        unfocused_seconds = 0

    update_screen()


def simulate_focused():
    global focused, unfocused_seconds, pending_rewind

    if not running:
        message_label.configure(text="Click Start Session first.")
        return

    if not focused:
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

    focused = True
    unfocused_seconds = 0
    update_screen()


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


def send_rewind(seconds):
    try:
        pyautogui.press("left", presses=seconds // 5, interval=0.2)
        message_label.configure(text=f"Sent {seconds // 5} rewind commands.")
    except Exception as error:
        message_label.configure(text=f"Rewind error: {error}")


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

    app.after(5000, lambda: send_rewind(seconds))


header = ctk.CTkLabel(
    app,
    text="NeuroLearn",
    font=ctk.CTkFont(size=34, weight="bold")
)
header.pack(pady=(24, 3))

subtitle = ctk.CTkLabel(
    app,
    text="EEG lecture companion | Demo mode",
    text_color="#9EAFC6"
)
subtitle.pack(pady=(0, 18))

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

update_timer()
app.mainloop()
