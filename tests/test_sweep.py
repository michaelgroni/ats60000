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
        # VHF: 44 MHz Spanne, FM-Raster 200 kHz -> 221 Punkte
        self.assertEqual(protocol.suggested_sweep_points("VHF", "FM"), 221)

    def test_small_band_gets_minimum(self):
        # 15M: 200 kHz Spanne, AM-Raster 10 kHz -> 21 Punkte
        self.assertEqual(protocol.suggested_sweep_points("15M", "AM"), 21)

    def test_medium_band(self):
        # 31M: 2 MHz, AM-Raster 10 kHz -> 201 Punkte
        self.assertEqual(protocol.suggested_sweep_points("31M", "AM"), 201)

    def test_ssb_resolves_single_signals(self):
        # 80M (500 kHz, SSB): ~1 kHz Raster, damit knapp 3 kHz breite
        # SSB-Signale einzeln unterscheidbar sind -> 500 (Deckelung)
        self.assertEqual(protocol.suggested_sweep_points("80M", "LSB"), 500)

    def test_ssb_40m(self):
        # 40M: 300 kHz -> 301 Punkte mit ~1 kHz Raster
        self.assertEqual(protocol.suggested_sweep_points("40M", "LSB"), 301)

    def test_unknown_band_fallback(self):
        self.assertEqual(protocol.suggested_sweep_points("XX", "AM"), 60)



class ModeStepsTest(unittest.TestCase):
    def test_am_to_lsb_needs_one_up(self):
        # Zyklus LSB -> USB -> AM -> LSB: AM -> LSB ist 1x M
        self.assertEqual(protocol.mode_steps("AM", "LSB"), b"M")

    def test_lsb_to_am_needs_one_down(self):
        self.assertEqual(protocol.mode_steps("LSB", "AM"), b"m")

    def test_same_mode_is_no_command(self):
        self.assertEqual(protocol.mode_steps("AM", "AM"), b"")
        self.assertEqual(protocol.mode_steps("LSB", "LSB"), b"")

    def test_fm_never_changes(self):
        # FM kann per Befehl weder betreten noch verlassen werden
        self.assertEqual(protocol.mode_steps("FM", "AM"), b"")
        self.assertEqual(protocol.mode_steps("AM", "FM"), b"")

    def test_shortest_path(self):
        # LSB -> AM: 1x m statt 2x M
        self.assertEqual(protocol.mode_steps("LSB", "AM"), b"m")
        # USB -> LSB: 1x m statt 2x M
        self.assertEqual(protocol.mode_steps("USB", "LSB"), b"m")


class ModeDefaultsTest(unittest.TestCase):
    def test_default_step_matches_firmware(self):
        # Menu.cpp: defaultStepIdx[4] = { 2, 5, 5, 1 } (FM, LSB, USB, AM)
        self.assertEqual(protocol.default_step("FM"), "100k")
        self.assertEqual(protocol.default_step("LSB"), "1k")
        self.assertEqual(protocol.default_step("USB"), "1k")
        self.assertEqual(protocol.default_step("AM"), "5k")

    def test_default_bandwidth_matches_firmware(self):
        # Menu.cpp: defaultBwIdx[4] = { 0, 4, 4, 4 } (FM, LSB, USB, AM)
        self.assertEqual(protocol.default_bandwidth("FM"), "Auto")
        self.assertEqual(protocol.default_bandwidth("LSB"), "3.0k")
        self.assertEqual(protocol.default_bandwidth("AM"), "3.0k")

    def test_ssb_step_list_matches_firmware(self):
        # Menu.cpp: ssbSteps hat 9 Eintraege (inkl. 9k, 10k)
        self.assertEqual(
            protocol.SSB_STEPS,
            ["10", "25", "50", "100", "500", "1k", "5k", "9k", "10k"])


class SuggestedPointsModeIndependenceTest(unittest.TestCase):
    def test_same_for_any_mode(self):
        # Empfehlung haengt nur vom Band ab, nicht vom eingestellten Modus
        for band in ("80M", "40M", "31M", "VHF"):
            values = {protocol.suggested_sweep_points(band, mode)
                      for mode in ("AM", "LSB", "USB")}
            self.assertEqual(len(values), 1, band)

    def test_80m_resolves_ssb_even_in_am(self):
        # 80M ist ein Amateurband: ~1-kHz-Raster, auch bei AM-Empfang
        self.assertEqual(protocol.suggested_sweep_points("80M", "AM"), 500)

    def test_ambiguous_band_uses_current_frequency(self):
        # '15M' ist Rundfunkband (AM, 18900-19100) und Amateurband (USB,
        # 21000-21500): ohne Frequenz zaehlt der Modus, mit Frequenz der
        # Bereich, in dem die aktuelle Frequenz liegt.
        self.assertEqual(protocol.suggested_sweep_points("15M", "AM"), 21)
        self.assertEqual(protocol.suggested_sweep_points("15M", "USB"), 500)
        # 19 MHz: Rundfunkband -> 10-kHz-Raster
        self.assertEqual(
            protocol.suggested_sweep_points("15M", "USB", 19_050_000), 21)
        # 21,2 MHz: Amateurband -> 1-kHz-Raster
        self.assertEqual(
            protocol.suggested_sweep_points("15M", "AM", 21_200_000), 500)


class BandTableModeTest(unittest.TestCase):
    def test_amateur_bands_are_ssb(self):
        self.assertEqual(protocol.band_table_mode("80M"), "LSB")
        self.assertEqual(protocol.band_table_mode("20M"), "USB")

    def test_broadcast_bands_are_am(self):
        self.assertEqual(protocol.band_table_mode("31M"), "AM")

    def test_vhf_is_fm(self):
        self.assertEqual(protocol.band_table_mode("VHF"), "FM")

    def test_unknown_band(self):
        self.assertIsNone(protocol.band_table_mode("XX"))


class MockModeSwitchTest(unittest.TestCase):
    """Mock bildet doMode() der Firmware nach: Defaults + Zyklus."""

    def setUp(self):
        from ats_mini_remote.mock_receiver import MockState
        self.state = MockState()
        # 80m-Band: Modi AM/LSB/USB laut Bandtabelle des Mocks
        idx = [b[0] for b in __import__(
            "ats_mini_remote.mock_receiver", fromlist=["BANDS"]).BANDS].index("80m")
        self.state.band_idx = idx

    def test_switch_resets_step_and_bandwidth_defaults(self):
        state = self.state
        state.mode_idx = 0            # AM
        state.step_idx = 3            # 10k
        state.bandwidth_idx = 0       # 1.0k
        state.rotate_mode(1)          # AM -> LSB
        self.assertEqual(state.mode(), "LSB")
        # defaultStepIdx[SSB] = 5 -> '1k', defaultBwIdx[SSB] = 4 -> '3.0k'
        self.assertEqual(state.step_desc(), "1k")
        self.assertEqual(state.bandwidth_desc(), "3.0k")

    def test_switch_back_restores_original_settings(self):
        state = self.state
        state.mode_idx = 0            # AM
        state.step_idx = 3            # 10k
        state.bandwidth_idx = 6       # 6.0k
        state.rotate_mode(1)          # -> LSB (Defaults 1k / 3.0k)
        state.rotate_mode(-1)         # -> AM (Defaults 5k / 3.0k)
        self.assertEqual(state.mode(), "AM")
        self.assertEqual(state.step_desc(), "5k")
        self.assertEqual(state.bandwidth_desc(), "3.0k")

    def test_step_desc_follows_mode(self):
        state = self.state
        state.mode_idx = 1            # LSB (SSB-Liste)
        self.assertIn(state.step_desc(),
                      ["10", "25", "50", "100", "500", "1k", "5k", "9k", "10k"])


class SweepSetupOrderTest(unittest.TestCase):
    """Befehlsfolge fuer einen Sweep mit Moduswechsel (80M, AM eingestellt)."""

    def test_mode_switch_commands(self):
        # AM -> LSB: 1x M; danach Schrittweite/Bandbreite setzen
        self.assertEqual(protocol.mode_steps("AM", "LSB"), b"M")
        self.assertEqual(protocol.band_table_mode("80M"), "LSB")
        # Nach Rueckwechsel LSB -> AM: Defaults 5k/3.0k auf Originalwerte
        # zurueckstellen (hier: Original 10k/6.0k)
        step_cmd = protocol.step_steps(protocol.default_step("AM"), "10k", "AM")
        bw_cmd = protocol.bandwidth_steps(
            protocol.default_bandwidth("AM"), "6.0k", "AM")
        self.assertTrue(step_cmd)
        self.assertTrue(bw_cmd)


class ModeSwitchSweepIntegrationTest(unittest.TestCase):
    """Moduswechsel gegen den Mock: Defaults, Rueckwechsel, Restore."""

    def setUp(self):
        import threading
        from ats_mini_remote.mock_receiver import MockServer, MockState
        from ats_mini_remote.client import RemoteClient
        self._RemoteClient = RemoteClient
        self._threading = threading
        sock = __import__("socket").socket()
        sock.bind(("127.0.0.1", 0))
        self.port = sock.getsockname()[1]
        sock.close()
        state = MockState()
        idx = [b[0] for b in __import__(
            "ats_mini_remote.mock_receiver", fromlist=["BANDS"]).BANDS].index("80m")
        state.band_idx = idx
        self.server = MockServer(address=("127.0.0.1", self.port), state=state)
        self.state = state
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        threading.Thread(target=self.server.status_loop,
                         kwargs={"interval": 0.05}, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def _status(self, client):
        import time
        deadline = time.time() + 3
        last = None
        while time.time() < deadline:
            with self.state.lock:
                if self.state.mode() == "LSB":
                    return True
            time.sleep(0.02)
        return False

    def test_mode_switch_and_restore(self):
        import time
        client = self._RemoteClient()
        client.connect("127.0.0.1", self.port)
        try:
            client.send(b"t")
            time.sleep(0.3)
            with self.state.lock:
                self.assertEqual(self.state.mode(), "AM")
            client.send(b"M")          # AM -> LSB
            time.sleep(0.3)
            with self.state.lock:
                self.assertEqual(self.state.mode(), "LSB")
                self.assertEqual(self.state.step_desc(), "1k")
                self.assertEqual(self.state.bandwidth_desc(), "3.0k")
            client.send(b"m")          # LSB -> AM
            time.sleep(0.3)
            with self.state.lock:
                self.assertEqual(self.state.mode(), "AM")
        finally:
            client.disconnect()


if __name__ == "__main__":
    unittest.main()
