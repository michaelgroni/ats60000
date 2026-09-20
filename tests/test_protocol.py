"""Tests für die Protokollimplementierung."""

import unittest

from ats_mini_remote import protocol


class ParseStatusTest(unittest.TestCase):
    def test_valid_fm_status(self):
        line = "201,10000,0,0,VHF,FM,100k,Auto,1,30,32,25,1500,4.05,7"
        status = protocol.parse_status(line)
        self.assertIsNotNone(status)
        self.assertEqual(status.version, 201)
        self.assertEqual(status.frequency, 10000)  # 10-kHz-Schritte
        self.assertEqual(status.band, "VHF")
        self.assertEqual(status.mode, "FM")
        self.assertEqual(status.volume, 30)
        self.assertEqual(status.display_frequency_hz(), 100_000_000)

    def test_valid_ssb_status(self):
        line = "201,3700,150,25,80m,USB,100,2.5k,0,20,28,18,3200,3.90,42"
        status = protocol.parse_status(line)
        self.assertIsNotNone(status)
        self.assertEqual(status.mode, "USB")
        self.assertEqual(status.bfo, 150)
        self.assertEqual(status.display_frequency_hz(), 3_700_150)

    def test_invalid_lines(self):
        self.assertIsNone(protocol.parse_status(""))
        self.assertIsNone(protocol.parse_status("hallo welt"))
        self.assertIsNone(protocol.parse_status("1,2,3"))
        self.assertIsNone(protocol.parse_status("a,b,c,d,e,f,g,h,i,j,k,l,m,n,o"))


class MemoryLineTest(unittest.TestCase):
    def test_parse_memory(self):
        result = protocol.parse_memory_line("#01,VHF,107900000,FM")
        self.assertEqual(result, (1, "VHF", 107_900_000, "FM"))

    def test_parse_invalid(self):
        self.assertIsNone(protocol.parse_memory_line("01,VHF,107900000,FM"))
        self.assertIsNone(protocol.parse_memory_line("#01,VHF,abc,FM"))
        self.assertIsNone(protocol.parse_memory_line("#01,VHF,100000"))


class CommandFormatTest(unittest.TestCase):
    def test_frequency_command(self):
        cmd = protocol.format_frequency_command(107_900_000, ssb=False)
        self.assertEqual(cmd, b"F107900000\r\n")

    def test_frequency_command_ssb_keeps_hz(self):
        cmd = protocol.format_frequency_command(3_700_150, ssb=True)
        self.assertEqual(cmd, b"F3700150\r\n")

    def test_frequency_command_rejects_zero(self):
        with self.assertRaises(ValueError):
            protocol.format_frequency_command(0, ssb=False)

    def test_memory_command(self):
        cmd = protocol.format_memory_command(1, "VHF", 107_900_000, "FM")
        self.assertEqual(cmd, b"#01,VHF,107900000,FM\r\n")

    def test_memory_command_clear(self):
        cmd = protocol.format_memory_command(3, "MW", 0, "AM")
        self.assertEqual(cmd, b"#03,MW,0,AM\r\n")

    def test_memory_command_rejects_bad_slot(self):
        with self.assertRaises(ValueError):
            protocol.format_memory_command(0, "MW", 1000, "AM")
        with self.assertRaises(ValueError):
            protocol.format_memory_command(33, "MW", 1000, "AM")


class ScreenshotDecodeTest(unittest.TestCase):
    def _build(self, width=4, height=2, pixel=0x1234):
        # Headerzeile exakt wie von der Firmware: printf("%08x", htonl(v)),
        # im Hex-Stream therefore little-endian (Byte-Reihenfolge eines BMP)
        size = 14 + 40 + 12 + width * height * 2
        header_hex = (
            "424d"
            + size.to_bytes(4, "little").hex()
            + "00000000"
            + (14 + 40 + 12).to_bytes(4, "little").hex()
            + "28000000"
            + width.to_bytes(4, "little").hex()
            + height.to_bytes(4, "little").hex()
            + "01001000"
            + "03000000"
            + "00000000"
            + "00000000"
            + "00000000"
            + "00000000"
            + "00000000"
            + "00f80000"
            + "e0070000"
            + "1f000000"
        )
        lines = [header_hex]
        px_le = ((pixel & 0xFF) << 8) | (pixel >> 8)
        for _ in range(height):
            lines.append(f"{px_le:04x}" * width)
        return lines

    def test_decode_valid(self):
        shot = protocol.decode_screenshot(self._build(pixel=0x07E0))
        self.assertEqual(shot.width, 4)
        self.assertEqual(shot.height, 2)
        self.assertEqual(shot.rows[0][0], (0, 255, 0))  # 0x07E0 = reines Grün (565 -> 888)

    def test_decode_rejects_garbage(self):
        with self.assertRaises(ValueError):
            protocol.decode_screenshot(["zzzz", "nothex"])

    def test_decode_ignores_leading_blank_lines(self):
        lines = [""] + self._build()
        shot = protocol.decode_screenshot(lines)
        self.assertEqual((shot.width, shot.height), (4, 2))

    def test_decode_rejects_truncated(self):
        lines = self._build()
        with self.assertRaises(ValueError):
            protocol.decode_screenshot(lines[:-1])

    def test_ppm_output(self):
        shot = protocol.decode_screenshot(self._build())
        ppm = shot.to_ppm()
        self.assertTrue(ppm.startswith(b"P6\n4 2\n255\n"))
        self.assertEqual(len(ppm), len(b"P6\n4 2\n255\n") + 4 * 2 * 3)

    def test_bmp_output(self):
        shot = protocol.decode_screenshot(self._build())
        bmp = shot.to_bmp()
        self.assertEqual(bmp[:2], b"BM")
        size = int.from_bytes(bmp[2:6], "little")
        self.assertEqual(size, len(bmp))


class LocaleNumberTest(unittest.TestCase):
    def test_fmt_num_uses_active_locale(self):
        sep = protocol.decimal_separator()
        self.assertEqual(protocol.fmt_num(3.5, 1), "3" + sep + "5")

    def test_parse_float_accepts_both_separators(self):
        self.assertEqual(protocol.parse_float("3.5"), 3.5)
        self.assertEqual(protocol.parse_float(" 3,5 "), 3.5)
