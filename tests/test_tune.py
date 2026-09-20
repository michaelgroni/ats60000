"""Tests für die kontextsichere Frequenzsteuerung (tune über F-Befehl)."""

import unittest

from ats_mini_remote import protocol


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


if __name__ == "__main__":
    unittest.main()
