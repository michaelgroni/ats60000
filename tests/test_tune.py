"""Tests für die kontextsichere Frequenzsteuerung (tune über F-Befehl)."""

import sys
import unittest

from ats_mini_remote import protocol
from tests.test_gui_headless import make_tkinter_mock


class StepHzTest(unittest.TestCase):
    def _step(self, step_desc: str, mode: str = "FM") -> int:
        status = protocol.ReceiverStatus(step=step_desc, mode=mode)
        return protocol.step_size_hz(status)

    def test_fm_steps(self):
        self.assertEqual(self._step("10k"), 10_000)
        self.assertEqual(self._step("50k"), 50_000)
        self.assertEqual(self._step("100k"), 100_000)
        self.assertEqual(self._step("1M"), 1_000_000)

    def test_ssb_steps_in_hz(self):
        self.assertEqual(self._step("25", "USB"), 25)
        self.assertEqual(self._step("100", "LSB"), 100)
        self.assertEqual(self._step("1k", "LSB"), 1000)

    def test_unknown_step_falls_back(self):
        self.assertEqual(self._step("", "AM"), 1000)
        self.assertEqual(self._step("x", "AM"), 1000)


class TuneCommandTest(unittest.TestCase):
    def test_tune_uses_f_command_not_encoder(self):
        # Der F-Befehl muss die Schrittweite addieren; R/r wäre
        # kontextabhängig (Menü) und ist verboten.
        status = protocol.ReceiverStatus(frequency=10000, mode="FM", step="100k")
        hz = status.display_frequency_hz()
        self.assertEqual(hz, 100_000_000)
        cmd = protocol.format_frequency_command(hz + 100_000, ssb=False)
        self.assertEqual(cmd, b"F100100000\r\n")
        self.assertNotIn(b"R", cmd)

    def test_ssb_tune_includes_bfo(self):
        status = protocol.ReceiverStatus(frequency=3700, bfo=150, mode="USB", step="100")
        hz = status.display_frequency_hz()
        self.assertEqual(hz, 3_700_150)
        cmd = protocol.format_frequency_command(hz + 100, ssb=True)
        self.assertEqual(cmd, b"F3700250\r\n")

    def test_tune_snaps_to_step_grid(self):
        """tune() muss auf Vielfache der Schrittweite landen.

        Liegt die aktuelle Frequenz auf dem Raster, ist es der normale
        Schritt; liegt sie daneben (BFO, manuelle Eingabe), springt der
        Schritt auf das naechste Vielfache in Klickrichtung.
        """
        make_tkinter_mock()
        for name in list(sys.modules):
            if name.startswith("ats_mini_remote.app"):
                del sys.modules[name]
        from ats_mini_remote import app as app_mod
        app = object.__new__(app_mod.RemoteApp)
        app.log = lambda msg: None
        sent = []
        app.send = lambda cmd: sent.append(cmd)

        # auf dem Raster (5 kHz): normaler Schritt
        app._last_status = protocol.ReceiverStatus(
            frequency=3_600, mode="AM", band="80M", step="5k")
        app.tune(+1)
        self.assertEqual(sent[-1], b"F3605000\r\n")
        app.tune(-1)
        self.assertEqual(sent[-1], b"F3595000\r\n")

        # neben dem Raster (3.602.017 Hz): naechstes Vielfaches in
        # Klickrichtung -- Up auf 3.605 MHz, Down auf 3.600 MHz
        app._last_status = protocol.ReceiverStatus(
            frequency=3_602, bfo=17, mode="AM", band="80M", step="5k")
        app.tune(+1)
        self.assertEqual(sent[-1], b"F3605000\r\n")
        app.tune(-1)
        self.assertEqual(sent[-1], b"F3600000\r\n")


if __name__ == "__main__":
    unittest.main()
