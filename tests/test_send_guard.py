"""Tests für die sendeseitige Schutzschicht gegen Firmware-Blockaden."""

import socket
import threading
import time
import unittest

from ats_mini_remote import protocol
from ats_mini_remote.client import RemoteClient
from ats_mini_remote.mock_receiver import MockServer


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class SendGuardTest(unittest.TestCase):
    def setUp(self):
        self.port = free_port()
        self.server = MockServer(address=("127.0.0.1", self.port))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        threading.Thread(target=self.server.status_loop,
                         kwargs={"interval": 0.1}, daemon=True).start()
        self.client = RemoteClient()
        self.client.connect("127.0.0.1", self.port)

    def tearDown(self):
        self.client.disconnect()
        self.server.shutdown()
        self.server.server_close()

    def test_fragmented_frequency_command_recovers(self):
        """Zeilenbefehl, der in zwei Segmenten ankommt, muss verarbeitet werden."""
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=3)
        try:
            sock.sendall(b"F1079")   # erstes Fragment
            time.sleep(0.3)          # bewusst lange Lücke
            sock.sendall(b"00000\r\n")
            time.sleep(0.4)
            state = self.server.state
            with state.lock:
                self.assertEqual(state.frequency, 107_900)
        finally:
            sock.close()

    def test_line_commands_are_spaced(self):
        """Aufeinanderfolgende Zeilenbefehle werden zeitlich entzerrt."""
        start = time.monotonic()
        self.client.send(protocol.format_frequency_command(107_900_000, ssb=False))
        self.client.send(protocol.format_frequency_command(107_800_000, ssb=False))
        elapsed = time.monotonic() - start
        # Der Guard erzwingt mindestens 50 ms zwischen zwei Zeilenbefehlen
        self.assertGreaterEqual(elapsed, 0.045)

    def test_single_key_commands_unguarded(self):
        """Einzeltasten dürfen unverzüglich gesendet werden."""
        start = time.monotonic()
        self.client.send(protocol.CMD_VOLUME_UP)
        self.client.send(protocol.CMD_VOLUME_DOWN)
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 0.045)


if __name__ == "__main__":
    unittest.main()
