"""Tests für die Lautstärkesteuerung (Burst-Verfahren)."""

import unittest

from ats_mini_remote import protocol


class VolumeBurstTest(unittest.TestCase):
    def test_up_burst(self):
        self.assertEqual(protocol.volume_burst(30, 40), b"V" * 10)

    def test_down_burst(self):
        self.assertEqual(protocol.volume_burst(40, 30), b"v" * 10)

    def test_no_change_no_burst(self):
        self.assertEqual(protocol.volume_burst(30, 30), b"")

    def test_single_step(self):
        self.assertEqual(protocol.volume_burst(10, 11), b"V")
        self.assertEqual(protocol.volume_burst(11, 10), b"v")

    def test_burst_is_single_message(self):
        # Der Burst muss als EIN zusammenhängender Bytestrom übertragbar
        # sein, nicht als viele einzelne Sendevorgänge.
        burst = protocol.volume_burst(0, 63)
        self.assertEqual(len(burst), 63)
        self.assertEqual(burst.count(b"V"), 63)


if __name__ == "__main__":
    unittest.main()
