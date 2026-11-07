
import pyautogui
import time

def rewind():
    pyautogui.press("left")

def forward():
    pyautogui.press("right")

def slow_down():
    pyautogui.hotkey("shift", ",")

def normal_speed():
    pyautogui.hotkey("shift", ".")

print("Switch to your YouTube video within 10 seconds.")
time.sleep(10)

print("Rewinding 10 seconds...")
rewind()
time.sleep(5)

print("Forwarding 10 seconds...")
forward()
time.sleep(5)

print("Slowing down...")
slow_down()
time.sleep(5)

print("Returning to normal speed...")
normal_speed()
