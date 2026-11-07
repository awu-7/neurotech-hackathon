import numpy as np
from scipy.signal import butter, filtfilt
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore
import csv
from datetime import datetime
import os
import time
from pylsl import StreamInlet, resolve_stream

# Setup
Fs = 250             # NeuroPawn default EEG sampling rate
BUFFER_LEN = Fs * 2  # 2-second sliding window
PROCESS_EVERY = 10   # process/plot every N samples

print("Looking for an active EEG stream...")
streams = resolve_stream('type', 'EEG')
if not streams:
    raise RuntimeError("No stream found. Ensure the LSL stream is active.")

inlet = StreamInlet(streams[0])
print(f"Successfully connected to stream: {streams[0].name()}")

# Updated buffer to hold all 8 channels (we will extract CH1 for the plot)
data_buffer = np.zeros((BUFFER_LEN, 8))

# Bandpass filters for Alpha and Beta
nyq = Fs / 2

# Alpha filter (8-13 Hz)
alpha_low = 8 / nyq
alpha_high = 13 / nyq
b_alpha, a_alpha = butter(4, [alpha_low, alpha_high], btype='band')

# Beta filter (13-30 Hz)
beta_low = 13 / nyq
beta_high = 30 / nyq
b_beta, a_beta = butter(4, [beta_low, beta_high], btype='band')

# Logging
log_dir = "log"
os.makedirs(log_dir, exist_ok=True)
timestamp_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
log_filename = os.path.join(log_dir, f"eeg_raw_{timestamp_tag}.csv")
results_filename = os.path.join(log_dir, f"eeg_results_{timestamp_tag}.csv")

log_file = open(log_filename, "w", newline="")
log_writer = csv.writer(log_file)
# Logging all 8 channels to keep the raw data intact for later analysis
log_writer.writerow(["timestamp", "CH1", "CH2", "CH3", "CH4", "CH5", "CH6", "CH7", "CH8"])

results_file = open(results_filename, "w", newline="")
results_writer = csv.writer(results_file)
results_writer.writerow(["timestamp", "alphaPeakFreqHz", "alphaPeakAmp", "betaPeakFreqHz", "betaPeakAmp"])

print(f"Logging raw data to: {log_filename}")
print(f"Logging EEG results to: {results_filename}")

# Plot setup
app = pg.mkQApp("EEG Analysis")
win = pg.GraphicsLayoutWidget(show=True, title="Live Alpha & Beta Brainwaves (Channel 1)")
win.resize(1000, 700)

# Alpha time domain plot
plot_alpha = win.addPlot(title="Alpha Band (8-13 Hz)")
curve_alpha = plot_alpha.plot(pen='y')
plot_alpha.setLabel('bottom', 'Sample')
plot_alpha.setLabel('left', 'Amplitude')

# Beta time domain plot
plot_beta = win.addPlot(title="Beta Band (13-30 Hz)")
curve_beta = plot_beta.plot(pen='m')
plot_beta.setLabel('bottom','Sample')
plot_beta.setLabel('left', 'Amplitude')

win.nextRow()

# Alpha FFT plot
plot_alpha_FFT = win.addPlot(title="Alpha FFT")
curve_alpha_FFT = plot_alpha_FFT.plot(pen='c')
alpha_peak_marker = plot_alpha_FFT.plot(pen=None, symbol='o', symbolBrush='r', symbolSize=10)
plot_alpha_FFT.setLabel('bottom', 'Frequency (Hz)')
plot_alpha_FFT.setLabel('left', 'Magnitude')

# Beta FFT plot
plot_beta_FFT = win.addPlot(title="Beta FFT")
curve_beta_FFT = plot_beta_FFT.plot(pen='c')
beta_peak_marker = plot_beta_FFT.plot(pen=None, symbol='o', symbolBrush='r', symbolSize=10)
plot_beta_FFT.setLabel('bottom', 'Frequency (Hz)')
plot_beta_FFT.setLabel('left', 'Magnitude')

# Adjust axes
plot_alpha.setXRange(0, BUFFER_LEN)
plot_alpha.enableAutoRange(axis='x', enable=False)
plot_alpha.hideButtons()

plot_alpha_FFT.setXRange(0, 40)        # 0-40 Hz to view both bands comfortably
plot_alpha_FFT.enableAutoRange(axis='x', enable=False)
plot_alpha_FFT.getViewBox().setLimits(yMin=0)
plot_alpha