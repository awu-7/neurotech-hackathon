import serial, time

ser = serial.Serial("COM7", 115200, timeout=1)

for ch in range(1, 9):
    ser.write(f"chon_{ch}_12".encode("ascii"))
    time.sleep(2)
    ser.write(f"rldadd_{ch}".encode("ascii"))
    time.sleep(2)

import numpy as np

NUM_CHANNELS = 8
GAIN = 12
AFE_GAIN = 79.57  # fixed analog front-end gain
SCALE = 4.0 / (2**15 - 1) / AFE_GAIN / GAIN * 1_000_000.0  # µV per count

def read_eeg_sample(ser):
    if ser.read(1) != b"\xA0":
        return None
    payload = ser.read(20)               # counter + 8×EXG + 2 LOFF + end byte
    if payload[19] != 0xC0:
        return None
    sample = np.zeros(NUM_CHANNELS, dtype=np.float64)
    for i in range(NUM_CHANNELS):
        hi, lo = payload[1 + 2 * i], payload[2 + 2 * i]
        raw = (hi << 8) | lo
        if raw & 0x8000:
            raw -= 0x10000
        sample[i] = raw * SCALE
    return sample


from pylsl import StreamInfo, StreamOutlet

info = StreamInfo(
    name="NeuroPawnKnight",
    type="EEG",
    channel_count=NUM_CHANNELS,
    nominal_srate=125,
    channel_format="float32",
    source_id="neuropawn_knight",
)
channels = info.desc().append_child("channels")
for i in range(NUM_CHANNELS):
    ch = channels.append_child("channel")
    ch.append_child_value("label", f"EXG{i + 1}")
    ch.append_child_value("unit", "microvolts")
    ch.append_child_value("type", "EEG")

outlet = StreamOutlet(info)

while True:
    sample = read_eeg_sample(ser)
    if sample is not None:
        outlet.push_sample(sample.astype(np.float32).tolist())