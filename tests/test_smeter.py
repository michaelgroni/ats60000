"""Tests für die S-Meter-Umrechnung (Firmware-Tabelle Utils.cpp:421)."""

import unittest

from ats_mini_remote import protocol


class SMeterHFTest(unittest.TestCase):
    def test_hf_scale(self):
        cases = [
            (0, "S0"), (1, "S0"),
            (2, "S1"), (3, "S2"), (4, "S3"),
            (10, "S4"), (16, "S5"), (22, "S6"), (28, "S7"),
            (34, "S8"), (44, "S9"),
            (54, "S9+10"), (64, "S9+20"), (74, "S9+30"),
            (84, "S9+40"), (94, "S9+50"), (95, "S9+60"),
            (96, ">S9+60"), (127, ">S9+60"),
        ]
        for rssi, expected in cases:
            self.assertEqual(protocol.s_meter(rssi, fm=False), expected,
                             f"HF: rssi={rssi}")

    def test_fm_scale(self):
        cases = [
            (0, "S0"), (1, "S0"), (2, "S6"), (8, "S7"), (14, "S8"),
            (24, "S9"), (34, "S9+10"), (44, "S9+20"), (54, "S9+30"),
            (64, "S9+40"), (74, "S9+50"), (76, "S9+60"),
            (77, ">S9+60"), (127, ">S9+60"),
        ]
        for rssi, expected in cases:
            self.assertEqual(protocol.s_meter(rssi, fm=True), expected,
                             f"FM: rssi={rssi}")


if __name__ == "__main__":
    unittest.main()
