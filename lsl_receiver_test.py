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

WINDOW_SECONDS = 5.0     # Sliding window length for signal analysis
REDRAW_MS = 40           # ~25 FPS redraw timer
TILT_THRESHOLD_DEG = 30.0# Tilt angle threshold (+30° forward, -30° backward)
TILT_DURATION_SEC = 5.0  # Required continuous duration threshold in seconds


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
        self.title("NeuroPawn Knight - LSL Cognitive Load & Posture Analyzer")
        self.geometry("1150x880")

        self.inlet = None
        self.srate = 250.0
        self.n_channels = 0
        self.labels = []
        self.buffer = None       # shape (n_channels, n_samples)
        self.streams = []
        self._after_id = None

        # Control States
        self.is_paused = False
        self.baseline_ratio = 1.0  # Default threshold baseline (below 1.0 is focused)

        # Calibration Variables
        self.is_calibrating = False
        self.calibration_samples = []
        self.calibration_end_time = 0.0
        self.calib_win = None

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
            top, text="Calibrate (5s)", command=self.start_calibration, state="disabled"
        )
        self.calib_btn.pack(side="left", padx=2)

        # Scale Spinbox
        ttk.Label(top, text="Scale (uV):").pack(side="left", padx=(12, 2))
        self.scale_var = tk.DoubleVar(value=200.0)
        ttk.Spinbox(
            top, from_=1, to=100000, increment=50, width=6,
            textvariable=self.scale_var,
        ).pack(side="left", padx=2)

        # Quit Button
        ttk.Button(top, text="Quit", command=self.on_close).pack(
            side="right", padx=6
        )

        # Real-Time Telemetry HUD Banner
        hud_frame = tk.Frame(self, bg="#181818", bd=2, relief="groove")
        hud_frame.pack(side="top", fill="x", padx=6, pady=(0, 2))

        self.ratio_hud_var = tk.StringVar(
            value="Alpha/Beta Ratio: -- | Focus Index: -- | Baseline: 1.00"
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

        # Figure GridSpec (Time-domain plots larger, Power band plots smaller)
        self.fig = Figure(figsize=(10, 6.2), dpi=100)
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

    # -- Connection & IMU Index Detection ----------------------------------
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

        # Detect Accelerometer Channels for Head Posture (Default mapping: 8=X, 9=Y, 10=Z)
        self.acc_x_idx = self._find_channel_index(["ACC_X", "ACCEL_X", "AX"], fallback=8 if self.n_channels >= 11 else None)
        self.acc_y_idx = self._find_channel_index(["ACC_Y", "ACCEL_Y", "AY"], fallback=9 if self.n_channels >= 11 else None)
        self.acc_z_idx = self._find_channel_index(["ACC_Z", "ACCEL_Z", "AZ"], fallback=10 if self.n_channels >= 11 else None)

        self.tilt_start_time = None
        self.tilt_alert_active = False

        n_samples = max(1, int(self.srate * WINDOW_SECONDS))
        self.buffer = np.zeros((self.n_channels, n_samples), dtype=np.float64)

        # Filter Design Coefficients based on sampling rate
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
            "baselineRatio", "pitchDeg", "postureAlert"
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
        self.ratio_hud_var.set("Alpha/Beta Ratio: -- | Focus Index: -- | Baseline: 1.00")
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

    # -- Calibration Feature -----------------------------------------------
    def start_calibration(self):
        if self.inlet is None:
            return

        self.is_calibrating = True
        self.calibration_samples = []
        self.calibration_end_time = time.time() + 5.0

        self.calib_win = tk.Toplevel(self)
        self.calib_win.title("Baseline Focus Calibration")
        self.calib_win.geometry("400x350")
        self.calib_win.configure(bg="#111111")
        self.calib_win.transient(self)
        self.calib_win.grab_set()

        lbl = tk.Label(
            self.calib_win, 
            text="Focus intently on the dot below...", 
            font=("Arial", 12, "bold"), 
            fg="#FFFFFF", 
            bg="#111111"
        )
        lbl.pack(pady=15)

        canvas = tk.Canvas(self.calib_win, width=180, height=180, bg="#111111", highlightthickness=0)
        canvas.pack()
        canvas.create_oval(30, 30, 150, 150, fill="#00FFCC", outline="#FFFFFF", width=3)

        self.calib_timer_lbl = tk.Label(
            self.calib_win, 
            text="Time Remaining: 5.0s", 
            font=("Consolas", 11), 
            fg="#888888", 
            bg="#111111"
        )
        self.calib_timer_lbl.pack(pady=15)

    def _update_calibration(self, current_ab_ratio):
        remaining = self.calibration_end_time - time.time()
        self.calibration_samples.append(current_ab_ratio)

        if remaining > 0:
            if self.calib_timer_lbl and self.calib_win.winfo_exists():
                self.calib_timer_lbl.configure(text=f"Time Remaining: {remaining:.1f}s")
        else:
            self.is_calibrating = False
            if self.calibration_samples:
                self.baseline_ratio = float(np.mean(self.calibration_samples))

            if self.calib_win and self.calib_win.winfo_exists():
                self.calib_win.destroy()

            messagebox.showinfo(
                "Calibration Complete", 
                f"Baseline Alpha/Beta ratio set to: {self.baseline_ratio:.3f}"
            )

    # -- Subplot Setup (GridSpec for smaller power band graphs) ------------
    def _build_axes(self):
        self.fig.clear()
        gs = self.fig.add_gridspec(2, 2, height_ratios=[3, 1], hspace=0.35, wspace=0.2)

        self.ax_alpha = self.fig.add_subplot(gs[0, 0])
        self.ax_beta = self.fig.add_subplot(gs[0, 1])
        self.ax_alpha_fft = self.fig.add_subplot(gs[1, 0])
        self.ax_beta_fft = self.fig.add_subplot(gs[1, 1])

        n_samples = self.buffer.shape[1]
        t = np.linspace(-WINDOW_SECONDS, 0, n_samples)
        target_ch_name = self.labels[0]

        # Time-Domain Subplots
        (self.line_alpha,) = self.ax_alpha.plot(t, np.zeros(n_samples), color='gold', linewidth=1.0)
        self.ax_alpha.set_title(f"Alpha Band (8–13 Hz) - {target_ch_name}", fontsize=10)
        self.ax_alpha.set_xlabel("Time (s)", fontsize=8)
        self.ax_alpha.set_ylabel("uV", fontsize=8)
        self.ax_alpha.set_xlim(-WINDOW_SECONDS, 0)

        (self.line_beta,) = self.ax_beta.plot(t, np.zeros(n_samples), color='magenta', linewidth=1.0)
        self.ax_beta.set_title(f"Beta Band (13–30 Hz) - {target_ch_name}", fontsize=10)
        self.ax_beta.set_xlabel("Time (s)", fontsize=8)
        self.ax_beta.set_ylabel("uV", fontsize=8)
        self.ax_beta.set_xlim(-WINDOW_SECONDS, 0)

        # Smaller Power Band / FFT Subplots
        (self.line_alpha_fft,) = self.ax_alpha_fft.plot([], [], color='cyan', linewidth=1.0)
        (self.marker_alpha_fft,) = self.ax_alpha_fft.plot([], [], 'ro', markersize=5)
        self.ax_alpha_fft.set_title("Alpha Power Spectrum", fontsize=8)
        self.ax_alpha_fft.set_xlabel("Hz", fontsize=7)
        self.ax_alpha_fft.set_ylabel("Mag", fontsize=7)
        self.ax_alpha_fft.tick_params(labelsize=7)
        self.ax_alpha_fft.set_xlim(0, 40)
        self.ax_alpha_fft.set_ylim(bottom=0)

        (self.line_beta_fft,) = self.ax_beta_fft.plot([], [], color='cyan', linewidth=1.0)
        (self.marker_beta_fft,) = self.ax_beta_fft.plot([], [], 'ro', markersize=5)
        self.ax_beta_fft.set_title("Beta Power Spectrum", fontsize=8)
        self.ax_beta_fft.set_xlabel("Hz", fontsize=7)
        self.ax_beta_fft.set_ylabel("Mag", fontsize=7)
        self.ax_beta_fft.tick_params(labelsize=7)
        self.ax_beta_fft.set_xlim(0, 40)
        self.ax_beta_fft.set_ylim(bottom=0)

        self.canvas.draw()

    # -- Process IMU Head Tilt (+X Forward / -X Backward) ------------------
    def _process_posture(self):
        if self.acc_x_idx is None or self.acc_x_idx >= self.n_channels:
            self.posture_hud_var.set("Posture Status: IMU Accelerometer channels unavailable.")
            self.posture_label.configure(fg="#AAAAAA")
            return

        ax_val = self.buffer[self.acc_x_idx, -1]
        ay_val = self.buffer[self.acc_y_idx, -1] if self.acc_y_idx is not None else 0.0
        az_val = self.buffer[self.acc_z_idx, -1] if self.acc_z_idx is not None else 1.0

        # Pitch angle calculation in degrees (+X axis for forward tilt, -X for backward tilt)
        denom = np.sqrt(ay_val**2 + az_val**2)
        if denom < 1e-6:
            denom = 1e-6
        pitch_rad = np.arctan2(ax_val, denom)
        self.current_pitch_deg = float(np.degrees(pitch_rad))

        now = time.time()
        is_forward_tilt = self.current_pitch_deg > TILT_THRESHOLD_DEG
        is_backward_tilt = self.current_pitch_deg < -TILT_THRESHOLD_DEG
        is_tilted = is_forward_tilt or is_backward_tilt

        if is_tilted:
            tilt_dir = "FORWARD" if is_forward_tilt else "BACKWARD"
            if self.tilt_start_time is None:
                self.tilt_start_time = now

            elapsed = now - self.tilt_start_time
            if elapsed >= TILT_DURATION_SEC:
                self.tilt_alert_active = True
                self.posture_hud_var.set(
                    f"⚠️ POSTURE WARNING: Head tilted {tilt_dir} past 30° for {elapsed:.1f}s! (Tilt: {self.current_pitch_deg:.1f}°)"
                )
                self.posture_label.configure(fg="#FF2222")
            else:
                self.tilt_alert_active = False
                self.posture_hud_var.set(
                    f"Posture Warning Pending... Head tilted {tilt_dir} ({self.current_pitch_deg:.1f}°) for {elapsed:.1f}s / {TILT_DURATION_SEC:.0f}s"
                )
                self.posture_label.configure(fg="#FFAA00")
        else:
            self.tilt_start_time = None
            self.tilt_alert_active = False
            self.posture_hud_var.set(
                f"Posture Status: Good (Pitch: {self.current_pitch_deg:.1f}°)"
            )
            self.posture_label.configure(fg="#00FF66")

    # -- Main Update Loop --------------------------------------------------
    def _update(self):
        if self
