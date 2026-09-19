"""Integrationstest: Client gegen den Mock-Empfänger."""

import socket
import threading
import unittest

from ats_mini_remote import protocol
from ats_mini_remote.client import RemoteClient
from ats_mini_remote.mock_receiver import MockServer, MockState


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class MockReceiverTest(unittest.TestCase):
    def setUp(self):
        self.port = free_port()
        self.server = MockServer(address=("127.0.0.1", self.port))
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.status_thread = threading.Thread(
            target=self.server.status_loop, kwargs={"interval": 0.05}, daemon=True)
        self.status_thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def connect_client(self, **kwargs):
        events = kwargs.pop("events")
        client = RemoteClient(**{
            "on_status": events.on_status,
            "on_memory": events.on_memory,
            "on_line": events.on_line,
            "on_disconnect": events.on_disconnect,
            "on_screenshot": events.on_screenshot,
        })
        client.connect("127.0.0.1", self.port)
        return client

    def test_status_stream(self):
        class Events:
            def __init__(self):
                self.statuses = []
                self.memories = []
                self.lines = []
                self.disconnected = []
                self.screenshots = []

            def on_status(self, s):
                self.statuses.append(s)

            def on_memory(self, m):
                self.memories.append(m)

            def on_line(self, l):
                self.lines.append(l)

            def on_disconnect(self, r):
                self.disconnected.append(r)

            def on_screenshot(self, s):
                self.screenshots.append(s)

        import time
        events = Events()
        client = self.connect_client(events=events)
        try:
            client.send(protocol.CMD_TOGGLE_LOG)
            deadline = time.time() + 3
            while not events.statuses and time.time() < deadline:
                time.sleep(0.02)
            self.assertTrue(events.statuses)
            first = events.statuses[0]
            self.assertEqual(first.band, "VHF")
            self.assertEqual(first.mode, "FM")

            client.send(b"V")
            client.send(protocol.CMD_BAND_DOWN)  # VHF -> SW
            deadline = time.time() + 3
            while time.time() < deadline:
                last = events.statuses[-1]
                if last.band == "SW" and last.volume == 31:
                    break
                time.sleep(0.02)
            last = events.statuses[-1]
            self.assertEqual(last.band, "SW")
            self.assertEqual(last.volume, 31)  # V wurde verarbeitet
        finally:
            client.disconnect()

    def test_frequency_and_memory(self):
        class Events:
            def __init__(self):
                self.statuses = []
                self.memories = []
                self.lines = []
                self.disconnected = []
                self.screenshots = []

            def on_status(self, s):
                self.statuses.append(s)

            def on_memory(self, m):
                self.memories.append(m)

            def on_line(self, l):
                self.lines.append(l)

            def on_disconnect(self, r):
                self.disconnected.append(r)

            def on_screenshot(self, s):
                self.screenshots.append(s)

        events = Events()
        client = self.connect_client(events=events)
        try:
            client.send(protocol.format_frequency_command(107_900_000, ssb=False))
            client.send(protocol.CMD_TOGGLE_LOG)
            client.send(protocol.format_memory_command(5, "VHF", 107_900_000, "FM"))
            client.send(protocol.CMD_SHOW_MEMORIES)
            import time
            time.sleep(0.6)
            self.assertEqual(events.memories, [(5, "VHF", 107_900_000, "FM")])
            state = self.server.state
            with state.lock:
                self.assertEqual(state.frequency, 107_900)
        finally:
            client.disconnect()

    def test_screenshot(self):
        class Events:
            def __init__(self):
                self.statuses = []
                self.memories = []
                self.lines = []
                self.disconnected = []
                self.screenshots = []

            def on_status(self, s):
                self.statuses.append(s)

            def on_memory(self, m):
                self.memories.append(m)

            def on_line(self, l):
                self.lines.append(l)

            def on_disconnect(self, r):
                self.disconnected.append(r)

            def on_screenshot(self, s):
                self.screenshots.append(s)

        events = Events()
        client = self.connect_client(events=events)
        try:
            client.request_screenshot()
            import time
            deadline = time.time() + 5
            while not events.screenshots and time.time() < deadline:
                time.sleep(0.05)
            self.assertEqual(len(events.screenshots), 1)
            shot = events.screenshots[0]
            self.assertEqual((shot.width, shot.height), (160, 80))
        finally:
            client.disconnect()


if __name__ == "__main__":
    unittest.main()
