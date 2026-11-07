import sys
import os
import csv
import time
from datetime import datetime
import numpy as np
from scipy.signal import butter, filtfilt
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore
from pylsl import StreamInlet, resolve_byprop, resolve_streams
import traceback

def main():
    # 1. Initialize Qt App first
    app = pg.mkQApp("EEG Analysis")

    # 2. Parameters
    Fs = 250.0             # Sampling frequency (Hz)
    BUFFER_LEN = int(Fs * 2)  # 2-second sliding window
    PROCESS_EVERY = 10   # Process/update every N incoming samples

    print("Searching for LSL stream...")
    
    # Try resolving by type 'EEG', then 'eeg', then fallback to all streams
    streams = resolve_byprop('type', 'EEG', timeout=2.0)
    if not streams:
        streams = resolve_byprop('type', 'eeg', timeout=2.0)
    if not streams:
        print("No stream found by type 'EEG'. Scanning all active LSL streams...")
        all_streams = resolve_streams(wait_time=2.0)
        if all_streams:
            print(f"Found stream by name: '{all_streams[0].name()}' (Type: '{all_streams[0].type()}')")
            streams = [all_streams[0]]

    if not streams:
        print("\n[ERROR] No active LSL stream detected on the network.")
        print("1. Ensure NeuroPawn software is connected to COM7.")
        print("2. Ensure 'Start LSL' is toggled ON in the NeuroPawn GUI.")
        input("\nPress Enter to exit...")
        return

    inlet = StreamInlet(streams[0])
    print(f"Connected to LSL Stream: {streams[0].name()}")

    # 8-channel rolling buffer
    data_buffer = np.zeros((BUFFER_LEN, 8))

    # Bandpass Filter Setup
    nyq = Fs / 2.0
    b_alpha, a_alpha = butter(4, [8.0 / nyq, 13.0 / nyq], btype='band')
    b_beta, a_beta = butter(4, [13.0 / nyq, 30.0 / nyq], btype='band')

    # File Logging
    log_dir = "log"
    os.makedirs(log_dir, exist_ok=True)
    timestamp_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(log_dir, f"eeg_raw_{timestamp_tag}.csv")
    results_filename = os.path.join(log_dir, f"eeg_results_{timestamp_tag}.csv")

    log_file = open(log_filename, "w", newline="")
    log_writer = csv.writer(log_file)
    log_writer.writerow(["timestamp", "CH1", "CH2", "CH3", "CH4", "CH5", "CH6", "CH7", "CH8"])

    results_file = open(results_filename, "w", newline="")
    results_writer = csv.writer(results_file)
    results_writer.writerow(["timestamp", "alphaPeakFreqHz", "alphaPeakAmp", "betaPeakFreqHz", "betaPeakAmp"])

    # UI Setup
    win = pg.GraphicsLayoutWidget(show=True, title=f"Live Brainwaves - Stream: {streams[0].name()}")
    win.resize(1000, 700)

    plot_alpha = win.addPlot(title="Alpha Band (8–13 Hz) - CH1")
    curve_alpha = plot_alpha.plot(pen='y')
    plot_alpha.setLabel('bottom', 'Sample Index')
    plot_alpha.setLabel('left', 'Amplitude')
    plot_alpha.enableAutoRange(axis='y', enable=True)

    plot_beta = win.addPlot(title="Beta Band (13–30 Hz) - CH1")
    curve_beta = plot_beta.plot(pen='m')
    plot_beta.setLabel('bottom', 'Sample Index')
    plot_beta.setLabel('left', 'Amplitude')
    plot_beta.enableAutoRange(axis='y', enable=True)

    win.nextRow()

    plot_alpha_FFT = win.addPlot(title="Alpha FFT")
    curve_alpha_FFT = plot_alpha_FFT.plot(pen='c')
    alpha_peak_marker = plot_alpha_FFT.plot(pen=None, symbol='o', symbolBrush='r', symbolSize=10)
    plot_alpha_FFT.setLabel('bottom', 'Frequency (Hz)')
    plot_alpha_FFT.setLabel('left', 'Magnitude')
    plot_alpha_FFT.setXRange(0, 40)
    plot_alpha_FFT.enableAutoRange(axis='y', enable=True)

    plot_beta_FFT = win.addPlot(title="Beta FFT")
    curve_beta_FFT = plot_beta_FFT.plot(pen='c')
    beta_peak_marker = plot_beta_FFT.plot(pen=None, symbol='o', symbolBrush='r', symbolSize=10)
    plot_beta_FFT.setLabel('bottom', 'Frequency (Hz)')
    plot_beta_FFT.setLabel('left', 'Magnitude')
    plot_beta_FFT.setXRange(0, 40)
    plot_beta_FFT.enableAutoRange(axis='y', enable=True)

    sample_count = 0
    last_processed_count = 0

    def find_peak(filtered_signal, Fs, band_low, band_high):
        N = len(filtered_signal)
        Y = np.fft.fft(filtered_signal)
        f = np.fft.fftfreq(N, d=1/Fs)
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

    def analyze_eeg(buffer):
        raw_eeg = buffer[:, 0]
        if np.all(raw_eeg == 0):
            return

        raw_eeg = raw_eeg - np.mean(raw_eeg)

        filtered_alpha = np.nan_to_num(filtfilt(b_alpha, a_alpha, raw_eeg))
        filtered_beta = np.nan_to_num(filtfilt(b_beta, a_beta, raw_eeg))

        f_pos_a, P_pos_a, alpha_peak_freq, alpha_peak_amp = find_peak(filtered_alpha, Fs, band_low=8, band_high=13)
        f_pos_b, P_pos_b, beta_peak_freq, beta_peak_amp = find_peak(filtered_beta, Fs, band_low=13, band_high=30)

        results_writer.writerow([
            datetime.now().strftime("%H:%M:%S.%f"),
            f"{alpha_peak_freq:.2f}", f"{alpha_peak_amp:.2f}",
            f"{beta_peak_freq:.2f}", f"{beta_peak_amp:.2f}",
        ])

        curve_alpha.setData(filtered_alpha)
        curve_beta.setData(filtered_beta)

        alpha_mask = f_pos_a <= 40
        curve_alpha_FFT.setData(f_pos_a[alpha_mask], P_pos_a[alpha_mask])
        alpha_peak_marker.setData([alpha_peak_freq], [alpha_peak_amp])
        plot_alpha_FFT.setTitle(f"Alpha FFT - Peak: {alpha_peak_freq:.1f} Hz, Amp: {alpha_peak_amp:.2f}")

        beta_mask = f_pos_b <= 40
        curve_beta_FFT.setData(f_pos_b[beta_mask], P_pos_b[beta_mask])
        beta_peak_marker.setData([beta_peak_freq], [beta_peak_amp])
        plot_beta_FFT.setTitle(f"Beta FFT - Peak: {beta_peak_freq:.1f} Hz, Amp: {beta_peak_amp:.2f}")

    def update():
        nonlocal sample_count, last_processed_count, data_buffer
        try:
            samples, timestamps = inlet.pull_chunk(timeout=0.0)
            if samples:
                for val, ts in zip(samples, timestamps):
                    data_buffer = np.roll(data_buffer, -1, axis=0)
                    data_buffer[-1, :] = val
                    sample_count += 1
                    log_writer.writerow([ts] + list(val))

                if sample_count - last_processed_count >= PROCESS_EVERY:
                    analyze_eeg(data_buffer)
                    last_processed_count = sample_count
        except Exception as e:
            print(f"Error during loop: {e}")

    timer = QtCore.QTimer()
    timer.timeout.connect(update)
    timer.start(10)

    try:
        # Cross-version compatibility for pyqtgraph exec
        if hasattr(pg, 'exec'):
            pg.exec()
        else:
            app.exec_()
    finally:
        log_file.close()
        results_file.close()
        print("CSV files closed.")

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print("\n--- FATAL CRASH DETECTED ---")
        traceback.print_exc()
        input("\nPress Enter to exit...")
