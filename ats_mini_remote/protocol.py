"""Protokollimplementierung des ATS-Mini Ad-hoc-Fernsteuerprotokolls.

Befehle und Datenformate folgen der Firmware-Dokumentation des
ATS-Mini-Projekts (esp32-si4732/ats-mini, Remote.cpp):
  * Zeilenbefehle: 'F<frequenz-hz>\r\n', '#<slot>,<band>,<freq>,<mode>\r\n'
  * Einzeltasten: 'R'/'r' (Encoder), 'V'/'v' (Lautstärke), 'B'/'b' (Band),
    'M'/'m' (Modus), 'S'/'s' (Schrittweite), 'W'/'w' (Bandbreite),
    'A'/'a' (AGC), 't' (Monitor an/aus), '$' (Speicher ausgeben),
    'C' (Screenshot als BMP in Hex), 'e' (Encoder-Klick)
  * Monitor: CSV-Zeile mit 15 Feldern, alle 500 ms
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

DEFAULT_PORT = 60000

# Feldindizes der Monitor-CSV-Zeile
STATUS_FIELDS = 15
_IDX_VERSION = 0
_IDX_FREQUENCY = 1
_IDX_BFO = 2
_IDX_CAL = 3
_IDX_BAND = 4
_IDX_MODE = 5
_IDX_STEP = 6
_IDX_BANDWIDTH = 7
_IDX_AGC = 8
_IDX_VOLUME = 9
_IDX_RSSI = 10
_IDX_SNR = 11
_IDX_CAPACITOR = 12
_IDX_VOLTAGE = 13
_IDX_SEQNUM = 14


@dataclass
class ReceiverStatus:
    """Ein Statusdatensatz, wie ihn der Monitor des Empfängers sendet."""

    version: int = 0
    frequency: int = 0        # FM: 10-kHz-Schritte, AM/SSB: kHz
    bfo: int = 0              # SSB: Hz
    cal: int = 0
    band: str = ""
    mode: str = ""            # FM / AM / LSB / USB
    step: str = ""
    bandwidth: str = ""
    agc: int = 0
    volume: int = 0           # 0..63, 0 = stumm
    rssi: int = 0             # dBuV
    snr: int = 0              # dB
    capacitor: int = 0
    voltage: float = 0.0      # V
    seqnum: int = 0

    def display_frequency_hz(self) -> int:
        """Anzeigefrequenz in Hz; in SSB-Modi kHz*1000 + BFO."""
        if self.mode.upper() == "FM":
            return self.frequency * 10_000
        return self.frequency * 1000 + self.bfo


def parse_status(line: str) -> ReceiverStatus | None:
    """Wandelt eine Monitor-CSV-Zeile in einen ReceiverStatus um.

    Rückgabe: None, wenn die Zeile kein gültiger Statusdatensatz ist.
    """
    fields = [f.strip() for f in line.split(",")]
    if len(fields) != STATUS_FIELDS:
        return None
    try:
        version = int(fields[_IDX_VERSION])
        frequency = int(fields[_IDX_FREQUENCY])
        bfo = int(fields[_IDX_BFO])
        cal = int(fields[_IDX_CAL])
        agc = int(fields[_IDX_AGC])
        volume = int(fields[_IDX_VOLUME])
        rssi = int(fields[_IDX_RSSI])
        snr = int(fields[_IDX_SNR])
        capacitor = int(fields[_IDX_CAPACITOR])
        voltage = float(fields[_IDX_VOLTAGE])
        seqnum = int(fields[_IDX_SEQNUM])
    except ValueError:
        return None

    return ReceiverStatus(
        version=version,
        frequency=frequency,
        bfo=bfo,
        cal=cal,
        band=fields[_IDX_BAND],
        mode=fields[_IDX_MODE],
        step=fields[_IDX_STEP],
        bandwidth=fields[_IDX_BANDWIDTH],
        agc=agc,
        volume=volume,
        rssi=rssi,
        snr=snr,
        capacitor=capacitor,
        voltage=voltage,
        seqnum=seqnum,
    )


def parse_memory_line(line: str) -> tuple[int, str, int, str] | None:
    """Wandelt eine Speicherzeile '#01,VHF,107900000,FM' um.

    Rückgabe: (Slot, Band, Frequenz, Modus) oder None.
    """
    if not line.startswith("#"):
        return None
    fields = line[1:].split(",")
    if len(fields) != 4:
        return None
    try:
        slot = int(fields[0])
        freq = int(fields[2])
    except ValueError:
        return None
    return slot, fields[1], freq, fields[3]


def format_frequency_command(hz: int, ssb: bool) -> bytes:
    """Erzeugt den Frequenzbefehl 'F<hz>\r\n'.

    In SSB-Modi setzen Stellen unter 1 kHz den BFO; das Radio prüft,
    dass die Frequenz im aktuellen Band liegt.
    """
    if hz <= 0:
        raise ValueError("Frequenz muss positiv sein")
    if ssb:
        payload = str(hz)
    else:
        payload = str((hz // 1000) * 1000)
    return f"F{payload}\r\n".encode("ascii")


def format_memory_command(slot: int, band: str, hz: int, mode: str) -> bytes:
    """Erzeugt den Speicherbefehl '#<slot>,<band>,<freq>,<mode>\r\n'.

    Frequenz 0 löscht den Slot.
    """
    if not 1 <= slot <= 32:
        raise ValueError("Slot muss zwischen 1 und 32 liegen")
    return f"#{slot:02d},{band},{hz},{mode}\r\n".encode("ascii")


# Einzeltasten-Befehle (siehe docs/source/remote.md der Firmware)
CMD_ENCODER_UP = b"R"
CMD_ENCODER_DOWN = b"r"
CMD_ENCODER_CLICK = b"e"
CMD_VOLUME_UP = b"V"
CMD_VOLUME_DOWN = b"v"
CMD_BAND_UP = b"B"
CMD_BAND_DOWN = b"b"
CMD_MODE_UP = b"M"
CMD_MODE_DOWN = b"m"
CMD_STEP_UP = b"S"
CMD_STEP_DOWN = b"s"
CMD_BANDWIDTH_UP = b"W"
CMD_BANDWIDTH_DOWN = b"w"
CMD_AGC_UP = b"A"
CMD_AGC_DOWN = b"a"
CMD_BACKLIGHT_UP = b"L"
CMD_BACKLIGHT_DOWN = b"l"
CMD_CALIBRATION_UP = b"I"
CMD_CALIBRATION_DOWN = b"i"
CMD_SLEEP_ON = b"O"
CMD_SLEEP_OFF = b"o"
CMD_TOGGLE_LOG = b"t"
CMD_SHOW_MEMORIES = b"$"
CMD_SCREENSHOT = b"C"


class Screenshot:
    """Decodiertes Display-Abbild des Empfängers (RGB, zeilenweise oben nach unten)."""

    def __init__(self, width: int, height: int, rows: list[list[tuple[int, int, int]]]):
        self.width = width
        self.height = height
        self.rows = rows

    def to_ppm(self) -> bytes:
        """Bild als binäres PPM (P6) – zur Anzeige in Tkinter."""
        header = f"P6\n{self.width} {self.height}\n255\n".encode("ascii")
        data = bytearray()
        for row in self.rows:
            for r, g, b in row:
                data += bytes((r, g, b))
        return header + bytes(data)

    def to_bmp(self) -> bytes:
        """Bild als reguläres 16-Bit-BMP (little-endian, BI_BITFIELDS)."""
        size = 14 + 40 + 12 + self.width * self.height * 2
        out = bytearray()
        out += b"BM"
        out += struct.pack("<I", size)
        out += b"\x00" * 4
        out += struct.pack("<I", 14 + 40 + 12)
        out += struct.pack("<IiiHHIIiiII", 40, self.width, self.height,
                            1, 16, 3, 0, 0, 0, 0, 0)
        out += struct.pack("<III", 0x00F80000, 0x000007E0, 0x0000001F)
        for row in reversed(self.rows):
            for r, g, b in row:
                out += struct.pack("<H", (r >> 3) << 11 | (g >> 2) << 5 | (b >> 3))
        return bytes(out)


def decode_screenshot(lines: list[str]) -> Screenshot:
    """Dekodiert die HEX-Ausgabe des Screenshot-Befehls.

    Das Radio sendet 14 Bytes BMP-Dateiheader, 40 Bytes BITMAPINFOHEADER
    und 12 Bytes Farbmasken in einer Hexzeile, danach je Displayzeile eine
    Hexzeile mit 16-Bit-Pixeldaten (bottom-up). Größe, Offset, Breite und
    Höhe werden von der Firmware mit htonl() bzw. die Pixel mit htons()
    ausgegeben und sind daher im Stream big-endian codiert, die übrigen
    Headerfelder sind little-endian Literale.
    """
    hexdata = ""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if not all(c in "0123456789abcdefABCDEF" for c in stripped):
            raise ValueError("Ungültige Zeile in Screenshot-Daten")
        hexdata += stripped
    raw = bytes.fromhex(hexdata)
    if len(raw) < 14 + 40 + 12:
        raise ValueError("Screenshot-Daten unvollständig")

    if raw[0:2] != b"BM":
        raise ValueError("Keine BMP-Signatur im Screenshot")

    size = int.from_bytes(raw[2:6], "big")
    offset = int.from_bytes(raw[10:14], "big")
    header_size = int.from_bytes(raw[14:18], "little")
    width = int.from_bytes(raw[18:22], "big")
    height = int.from_bytes(raw[22:26], "big")
    planes = int.from_bytes(raw[26:28], "little")
    bpp = int.from_bytes(raw[28:30], "little")
    compression = int.from_bytes(raw[30:34], "little")

    if header_size != 40:
        raise ValueError("Unerwartete BITMAPINFOHEADER-Größe")

    if size != len(raw):
        raise ValueError("Screenshot-Größe passt nicht zu den Daten")
    if (planes, bpp, compression, offset) != (1, 16, 3, 14 + 40 + 12):
        raise ValueError("Unerwartetes Screenshot-Format")

    rowsize = width * 2
    if len(raw) < offset + rowsize * height:
        raise ValueError("Screenshot-Pixeldaten unvollständig")

    rows: list[list[tuple[int, int, int]]] = []
    for y in range(height - 1, -1, -1):
        row: list[tuple[int, int, int]] = []
        base = offset + y * rowsize
        for x in range(width):
            value = int.from_bytes(raw[base + x * 2: base + x * 2 + 2], "big")
            r5 = (value >> 11) & 0x1F
            g6 = (value >> 5) & 0x3F
            b5 = value & 0x1F
            row.append((r5 << 3 | r5 >> 2, g6 << 2 | g6 >> 4, b5 << 3 | b5 >> 2))
        rows.append(row)
    return Screenshot(width, height, rows)
