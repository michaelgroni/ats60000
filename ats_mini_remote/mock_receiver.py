"""Mock-Empfänger: Nachbau des Ad-hoc-Fernsteuerprotokolls des ATS-Mini.

Öffnet einen TCP-Server auf Port 60000 und bedient die Befehle des
Ad-hoc-Protokolls, damit sich die Fernbedienung ohne Hardware testen lässt:

    python3 -m ats_mini_remote.mock_receiver

Befehle (siehe ats_mini_remote/protocol.py): R/r, e, V/v, B/b, M/m, S/s,
W/w, A/a, L/l, I/i, O/o, t, $, C, F<Hz>, #<slot>,<band>,<freq>,<mode>
"""

from __future__ import annotations

import socket
import socketserver
import struct
import threading
import time

SCREEN_WIDTH = 160
SCREEN_HEIGHT = 80

BANDS = [
    # Name, min (kHz), max (kHz), Modusliste, Standardfrequenz (kHz)
    ("LW", 144, 288, ["AM"], 200),
    ("MW", 522, 1701, ["AM"], 1008),
    ("80m", 3400, 3800, ["AM", "LSB", "USB"], 3700),
    ("SW", 5800, 6300, ["AM", "LSB", "USB"], 6070),
    ("VHF", 76000, 108000, ["FM"], 100000),
]

STEPS = ["1k", "5k", "9k", "10k", "100k", "0.1M"]
BANDWIDTHS = ["6.0k", "4.0k", "2.5k", "1.8k"]

BFO_STEPS = [50, 100, 250]


class MockState:
    def __init__(self):
        self.lock = threading.Lock()
        self.version = 201
        self.band_idx = 4
        self.mode_idx = 0
        self.frequency = 100000  # kHz
        self.bfo = 0
        self.cal = 0
        self.step_idx = 0
        self.bandwidth_idx = 0
        self.agc_idx = 0
        self.volume = 30
        self.rssi = 32
        self.snr = 25
        self.capacitor = 1500
        self.voltage = 4.05
        self.seqnum = 0
        self.sleep = False
        self.backlight = 7
        self.memories: dict[int, tuple[str, int, str]] = {}
        self.log_on = False

    def band(self):
        return BANDS[self.band_idx]

    def modes(self):
        return self.band()[3]

    def mode(self):
        return self.modes()[self.mode_idx]

    def is_ssb(self):
        return self.mode() in ("LSB", "USB")

    def freq_khz(self):
        return self.frequency

    def display_freq_khz(self):
        return self.frequency + self.bfo // 1000

    def step_khz(self):
        text = STEPS[self.step_idx]
        if text == "0.1M":
            return 100
        return int(text.rstrip("kM"))

    def rotate_frequency(self, direction: int):
        freq = self.frequency + direction * self.step_khz()
        _name, lo, hi = self.band()[:3]
        self.frequency = max(lo, min(hi, freq))

    def status_csv(self):
        with self.lock:
            self.seqnum = (self.seqnum + 1) % 256
            step_desc = STEPS[self.step_idx] if not self.is_ssb() else BFO_STEPS[self.step_idx % len(BFO_STEPS)]
            # FM-Status meldet Frequenz in 10-kHz-Schritten, AM/SSB in kHz
            freq_field = self.frequency // 10 if self.mode() == "FM" else self.frequency
            return (
                f"{self.version},{freq_field},{self.bfo},{self.cal},{self.band()[0]},"
                f"{self.mode()},{step_desc},{BANDWIDTHS[self.bandwidth_idx]},"
                f"{self.agc_idx},{self.volume},{self.rssi},{self.snr},"
                f"{self.capacitor},{self.voltage:.2f},{self.seqnum}\r\n"
            ).encode("ascii")

    def screenshot_hex(self):
        theme = (
            (0x00, 0x00, 0x00),
            (0xFF, 0xFF, 0xFF),
            (0x07, 0xE0, 0x00),
            (0x1F, 0x3F, 0x1F),
        )
        # Zeichne ein vereinfachtes Empfängerdisplay mit Frequenzangabe
        freq_text = f"{self.display_freq_khz() / 1000:8.3f}"
        grid = [[0 for _ in range(SCREEN_WIDTH)] for _ in range(SCREEN_HEIGHT)]
        for row in grid:
            for x in range(SCREEN_WIDTH):
                row[x] = 0
        for y in range(SCREEN_HEIGHT):
            for x in range(SCREEN_WIDTH):
                grid[y][x] = 0x0000 if (x // 16 + y // 16) % 2 == 0 else 0x18E3
        # Textbereich
        for i, ch in enumerate(freq_text):
            self._draw_char(grid, 30 + i * 8, 10, ch)
        label = self.band()[0] + " " + self.mode()
        for i, ch in enumerate(label):
            self._draw_char(grid, 30 + i * 8, 40, ch)

        size = 14 + 40 + 12 + SCREEN_WIDTH * SCREEN_HEIGHT * 2
        header = bytearray()
        header += b"BM"
        header += size.to_bytes(4, "big")
        header += b"\x00\x00\x00\x00"
        header += (14 + 40 + 12).to_bytes(4, "big")
        header += (40).to_bytes(4, "little")
        header += SCREEN_WIDTH.to_bytes(4, "big")
        header += SCREEN_HEIGHT.to_bytes(4, "big")
        header += struct.pack("<HH", 1, 16)
        header += struct.pack("<I", 3)
        header += struct.pack("<I", 0)
        header += b"\x00" * 16
        header += struct.pack(">III", 0x00F80000, 0xE0070000, 0x1F000000)

        lines = [header.hex()]
        for y in range(SCREEN_HEIGHT - 1, -1, -1):
            row_hex = ""
            for x in range(SCREEN_WIDTH):
                rgb = grid[y][x]
                row_hex += f"{rgb:04x}"
            lines.append(row_hex)
        return "\r\n".join(lines) + "\r\n"

    def _draw_char(self, grid, x0, y0, ch):
        font = {
            "0": ["011", "101", "101", "101", "011"],
            "1": ["010", "110", "010", "010", "111"],
            "2": ["111", "001", "111", "100", "111"],
            "3": ["111", "001", "111", "001", "111"],
            "4": ["101", "101", "111", "001", "001"],
            "5": ["111", "100", "111", "001", "111"],
            "6": ["111", "100", "111", "101", "111"],
            "7": ["111", "001", "010", "010", "010"],
            "8": ["111", "101", "111", "101", "111"],
            "9": ["111", "101", "111", "001", "111"],
            ".": ["000", "000", "000", "000", "010"],
            " ": ["000", "000", "000", "000", "000"],
            "F": ["111", "100", "110", "100", "100"],
            "M": ["101", "111", "111", "101", "101"],
            "L": ["100", "100", "100", "100", "111"],
            "S": ["111", "100", "111", "001", "111"],
            "B": ["110", "101", "110", "101", "110"],
            "U": ["101", "101", "101", "101", "111"],
            "W": ["101", "101", "111", "111", "101"],
            "V": ["101", "101", "101", "101", "010"],
            "H": ["101", "101", "111", "101", "101"],
            "A": ["010", "101", "111", "101", "101"],
            "T": ["111", "010", "010", "010", "010"],
        }
        glyph = font.get(ch, font[" "])
        for dy, row_bits in enumerate(glyph):
            for dx, bit in enumerate(row_bits):
                if bit == "1":
                    y, x = y0 + dy, x0 + dx
                    if 0 <= y < SCREEN_HEIGHT and 0 <= x < SCREEN_WIDTH:
                        grid[y][x] = 0xFFFF


class MockHandler(socketserver.BaseRequestHandler):
    def setup(self):
        self.state: MockState = self.server.state
        self.server.register(self)

    def finish(self):
        self.server.unregister(self)

    def handle(self):
        # Einzeltasten des Ad-hoc-Protokolls kommen ohne Newline; nur die
        # Befehle 'F<hz>\r\n' und '#slot,...\r\n' sind Zeilenbefehle.
        pending = bytearray()
        while True:
            try:
                chunk = self.request.recv(4096)
            except OSError:
                return
            if not chunk:
                return
            for byte in chunk:
                if pending:
                    pending.append(byte)
                    if byte == 10:
                        self.handle_command(bytes(pending))
                        pending.clear()
                    elif len(pending) > 64:
                        pending.clear()
                elif byte in (ord("F"), ord("#")):
                    pending.append(byte)
                else:
                    self.handle_command(bytes([byte]))

    def send(self, data: bytes):
        try:
            self.request.sendall(data)
        except OSError:
            pass

    def handle_command(self, line: bytes):
        state = self.state
        if not line:
            return
        key = line[0:1]
        payload = line[1:].decode("ascii", errors="replace").strip("\r")
        with state.lock:
            if key == b"F":
                self.cmd_frequency(payload)
            elif line == b"$":
                for slot, (band, freq, mode) in sorted(state.memories.items()):
                    if freq:
                        self.send(f"#{slot:02d},{band},{freq},{mode}\r\n".encode())
            elif key == b"#":
                self.cmd_memory(payload)
            elif key == b"t":
                state.log_on = not state.log_on
            elif line == b"C":
                self.send(("\r\n" + state.screenshot_hex()).encode("ascii"))
            else:
                self.cmd_key(line)

    def cmd_frequency(self, payload: str):
        state = self.state
        try:
            hz = int(payload)
        except ValueError:
            self.send(b"\r\nError: Invalid frequency\r\n")
            return
        if hz <= 0:
            self.send(b"\r\nError: Invalid frequency\r\n")
            return
        if state.mode() == "FM":
            khz = hz // 1000
        else:
            khz = hz // 1000
            state.bfo = hz % 1000 if state.is_ssb() else 0
        name, lo, hi = state.band()[:3]
        if not lo <= khz <= hi:
            self.send(b"\r\nError: Frequency is out of range for the current band\r\n")
            return
        state.frequency = khz
        self.send(b"\r\n")

    def cmd_memory(self, payload: str):
        state = self.state
        parts = payload.split(",")
        if len(parts) != 4:
            self.send(b"\r\nError: Expected ','\r\n")
            return
        try:
            slot = int(parts[0])
            freq = int(parts[2])
        except ValueError:
            self.send(b"\r\nError: Invalid memory slot number\r\n")
            return
        band, mode = parts[1], parts[3]
        band_names = [b[0] for b in BANDS]
        if band not in band_names:
            self.send(b"\r\nError: No such band\r\n")
            return
        if freq == 0:
            state.memories.pop(slot, None)
            self.send(b"\r\n")
            return
        state.memories[slot] = (band, freq, mode)
        self.send(b"\r\n")

    def cmd_key(self, line: bytes):
        state = self.state
        if line == b"R":
            state.rotate_frequency(1)
        elif line == b"r":
            state.rotate_frequency(-1)
        elif line == b"V":
            state.volume = min(63, state.volume + 1)
        elif line == b"v":
            state.volume = max(0, state.volume - 1)
        elif line == b"B":
            state.band_idx = (state.band_idx + 1) % len(BANDS)
            state.mode_idx = 0
            state.frequency = state.band()[4]
            state.bfo = 0
        elif line == b"b":
            state.band_idx = (state.band_idx - 1) % len(BANDS)
            state.mode_idx = 0
            state.frequency = state.band()[4]
            state.bfo = 0
        elif line == b"M":
            state.mode_idx = (state.mode_idx + 1) % len(state.modes())
        elif line == b"m":
            state.mode_idx = (state.mode_idx - 1) % len(state.modes())
        elif line == b"S":
            state.step_idx = (state.step_idx + 1) % len(STEPS)
        elif line == b"s":
            state.step_idx = (state.step_idx - 1) % len(STEPS)
        elif line == b"W":
            state.bandwidth_idx = (state.bandwidth_idx + 1) % len(BANDWIDTHS)
        elif line == b"w":
            state.bandwidth_idx = (state.bandwidth_idx - 1) % len(BANDWIDTHS)
        elif line == b"A":
            state.agc_idx = (state.agc_idx + 1) % 8
        elif line == b"a":
            state.agc_idx = (state.agc_idx - 1) % 8
        elif line == b"O":
            state.sleep = True
        elif line == b"o":
            state.sleep = False
        elif line == b"L":
            state.backlight = min(15, state.backlight + 1)
        elif line == b"l":
            state.backlight = max(0, state.backlight - 1)
        elif line == b"I":
            state.cal += 25
        elif line == b"i":
            state.cal -= 25


class MockServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address=("127.0.0.1", 60000), state: MockState | None = None):
        self.state = state or MockState()
        self.handlers: list[MockHandler] = []
        self.lock = threading.Lock()
        super().__init__(address, MockHandler)

    def register(self, handler):
        with self.lock:
            self.handlers.append(handler)

    def unregister(self, handler):
        with self.lock:
            if handler in self.handlers:
                self.handlers.remove(handler)

    def status_loop(self, interval=0.5):
        while True:
            time.sleep(interval)
            with self.lock:
                handlers = list(self.handlers)
            if not handlers:
                continue
            if not self.state.log_on:
                continue
            data = self.state.status_csv()
            for handler in handlers:
                handler.send(data)


def main():
    server = MockServer()
    thread = threading.Thread(target=server.status_loop, daemon=True)
    thread.start()
    print("ATS-Mini Mock-Empfänger lauscht auf Port 60000 (Strg+C zum Beenden)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
