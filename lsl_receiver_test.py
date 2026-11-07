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

WINDOW_SECONDS = 5.0     # sliding window length for signal analysis
REDRAW_MS = 40           # ~25 FPS redraw timer


def find_peak(filtered_signal, srate, band_low, band_high):
    """Computes FFT and identifies the frequency and amplitude of the peak power within a specific band."""
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
        self.title("NeuroPawn Knight - LSL Alpha/Beta Analyzer")
        self.geometry("1050x750")

        self.inlet = None
        self.srate = 250.0
        self.n_channels = 0
        self.labels = []
        self.buffer = None       # shape (n_channels, n_samples)
        self.streams = []
        self._after_id = None

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

        ttk.Label(top, text="Stream:").pack(side="left", padx=4)
        self.stream_var = tk.StringVar()
        self.stream_combo = ttk.Combobox(
            top, textvariable=self.stream_var, width=30, state="readonly"
        )
        self.stream_combo.pack(side="left", padx=4)

        ttk.Button(top, text="Refresh", command=self.refresh_streams).pack(
            side="left", padx=4
        )
        self.connect_btn = ttk.Button(
            top, text="Connect", command=self.toggle_connect
        )
        self.connect_btn.pack(side="left", padx=4)

        ttk.Label(top, text="Scale (uV):").pack(side="left", padx=(16, 4))
        self.scale_var = tk.DoubleVar(value=200.0)
        ttk.Spinbox(
            top, from_=1, to=100000, increment=50, width=8,
            textvariable=self.scale_var,
        ).pack(side="left", padx=4)

        self.status_var = tk.StringVar(value="Not connected.")
        ttk.Label(self, textvariable=self.status_var).pack(
            side="bottom", fill="x", padx=6, pady=2
        )

        # 2x2 Grid Plotting Figure
        self.fig = Figure(figsize=(10, 6), dpi=100)
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

    # -- Connection & CSV Setup ---------------------------------------------
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

        n_samples = max(1, int(self.srate * WINDOW_SECONDS))
        self.buffer = np.zeros((self.n_channels, n_samples), dtype=np.float64)

        # Filter Design Coefficients based on stream sampling rate
        nyq = self.srate / 2.0
        self.b_alpha, self.a_alpha = butter(4, [8.0 / nyq, 13.0 / nyq], btype='band')
        self.b_beta, self.a_beta = butter(4, [13.0 / nyq, 30.0 / nyq], btype='band')

        # Initialize CSV Logging
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
            "timestamp", "alphaPeakFreqHz", "alphaPeakAmp", "betaPeakFreqHz", "betaPeakAmp"
        ])

        self._build_axes()
        self.connect_btn.configure(text="Disconnect")
        self.status_var.set(
            f"Connected to {info.name()} - {self.n_channels} ch @ {self.srate:.0f} Hz. Logging active."
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

        # Close CSV File Handlers safely
        if self.log_file and not self.log_file.closed:
            self.log_file.close()
        if self.results_file and not self.results_file.closed:
            self.results_file.close()

        self.connect_btn.configure(text="Connect")
        self.status_var.set("Disconnected. Logs saved to /log directory.")

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

    # -- Plotting Setup (2x2 Grid) ------------------------------------------
    def _build_axes(self):
        self.fig.clear()

        # 2x2 Subplot Layout for Channel 1 Signal Analysis
        self.ax_alpha = self.fig.add_subplot(2, 2, 1)
        self.ax_beta = self.fig.add_subplot(2, 2, 2)
        self.ax_alpha_fft = self.fig.add_subplot(2, 2, 3)
        self.ax_beta_fft = self.fig.add_subplot(2, 2, 4)

        n_samples = self.buffer.shape[1]
        t = np.linspace(-WINDOW_SECONDS, 0, n_samples)
        target_ch_name = self.labels[0]

        # Time-Domain Lines
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

        # FFT Lines & Peak Markers
        (self.line_alpha_fft,) = self.ax_alpha_fft.plot([], [], color='cyan', linewidth=1.0)
        (self.marker_alpha_fft,) = self.ax_alpha_fft.plot([], [], 'ro', markersize=6)
        self.ax_alpha_fft.set_title("Alpha FFT", fontsize=10)
        self.ax_alpha_fft.set_xlabel("Frequency (Hz)", fontsize=8)
        self.ax_alpha_fft.set_ylabel("Magnitude", fontsize=8)
        self.ax_alpha_fft.set_xlim(0, 40)
        self.ax_alpha_fft.set_ylim(bottom=0)

        (self.line_beta_fft,) = self.ax_beta_fft.plot([], [], color='cyan', linewidth=1.0)
        (self.marker_beta_fft,) = self.ax_beta_fft.plot([], [], 'ro', markersize=6)
        self.ax_beta_fft.set_title("Beta FFT", fontsize=10)
        self.ax_beta_fft.set_xlabel("Frequency (Hz)", fontsize=8)
        self.ax_beta_fft.set_ylabel("Magnitude", fontsize=8)
        self.ax_beta_fft.set_xlim(0, 40)
        self.ax_beta_fft.set_ylim(bottom=0)

        self.fig.tight_layout(pad=2.0)
        self.canvas.draw()

    # -- Processing & Update Loop -------------------------------------------
    def _update(self):
        if self.inlet is None:
            return

        chunk, timestamps = self.inlet.pull_chunk(timeout=0.0)
        if chunk:
            data = np.asarray(chunk, dtype=np.float64).T  # (n_channels, n_samples_pulled)
            k = data.shape[1]

            # Log incoming raw samples with timestamps to CSV
            for col_idx in range(k):
                ts = timestamps[col_idx] if timestamps else time.time()
                raw_sample = data[:, col_idx].tolist()
                self.log_writer.writerow([ts] + raw_sample)

            # Update sliding buffer
            if k >= self.buffer.shape[1]:
                self.buffer = data[:, -self.buffer.shape[1]:]
            else:
                self.buffer = np.roll(self.buffer, -k, axis=1)
                self.buffer[:, -k:] = data

            # Process Channel 1 (index 0) EEG data
            raw_eeg = self.buffer[0, :].copy()

            if not np.all(raw_eeg == 0):
                # Remove DC Offset
                raw_eeg -= np.mean(raw_eeg)

                # Filter Alpha and Beta bands
                filtered_alpha = np.nan_to_num(filtfilt(self.b_alpha, self.a_alpha, raw_eeg))
                filtered_beta = np.nan_to_num(filtfilt(self.b_beta, self.a_beta, raw_eeg))

                # Compute FFT & Detect Peak Frequencies / Amplitudes
                f_pos_a, P_pos_a, alpha_freq, alpha_amp = find_peak(
                    filtered_alpha, self.srate, band_low=8.0, band_high=13.0
                )
                f_pos_b, P_pos_b, beta_freq, beta_amp = find_peak(
                    filtered_beta, self.srate, band_low=13.0, band_high=30.0
                )

                # Log Peak Metrics to CSV
                self.results_writer.writerow([
                    datetime.now().strftime("%H:%M:%S.%f"),
                    f"{alpha_freq:.2f}", f"{alpha_amp:.2f}",
                    f"{beta_freq:.2f}", f"{beta_amp:.2f}"
                ])

                # Update Time-Domain Signals
                self.line_alpha.set_ydata(filtered_alpha)
                self.line_beta.set_ydata(filtered_beta)

                scale = self.scale_var.get()
                self.ax_alpha.set_ylim(-scale, scale)
                self.ax_beta.set_ylim(-scale, scale)

                # Update FFT Power Spectra & Markers
                alpha_mask = f_pos_a <= 40
                self.line_alpha_fft.set_data(f_pos_a[alpha_mask], P_pos_a[alpha_mask])
                self.marker_alpha_fft.set_data([alpha_freq], [alpha_amp])
                self.ax_alpha_fft.set_title(
                    f"Alpha FFT - Peak: {alpha_freq:.1f} Hz ({alpha_amp:.2f} uV)", fontsize=10
                )
                self.ax_alpha_fft.set_ylim(0, max(0.1, np.max(P_pos_a[alpha_mask]) * 1.15))

                beta_mask = f_pos_b <= 40
                self.line_beta_fft.set_data(f_pos_b[beta_mask], P_pos_b[beta_mask])
                self.marker_beta_fft.set_data([beta_freq], [beta_amp])
                self.ax_beta_fft.set_title(
                    f"Beta FFT - Peak: {beta_freq:.1f} Hz ({beta_amp:.2f} uV)", fontsize=10
                )
                self.ax_beta_fft.set_ylim(0, max(0.1, np.max(P_pos_b[beta_mask]) * 1.15))

                self.canvas.draw_idle()

        self._after_id = self.after(REDRAW_MS, self._update)

    # -- Shutdown Handling --------------------------------------------------
    def on_close(self):
        try:
            self.disconnect()
        finally:
            self.destroy()


if __name__ == "__main__":
    ReceiverApp().mainloop()
