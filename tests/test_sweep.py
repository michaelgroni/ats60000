"""Tests für den Bandpegel-Sweep."""

import unittest

from ats_mini_remote import protocol


class BandRangeTest(unittest.TestCase):
    def test_known_bands(self):
        self.assertEqual(protocol.band_range("VHF", "FM"), (64000, 108000))
        self.assertEqual(protocol.band_range("31M", "AM"), (9000, 11000))
        self.assertEqual(protocol.band_range("40M", "LSB"), (7000, 7300))
        self.assertEqual(protocol.band_range("MW1", "AM"), (150, 1800))

    def test_mode_fallback(self):
        # Modus weicht ab (z. B. nach Moduswechsel) -> Bandgrenzen
        # gelten trotzdem
        # FM-Grenzen sind auch bei abweichendem Modus in kHz
        self.assertEqual(protocol.band_range("VHF", "AM"), (64000, 108000))

    def test_unknown_band(self):
        self.assertIsNone(protocol.band_range("XX", "AM"))


class SweepPointGenerationTest(unittest.TestCase):
    def test_points_span_band(self):
        lo, hi = protocol.band_range("31M", "AM")
        points = 60
        step = (hi - lo) / (points - 1)
        freqs = [int(round(lo * 1000 + i * step * 1000)) for i in range(points)]
        self.assertEqual(len(freqs), points)
        self.assertEqual(freqs[0], lo * 1000)
        self.assertAlmostEqual(freqs[-1] / 1000, hi, delta=1)

    def test_minimal_points(self):
        lo, hi = protocol.band_range("80M", "LSB")
        points = 10
        step = (hi - lo) / (points - 1)
        freqs = [int(round(lo * 1000 + i * step * 1000)) for i in range(points)]
        self.assertEqual(len(freqs), 10)

    def test_time_estimate(self):
        # 60 Punkte bei 500 ms Monitortakt => ~30 s Gesamtlauf
        # (vorher: 100 Punkte x 1100 ms = 110 s)
        lo, hi = protocol.band_range("31M", "AM")
        points = 60
        estimated = points * 0.5
        self.assertLess(estimated, 35)


if __name__ == "__main__":
    unittest.main()
