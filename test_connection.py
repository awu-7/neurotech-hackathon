"""Headset-free smoke test for the shared LSL FocusReceiver.
Run: python test_connection.py
"""
import sys
import time
import types
import unittest

from focus_link import FocusReceiver


class FakeInlet:
    def __init__(self, info, max_buflen=3):
        self.states = [[1], [0], [1]]

    def pull_sample(self, timeout=0.5):
        if self.states:
            return self.states.pop(0), 0.0
        time.sleep(min(timeout, 0.02))
        return None, None

    def close_stream(self):
        pass


class TestFocusConnection(unittest.TestCase):
    def test_receives_focus_transitions(self):
        fake = types.ModuleType('pylsl')
        fake.StreamInlet = FakeInlet
        fake.resolve_byprop = lambda *args, **kwargs: [object()]
        old = sys.modules.get('pylsl')
        sys.modules['pylsl'] = fake
        receiver = FocusReceiver()
        try:
            receiver.start()
            found = []
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and len(found) < 3:
                found += [value for kind, value in receiver.drain() if kind == 'state']
                time.sleep(0.01)
            self.assertEqual(found[:3], [True, False, True])
        finally:
            receiver.stop()
            if old is None:
                del sys.modules['pylsl']
            else:
                sys.modules['pylsl'] = old


if __name__ == '__main__':
    unittest.main()
