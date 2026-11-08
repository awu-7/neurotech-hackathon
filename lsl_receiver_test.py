import os
import csv
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox

import numpy as np
from scipy.signal import butter, filtfilt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from pylsl import StreamInlet, StreamOutlet, StreamInfo, resolve_streams

WINDOW_SECONDS = 5.0          # Sliding window length for raw EEG
AB_WINDOW_SECONDS = 10.0      # Live A/B ratio window length
REDRAW_MS = 40                # ~25 FPS redraw timer
TILT_OFFSET_DEG = 25.0        # Allowed head posture deviation (+/- 25° from calibrated baseline)
TILT_DURATION_SEC = 5.0       # Required continuous posture deviation duration (seconds)
UNFOCUSED_MULT = 1.8          # Unfocused threshold multiplier (1.8x baseline)
UNFOCUSED_DURATION_SEC = 10.0 # 10-second continuous unfocused threshold for external alert

# Dark Theme Palette
DARK_BG = "#0D0F12"
CARD_BG = "#161920"
CARD_BORDER = "#232834"
ACCENT_CYAN = "#00E5FF"
ACCENT_GREEN = "#00FF9D"
ACCENT_AMBER = "#FFB300"
ACCENT_RED = "#FF3366"
TEXT_MAIN = "#F0F3F8"
TEXT_MUTED = "#8C96A8"


def find_peak(filtered_signal, srate, band_low, band_high):
    """Computes FFT and identifies peak frequency and amplitude within a specific band."""
    N = len(filtered_signal)
    if N == 0:
        return np.array([]), np.array([]), 0.0, 0.0

    Y = np.fft.fft(filtered_signal)
    f = np.fft.fftfreq(N, d=1.0 / srate)
    P = np.abs(Y) / N

    pos_mask = f >= 0
    f_pos = f[pos_mask]
    P_pos = P[pos_mask]

    band_mask = (f_pos >= band_low) & (f_pos <= band_high)
    if np.any(band_mask):
        band_amps = P_pos[band_mask]
        band_freqs = f_pos[band_mask]
        peak_idx = np.argmax(band_amps)
        peak_freq = band_freqs[peak_idx]
        peak_amp = band_amps[peak_idx]
    else:
        peak_freq, peak_amp = 0.0, 0.0

    return f_pos, P_pos, peak_freq, peak_amp


def detect_blink(alpha_power, baseline_alpha_power, threshold_scale=0.3):
    """Detects an eye blink when Alpha wave power drops below a threshold relative to baseline.

    Parameters:
        alpha_power (float): Current frame's Alpha band power.
        baseline_alpha_power (float): Calibrated baseline Alpha power.
        threshold_scale (float): Multiplier scale (default 0.3 = 30% of baseline).

    Returns:
        bool: True if a blink is detected, False otherwise.
    """
    if baseline_alpha_power <= 0:
        return False
    return alpha_power < (baseline_alpha_power * threshold_scale)


class ReceiverApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NeuroPawn Knight - Multimodal Studio")
        self.geometry("1240x940")
        self.configure(bg=DARK_BG)

        self.inlet = None
        self.focus_outlet = None  # Outbound 2-channel LSL stream outlet
        self.srate = 250.0
        self.n_channels = 0
        self.labels = []
        self.buffer = None
        
        self.ab_history = None
        self.ab_history_size = 0

        # Full Session Focus Tracking (Immediate Focus State History)
        self.full_focus_history = []
        self.session_start_time = 0.0

        self.streams = []
        self._after_id = None

        # Focus & Blink State Variables
        self.is_instant_unfocused = False   # Immediate threshold status (>1.8x baseline)
        self.is_instant_focused = True      # Immediate focus status (<1.8x baseline)
        self.is_sustained_unfocused = False # Continuous >10s unfocused alert
        self.is_sustained_focused = True    # 10s sustained focus status (broadcasting to external script)
        self.is_focused = True              # Alias for external LSL stream compatibility
        
        self.baseline_alpha_power = 1.0     # Baseline Alpha power threshold for blink detection
        self.is_blink_detected = False      # Blink status flag

        # Posture State Variables
        self.is_posture_good = True
        self.baseline_ratio = 1.0
        self.baseline_pitch = 0.0

        # Calibration State Machine
        self.calib_state = None
        self.calib_timer_start = 0.0
        self.is_calibrating = False
        self.calibration_samples = []
        self.calibration_pitch_samples = []
        self.calibration_alpha_samples = []
        self.calib_win = None

        # Focus Tracker State
        self.unfocused_start_time = None
        self.unfocused_alert_active = False

        # IMU Posture Tracker State
        self.acc_x_idx = None
        self.acc_y_idx = None
        self.acc_z_idx = None
        self.tilt_start_time = None
        self.tilt_alert_active = False
        self.current_pitch_deg = 0.0

        # CSV Logging Handles
        self.log_file = None
        self.log_writer = None
        self.results_file = None
        self.results_writer = None

        self._setup_styles()
        self._build_ui()

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use('clam')

        style.configure('.', background=DARK_BG, foreground=TEXT_MAIN)
        style.configure('TFrame', background=DARK_BG)
        style.configure('TLabel', background=DARK_BG, foreground=TEXT_MAIN, font=("Segoe UI", 10))
        
        style.configure(
            'Dark.TButton',
            background='#1F2430',
            foreground=TEXT_MAIN,
            bordercolor=CARD_BORDER,
            borderwidth=1,
            focuscolor='none',
            padding=(10, 6),
            font=("Segoe UI", 9, "bold")
        )
        style.map(
            'Dark.TButton',
            background=[('active', '#2A3142'), ('disabled', '#141720')],
            foreground=[('disabled', '#525B6C')]
        )

        style.configure(
            'TCombobox',
            fieldbackground='#181C26',
            background='#232836',
            foreground=TEXT_MAIN,
            arrowcolor=TEXT_MAIN,
            bordercolor=CARD_BORDER
        )
        style.map('TCombobox', fieldbackground=[('readonly', '#181C26')])

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(side="top", fill="x", padx=14, pady=10)

        ttk.Label(top, text="LSL STREAM", font=("Segoe UI", 9, "bold"), foreground=TEXT_MUTED).pack(side="left", padx=(4, 6))
        self.stream_var = tk.StringVar()
        self.stream_combo = ttk.Combobox(
            top, textvariable=self.stream_var, width=28, state="readonly"
        )
        self.stream_combo.pack(side="left", padx=4)

        ttk.Button(top, text="Refresh", style="Dark.TButton", command=self.refresh_streams).pack(
            side="left", padx=3
        )
        self.connect_btn = ttk.Button(
            top, text="Connect Stream", style="Dark.TButton", command=self.toggle_connect
        )
        self.connect_btn.pack(side="left", padx=3)

        self.pause_btn = ttk.Button(
            top, text="Pause", style="Dark.TButton", command=self.toggle_pause, state="disabled"
        )
        self.pause_btn.pack(side="left", padx=(14, 3))

        self.calib_btn = ttk.Button(
            top, text="Calibrate (10s)", style="Dark.TButton", command=self.start_calibration, state="disabled"
        )
        self.calib_btn.pack(side="left", padx=3)

        ttk.Button(top, text="Quit Application", style="Dark.TButton", command=self.on_close).pack(
            side="right", padx=4
        )

        hud_frame = tk.Frame(self, bg=CARD_BG, bd=1, relief="solid", highlightbackground=CARD_BORDER, highlightthickness=1)
        hud_frame.pack(side="top", fill="x", padx=14, pady=(0, 4))

        self.ratio_hud_var = tk.StringVar(
            value="Alpha/Beta Ratio: -- | Focus Index: -- | Baseline Ratio: 1.00"
        )
        self.hud_label = tk.Label(
            hud_frame,
            textvariable=self.ratio_hud_var,
            font=("Consolas", 11, "bold"),
            fg=ACCENT_CYAN,
            bg=CARD_BG,
            padx=14,
            pady=8
        )
        self.hud_label.pack(side="left")

        posture_frame = tk.Frame(self, bg=CARD_BG, bd=1, relief="solid", highlightbackground=CARD_BORDER, highlightthickness=1)
        posture_frame.pack(side="top", fill="x", padx=14, pady=(0, 8))

        self.posture_hud_var = tk.StringVar(
            value="Posture Status: Searching for IMU channels..."
        )
        self.posture_label = tk.Label(
            posture_frame,
            textvariable=self.posture_hud_var,
            font=("Consolas", 11, "bold"),
            fg=TEXT_MUTED,
            bg=CARD_BG,
            padx=14,
            pady=8
        )
        self.posture_label.pack(side="left")

        self.status_var = tk.StringVar(value="System Ready. Connect an LSL stream to begin.")
        status_bar = tk.Label(
            self, textvariable=self.status_var, font=("Segoe UI", 9), fg=TEXT_MUTED, bg="#08090C", anchor="w", padx=14, pady=4
        )
        status_bar.pack(side="bottom", fill="x")

        self.fig = Figure(figsize=(10, 6.8), dpi=100, facecolor=DARK_BG)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(
            side="top", fill="both", expand=True, padx=14, pady=(0, 8)
        )

        self.refresh_streams()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def refresh_streams(self):
        self.streams = resolve_streams(wait_time=1.0)
        names = [
            f"{s.name()} ({s.type()}, {s.channel_count()}ch)"
            for s in self.streams
        ]
        self.stream_combo["values"] = names
        if names:
            idx = next(
                (i for i, s in enumerate(self.streams)
                 if s.name() == "NeuroPawnKnight"),
                0,
            )
            self.stream_combo.current(idx)
        self.status_var.set(f"Found {len(names)} stream(s) broadcasting on local LSL.")

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_btn.configure(text="Resume")
            self.status_var.set("Visualization Paused (LSL data buffering active).")
        else:
            self.pause_btn.configure(text="Pause")
            self.status_var.set("Visualization Resumed.")

    def toggle_connect(self):
        if self.inlet is not None:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        idx = self.stream_combo.current()
        if idx < 0 or idx >= len(self.streams):
            messagebox.showerror("Error", "No stream selected.")
            return

        info = self.streams[idx]
        self.inlet = StreamInlet(info, max_buflen=int(WINDOW_SECONDS) + 2)
        full = self.inlet.info()

        self.n_channels = full.channel_count()
        self.srate = full.nominal_srate() if full.nominal_srate() > 0 else 250.0
        self.labels = self._read_labels(full, self.n_channels)

        # 2-Channel Telemetry Stream (Ch0 = Focus State, Ch1 = Head Pitch Angle)
        telemetry_info = StreamInfo('NeuroPawnTelemetry', 'Telemetry', 2, 0, 'float32', 'telemetry_stream_01')
        self.focus_outlet = StreamOutlet(telemetry_info)

        self.acc_x_idx = self._find_channel_index(["ACC_X", "ACCEL_X", "AX"], fallback=8 if self.n_channels >= 11 else None)
        self.acc_y_idx = self._find_channel_index(["ACC_Y", "ACCEL_Y", "AY"], fallback=9 if self.n_channels >= 11 else None)
        self.acc_z_idx = self._find_channel_index(["ACC_Z", "ACCEL_Z", "AZ"], fallback=10 if self.n_channels >= 11 else None)

        self.tilt_start_time = None
        self.tilt_alert_active = False
        self.unfocused_start_time = None
        self.unfocused_alert_active = False
        self.is_instant_unfocused = False
        self.is_instant_focused = True
        self.is_sustained_unfocused = False
        self.is_sustained_focused = True
        self.is_focused = True
        self.is_posture_good = True
        self.is_blink_detected = False

        n_samples = max(1, int(self.srate * WINDOW_SECONDS))
        self.buffer = np.zeros((self.n_channels, n_samples), dtype=np.float64)

        self.ab_history_size = int((AB_WINDOW_SECONDS * 1000) / REDRAW_MS)
        self.ab_history = np.zeros(self.ab_history_size, dtype=np.float64)

        self.full_focus_history = []
        self.session_start_time = time.time()

        nyq = self.srate / 2.0
        self.b_alpha, self.a_alpha = butter(4, [8.0 / nyq, 13.0 / nyq], btype='band')
        self.b_beta, self.a_beta = butter(4, [13.0 / nyq, 30.0 / nyq], btype='band')

        log_dir = "log"
        os.makedirs(log_dir, exist_ok=True)
        timestamp_tag = datetime.now().strftime("%Y%m%d_%H%M%S")

        raw_filename = os.path.join(log_dir, f"eeg_raw_{timestamp_tag}.csv")
        results_filename = os.path.join(log_dir, f"eeg_results_{timestamp_tag}.csv")

        self.log_file = open(raw_filename, "w", newline="")
        self.log_writer = csv.writer(self.log_file)
        self.log_writer.writerow(["timestamp"] + self.labels)

        self.results_file = open(results_filename, "w", newline="")
        self.results_writer = csv.writer(self.results_file)
        self.results_writer.writerow([
            "timestamp", "alphaPeakFreqHz", "alphaPeakAmp", "betaPeakFreqHz", 
            "betaPeakAmp", "alphaPower", "betaPower", "alphaBetaRatio", 
            "baselineRatio", "pitchDeg", "baselinePitch", "postureAlert", "unfocusedAlert"
        ])

        self._build_axes()
        self.connect_btn.configure(text="Disconnect Stream")
        self.pause_btn.configure(state="normal")
        self.calib_btn.configure(state="normal")
        
        imu_status = "IMU Active" if self.acc_x_idx is not None else "No IMU detected"
        self.status_var.set(
            f"Connected: {info.name()} - {self.n_channels} ch @ {self.srate:.0f} Hz ({imu_status}). Outbound 2-channel telemetry stream initialized."
        )
        self._after_id = self.after(REDRAW_MS, self._update)

    def disconnect(self):
        if self._after_id is not None:
            self.after_cancel(self._after_id)
            self._after_id = None

        if self.inlet is not None:
            try:
                self.inlet.close_stream()
            except Exception:
                pass
            self.inlet = None

        if hasattr(self, 'focus_outlet') and self.focus_outlet:
            self.focus_outlet = None

        if self.log_file and not self.log_file.closed:
            self.log_file.close()
        if self.results_file and not self.results_file.closed:
            self.results_file.close()

        self.connect_btn.configure(text="Connect Stream")
        self.pause_btn.configure(state="disabled")
        self.calib_btn.configure(state="disabled")
        self.is_paused = False
        self.status_var.set("Disconnected. Logs written to /log directory.")
        self.hud_label.configure(fg=ACCENT_CYAN)
        self.ratio_hud_var.set("Alpha/Beta Ratio: -- | Focus Index: -- | Baseline Ratio: 1.00")
        self.posture_hud_var.set("Posture Status: Not connected.")
        self.posture_label.configure(fg=TEXT_MUTED)

    def _find_channel_index(self, target_keywords, fallback=None):
        for idx, label in enumerate(self.labels):
            if any(kw in label.upper() for kw in target_keywords):
                return idx
        if fallback is not None and fallback < len(self.labels):
            return fallback
        return None

    @staticmethod
    def _read_labels(info, n_channels):
        labels = []
        try:
            ch = info.desc().child("channels").child("channel")
            for _ in range(n_channels):
                label = ch.child_value("label")
                labels.append(label if label else "?")
                ch = ch.next_sibling()
        except Exception:
            labels = []

        if len(labels) != n_channels or any(l == "?" for l in labels):
            labels = [f"CH{i + 1}" for i in range(n_channels)]
        return labels

    def start_calibration(self):
        if self.inlet is None:
            return

        self.calib_state = "COUNTDOWN"
        self.calib_timer_start = time.time()
        self.calibration_samples = []
        self.calibration_pitch_samples = []
        self.calibration_alpha_samples = []
        self.is_calibrating = False

        self.calib_win = tk.Toplevel(self)
        self.calib_win.title("Baseline Focus & Posture Calibration")
        self.calib_win.attributes("-fullscreen", True)
        self.calib_win.configure(bg="#060709")
        self.calib_win.transient(self)
        self.calib_win.grab_set()
        self.calib_win.bind("<Escape>", lambda e: self.cancel_calibration())

        top_bar = tk.Frame(self.calib_win, bg="#060709")
        top_bar.pack(side="top", fill="x", padx=30, pady=30)
        tk.Button(
            top_bar, text="Exit Fullscreen (Esc)", command=self.cancel_calibration,
            bg="#181B24", fg=TEXT_MUTED, bd=0, font=("Segoe UI", 10, "bold"), padx=12, pady=6
        ).pack(side="right")

        self.calib_lbl_instruction = tk.Label(
            self.calib_win, text="Focus your gaze on the cross in the center", 
            font=("Segoe UI", 24, "bold"), fg=ACCENT_AMBER, bg="#060709"
        )
        self.calib_lbl_instruction.pack(pady=(40, 10))

        canvas_size = 260
        canvas = tk.Canvas(
            self.calib_win, width=canvas_size, height=canvas_size, 
            bg="#060709", highlightthickness=0
        )
        canvas.pack(expand=True)

        cx, cy = canvas_size // 2, canvas_size // 2
        arm_len = 55
        canvas.create_line(cx - arm_len, cy, cx + arm_len, cy, fill=ACCENT_CYAN, width=5)
        canvas.create_line(cx, cy - arm_len, cx, cy + arm_len, fill=ACCENT_CYAN, width=5)

        self.calib_timer_lbl = tk.Label(
            self.calib_win, text="Starting in 3...", 
            font=("Consolas", 20, "bold"), fg=TEXT_MAIN, bg="#060709"
        )
        self.calib_timer_lbl.pack(pady=(10, 60))

    def cancel_calibration(self):
        self.is_calibrating = False
        self.calib_state = None
        if self.calib_win and self.calib_win.winfo_exists():
            self.calib_win.destroy()

    def _update_calibration_flow(self, ab_ratio, alpha_power):
        if self.calib_state is None or self.calib_win is None or not self.calib_win.winfo_exists():
            return

        now = time.time()
        if self.calib_state == "COUNTDOWN":
            elapsed = now - self.calib_timer_start
            remaining = 3.0 - elapsed
            if remaining > 0:
                self.calib_timer_lbl.configure(text=f"Starting in {int(np.ceil(remaining))}...")
            else:
                self.calib_state = "RECORDING"
                self.calib_timer_start = now
                self.is_calibrating = True
                self.calib_lbl_instruction.pack_forget()

        elif self.calib_state == "RECORDING":
            elapsed = now - self.calib_timer_start
            remaining = 10.0 - elapsed
            if remaining > 0:
                self.calib_timer_lbl.configure(text=f"Recording Baseline: {remaining:.1f}s")
                self.calibration_samples.append(ab_ratio)
                self.calibration_pitch_samples.append(self.current_pitch_deg)
                self.calibration_alpha_samples.append(alpha_power)
            else:
                self.is_calibrating = False
                self.calib_state = None
                if self.calibration_samples:
                    self.baseline_ratio = float(np.mean(self.calibration_samples))
                if self.calibration_pitch_samples:
                    self.baseline_pitch = float(np.mean(self.calibration_pitch_samples))
                if self.calibration_alpha_samples:
                    self.baseline_alpha_power = float(np.mean(self.calibration_alpha_samples))
                if self.calib_win and self.calib_win.winfo_exists():
                    self.calib_win.destroy()

                messagebox.showinfo(
                    "Calibration Complete", 
                    f"Baseline Alpha/Beta Ratio set to: {self.baseline_ratio:.3f}\n"
                    f"Baseline Alpha Power set to: {self.baseline_alpha_power:.4f}"
                )

    def _build_axes(self):
        self.fig.clear()
        
        # 3 Rows x 16 Columns layout for an ultra-thin vertical focus bar (1/16th ratio)
        gs = self.fig.add_gridspec(3, 16, height_ratios=[2.2, 1.6, 1.8], hspace=0.48, wspace=0.35)

        self.ax_alpha = self.fig.add_subplot(gs[0, 0:8])
        self.ax_beta = self.fig.add_subplot(gs[0, 8:16])
        self.ax_ab_ratio = self.fig.add_subplot(gs[1, 0:15])
        self.ax_focus_bar = self.fig.add_subplot(gs[1, 15])
        self.ax_alpha_fft = self.fig.add_subplot(gs[2, 0:8])
        self.ax_beta_fft = self.fig.add_subplot(gs[2, 8:16])

        axes_list = [self.ax_alpha, self.ax_beta, self.ax_ab_ratio, self.ax_focus_bar, self.ax_alpha_fft, self.ax_beta_fft]
        for ax in axes_list:
            ax.set_facecolor(CARD_BG)
            ax.xaxis.label.set_color(TEXT_MUTED)
            ax.yaxis.label.set_color(TEXT_MUTED)
            ax.title.set_color(TEXT_MAIN)
            ax.tick_params(colors=TEXT_MUTED, labelsize=8)
            for spine in ax.spines.values():
                spine.set_color(CARD_BORDER)

        n_samples = self.buffer.shape[1]
        t = np.linspace(-WINDOW_SECONDS, 0, n_samples)
        target_ch_name = self.labels[0]

        (self.line_alpha,) = self.ax_alpha.plot(t, np.zeros(n_samples), color='#FFD700', linewidth=1.1)
        self.ax_alpha.set_title(f"Alpha Band (8–13 Hz) - {target_ch_name}", fontsize=9, fontweight='bold')
        self.ax_alpha.set_xlabel("Time (s)", fontsize=7)
        self.ax_alpha.set_xlim(-WINDOW_SECONDS, 0)

        (self.line_beta,) = self.ax_beta.plot(t, np.zeros(n_samples), color='#E040FB', linewidth=1.1)
        self.ax_beta.set_title(f"Beta Band (13–30 Hz) - {target_ch_name}", fontsize=9, fontweight='bold')
        self.ax_beta.set_xlabel("Time (s)", fontsize=7)
        self.ax_beta.set_xlim(-WINDOW_SECONDS, 0)

        t_ab = np.linspace(-AB_WINDOW_SECONDS, 0, self.ab_history_size)
        (self.line_ab_ratio,) = self.ax_ab_ratio.plot(t_ab, np.zeros(self.ab_history_size), color=ACCENT_CYAN, linewidth=1.3)
        self.line_baseline = self.ax_ab_ratio.axhline(self.baseline_ratio, color=ACCENT_AMBER, linestyle='--', linewidth=1.1, label='Baseline')
        self.ax_ab_ratio.set_title("Live Alpha / Beta Ratio (10s Window)", fontsize=9, fontweight='bold', color=ACCENT_CYAN)
        self.ax_ab_ratio.set_xlabel("Time (s)", fontsize=7)
        self.ax_ab_ratio.set_xlim(-AB_WINDOW_SECONDS, 0)
        self.ax_ab_ratio.grid(True, linestyle=':', color=CARD_BORDER, alpha=0.6)

        # Ultra-Thin Vertical Stacked Bar Chart for Session Focus Percentage
        self.ax_focus_bar.set_title("Focus %", fontsize=7, fontweight='bold', color=TEXT_MAIN)
        self.ax_focus_bar.set_xlim(-0.5, 0.5)
        self.ax_focus_bar.set_ylim(0, 100)
        self.ax_focus_bar.set_xticks([])
        self.ax_focus_bar.tick_params(colors=TEXT_MUTED, labelsize=7)

        self.bar_green = self.ax_focus_bar.bar([0], [100], color=ACCENT_GREEN, width=0.3)
        self.bar_red = self.ax_focus_bar.bar([0], [0], bottom=[100], color=ACCENT_RED, width=0.3)
        self.text_focus_pct = self.ax_focus_bar.text(
            0, 50, "100%", color="#0B0D10", ha='center', va='center', fontweight='bold', fontsize=7
        )

        (self.line_alpha_fft,) = self.ax_alpha_fft.plot([], [], color=ACCENT_CYAN, linewidth=1.0)
        (self.marker_alpha_fft,) = self.ax_alpha_fft.plot([], [], 'ro', color=ACCENT_RED, markersize=4)
        self.ax_alpha_fft.set_title("Alpha Power", fontsize=8)
        self.ax_alpha_fft.set_xlim(0, 40)

        (self.line_beta_fft,) = self.ax_beta_fft.plot([], [], color=ACCENT_CYAN, linewidth=1.0)
        (self.marker_beta_fft,) = self.ax_beta_fft.plot([], [], 'ro', color=ACCENT_RED, markersize=4)
        self.ax_beta_fft.set_title("Beta Power", fontsize=8)
        self.ax_beta_fft.set_xlim(0, 40)

        self.canvas.draw()

    def _process_posture(self):
        if self.acc_x_idx is None or self.acc_x_idx >= self.n_channels:
            self.is_posture_good = True
            self.posture_hud_var.set("Posture Status: IMU Accelerometer channels unavailable.")
            self.posture_label.configure(fg=TEXT_MUTED)
            return

        ax_val = self.buffer[self.acc_x_idx, -1]
        ay_val = self.buffer[self.acc_y_idx, -1] if self.acc_y_idx is not None else 0.0
        az_val = self.buffer[self.acc_z_idx, -1] if self.acc_z_idx is not None else 1.0

        denom = np.sqrt(ay_val**2 + az_val**2)
        if denom < 1e-6: denom = 1e-6
        pitch_rad = np.arctan2(ax_val, denom)
        self.current_pitch_deg = float(np.degrees(pitch_rad))

        max_pitch = self.baseline_pitch + TILT_OFFSET_DEG
        min_pitch = self.baseline_pitch - TILT_OFFSET_DEG
        now = time.time()
        is_tilted = self.current_pitch_deg > max_pitch or self.current_pitch_deg < min_pitch

        if is_tilted:
            tilt_dir = "FORWARD" if self.current_pitch_deg > max_pitch else "BACKWARD"
            if self.tilt_start_time is None: self.tilt_start_time = now
            elapsed = now - self.tilt_start_time
            if elapsed >= TILT_DURATION_SEC:
                self.tilt_alert_active = True
                self.is_posture_good = False  
                self.posture_hud_var.set(f"⚠️ POOR POSTURE ALERT: Head tilted {tilt_dir} for {elapsed:.1f}s!")
                self.posture_label.configure(fg=ACCENT_RED)
            else:
                self.tilt_alert_active = False
                self.is_posture_good = True   
                self.posture_hud_var.set(f"Posture Warning Pending... ({elapsed:.1f}s / {TILT_DURATION_SEC:.0f}s)")
                self.posture_label.configure(fg=ACCENT_AMBER)
        else:
            self.tilt_start_time = None
            self.tilt_alert_active = False
            self.is_posture_good = True       
            self.posture_hud_var.set("Posture Status: Good")
            self.posture_label.configure(fg=ACCENT_GREEN)

    def _update(self):
        if self.inlet is None:
            return

        self._after_id = self.after(REDRAW_MS, self._update)

        try:
            chunk, timestamps = self.inlet.pull_chunk(timeout=0.0)
            if chunk:
                data = np.asarray(chunk, dtype=np.float64).T
                data = np.nan_to_num(data, nan=0.0)
                k = data.shape[1]

                for col_idx in range(k):
                    ts = timestamps[col_idx] if timestamps else time.time()
                    self.log_writer.writerow([ts] + data[:, col_idx].tolist())

                if k >= self.buffer.shape[1]:
                    self.buffer = data[:, -self.buffer.shape[1]:]
                else:
                    self.buffer = np.roll(self.buffer, -k, axis=1)
                    self.buffer[:, -k:] = data

            if not self.is_paused and self.buffer is not None:
                self._process_posture()
                raw_eeg = np.nan_to_num(self.buffer[0, :].copy(), nan=0.0)

                if not np.all(raw_eeg == 0):
                    raw_eeg -= np.mean(raw_eeg)

                    filtered_alpha = np.nan_to_num(filtfilt(self.b_alpha, self.a_alpha, raw_eeg), nan=0.0)
                    filtered_beta = np.nan_to_num(filtfilt(self.b_beta, self.a_beta, raw_eeg), nan=0.0)

                    alpha_power = max(1e-9, float(np.mean(filtered_alpha ** 2)))
                    beta_power = max(1e-9, float(np.mean(filtered_beta ** 2)))

                    # Real-time Blink Detection
                    self.is_blink_detected = detect_blink(alpha_power, self.baseline_alpha_power, threshold_scale=0.3)

                    ab_ratio = float(alpha_power / (beta_power + 1e-9))
                    if np.isnan(ab_ratio) or np.isinf(ab_ratio):
                        ab_ratio = 1.0

                    self.ab_history = np.roll(self.ab_history, -1)
                    self.ab_history[-1] = ab_ratio

                    self._update_calibration_flow(ab_ratio, alpha_power)

                    unfocused_limit = UNFOCUSED_MULT * self.baseline_ratio
                    now = time.time()

                    # 1. Immediate Unfocused State (drives vertical bar percentage)
                    self.is_instant_unfocused = bool(ab_ratio >= unfocused_limit)
                    self.is_instant_focused = not self.is_instant_unfocused

                    # 2. 10-Second Sustained Unfocused Tracker
                    if self.is_instant_unfocused:
                        if self.unfocused_start_time is None: self.unfocused_start_time = now
                        elapsed = now - self.unfocused_start_time
                        if elapsed >= UNFOCUSED_DURATION_SEC:
                            self.unfocused_alert_active = True
                            text_color = ACCENT_RED
                            focus_status_text = "⚠️ UNFOCUSED ALERT (>10s)"
                        else:
                            self.unfocused_alert_active = False
                            text_color = ACCENT_AMBER
                            focus_status_text = f"Unfocused Pending ({elapsed:.1f}s / {UNFOCUSED_DURATION_SEC:.0f}s)"
                    else:
                        self.unfocused_start_time = None
                        self.unfocused_alert_active = False
                        text_color = ACCENT_GREEN
                        focus_status_text = "Focused"

                    # 3. Sustained Focus Variables (10-second alert state broadcasted to companion app)
                    self.is_sustained_unfocused = self.unfocused_alert_active
                    self.is_sustained_focused = not self.is_sustained_unfocused
                    self.is_focused = self.is_sustained_focused

                    # 4. Accumulate Immediate Focus State for Vertical Bar
                    self.full_focus_history.append(1 if self.is_instant_focused else 0)

                    # 5. Broadcast 2-Channel Telemetry Vector [Focus State, Pitch Angle] over LSL
                    if hasattr(self, 'focus_outlet') and self.focus_outlet:
                        focus_val = 1.0 if self.is_sustained_focused else 0.0
                        pitch_val = float(self.current_pitch_deg)
                        self.focus_outlet.push_sample([focus_val, pitch_val])

                    f_pos_a, P_pos_a, alpha_freq, alpha_amp = find_peak(filtered_alpha, self.srate, 8.0, 13.0)
                    f_pos_b, P_pos_b, beta_freq, beta_amp = find_peak(filtered_beta, self.srate, 13.0, 30.0)

                    self.results_writer.writerow([
                        datetime.now().strftime("%H:%M:%S.%f"),
                        f"{alpha_freq:.2f}", f"{alpha_amp:.2f}",
                        f"{beta_freq:.2f}", f"{beta_amp:.2f}",
                        f"{alpha_power:.4f}", f"{beta_power:.4f}",
                        f"{ab_ratio:.4f}", f"{self.baseline_ratio:.4f}",
                        f"{self.current_pitch_deg:.2f}", f"{self.baseline_pitch:.2f}",
                        int(self.tilt_alert_active), int(self.unfocused_alert_active)
                    ])

                    # HUD status includes optional visual indicator when an eye blink occurs
                    blink_flag = " | 👁️ BLINK" if self.is_blink_detected else ""
                    self.hud_label.configure(fg=text_color)
                    self.ratio_hud_var.set(
                        f"Alpha/Beta: {ab_ratio:.2f} | Baseline: {self.baseline_ratio:.2f} | Status: {focus_status_text}{blink_flag}"
                    )

                    self.line_alpha.set_ydata(filtered_alpha)
                    self.line_beta.set_ydata(filtered_beta)
                    self.line_ab_ratio.set_ydata(self.ab_history)
                    self.line_baseline.set_ydata([self.baseline_ratio, self.baseline_ratio])

                    # Render Ultra-Thin Vertical Focus Percentage Bar
                    total_samples = len(self.full_focus_history)
                    focused_pct = (sum(self.full_focus_history) / total_samples * 100.0) if total_samples > 0 else 100.0
                    unfocused_pct = 100.0 - focused_pct

                    self.bar_green[0].set_height(focused_pct)
                    self.bar_red[0].set_height(unfocused_pct)
                    self.bar_red[0].set_y(focused_pct)
                    self.text_focus_pct.set_text(f"{focused_pct:.0f}%")

                    # Axis Autoscaling Protection
                    a_min, a_max = float(np.nanmin(filtered_alpha)), float(np.nanmax(filtered_alpha))
                    if np.isnan(a_min) or np.isnan(a_max) or a_max - a_min < 1e-3:
                        a_min, a_max = a_min - 1.0, a_max + 1.0
                    self.ax_alpha.set_ylim(a_min * 1.15, a_max * 1.15)

                    b_min, b_max = float(np.nanmin(filtered_beta)), float(np.nanmax(filtered_beta))
                    if np.isnan(b_min) or np.isnan(b_max) or b_max - b_min < 1e-3:
                        b_min, b_max = b_min - 1.0, b_max + 1.0
                    self.ax_beta.set_ylim(b_min * 1.15, b_max * 1.15)

                    ab_min = float(np.nanmin(self.ab_history)) if len(self.ab_history) > 0 else 0.0
                    ab_max = float(np.nanmax(self.ab_history)) if len(self.ab_history) > 0 else 1.0
                    if np.isnan(ab_min) or np.isnan(ab_max) or ab_max - ab_min < 0.1:
                        ab_min, ab_max = 0.0, 2.0
                    self.ax_ab_ratio.set_ylim(max(0.0, ab_min * 0.9), max(ab_min + 0.5, ab_max * 1.15))

                    alpha_mask = f_pos_a <= 40
                    if np.any(alpha_mask):
                        self.line_alpha_fft.set_data(f_pos_a[alpha_mask], P_pos_a[alpha_mask])
                        self.marker_alpha_fft.set_data([alpha_freq], [alpha_amp])
                        self.ax_alpha_fft.set_ylim(0, max(0.1, float(np.nanmax(P_pos_a[alpha_mask])) * 1.15))

                    beta_mask = f_pos_b <= 40
                    if np.any(beta_mask):
                        self.line_beta_fft.set_data(f_pos_b[beta_mask], P_pos_b[beta_mask])
                        self.marker_beta_fft.set_data([beta_freq], [beta_amp])
                        self.ax_beta_fft.set_ylim(0, max(0.1, float(np.nanmax(P_pos_b[beta_mask])) * 1.15))

                    self.canvas.draw_idle()
        except Exception:
            pass

    def on_close(self):
        try:
            self.disconnect()
        finally:
            self.destroy()

if __name__ == "__main__":
    ReceiverApp().mainloop()
