"""TCP-Client für das Ad-hoc-Fernsteuerprotokoll des ATS-Mini.

Ein Hintergrund-Thread liest fortlaufend vom Socket und verteilt komplette
Zeilen an Callbacks. Die Verbindung hält genau einen Controller zu, wie es
die Firmware vorgibt (tcpLoop akzeptiert nur einen Client).
"""

from __future__ import annotations

import socket
import threading
import time
from typing import Callable

from . import protocol


_HEX_CHARS = set("0123456789abcdefABCDEF")


def _is_hex(text: str) -> bool:
    """True wenn der Text ausschliesslich Hex-Ziffern enthaelt."""
    return bool(text) and all(c in _HEX_CHARS for c in text)


class RemoteClient:
    """Verwaltung der TCP-Verbindung zum Empfänger (Port 60000)."""

    def __init__(
        self,
        on_status: Callable[[protocol.ReceiverStatus], None] | None = None,
        on_memory: Callable[[tuple[int, str, int, str]], None] | None = None,
        on_line: Callable[[str], None] | None = None,
        on_disconnect: Callable[[str], None] | None = None,
        on_screenshot: Callable[[protocol.Screenshot], None] | None = None,
        on_screenshot_progress: Callable[[int, int], None] | None = None,
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
        self._on_screenshot_progress: Callable[[int, int], None] | None = on_screenshot_progress
        self._last_line_command = 0.0

    def _send_guard(self, data: bytes) -> None:
        """Vollständige Befehlszeilen vor dem Versand schützen.

        Der Empfänger liest Zeilenbefehle ('F<hz>\\r\\n', '#slot,...\\r\\n')
        Zeichen für Zeichen in blockierenden Schleifen (remoteReadInteger,
        remoteReadString, expectNewline in der Firmware). Kommt der Rest
        eines solchen Befehls erst mit dem nächsten TCP-Segment, wartet die
        Firmware aktiv auf die fehlenden Zeichen. Damit der Empfänger nie
        zwischen Befehlsanfang und -ende auf Daten warten muss, werden
        Zeilenbefehle gepuffert und in einem einzigen write() übergeben und
        vor jedem neuen Zeilenbefehl mindestens ein Intervall abgewartet.
        """
        if data[:1] in (b"F", b"#"):
            now = time.monotonic()
            wait = 0.05 - (now - self._last_line_command)
            if wait > 0:
                time.sleep(wait)
            self._last_line_command = time.monotonic()

    def request_screenshot(self) -> None:
        """Fordert einen Screenshot an; das Ergebnis geht an on_screenshot.

        Die Antwort besteht aus einer Headerzeile (BMP-Dateiheader,
        BITMAPINFOHEADER und Farbmasken) und anschließend je Displayzeile
        eine Hexzeile (bottom-up). Der Leser-Thread sammelt die Zeilen und
        übergibt das dekodierte Bild, sobald die letzte Pixelzeile da ist.
        """
        # Firmware schaltet bei 'C' den Statusmonitor ab; der Client
        # schaltet ihn nach dem Empfang automatisch wieder ein. Vor dem
        # Header koennen noch Monitorzeilen unterwegs sein -- sie werden
        # uebersprungen, bis die Hex-Headerzeile ankommt.
        self._screenshot_lines = []
        self._screenshot_target_rows = 0
        self._screenshot_skipped = 0
        self._collecting_screenshot = True
        if self._on_screenshot_progress is not None:
            self._on_screenshot_progress(0, 0)
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
        # Nagle aktiv lassen: kleine Zeilenbefehle sollen gesammelt und als
        # ein Segment übertragen werden (schützt die blockierenden Lese-
        # schleifen der Firmware vor halben Befehlen).
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
        self._send_guard(data)
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

    # Schutzbegrenzungen gegen boeswillige oder defekte Gegenseite:
    # Zeilen niemals endlos anwachsen lassen, Screenshot-Sammlung
    # nach Zeilenzahl/Bytes abbrechen. Ein CSV-Status ist ~100 Zeichen,
    # eine Screenshot-Pixelzeile ~640 Hex-Zeichen (320 Byte/Zeile * 2).
    _MAX_LINE_BYTES = 64 * 1024
    _SCREENSHOT_MAX_ROWS = 4097          # Header + 4096 Pixelzeilen
    _SCREENSHOT_MAX_LINE_CHARS = 16 * 1024

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
                    if len(line) > self._MAX_LINE_BYTES:
                        self._handle_disconnect(
                            "Verbindung wegen überlanger Zeile getrennt")
                        return
                    text = line.rstrip(b"\r").decode("ascii", errors="replace")
                    self._process_line(text)
        except (OSError, ConnectionError) as exc:
            self._handle_disconnect(str(exc) or "Verbindung verloren")

    def _abort_screenshot(self, reason: str) -> None:
        """Screenshot-Sammlung abbrechen statt endlos Daten zu sammeln."""
        self._collecting_screenshot = False
        self._screenshot_lines = []
        self._screenshot_target_rows = 0
        if self._on_screenshot_progress is not None:
            self._on_screenshot_progress(0, 0)
        if self._on_line is not None:
            self._on_line(f"Screenshot abgebrochen: {reason}")

    def _process_line(self, text: str) -> None:
        if self._collecting_screenshot:
            if self._screenshot_target_rows == 0 and not text.strip():
                return
            if len(text) > self._SCREENSHOT_MAX_LINE_CHARS:
                self._abort_screenshot("Zeile zu lang")
                return
            if self._screenshot_target_rows == 0:
                # Vor dem Header: Monitorzeilen (CSV, kein Hex) ueberspringen;
                # sie waren beim Absenden von 'C' schon unterwegs. Sicherheits-
                # begrenzung gegen Endlos-Skippen durch eine boese Gegenseite.
                if not _is_hex(text):
                    self._screenshot_skipped += 1
                    if self._screenshot_skipped > 16:
                        self._abort_screenshot("kein Header gefunden")
                    return
            self._screenshot_lines.append(text)
            if self._screenshot_target_rows == 0 and self._screenshot_lines:
                header_hex = self._screenshot_lines[0].strip()
                if len(header_hex) < (14 + 40 + 12) * 2:
                    self._abort_screenshot("Header zu kurz")
                    return
                try:
                    header = bytes.fromhex(header_hex)
                except ValueError:
                    self._abort_screenshot("Header kein Hex")
                    return
                height = int.from_bytes(header[22:26], "big")
                if not 1 <= height <= self._SCREENSHOT_MAX_ROWS - 1:
                    self._abort_screenshot("unplausible Bildhöhe")
                    return
                self._screenshot_target_rows = 1 + height
            if self._on_screenshot_progress is not None:
                self._on_screenshot_progress(
                    len(self._screenshot_lines), self._screenshot_target_rows)
            if self._screenshot_target_rows and \
                    len(self._screenshot_lines) >= self._screenshot_target_rows:
                self._collecting_screenshot = False
                lines = self._screenshot_lines[:self._screenshot_target_rows]
                self._screenshot_lines = []
                # Firmware schaltet den Monitor bei 'C' ab: wieder
                # einschalten, sonst bleibt die Verbindung still und
                # laeuft spaeter in den Empfangs-Timeout.
                try:
                    self.send(protocol.CMD_TOGGLE_LOG)
                except RuntimeError:
                    pass
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
