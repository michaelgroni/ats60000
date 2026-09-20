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




class BandwidthSelectionTest(unittest.TestCase):
    def test_am_step_matches_bandwidth(self):
        # 31M: 2 MHz / 60 Punkte = ~33,3 kHz -> groesste AM-Breite 6.0k
        self.assertEqual(protocol.bandwidth_for_step(33.3, "AM"), "6.0k")

    def test_small_step_smallest_bandwidth(self):
        self.assertEqual(protocol.bandwidth_for_step(0.4, "LSB"), "0.5k")

    def test_fm_wide_step(self):
        self.assertEqual(protocol.bandwidth_for_step(100.0, "FM"), "110k")

    def test_steps_shortest_path(self):
        # AM: 6.0k (Index 6) -> 1.0k (Index 0): 1x w statt 6x W
        # AM-Liste ist zyklisch: 6.0k -> 1.0k ist EIN W-Schritt (wrap)
        self.assertEqual(protocol.bandwidth_steps("6.0k", "1.0k", "AM"),
                         b"W")
        self.assertEqual(protocol.bandwidth_steps("1.0k", "6.0k", "AM"),
                         b"w")


class AllBandRangeTest(unittest.TestCase):
    def test_all_band_uses_current_mhz(self):
        # 15,2 MHz -> Sweep 15000-16000 kHz
        self.assertEqual(
            protocol.sweep_points_for_band("ALL", "AM", 15_200_000),
            (15000, 16000))

    def test_all_band_clamps_to_band(self):
        # untere Bandgrenze 150 kHz: 0,15 MHz -> 150-1000 kHz
        self.assertEqual(
            protocol.sweep_points_for_band("ALL", "AM", 150_000),
            (150, 1150))

    def test_normal_band_unchanged(self):
        self.assertEqual(
            protocol.sweep_points_for_band("31M", "AM", 9_650_000),
            (9000, 11000))




class StepSelectionTest(unittest.TestCase):
    def test_step_lists_match_firmware(self):
        self.assertEqual(protocol.FM_STEPS,
                         ["10k", "50k", "100k", "200k", "1M"])
        self.assertEqual(protocol.AM_STEPS,
                         ["1k", "5k", "9k", "10k", "50k", "100k", "1M"])
        self.assertEqual(protocol.SSB_STEPS[0], "10")

    def test_step_hz(self):
        self.assertEqual(protocol.step_hz("10k"), 10_000)
        self.assertEqual(protocol.step_hz("1M"), 1_000_000)
        self.assertEqual(protocol.step_hz("25"), 25)

    def test_step_for_spacing_am(self):
        # 31M, 60 Punkte: ~33,3 kHz Abstand -> 50k
        self.assertEqual(protocol.step_for_spacing(33_333, "AM"), "50k")
        # 41M, 60 Punkte: ~33,4 kHz -> 50k
        self.assertEqual(protocol.step_for_spacing(33_400, "AM"), "50k")

    def test_step_shortest_path(self):
        # AM-Liste zyklisch: 1k -> 5k = 1x S, 1k -> 1M = 1x s (wrap)
        self.assertEqual(protocol.step_steps("1k", "5k", "AM"), b"S")
        self.assertEqual(protocol.step_steps("1k", "1M", "AM"), b"s")

    def test_aligned_sweep_freqs_on_grid(self):
        # 3500-4000 kHz, 50k-Raster -> 3500, 3550, ..., 4000
        freqs = protocol.aligned_sweep_freqs(3_500_000, 4_000_000, 50_000)
        self.assertEqual(freqs[0], 3_500_000)
        self.assertEqual(freqs[-1], 4_000_000)
        self.assertEqual(len(freqs), 11)
        self.assertTrue(all(f % 50_000 == 0 for f in freqs))

    def test_aligned_sweep_freqs_no_fit(self):
        # kein Rasterpunkt im Band -> leer (Sweep startet dann nicht)
        self.assertEqual(
            protocol.aligned_sweep_freqs(3_510_000, 3_530_000, 50_000), [])
        self.assertEqual(
            protocol.aligned_sweep_freqs(3_510_000, 3_540_000, 50_000), [])





class SuggestedPointsTest(unittest.TestCase):
    def test_vhf_gets_more_points(self):
        # VHF: 44 MHz Spanne -> 200 (Deckelung)
        self.assertEqual(protocol.suggested_sweep_points("VHF", "FM"), 200)

    def test_small_band_gets_minimum(self):
        # 15M: 200 kHz Spanne -> Minimum 10
        self.assertEqual(protocol.suggested_sweep_points("15M", "AM"), 10)

    def test_medium_band(self):
        # 31M: 2 MHz -> 21 Punkte
        self.assertEqual(protocol.suggested_sweep_points("31M", "AM"), 21)

    def test_unknown_band_fallback(self):
        self.assertEqual(protocol.suggested_sweep_points("XX", "AM"), 60)



if __name__ == "__main__":
    unittest.main()
