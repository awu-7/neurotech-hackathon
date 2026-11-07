import os
import csv
import time
from datetime import datetime
import numpy as np
from scipy.signal import butter, filtfilt
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore
from pylsl import StreamInlet, resolve_byprop

# System Parameters
Fs = 250             # Sampling frequency in Hz (NeuroPawn default)
BUFFER_LEN = Fs * 2  # 2-second sliding window
PROCESS_EVERY = 10   # Process/update plots every N incoming samples

# Locate and connect to LSL EEG stream
print("Searching for active 'EEG' stream on LSL...")
streams = resolve_byprop('type', 'EEG', timeout=5.0)

if not streams:
    # Fallback check for lowercase 'eeg'
    streams = resolve_byprop('type', 'eeg', timeout=2.0)

if not streams:
    raise RuntimeError(
        "No LSL EEG stream found. Ensure NeuroPawn desktop software is running, "
        "connected to COM7, and actively broadcasting the LSL stream."
    )

inlet = StreamInlet(streams[0])
print(f"Connected to LSL Stream: {streams[0].name()}")

# 8-channel rolling buffer
data_buffer = np.zeros((BUFFER_LEN, 8))

# Bandpass Filter Coefficients (Nyquist = Fs / 2)
nyq = Fs / 2.0
b_alpha, a_alpha = butter(4, [8.0 / nyq, 13.0 / nyq], btype='band')
b_beta, a_beta = butter(4, [13.0 / nyq, 30.0 / nyq], btype='band')

# File Logging Setup
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

print(f"Logging raw data to: {log_filename}")
print(f"Logging results to:  {results_filename}")

# PyQtGraph UI Setup
app = pg.mkQApp("EEG Analysis")
win = pg.GraphicsLayoutWidget(show=True, title="Live Alpha & Beta Brainwaves (Channel 1)")
win.resize(1000, 700)

# Time-Domain Plots
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

# Frequency-Domain (FFT) Plots
plot_alpha_FFT = win.addPlot(title="Alpha FFT")
curve_alpha_FFT = plot_alpha_FFT.plot(pen='c')
alpha_peak_marker = plot_alpha_FFT.plot(pen=None, symbol='o', symbolBrush='r', symbolSize=10)
plot_alpha_FFT.setLabel('bottom', 'Frequency (Hz)')
plot_alpha_FFT.setLabel('left', 'Magnitude')
plot_alpha_FFT.setXRange(0, 40)
plot_alpha_FFT.enableAutoRange(axis='y', enable=True)

plot_beta_FFT = win.addPlot(title="Beta FFT")
curve_beta_FFT = plot_beta_FFT.plot(pen='c')
beta_peak_marker = plot_beta_FFT.plot