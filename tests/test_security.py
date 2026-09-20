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
        header += size.to_bytes(4, "big")
        header += b"\x00\x00\x00\x00"
        header += (14 + 40 + 12).to_bytes(4, "big")
        header += (40).to_bytes(4, "little")
        header += width.to_bytes(4, "big")
        header += height.to_bytes(4, "big")
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
            conn.sendall(b"\r\nZZZZnothex\r\n")
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
            header += (66).to_bytes(4, "big")
            header += b"\x00\x00\x00\x00"
            header += (66).to_bytes(4, "big")
            header += (40).to_bytes(4, "little")
            header += (4).to_bytes(4, "big")
            header += (10 ** 9).to_bytes(4, "big")
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
