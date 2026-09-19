"""TCP-Client für das Ad-hoc-Fernsteuerprotokoll des ATS-Mini.

Ein Hintergrund-Thread liest fortlaufend vom Socket und verteilt komplette
Zeilen an Callbacks. Die Verbindung hält genau einen Controller zu, wie es
die Firmware vorgibt (tcpLoop akzeptiert nur einen Client).
"""

from __future__ import annotations

import socket
import threading
from typing import Callable

from . import protocol


class RemoteClient:
    """Verwaltung der TCP-Verbindung zum Empfänger (Port 60000)."""

    def __init__(
        self,
        on_status: Callable[[protocol.ReceiverStatus], None] | None = None,
        on_memory: Callable[[tuple[int, str, int, str]], None] | None = None,
        on_line: Callable[[str], None] | None = None,
        on_disconnect: Callable[[str], None] | None = None,
        on_screenshot: Callable[[protocol.Screenshot], None] | None = None,
    ):
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self._connected = False
        self._on_status = on_status
        self._on_memory = on_memory
        self._on_line = on_line
        self._on_disconnect = on_disconnect
        self._collecting_screenshot = False
        self._screenshot_lines: list[str] = []
        self._screenshot_target_rows = 0
        self._on_screenshot: Callable[[protocol.Screenshot], None] | None = on_screenshot

    def request_screenshot(self) -> None:
        """Fordert einen Screenshot an; das Ergebnis geht an on_screenshot.

        Die Antwort besteht aus einer Headerzeile (BMP-Dateiheader,
        BITMAPINFOHEADER und Farbmasken) und anschließend je Displayzeile
        eine Hexzeile (bottom-up). Der Leser-Thread sammelt die Zeilen und
        übergibt das dekodierte Bild, sobald die letzte Pixelzeile da ist.
        """
        self._screenshot_lines = []
        self._screenshot_target_rows = 0
        self._collecting_screenshot = True
        self.send(protocol.CMD_SCREENSHOT)

    def is_connected(self) -> bool:
        return self._connected

    def connect(self, host: str, port: int = protocol.DEFAULT_PORT,
                timeout: float = 5.0) -> None:
        """Baut die Verbindung auf und startet den Leser-Thread.

        Wirft bei Fehler OSError mit beschreibender Meldung.
        """
        if self._connected:
            raise RuntimeError("Bereits verbunden")
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
        except OSError as exc:
            raise OSError(
                f"Keine Verbindung zu {host}:{port}: {exc.strerror or exc}"
            ) from exc
        self._sock = sock
        self._connected = True
        sock.settimeout(10.0)
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def disconnect(self) -> None:
        """Trennt die Verbindung; ruft on_disconnect nicht erneut auf."""
        self._connected = False
        sock = self._sock
        self._sock = None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()

    def send(self, data: bytes) -> None:
        """Sendet einen Rohbefehl an das Radio."""
        sock = self._sock
        if sock is None or not self._connected:
            raise RuntimeError("Nicht verbunden")
        try:
            sock.sendall(data)
        except OSError as exc:
            self._handle_disconnect(f"Sendefehler: {exc}")

    def _handle_disconnect(self, reason: str) -> None:
        was_connected = self._connected
        self._collecting_screenshot = False
        self._connected = False
        sock = self._sock
        self._sock = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if was_connected and self._on_disconnect is not None:
            self._on_disconnect(reason)

    def _read_loop(self) -> None:
        sock = self._sock
        if sock is None:
            return
        buf = bytearray()
        try:
            while self._connected:
                chunk = sock.recv(4096)
                if not chunk:
                    raise ConnectionError("Verbindung vom Empfänger geschlossen")
                buf += chunk
                while b"\n" in buf:
                    line, _, rest = buf.partition(b"\n")
                    buf = bytearray(rest)
                    text = line.rstrip(b"\r").decode("ascii", errors="replace")
                    self._process_line(text)
        except (OSError, ConnectionError) as exc:
            self._handle_disconnect(str(exc) or "Verbindung verloren")

    def _process_line(self, text: str) -> None:
        if self._collecting_screenshot:
            if self._screenshot_target_rows == 0 and not text.strip():
                return
            self._screenshot_lines.append(text)
            if self._screenshot_target_rows == 0 and self._screenshot_lines:
                header_hex = self._screenshot_lines[0].strip()
                if len(header_hex) < (14 + 40 + 12) * 2:
                    return
                height = int.from_bytes(bytes.fromhex(header_hex)[22:26], "big")
                self._screenshot_target_rows = 1 + height
            if self._screenshot_target_rows and \
                    len(self._screenshot_lines) >= self._screenshot_target_rows:
                self._collecting_screenshot = False
                lines = self._screenshot_lines[:self._screenshot_target_rows]
                self._screenshot_lines = []
                if self._on_screenshot is not None:
                    try:
                        self._on_screenshot(protocol.decode_screenshot(lines))
                    except ValueError as exc:
                        if self._on_line is not None:
                            self._on_line(f"Screenshot-Fehler: {exc}")
            return
        if self._on_line is not None:
            self._on_line(text)
        if not text:
            return
        status = protocol.parse_status(text)
        if status is not None:
            if self._on_status is not None:
                self._on_status(status)
            return
        mem = protocol.parse_memory_line(text)
        if mem is not None:
            if self._on_memory is not None:
                self._on_memory(mem)
