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
from pylsl import StreamInlet, resolve_streams

WINDOW_SECONDS = 5.0          # Sliding window length for signal analysis
REDRAW_MS = 40                # ~25 FPS redraw timer
TILT_OFFSET_DEG = 25.0        # Allowed head posture deviation (+/- 25° from calibrated baseline)
TILT_DURATION_SEC = 5.0       # Required continuous posture deviation duration (seconds)
UNFOCUSED_MULT = 2.0          # Unfocused threshold multiplier (2.0x baseline)
UNFOCUSED_DURATION_SEC = 15.0 # Continuous unfocused duration before alert (seconds)


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


class ReceiverApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NeuroPawn Knight - Multimodal Cognitive & Posture System")
        self.geometry("1200x920")

        self.inlet = None
        self.srate = 250.0
        self.n_channels = 0
        self.labels = []
        self.buffer = None       # shape (n_channels, n_samples)
        self.ab_history = None   # shape (n_samples,) for live A/B ratio graph
        self.streams = []
        self._after_id = None

        # Control States & Calibration Baselines
        self.is_paused = False
        self.baseline_ratio = 1.0  # Default A/B ratio baseline
        self.baseline_pitch = 0.0  # Calibrated average head pitch (degrees)

        # Calibration State Machine
        self.calib_state = None   # None, "COUNTDOWN", or "RECORDING"
        self.calib_timer_start = 0.0
        self.is_calibrating = False
        self.calibration_samples = []
        self.calibration_pitch_samples = []
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

        self._build_ui()

    # -- UI Setup ----------------------------------------------------------
    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(side="top", fill="x", padx=6, pady=6)

        # Stream Selection & Connection
        ttk.Label(top, text="Stream:").pack(side="left", padx=4)
        self.stream_var = tk.StringVar()
        self.stream_combo = ttk.Combobox(
            top, textvariable=self.stream_var, width=24, state="readonly"
        )
        self.stream_combo.pack(side="left", padx=4)

        ttk.Button(top, text="Refresh", command=self.refresh_streams).pack(
            side="left", padx=2
        )
        self.connect_btn = ttk.Button(
            top, text="Connect", command=self.toggle_connect
        )
        self.connect_btn.pack(side="left", padx=2)

        # Pause & Calibration Buttons
        self.pause_btn = ttk.Button(
            top, text="Pause", command=self.toggle_pause, state="disabled"
        )
        self.pause_btn.pack(side="left", padx=(10, 2))

        self.calib_btn = ttk.Button(
            top, text="Calibrate (10s)", command=self.start_calibration, state="disabled"
        )
        self.calib_btn.pack(side="left", padx=2)

        # Quit Button
        ttk.Button(top, text="Quit", command=self.on_close).pack(
            side="right", padx=6
        )

        # Real-Time Telemetry HUD Banner
        hud_frame = tk.Frame(self, bg="#181818", bd=2, relief="groove")
        hud_frame.pack(side="top", fill="x", padx=6, pady=(0, 2))

        self.ratio_hud_var = tk.StringVar(
            value="Alpha/Beta Ratio: -- | Focus Index: -- | Baseline Ratio: 1.00"
        )
        self.hud_label = tk.Label(
            hud_frame,
            textvariable=self.ratio_hud_var,
            font=("Consolas", 11, "bold"),
            fg="#00FFCC",
            bg="#181818",
            padx=10,
            pady=4
        )
        self.hud_label.pack(side="left")

        # Posture Alert Banner
        posture_frame = tk.Frame(self, bg="#111111", bd=2, relief="sunken")
        posture_frame.pack(side="top", fill="x", padx=6, pady=(0, 4))

        self.posture_hud_var = tk.StringVar(
            value="Posture Status: Searching for IMU channels..."
        )
        self.posture_label = tk.Label(
            posture_frame,
            textvariable=self.posture_hud_var,
            font=("Consolas", 11, "bold"),
            fg="#AAAAAA",
            bg="#111111",
            padx=10,
            pady=4
        )
        self.posture_label.pack(side="left")

        self.status_var = tk.StringVar(value="Not connected.")
        ttk.Label(self, textvariable=self.status_var).pack(
            side="bottom", fill="x", padx=6, pady=2
        )

        # Figure GridSpec Setup
        self.fig = Figure(figsize=(10, 6.8), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(
            side="top", fill="both", expand=True, padx=6, pady=6
        )

        self.refresh_streams()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # -- Stream Discovery --------------------------------------------------
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
        self.status_var.set(f"Found {len(names)} stream(s).")

    # -- Connection & IMU Detection ----------------------------------------
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

        # Detect Accelerometer Channels for Head Posture (+X Axis)
        self.acc_x_idx = self._find_channel_index(["ACC_X", "ACCEL_X", "AX"], fallback=8 if self.n_channels >= 11 else None)
        self.acc_y_idx = self._find_channel_index(["ACC_Y", "ACCEL_Y", "AY"], fallback=9 if self.n_channels >= 11 else None)
        self.acc_z_idx = self._find_channel_index(["ACC_Z", "ACCEL_Z", "AZ"], fallback=10 if self.n_channels >= 11 else None)

        self.tilt_start_time = None
        self.tilt_alert_active = False
        self.unfocused_start_time = None
        self.unfocused_alert_active = False

        n_samples = max(1, int(self.srate * WINDOW_SECONDS))
        self.buffer = np.zeros((self.n_channels, n_samples), dtype=np.float64)
        self.ab_history = np.zeros(n_samples, dtype=np.float64)

        # Filter Design Coefficients
        nyq = self.srate / 2.0
        self.b_alpha, self.a_alpha = butter(4, [8.0 / nyq, 13.0 / nyq], btype='band')
        self.b_beta, self.a_beta = butter(4, [13.0 / nyq, 30.0 / nyq], btype='band')

        # CSV Logging Setup
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
        self.connect_btn.configure(text="Disconnect")
        self.pause_btn.configure(state="normal")
        self.calib_btn.configure(state="normal")
        
        imu_status = "IMU Active" if self.acc_x_idx is not None else "No IMU detected"
        self.status_var.set(
            f"Connected to {info.name()} - {self.n_channels} ch @ {self.srate:.0f} Hz ({imu_status})."
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

        if self.log_file and not self.log_file.closed:
            self.log_file.close()
        if self.results_file and not self.results_file.closed:
            self.results_file.close()

        self.connect_btn.configure(text="Connect")
        self.pause_btn.configure(text="Pause", state="disabled")
        self.calib_btn.configure(state="disabled")
        self.is_paused = False
        self.status_var.set("Disconnected. Logs saved to /log directory.")
        self.hud_label.configure(fg="#00FFCC")
        self.ratio_hud_var.set("Alpha/Beta Ratio: -- | Focus Index: -- | Baseline Ratio: 1.00")
        self.posture_hud_var.set("Posture Status: Not connected.")
        self.posture_label.configure(fg="#AAAAAA")

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

    # -- Fullscreen Calibration with Target Cross (3s Countdown -> 10s Recording) --
    def start_calibration(self):
        if self.inlet is None:
            return

        self.calib_state = "COUNTDOWN"
        self.calib_timer_start = time.time()
        self.calibration_samples = []
        self.calibration_pitch_samples = []
        self.is_calibrating = False

        # Fullscreen Calibration Window
        self.calib_win = tk.Toplevel(self)
        self.calib_win.title("Baseline Focus & Posture Calibration")
        self.calib_win.attributes("-fullscreen", True)
        self.calib_win.configure(bg="#0A0A0A")
        self.calib_win.transient(self)
        self.calib_win.grab_set()

        # Exit calibration shortcut
        self.calib_win.bind("<Escape>", lambda e: self.cancel_calibration())

        # Top Control / Exit Bar
        top_bar = tk.Frame(self.calib_win, bg="#0A0A0A")
        top_bar.pack(side="top", fill="x", padx=20, pady=20)
        tk.Button(
            top_bar, text="Exit Fullscreen (Esc)", command=self.cancel_calibration,
            bg="#222222", fg="#AAAAAA", bd=1, font=("Arial", 10)
        ).pack(side="right")

        # Instruction Text Label (ONLY shown during countdown)
        self.calib_lbl_instruction = tk.Label(
            self.calib_win, 
            text="Focus your gaze on the cross in the center", 
            font=("Arial", 22, "bold"), 
            fg="#FFCC00", 
            bg="#0A0A0A"
        )
        self.calib_lbl_instruction.pack(pady=(40, 10))

        # Central Cross (+) Target
        canvas_size = 240
        canvas = tk.Canvas(
            self.calib_win, width=canvas_size, height=canvas_size, 
            bg="#0A0A0A", highlightthickness=0
        )
        canvas.pack(expand=True)

        cx, cy = canvas_size // 2, canvas_size // 2
        arm_len = 50
        # Horizontal cross line
        canvas.create_line(cx - arm_len, cy, cx + arm_len, cy, fill="#00FFCC", width=5)
        # Vertical cross line
        canvas.create_line(cx, cy - arm_len, cx, cy + arm_len, fill="#00FFCC", width=5)

        # Status / Countdown Timer Label
        self.calib_timer_lbl = tk.Label(
            self.calib_win, 
            text="Starting in 3...", 
            font=("Consolas", 18, "bold"), 
            fg="#FFFFFF", 
            bg="#0A0A0A"
        )
        self.calib_timer_lbl.pack(pady=(10, 60))

    def cancel_calibration(self):
        self.is_calibrating = False
        self.calib_state = None
        if self.calib_win and self.calib_win.winfo_exists():
            self.calib_win.destroy()

    def _update_calibration_flow(self, ab_ratio):
        if self.calib_state is None or self.calib_win is None or not self.calib_win.winfo_exists():
            return

        now = time.time()
        if self.calib_state == "COUNTDOWN":
            elapsed = now - self.calib_timer_start
            remaining = 3.0 - elapsed
            if remaining > 0:
                count_val = int(np.ceil(remaining))
                self.calib_timer_lbl.configure(text=f"Starting in {count_val}...")
            else:
                self.calib_state = "RECORDING"
                self.calib_timer_start = now
                self.is_calibrating = True
                # Remove the instruction label so it ONLY shows during the countdown
                self.calib_lbl_instruction.pack_forget()

        elif self.calib_state == "RECORDING":
            elapsed = now - self.calib_timer_start
            remaining = 10.0 - elapsed
            if remaining > 0:
                self.calib_timer_lbl.configure(text=f"Recording Baseline: {remaining:.1f}s")
                self.calibration_samples.append(ab_ratio)
                self.calibration_pitch_samples.append(self.current_pitch_deg)
            else:
                self.is_calibrating = False
                self.calib_state = None

                if self.calibration_samples:
                    self.baseline_ratio = float(np.mean(self.calibration_samples))
                if self.calibration_pitch_samples:
                    self.baseline_pitch = float(np.mean(self.calibration_pitch_samples))

                if self.calib_win and self.calib_win.winfo_exists():
                    self.calib_win.destroy()

                messagebox.showinfo(
                    "Calibration Complete", 
                    f"10-Second Baseline Calibration Complete!\n\n"
                    f"Baseline Alpha/Beta Ratio: {self.baseline_ratio:.3f}\n"
                    f"Baseline Head Pitch: {self.baseline_pitch:.1f}°\n"
                    f"Allowed Posture Range: {self.baseline_pitch - TILT_OFFSET_DEG:.1f}° to {self.baseline_pitch + TILT_OFFSET_DEG:.1f}°"
                )

    # -- Subplot Layout Setup ----------------------------------------------
    def _build_axes(self):
        self.fig.clear()
        
        # GridSpec: 3 rows layout (Top: EEG Bands, Middle: Live A/B Ratio, Bottom: FFT Power Spectrums)
        gs = self.fig.add_gridspec(3, 2, height_ratios=[2.2, 1.6, 1.8], hspace=0.45, wspace=0.22)

        self.ax_alpha = self.fig.add_subplot(gs[0, 0])
        self.ax_beta = self.fig.add_subplot(gs[0, 1])
        self.ax_ab_ratio = self.fig.add_subplot(gs[1, :])  # Spans across both columns
        self.ax_alpha_fft = self.fig.add_subplot(gs[2, 0])
        self.ax_beta_fft = self.fig.add_subplot(gs[2, 1])

        n_samples = self.buffer.shape[1]
        t = np.linspace(-WINDOW_SECONDS, 0, n_samples)
        target_ch_name = self.labels[0]

        # Time-Domain EEG Subplots (Autoscaling)
        (self.line_alpha,) = self.ax_alpha.plot(t, np.zeros(n_samples), color='gold', linewidth=1.0)
        self.ax_alpha.set_title(f"Alpha Band (8–13 Hz) - {target_ch_name}", fontsize=9)
        self.ax_alpha.set_xlabel("Time (s)", fontsize=7)
        self.ax_alpha.set_ylabel("uV", fontsize=7)
        self.ax_alpha.set_xlim(-WINDOW_SECONDS, 0)

        (self.line_beta,) = self.ax_beta.plot(t, np.zeros(n_samples), color='magenta', linewidth=1.0)
        self.ax_beta.set_title(f"Beta Band (13–30 Hz) - {target_ch_name}", fontsize=9)
        self.ax_beta.set_xlabel("Time (s)", fontsize=7)
        self.ax_beta.set_ylabel("uV", fontsize=7)
        self.ax_beta.set_xlim(-WINDOW_SECONDS, 0)

        # Live Alpha/Beta Ratio Scrolling Graph
        (self.line_ab_ratio,) = self.ax_ab_ratio.plot(t, np.zeros(n_samples), color='#00FFCC', linewidth=1.2)
        self.line_baseline = self.ax_ab_ratio.axhline(self.baseline_ratio, color='#FFCC00', linestyle='--', linewidth=1.0, label='Baseline')
        self.ax_ab_ratio.set_title("Live Alpha / Beta Ratio Stream", fontsize=9, fontweight='bold', color='#00FFCC')
        self.ax_ab_ratio.set_xlabel("Time (s)", fontsize=7)
        self.ax_ab_ratio.set_ylabel("A/B Ratio", fontsize=7)
        self.ax_ab_ratio.set_xlim(-WINDOW_SECONDS, 0)
        self.ax_ab_ratio.grid(True, linestyle=':', alpha=0.4)

        # Power Spectrum / FFT Subplots (Autoscaling)
        (self.line_alpha_fft,) = self.ax_alpha_fft.plot([], [], color='cyan', linewidth=1.0)
        (self.marker_alpha_fft,) = self.ax_alpha_fft.plot([], [], 'ro', markersize=4)
        self.ax_alpha_fft.set_title("Alpha Power Spectrum", fontsize=8)
        self.ax_alpha_fft.set_xlabel("Hz", fontsize=7)
        self.ax_alpha_fft.set_ylabel("Mag", fontsize=7)
        self.ax_alpha_fft.tick_params(labelsize=7)
        self.ax_alpha_fft.set_xlim(0, 40)

        (self.line_beta_fft,) = self.ax_beta_fft.plot([], [], color='cyan', linewidth=1.0)
        (self.marker_beta_fft,) = self.ax_beta_fft.plot([], [], 'ro', markersize=4)
        self.ax_beta_fft.set_title("Beta Power Spectrum", fontsize=8)
        self.ax_beta_fft.set_xlabel("Hz", fontsize=7)
        self.ax_beta_fft.set_ylabel("Mag", fontsize=7)
        self.ax_beta_fft.tick_params(labelsize=7)
        self.ax_beta_fft.set_xlim(0, 40)

        self.canvas.draw()

    # -- Process Posture Deviation relative to Calibrated Baseline (+/- 25°) -
    def _process_posture(self):
        if self.acc_x_idx is None or self.acc_x_idx >= self.n_channels:
            self.posture_hud_var.set("Posture Status: IMU Accelerometer channels unavailable.")
            self.posture_label.configure(fg="#AAAAAA")
            return

        ax_val = self.buffer[self.acc_x_idx, -1]
        ay_val = self.buffer[self.acc_y_idx, -1] if self.acc_y_idx is not None else 0.0
        az_val = self.buffer[self.acc_z_idx, -1] if self.acc_z_idx is not None else 1.0

        # Pitch angle calculation (+X forward, -X backward)
        denom = np.sqrt(ay_val**2 + az_val**2)
        if denom < 1e-6:
            denom = 1e-6
        pitch_rad = np.arctan2(ax_val, denom)
        self.current_pitch_deg = float(np.degrees(pitch_rad))

        max_pitch_limit = self.baseline_pitch + TILT_OFFSET_DEG
        min_pitch_limit = self.baseline_pitch - TILT_OFFSET_DEG

        now = time.time()
        is_forward_tilt = self.current_pitch_deg > max_pitch_limit
        is_backward_tilt = self.current_pitch_deg < min_pitch_limit
        is_tilted = is_forward_tilt or is_backward_tilt

        if is_tilted:
            tilt_dir = "FORWARD" if is_forward_tilt else "BACKWARD"
            if self.tilt_start_time is None:
                self.tilt_start_time = now

            elapsed = now - self.tilt_start_time
            if elapsed >= TILT_DURATION_SEC:
                self.tilt_alert_active = True
                self.posture_hud_var.set(
                    f"⚠️ POOR POSTURE ALERT: Head tilted {tilt_dir} >25° from baseline for {elapsed:.1f}s! (Tilt: {self.current_pitch_deg:.1f}°, Base: {self.baseline_pitch:.1f}°)"
                )
                self.posture_label.configure(fg="#FF2222")
            else:
                self.tilt_alert_active = False
                self.posture_hud_var.set(
                    f"Posture Warning Pending... Tilted {tilt_dir} ({self.current_pitch_deg:.1f}°) for {elapsed:.1f}s / {TILT_DURATION_SEC:.0f}s"
                )
                self.posture_label.configure(fg="#FFAA00")
        else:
            self.tilt_start_time = None
            self.tilt_alert_active = False
            self.posture_hud_var.set(
                f"Posture Status: Good (Pitch: {self.current_pitch_deg:.1f}°, Baseline: {self.baseline_pitch:.1f}°, Range: {min_pitch_limit:.1f}° to {max_pitch_limit:.1f}°)"
            )
            self.posture_label.configure(fg="#00FF66")

    # -- Main Processing & UI Redraw Loop ----------------------------------
    def _update(self):
        if self.inlet is None:
            return

        chunk, timestamps = self.inlet.pull_chunk(timeout=0.0)
        if chunk:
            data = np.asarray(chunk, dtype=np.float64).T  # (n_channels, n_samples)
            k = data.shape[1]

            # Log raw stream samples to CSV
            for col_idx in range(k):
                ts = timestamps[col_idx] if timestamps else time.time()
                raw_sample = data[:, col_idx].tolist()
                self.log_writer.writerow([ts] + raw_sample)

            # Update rolling buffer
            if k >= self.buffer.shape[1]:
                self.buffer = data[:, -self.buffer.shape[1]:]
            else:
                self.buffer = np.roll(self.buffer, -k, axis=1)
                self.buffer[:, -k:] = data

            # Evaluate posture and signal metrics if not paused
            if not self.is_paused:
                self._process_posture()
                raw_eeg = self.buffer[0, :].copy()

                if not np.all(raw_eeg == 0):
                    raw_eeg -= np.mean(raw_eeg)

                    # Filter EEG signals
                    filtered_alpha = np.nan_to_num(filtfilt(self.b_alpha, self.a_alpha, raw_eeg))
                    filtered_beta = np.nan_to_num(filtfilt(self.b_beta, self.a_beta, raw_eeg))

                    # Band Power & Ratios
                    alpha_power = float(np.mean(filtered_alpha ** 2))
                    beta_power = float(np.mean(filtered_beta ** 2))
                    eps = 1e-9
                    ab_ratio = alpha_power / (beta_power + eps)
                    ba_ratio = beta_power / (alpha_power + eps)

                    # Update rolling A/B ratio history array
                    self.ab_history = np.roll(self.ab_history, -1)
                    self.ab_history[-1] = ab_ratio

                    # Calibration step machine update
                    self._update_calibration_flow(ab_ratio)

                    # 15-second Unfocused Warning Tracking (2.0x Baseline Ratio)
                    unfocused_limit = UNFOCUSED_MULT * self.baseline_ratio
                    is_above_unfocused_limit = ab_ratio >= unfocused_limit
                    now = time.time()

                    if is_above_unfocused_limit:
                        if self.unfocused_start_time is None:
                            self.unfocused_start_time = now

                        unfocused_elapsed = now - self.unfocused_start_time
                        if unfocused_elapsed >= UNFOCUSED_DURATION_SEC:
                            self.unfocused_alert_active = True
                            text_color = "#FF2222"
                            focus_status_text = "⚠️ UNFOCUSED ALERT (>15s above 2.0x baseline!)"
                        else:
                            self.unfocused_alert_active = False
                            text_color = "#FFAA00"
                            focus_status_text = f"Unfocused Pending ({unfocused_elapsed:.1f}s / {UNFOCUSED_DURATION_SEC:.0f}s)"
                    else:
                        self.unfocused_start_time = None
                        self.unfocused_alert_active = False
                        text_color = "#00FF66"
                        focus_status_text = "Focused"

                    # Peak Frequencies & Amplitudes
                    f_pos_a, P_pos_a, alpha_freq, alpha_amp = find_peak(
                        filtered_alpha, self.srate, band_low=8.0, band_high=13.0
                    )
                    f_pos_b, P_pos_b, beta_freq, beta_amp = find_peak(
                        filtered_beta, self.srate, band_low=13.0, band_high=30.0
                    )

                    # CSV Results Logging
                    self.results_writer.writerow([
                        datetime.now().strftime("%H:%M:%S.%f"),
                        f"{alpha_freq:.2f}", f"{alpha_amp:.2f}",
                        f"{beta_freq:.2f}", f"{beta_amp:.2f}",
                        f"{alpha_power:.4f}", f"{beta_power:.4f}",
                        f"{ab_ratio:.4f}", f"{self.baseline_ratio:.4f}",
                        f"{self.current_pitch_deg:.2f}", f"{self.baseline_pitch:.2f}",
                        int(self.tilt_alert_active), int(self.unfocused_alert_active)
                    ])

                    self.hud_label.configure(fg=text_color)
                    self.ratio_hud_var.set(
                        f"Alpha/Beta Ratio: {ab_ratio:.2f} | Focus Index: {ba_ratio:.2f} | Baseline Ratio: {self.baseline_ratio:.2f} (Limit: {unfocused_limit:.2f}) | Status: {focus_status_text}"
                    )

                    # Update Lines
                    self.line_alpha.set_ydata(filtered_alpha)
                    self.line_beta.set_ydata(filtered_beta)
                    self.line_ab_ratio.set_ydata(self.ab_history)
                    self.line_baseline.set_ydata([self.baseline_ratio, self.baseline_ratio])

                    # Dynamic Y-Axis Autoscaling for Time-Domain EEG Subplots
                    a_min, a_max = float(np.min(filtered_alpha)), float(np.max(filtered_alpha))
                    if a_max - a_min < 1e-3:
                        a_min, a_max = a_min - 1.0, a_max + 1.0
                    self.ax_alpha.set_ylim(a_min * 1.15, a_max * 1.15)

                    b_min, b_max = float(np.min(filtered_beta)), float(np.max(filtered_beta))
                    if b_max - b_min < 1e-3:
                        b_min, b_max = b_min - 1.0, b_max + 1.0
                    self.ax_beta.set_ylim(b_min * 1.15, b_max * 1.15)

                    # Dynamic Y-Axis Autoscaling for Live A/B Ratio Subplot
                    ab_min, ab_max = float(np.min(self.ab_history)), float(np.max(self.ab_history))
                    if ab_max - ab_min < 0.1:
                        ab_min, ab_max = ab_min - 0.2, ab_max + 0.2
                    self.ax_ab_ratio.set_ylim(max(0.0, ab_min * 0.9), ab_max * 1.15)

                    # Dynamic Y-Axis Autoscaling for FFT Power Spectra Subplots
                    alpha_mask = f_pos_a <= 40
                    self.line_alpha_fft.set_data(f_pos_a[alpha_mask], P_pos_a[alpha_mask])
                    self.marker_alpha_fft.set_data([alpha_freq], [alpha_amp])
                    self.ax_alpha_fft.set_ylim(0, max(0.1, np.max(P_pos_a[alpha_mask]) * 1.15))

                    beta_mask = f_pos_b <= 40
                    self.line_beta_fft.set_data(f_pos_b[beta_mask], P_pos_b[beta_mask])
                    self.marker_beta_fft.set_data([beta_freq], [beta_amp])
                    self.ax_beta_fft.set_ylim(0, max(0.1, np.max(P_pos_b[beta_mask]) * 1.15))

                    self.canvas.draw_idle()

        self._after_id = self.after(REDRAW_MS, self._update)

    # -- Clean Shutdown ----------------------------------------------------
    def on_close(self):
        try:
            self.disconnect()
        finally:
            self.destroy()


if __name__ == "__main__":
    ReceiverApp().mainloop()
