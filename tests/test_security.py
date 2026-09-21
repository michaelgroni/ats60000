"""Sicherheitstests: manipulierte Gegenseite (boeswilliger 'Server').

Der Client vertraht dem Geraet am anderen Ende nicht: Statuszeilen,
Screenshot-Header und Zeilenlaengen werden auf plausible Grenzen
geprueft statt zu abstuerzen oder endlos Speicher zu sammeln.
"""

import socket
import threading
import unittest

from ats_mini_remote import protocol
from ats_mini_remote.client import RemoteClient


class MaliciousStatusTest(unittest.TestCase):
    """Manipulierte Statuszeilen duerfen weder crashen noch Riesenzahlen liefern."""

    def test_step_size_garbage_falls_back(self):
        for garbage in ("1e300k", "abc", "", "-5k", "99999999999999999999999k", "0"):
            status = protocol.ReceiverStatus(step=garbage)
            hz = protocol.step_size_hz(status)
            self.assertEqual(hz, 1000, msg=f"step={garbage!r}")

    def test_step_hz_garbage_falls_back(self):
        for garbage in ("1e300k", "abc", "", "-5k", "0.0000001M", "nan k"):
            self.assertEqual(protocol.step_hz(garbage), 1000,
                             msg=f"text={garbage!r}")

    def test_bandwidth_garbage_falls_back(self):
        for garbage in ("1e300k", "abc", "-1k", "0k", "1e40"):
            self.assertEqual(protocol.bandwidth_khz(garbage, fm=False), 6.0,
                             msg=f"text={garbage!r}")

    def test_parse_status_rejects_huge_fields(self):
        line = ("201," + "9" * 40 + ",0,0,VHF,FM,10k,Auto,0,30,32,25,1500,"
                "4.05,0")
        self.assertIsNone(protocol.parse_status(line))

    def test_parse_status_rejects_nan_voltage(self):
        line = "201,100000,0,0,VHF,FM,10k,Auto,0,30,32,25,1500,nan,0"
        self.assertIsNone(protocol.parse_status(line))

    def test_parse_status_rejects_inf_voltage(self):
        line = "201,100000,0,0,VHF,FM,10k,Auto,0,30,32,25,1500,inf,0"
        self.assertIsNone(protocol.parse_status(line))

    def test_parse_status_accepts_normal_line(self):
        line = "201,100000,0,0,VHF,FM,10k,Auto,0,30,32,25,1500,4.05,7"
        status = protocol.parse_status(line)
        self.assertIsNotNone(status)
        self.assertEqual(status.volume, 30)


class MaliciousScreenshotTest(unittest.TestCase):
    """Manipulierter Screenshot-Header/Inhalt fuehrt zu Fehler, nicht Crash."""

    def _header(self, width: int, height: int) -> str:
        size = 14 + 40 + 12 + width * height * 2
        header = bytearray()
        header += b"BM"
        header += size.to_bytes(4, "little")
        header += b"\x00\x00\x00\x00"
        header += (14 + 40 + 12).to_bytes(4, "little")
        header += (40).to_bytes(4, "little")
        header += width.to_bytes(4, "little")
        header += height.to_bytes(4, "little")
        header += b"\x01\x00"          # planes
        header += b"\x10\x00"          # bpp
        header += (3).to_bytes(4, "little")   # compression
        header += (0).to_bytes(4, "little")
        header += b"\x00" * 16
        header += b"\x00\xf8\x00\x00\xe0\x07\x00\x00\x1f\x00\x00\x00"
        return header.hex()

    def test_huge_dimensions_rejected(self):
        lines = [self._header(100_000, 1)]
        with self.assertRaises(ValueError):
            protocol.decode_screenshot(lines)

    def test_huge_payload_rejected(self):
        lines = [self._header(4096, 4096)]
        lines += ["0" * 32_768] * 100   # Hex, aber deutlich ueber 2 MiB roh
        with self.assertRaises(ValueError):
            protocol.decode_screenshot(lines)

    def test_normal_small_screenshot_decodes(self):
        lines = [self._header(4, 2), "00" * (4 * 2), "11" * (4 * 2)]
        shot = protocol.decode_screenshot(lines)
        self.assertEqual((shot.width, shot.height), (4, 2))


class MaliciousServerConnectionTest(unittest.TestCase):
    """Ein boeswilliger Server, der endlose Zeilen sendet, trennt der Client."""

    def _serve(self, ready: threading.Event, data_fn):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        ready.set()

        def run():
            conn, _ = server.accept()
            try:
                data_fn(conn)
            except OSError:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass
                server.close()

        threading.Thread(target=run, daemon=True).start()
        return port

    def test_overlong_line_disconnects(self):
        ready = threading.Event()

        def spam(conn):
            conn.sendall(b"A" * (RemoteClient._MAX_LINE_BYTES + 4096))

        port = self._serve(ready, spam)
        ready.wait(2)

        received = []
        client = RemoteClient(on_disconnect=received.append)
        client.connect("127.0.0.1", port)
        for _ in range(200):
            if received:
                break
            threading.Event().wait(0.02)
        client.disconnect()
        self.assertTrue(received, "Client muss bei ueberlanger Zeile trennen")
        self.assertFalse(client.is_connected())

    def test_screenshot_abort_on_garbage_header(self):
        ready = threading.Event()

        def send_garbage(conn):
            conn.recv(16)   # warten, bis der Client 'C' anfordert
            # einzelne Nicht-Hex-Zeilen werden als Monitorzeilen uebersprungen;
            # erst ab der Skip-Begrenzung bricht der Client ab
            garbage = b"\r\nZZZZnothex\r\n" * 20
            conn.sendall(garbage)
            threading.Event().wait(2)   # Verbindung offen halten

        port = self._serve(ready, send_garbage)
        ready.wait(2)

        logs = []
        client = RemoteClient(on_line=logs.append)
        client.connect("127.0.0.1", port)
        client.request_screenshot()
        for _ in range(100):
            if any("Screenshot" in entry for entry in logs):
                break
            threading.Event().wait(0.02)
        client.disconnect()
        self.assertTrue(any("abgebrochen" in entry for entry in logs),
                        f"logs={logs}")

    def test_screenshot_abort_on_huge_height(self):
        ready = threading.Event()

        def send_huge_height(conn):
            conn.recv(16)   # warten, bis der Client 'C' anfordert
            header = bytearray()
            header += b"BM"
            header += (66).to_bytes(4, "little")
            header += b"\x00\x00\x00\x00"
            header += (66).to_bytes(4, "little")
            header += (40).to_bytes(4, "little")
            header += (4).to_bytes(4, "little")
            header += (10 ** 9).to_bytes(4, "little")
            header += b"\x01\x00\x10\x00" + (3).to_bytes(4, "little")
            header += (0).to_bytes(4, "little") + b"\x00" * 16
            header += b"\x00\xf8\x00\x00\xe0\x07\x00\x00\x1f\x00\x00\x00"
            conn.sendall(b"\r\n" + header.hex().encode() + b"\r\n")
            threading.Event().wait(2)   # Verbindung offen halten

        port = self._serve(ready, send_huge_height)
        ready.wait(2)

        logs = []
        client = RemoteClient(on_line=logs.append)
        client.connect("127.0.0.1", port)
        client.request_screenshot()
        for _ in range(100):
            if any("Screenshot" in entry for entry in logs):
                break
            threading.Event().wait(0.02)
        client.disconnect()
        self.assertTrue(any("abgebrochen" in entry for entry in logs),
                        f"logs={logs}")


class MaliciousMockClientTest(unittest.TestCase):
    """Boeswilliger Client gegen den Mock-Server."""

    def test_memory_slot_out_of_range_rejected(self):
        from ats_mini_remote import mock_receiver
        state = mock_receiver.MockState()
        server = mock_receiver.MockServer(address=("127.0.0.1", 0), state=state)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2) as s:
                s.sendall(b"#999,VHF,100000000,FM\r\n")
                s.settimeout(2)
                response = s.recv(4096)
            self.assertIn(b"Error", response)
            self.assertNotIn(b"#999", bytes(state.memories.keys()) and b"" or b"")
            self.assertNotIn(999, state.memories)
        finally:
            server.server_close()


if __name__ == "__main__":
    unittest.main()


class MaliciousMemoryLineTest(unittest.TestCase):
    """Manipulierte Speicherzeilen ausserhalb der Firmware-Grenzen verwerfen."""

    def test_slot_out_of_range(self):
        self.assertIsNone(protocol.parse_memory_line("#99,VHF,100000000,FM"))
        self.assertIsNone(protocol.parse_memory_line("#0,VHF,100000000,FM"))
        self.assertIsNone(protocol.parse_memory_line(
            "#01,VHF," + "9" * 30 + ",FM"))

    def test_valid_memory_line_still_parses(self):
        self.assertEqual(protocol.parse_memory_line("#01,VHF,107900000,FM"),
                         (1, "VHF", 107_900_000, "FM"))


class ScreenshotProgressTest(unittest.TestCase):
    """Fortschrittsanzeige des Screenshot-Empfangs (Client-Callback)."""

    def test_progress_reports_rows(self):
        from ats_mini_remote import mock_receiver
        state = mock_receiver.MockState()
        server = mock_receiver.MockServer(address=("127.0.0.1", 0), state=state)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        progress = []
        screenshots = []
        try:
            client = RemoteClient(
                on_screenshot=screenshots.append,
                on_screenshot_progress=lambda r, t: progress.append((r, t)))
            client.connect("127.0.0.1", port)
            state.log_on = True
            client.request_screenshot()
            for _ in range(200):
                if screenshots:
                    break
                threading.Event().wait(0.02)
            client.disconnect()
            self.assertTrue(screenshots, "Screenshot muss ankommen")
            self.assertTrue(progress, "Fortschritt muss gemeldet werden")
            self.assertEqual(progress[0], (0, 0))
            # nach dem Header: Zielzeilenzahl bekannt, Werte steigen
            self.assertEqual(progress[1][1], 1 + mock_receiver.SCREEN_HEIGHT)
            self.assertEqual(progress[-1][0], progress[-1][1])
        finally:
            server.server_close()


class ScreenshotWithMonitorRaceTest(unittest.TestCase):
    """Screenshot trotz noch laufender Monitorzeilen (Race wie am Geraet).

    Die Firmware sendet alle 500 ms eine Statuszeile; beim 'C'-Befehl
    ist fast immer noch eine unterwegs. Der Client muss sie vor dem
    Hex-Header ueberspringen und danach den Monitor (den die Firmware
    bei 'C' abschaltet) automatisch wieder einschalten.
    """

    def test_monitor_line_before_header_is_skipped(self):
        import threading as _th
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        ready = _th.Event()

        from ats_mini_remote import mock_receiver

        def run():
            conn, _ = server.accept()
            ready.set()
            try:
                conn.recv(16)          # 'C' abwarten
                # 1) Monitorzeile, die noch unterwegs war
                state = mock_receiver.MockState()
                conn.sendall(state.status_csv())
                # 2) der eigentliche Screenshot
                conn.sendall(("\r\n" + state.screenshot_hex()).encode("ascii"))
                # 3) Monitor bleibt aus (wie Firmware) -> Client muss
                #    selbst wieder einschalten ('t'); kurz offen halten
                conn.settimeout(3)
                while True:
                    data = conn.recv(16)
                    if not data or b"t" in data:
                        break
            except OSError:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass
                server.close()

        _th.Thread(target=run, daemon=True).start()
        ready.wait(2)

        logs = []
        screenshots = []
        client = RemoteClient(on_line=logs.append,
                              on_screenshot=screenshots.append)
        client.connect("127.0.0.1", port)
        client.request_screenshot()
        for _ in range(200):
            if screenshots:
                break
            _th.Event().wait(0.02)
        client.disconnect()
        self.assertTrue(screenshots, "Screenshot muss trotz Monitorzeile ankommen")
        self.assertFalse(any("abgebrochen" in e for e in logs),
                         f"logs={logs}")


class MaliciousStatusBoundsTest(unittest.TestCase):
    """Werte ausserhalb der Firmware-Bereiche werden verworfen.

    Die Firmware druckt RSSI/SNR als uint8, Volume 0..63, AGC 0..37,
    Kondensator als uint16. Ein manipuliertes Radio, das Riesenwerte
    sendet, darf sie nicht in die UI durchreichen: volume_burst leitet
    aus _current_volume die Befehlslaenge ab und wuerde sonst beim
    naechsten Slider-Klick einen Riesen-Burst erzeugen.
    """

    def _line(self, **kw):
        base = {"201,100000,0,0,VHF,FM,10k,Auto,0,30,32,25,1500,4.05,0"}
        base = base.pop()
        fields = base.split(",")
        for idx, value in kw.items():
            fields[int(idx)] = value
        return ",".join(fields)

    def test_volume_out_of_range_rejected(self):
        self.assertIsNone(protocol.parse_status(self._line(**{"9": "64"})))
        self.assertIsNone(protocol.parse_status(self._line(**{"9": "-1"})))
        self.assertIsNone(protocol.parse_status(self._line(**{"9": "100000000"})))

    def test_rssi_snr_out_of_range_rejected(self):
        self.assertIsNone(protocol.parse_status(self._line(**{"10": "256"})))
        self.assertIsNone(protocol.parse_status(self._line(**{"11": "-5"})))
        self.assertIsNone(protocol.parse_status(self._line(**{"11": "999"})))

    def test_frequency_out_of_range_rejected(self):
        # Firmware: kHz (AM/SSB) oder 10-kHz-Schritte (FM), max. VHF-Oberband
        self.assertIsNone(protocol.parse_status(self._line(**{"1": "999999999"})))
        self.assertIsNone(protocol.parse_status(self._line(**{"1": "-100"})))

    def test_voltage_out_of_range_rejected(self):
        self.assertIsNone(protocol.parse_status(self._line(**{"13": "25.0"})))
        self.assertIsNone(protocol.parse_status(self._line(**{"13": "-0.1"})))

    def test_control_characters_in_text_fields_rejected(self):
        line = "201,100000,0,0,VH\tF,FM,10k,Auto,0,30,32,25,1500,4.05,0"
        self.assertIsNone(protocol.parse_status(line))
        line = "201,100000,0,0,VH\rF,FM,10k,Auto,0,30,32,25,1500,4.05,0"
        self.assertIsNone(protocol.parse_status(line))

    def test_long_text_fields_rejected(self):
        line = ("201,100000,0,0," + "A" * 20 + ",FM,10k,Auto,0,30,32,25,1500,"
                "4.05,0")
        self.assertIsNone(protocol.parse_status(line))

    def test_valid_status_still_parses(self):
        status = protocol.parse_status(self._line())
        self.assertIsNotNone(status)
        self.assertEqual(status.volume, 30)


class MemoryCommandInjectionTest(unittest.TestCase):
    """Band/Modus aus einem manipulierten Status duerfen keinen
    Steuerzeichencode in den Speicherbefehl einschleusen."""

    def test_control_characters_rejected(self):
        with self.assertRaises(ValueError):
            protocol.format_memory_command(1, "VH\tF", 100_000, "FM")
        with self.assertRaises(ValueError):
            protocol.format_memory_command(1, "VHF", 100_000, "F\rM123,1,2")

    def test_empty_and_long_rejected(self):
        with self.assertRaises(ValueError):
            protocol.format_memory_command(1, "", 100_000, "FM")
        with self.assertRaises(ValueError):
            protocol.format_memory_command(1, "VHF", 100_000, "M" * 20)

    def test_huge_frequency_rejected(self):
        with self.assertRaises(ValueError):
            protocol.format_memory_command(1, "VHF", 10**12, "FM")

    def test_valid_command_still_formats(self):
        cmd = protocol.format_memory_command(1, "VHF", 107_900_000, "FM")
        self.assertEqual(cmd, b"#01,VHF,107900000,FM\r\n")


class VolumeBurstBoundsTest(unittest.TestCase):
    """volume_burst begrenzt beide Werte auf den Firmware-Bereich 0..63;
    ein manipulierter _current_volume darf keinen Riesen-Burst erzeugen."""

    def test_current_out_of_range_clamped(self):
        self.assertEqual(protocol.volume_burst(10**9, 0), b"v" * 63)
        self.assertEqual(protocol.volume_burst(-5, 10), b"V" * 10)

    def test_target_out_of_range_clamped(self):
        self.assertEqual(protocol.volume_burst(10, 10**9), b"V" * 53)
        self.assertEqual(protocol.volume_burst(10, -100), b"v" * 10)

    def test_normal_burst_unchanged(self):
        self.assertEqual(protocol.volume_burst(30, 40), b"V" * 10)
        self.assertEqual(protocol.volume_burst(40, 30), b"v" * 10)


class ModeStepsRobustnessTest(unittest.TestCase):
    """Unbekannte Modi aus einem manipulierten Status duerfen keine
    Ausnahme werfen (der Sweep-Button wuerde sonst crashen)."""

    def test_unknown_mode_returns_empty(self):
        self.assertEqual(protocol.mode_steps("XX", "LSB"), b"")
        self.assertEqual(protocol.mode_steps("LSB", "XX"), b"")
        self.assertEqual(protocol.mode_steps("", "AM"), b"")

    def test_normal_steps_unchanged(self):
        self.assertEqual(protocol.mode_steps("AM", "LSB"), b"M")
        self.assertEqual(protocol.mode_steps("LSB", "AM"), b"m")


class EndlessStreamWithoutNewlineTest(unittest.TestCase):
    """Ein Boeswilling, der endlos Daten OHNE Zeilenende schickt,
    muss zum Abbruch der Verbindung fuehren (RAM-DoS)."""

    def test_flood_without_newline_disconnects(self):
        import threading as _th
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        ready = _th.Event()

        def run():
            conn, _ = server.accept()
            ready.set()
            try:
                payload = b"A" * 4096
                while True:
                    conn.sendall(payload)
                    _th.Event().wait(0.001)
            except OSError:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass
                server.close()

        _th.Thread(target=run, daemon=True).start()
        ready.wait(2)

        received = []
        client = RemoteClient(on_disconnect=received.append)
        # Grenze fuer den Test niedrig setzen, sonst dauert der Test zu lang
        client._MAX_PENDING_BYTES = 64 * 1024
        client.connect("127.0.0.1", port)
        for _ in range(600):
            if received:
                break
            _th.Event().wait(0.01)
        client.disconnect()
        self.assertTrue(received, "Client muss bei Datenflut ohne "
                                  "Zeilenende trennen")
        self.assertFalse(client.is_connected())


class ScreenshotSizeLimitTest(unittest.TestCase):
    """Header mit Riesen-Breite*Hoehe (aber einzeln plausiblen Werten)
    wird schon beim Empfang abgelehnt, nicht erst beim Dekodieren."""

    def test_oversize_image_aborts_transfer(self):
        import threading as _th
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        ready = _th.Event()

        def run():
            conn, _ = server.accept()
            ready.set()
            try:
                conn.recv(16)   # 'C' abwarten
                header = bytearray()
                header += b"BM"
                header += (66).to_bytes(4, "little")
                header += b"\x00\x00\x00\x00"
                header += (66).to_bytes(4, "little")
                header += (40).to_bytes(4, "little")
                header += (4096).to_bytes(4, "little")     # Breite
                header += (4096).to_bytes(4, "little")     # Hoehe
                header += b"\x01\x00\x10\x00" + (3).to_bytes(4, "little")
                header += (0).to_bytes(4, "little") + b"\x00" * 16
                header += b"\x00\xf8\x00\x00\xe0\x07\x00\x00\x1f\x00\x00\x00"
                conn.sendall(b"\r\n" + header.hex().encode() + b"\r\n")
                conn.settimeout(3)
                while True:
                    data = conn.recv(16)
                    if not data:
                        break
            except OSError:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass
                server.close()

        _th.Thread(target=run, daemon=True).start()
        ready.wait(2)

        logs = []
        client = RemoteClient(on_line=logs.append)
        client.connect("127.0.0.1", port)
        client.request_screenshot()
        for _ in range(100):
            if any("Screenshot" in e for e in logs):
                break
            _th.Event().wait(0.02)
        client.disconnect()
        self.assertTrue(any("abgebrochen" in e for e in logs), f"logs={logs}")


class ScreenshotRowLengthTest(unittest.TestCase):
    """Pixelzeilen, die laenger sind als die Headerbreite verspricht,
    brechen die Uebertragung ab."""

    def test_oversize_row_aborts_transfer(self):
        import threading as _th
        from ats_mini_remote import mock_receiver
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        ready = _th.Event()

        def run():
            conn, _ = server.accept()
            ready.set()
            try:
                conn.recv(16)   # 'C' abwarten
                state = mock_receiver.MockState()
                lines = state.screenshot_hex().split("\r\n")
                # zweite Pixelzeile um Faktor 3 verlaengern
                lines[2] = lines[2] * 3
                conn.sendall(("\r\n" + "\r\n".join(lines)).encode("ascii"))
                conn.settimeout(3)
                while True:
                    data = conn.recv(16)
                    if not data:
                        break
            except OSError:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass
                server.close()

        _th.Thread(target=run, daemon=True).start()
        ready.wait(2)

        logs = []
        client = RemoteClient(on_line=logs.append)
        client.connect("127.0.0.1", port)
        client.request_screenshot()
        for _ in range(100):
            if any("Screenshot" in e for e in logs):
                break
            _th.Event().wait(0.02)
        client.disconnect()
        self.assertTrue(any("abgebrochen" in e for e in logs), f"logs={logs}")
