# NeuroLearn Flask status synchronization

Run all commands from the same extracted folder, in **three separate terminals**:

1. Install requirements: `py -m pip install flask numpy scipy matplotlib pylsl customtkinter pyautogui`
2. `py status_server.py` — MUST remain open; listens at http://127.0.0.1:5001
3. `py test.py` — connect to NeuroPawnKnight EEG stream; once data starts arriving, it POSTs the exact UI focus label to Flask
4. `py desktop_app.py` — reads Flask every ~300 ms and mirrors the same label **even before starting a session**. Click Start Session only for distraction timer and rewind.

Optional: `py neuropawngui.py` separately, to see raw EEG. The original bridge.py is included for other events and continues on port 8765.

## Troubleshoot

Open http://127.0.0.1:5001/health in your browser. Expected: `{"ok":true,...}`.

Open http://127.0.0.1:5001/api/status in your browser. When test.py is receiving EEG data, `"live":true`, and `"display"` is its current focus label. `"live":false` means no recent updates from test.py (or it was paused/closed).

Test without EEG by running this in another terminal (PowerShell):

`Invoke-RestMethod -Uri http://127.0.0.1:5001/api/status -Method Post -ContentType 'application/json' -Body '{"status":"unfocused","display":"UNFOCUSED ALERT"}'`

The desktop label should say UNFOCUSED ALERT immediately (until the server reports the status stale ~3s later). If test.py is running it will override the test payload with real data.

The app displays three test.py states: Focused / Unfocused Pending (0-15 seconds above threshold) / UNFOCUSED ALERT (after 15 seconds). The latter two both start the distraction timer if a desktop session is active.

This server is intentionally bound to loopback (127.0.0.1); both applications must run on the same machine. If running on separate computers, the URL and security configuration must be changed.

## Timestamped logs (added for debugging)

All three programs print timestamps in their terminals and also save logs in the `logs` subfolder:

- `logs/test_sender.log`: `SENT to Flask | status=pending ...` or send errors.
- `logs/server.log`: `RECEIVED from test.py | status=pending ...`.
- `logs/desktop.log`: `DISPLAY UPDATED | status=pending ...` or offline/stale messages.

Logs report every status *transition*, plus a heartbeat about every 10 seconds to avoid flooding your terminal. The dynamic countdown (for example `Unfocused Pending (3.5s / 15s)`) still updates on screen as the desktop polls the server. Compare the three log timestamps when you see a mismatch.

### Test the plumbing without wearing a headset

With `status_server.py` and `desktop_app.py` running, run `py simulate_status.py` in a third terminal. It sends Focused, Unfocused Pending, UNFOCUSED ALERT, and Focused in sequence. The desktop should show each state, and all three logs (except `test_sender.log` when `test.py` is not running) should register the change. **Close `test.py` for this test** so its real stream does not overwrite the simulator's changes.

If the simulated sequence appears correctly, the remaining problem is likely in whether `test.py` is receiving and processing EEG samples. If it does not appear, inspect the server and desktop log errors. Logs have no EEG raw data, but they do include focus status and alpha/beta ratio values.
