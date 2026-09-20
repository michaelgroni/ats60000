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


# Bandtabelle der Firmware (Menu.cpp: bands[]), kHz.
# Achtung: Die Firmware speichert Bandgrenzen in modusspezifischen Einheiten
# (FM: 10-kHz-Schritte, AM/SSB: kHz, siehe Utils.cpp freqFromHz/freqToHz).
# Hier sind alle Grenzen einheitlich in kHz umgerechnet.
# Name, Modus, min (kHz), max (kHz)
BANDS = [
    ("VHF", "FM", 64000, 108000),
    ("ALL", "AM", 150, 30000),
    ("11M", "AM", 25600, 26100),
    ("13M", "AM", 21500, 21900),
    ("15M", "AM", 18900, 19100),
    ("16M", "AM", 17400, 18100),
    ("19M", "AM", 15100, 15900),
    ("22M", "AM", 13500, 13900),
    ("25M", "AM", 11000, 13000),
    ("31M", "AM", 9000, 11000),
    ("41M", "AM", 7000, 9000),
    ("49M", "AM", 5000, 7000),
    ("60M", "AM", 4000, 5100),
    ("75M", "AM", 3500, 4000),
    ("90M", "AM", 3000, 3500),
    ("MW3", "AM", 1700, 3500),
    ("MW2", "AM", 495, 1701),
    ("MW1", "AM", 150, 1800),
    ("160M", "LSB", 1800, 2000),
    ("80M", "LSB", 3500, 4000),
    ("40M", "LSB", 7000, 7300),
    ("30M", "LSB", 10000, 10200),
    ("20M", "USB", 14000, 14400),
    ("17M", "USB", 18000, 18200),
    ("15M", "USB", 21000, 21500),
    ("12M", "USB", 24800, 25000),
    ("10M", "USB", 28000, 29700),
    ("CB", "AM", 25000, 28000),
]


def band_range(band_name: str, mode: str) -> tuple[int, int] | None:
    """Liefert (min_kHz, max_kHz) für ein Band, oder None wenn unbekannt."""
    for name, _mode, lo, hi in BANDS:
        if name.upper() == band_name.upper() and _mode == mode.upper():
            return (lo, hi)
    # Fallback: Bandname passt, Modus weicht ab (z. B. nach Moduswechsel)
    for name, _mode, lo, hi in BANDS:
        if name.upper() == band_name.upper():
            return (lo, hi)
    return None


def s_meter(rssi: int, fm: bool) -> str:
    """S-Wert nach Kurzwellen-Praxis aus der RSSI-Angabe (dBµV).

    Entspricht der Umrechnungstabelle der Firmware (Utils.cpp:421);
    HF (AM/SSB) und FM haben unterschiedliche Skalen, über S9 hinaus
    wird wie üblich in 10-dB-Schritten weitergezählt.
    """
    if not fm:
        if rssi <= 1: return "S0"
        if rssi <= 2: return "S1"
        if rssi <= 3: return "S2"
        if rssi <= 4: return "S3"
        if rssi <= 10: return "S4"
        if rssi <= 16: return "S5"
        if rssi <= 22: return "S6"
        if rssi <= 28: return "S7"
        if rssi <= 34: return "S8"
        if rssi <= 44: return "S9"
        if rssi <= 54: return "S9+10"
        if rssi <= 64: return "S9+20"
        if rssi <= 74: return "S9+30"
        if rssi <= 84: return "S9+40"
        if rssi <= 94: return "S9+50"
        if rssi <= 95: return "S9+60"
        return ">S9+60"
    if rssi <= 1: return "S0"
    if rssi <= 2: return "S6"
    if rssi <= 8: return "S7"
    if rssi <= 14: return "S8"
    if rssi <= 24: return "S9"
    if rssi <= 34: return "S9+10"
    if rssi <= 44: return "S9+20"
    if rssi <= 54: return "S9+30"
    if rssi <= 64: return "S9+40"
    if rssi <= 74: return "S9+50"
    if rssi <= 76: return "S9+60"
    return ">S9+60"


def step_size_hz(status: "ReceiverStatus") -> int:
    """Wandelt das Schrittweiten-Feld des Monitor-Status in Hz um.

    FM/AM-Schritte sind wie '10k', '100k' oder '1M' formatiert,
    SSB-Schritte sind reine Zahlen in Hz ('25', '100').
    """
    text = status.step.lower()
    if text.endswith("k"):
        return int(float(text[:-1]) * 1000)
    if text.endswith("m"):
        return int(float(text[:-1]) * 1_000_000)
    try:
        return int(text)
    except ValueError:
        return 1000


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
#
# Achtung: R/r/e emulieren den Drehencoder bzw. dessen Tastendruck und
# wirken in der Firmware je nach aktuell geöffnetem Menü auf den
# MENÜEINTRAG (z. B. den Wi-Fi-Modus), nicht auf die Frequenz. Für
# Fernsteuerung daher nicht verwenden.
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

# Schrittweiten je Modus in Firmware-Reihenfolge (Menu.cpp: steps[]).
# S/s laufen zyklisch durch diese Liste; der Status meldet den Text.
# FM: kHz, SSB: Hz, AM: kHz (Einheiten wie in der Firmware-Tabelle).
FM_STEPS = ["10k", "50k", "100k", "200k", "1M"]
SSB_STEPS = ["10", "25", "50", "100", "500", "1k", "5k", "9k", "10k"]
AM_STEPS = ["1k", "5k", "9k", "10k", "50k", "100k", "1M"]

# Modi in Firmware-Reihenfolge (Menu.cpp: bandModeDesc). M/m laufen im
# Zyklus LSB -> USB -> AM -> LSB; FM ist nur auf FM-Baendern moeglich und
# kann per Befehl weder betreten noch verlassen werden (doMode).
NON_FM_MODES = ["LSB", "USB", "AM"]


def mode_steps(current: str, target: str) -> bytes:
    """Befehlsfolge (M/m), um von 'current' auf 'target' zu kommen.

    Wie doMode() der Firmware: pro M/m genau ein Schritt im Zyklus
    LSB -> USB -> AM -> LSB, FM wird uebersprungen. Bereits passender
    Modus oder FM als Quelle oder Ziel -> leerer Befehl.
    """
    cur = current.upper()
    tgt = target.upper()
    if cur == tgt or cur == "FM" or tgt == "FM":
        return b""
    i_cur = NON_FM_MODES.index(cur)
    i_tgt = NON_FM_MODES.index(tgt)
    n = len(NON_FM_MODES)
    fwd = (i_tgt - i_cur) % n
    rev = (i_cur - i_tgt) % n
    if rev < fwd:
        return CMD_MODE_DOWN * rev
    return CMD_MODE_UP * fwd


# Modus-Defaults der Firmware (Menu.cpp: defaultStepIdx/defaultBwIdx):
# doMode() setzt Schrittweite und Bandbreite bei jedem Moduswechsel
# auf diese Werte zurueck (getCurrentStep/getCurrentBandwidth).
def default_step(mode: str) -> str:
    """Schrittweite, die die Firmware nach einem Moduswechsel einstellt."""
    m = mode.upper()
    if m == "FM":
        return FM_STEPS[2]
    if m in ("LSB", "USB"):
        return SSB_STEPS[5]
    return AM_STEPS[1]


def default_bandwidth(mode: str) -> str:
    """Bandbreite, die die Firmware nach einem Moduswechsel einstellt."""
    m = mode.upper()
    if m == "FM":
        return FM_BANDWIDTHS[0]
    if m in ("LSB", "USB"):
        return SSB_BANDWIDTHS[4]
    return AM_BANDWIDTHS[4]


def step_list(mode: str) -> list[str]:
    """Schrittweiten-Texte des Modus in Firmware-Reihenfolge (S/s-Zyklus)."""
    if mode.upper() == "FM":
        return list(FM_STEPS)
    if mode.upper() in ("LSB", "USB"):
        return list(SSB_STEPS)
    return list(AM_STEPS)


def step_hz(text: str) -> int:
    """Schrittweiten-Text in Hz ('10k' -> 10000, '1M' -> 1000000)."""
    value = text.strip().lower()
    if value.endswith("m"):
        return int(float(value[:-1]) * 1_000_000)
    if value.endswith("k"):
        return int(float(value[:-1]) * 1000)
    return int(value)


def step_steps(current: str, target: str, mode: str) -> bytes:
    """Befehlsfolge (S/s), um von 'current' auf 'target' zu kommen.

    Die Firmware laeuft zyklisch durch die Schrittweitenliste des Modus;
    es wird der kuerzere Weg gewaehlt.
    """
    entries = step_list(mode)
    cur = current if current in entries else entries[0]
    tgt = target if target in entries else entries[0]
    i_cur = entries.index(cur)
    i_tgt = entries.index(tgt)
    n = len(entries)
    fwd = (i_tgt - i_cur) % n
    rev = (i_cur - i_tgt) % n
    if rev < fwd:
        return CMD_STEP_DOWN * rev
    return CMD_STEP_UP * fwd


def step_for_points(lo_hz: int, hi_hz: int, points: int,
                   mode: str) -> str:
    """Schrittweite, deren Rasterpunktzahl der gewuenschten am naechsten ist.

    Das Radio kann nur auf seinen Schrittweitenrastern messen; die
    tatsaechliche Punktzahl weicht daher von der eingestellten ab. Frueher
    wurde die dem idealen Punktabstand naechste Schrittweite gewaehlt --
    das rundete oft auf ein feineres Raster und der Sweep bekam deutlich
    mehr Punkte als bestellt (80M, 200 Punkte: Abstand 2,5 kHz, 'naechste'
    Schrittweite 1 kHz -> 501 Punkte). Jetzt zaehlt die Punktzahl, die das
    Raster im Band tatsaechlich liefert; bei Gleichstand gewinnt das
    groebere Raster (weniger Punkte).
    """
    entries = step_list(mode)
    best: tuple[int, int, str] | None = None   # (|diff|, punktzahl, text)
    for text in entries:
        step = step_hz(text)
        count = len(aligned_sweep_freqs(lo_hz, hi_hz, step))
        if count < 2:
            continue
        candidate = (abs(count - points), count, text)
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    if best is not None:
        return best[2]
    # Kein Raster mit >= 2 Punkten im Band: feinstes Raster als Rueckfall
    return min(entries, key=step_hz)


def aligned_sweep_freqs(lo_hz: int, hi_hz: int, step: int) -> list[int]:
    """Sweep-Frequenzen auf das Schrittweitenraster gerundet, in [lo, hi]."""
    if step <= 0:
        return [lo_hz, hi_hz]
    first = ((lo_hz + step - 1) // step) * step
    last = (hi_hz // step) * step
    if last < first:
        return [first] if first <= hi_hz else []
    return list(range(first, last + 1, step))


# Bandbreiten je Modus in Firmware-Reihenfolge (Menu.cpp: bandwidths[]).
# W/w laufen zyklisch durch diese Liste; der Status meldet den Text.
FM_BANDWIDTHS = ["Auto", "110k", "84k", "60k", "40k"]
SSB_BANDWIDTHS = ["0.5k", "1.0k", "1.2k", "2.2k", "3.0k", "4.0k"]
AM_BANDWIDTHS = ["1.0k", "1.8k", "2.0k", "2.5k", "3.0k", "4.0k", "6.0k"]


def bandwidth_list(mode: str) -> list[str]:
    """Bandbreiten-Texte des Modus in Firmware-Reihenfolge (W/w-Zyklus)."""
    if mode.upper() == "FM":
        return list(FM_BANDWIDTHS)
    if mode.upper() in ("LSB", "USB"):
        return list(SSB_BANDWIDTHS)
    return list(AM_BANDWIDTHS)


def bandwidth_khz(text: str, fm: bool) -> float:
    """Bandbreiten-Text in kHz ('Auto' -> 110.0 bei FM)."""
    if text.lower() == "auto":
        return 110.0 if fm else 6.0
    value = float(text.rstrip("kK"))
    return value


def bandwidth_steps(current: str, target: str, mode: str) -> bytes:
    """Befehlsfolge (W/w), um von 'current' auf 'target' zu kommen.

    Die Firmware laeuft zyklisch durch die Liste des Modus; W = vorwaerts,
    w = rueckwaerts. Es wird der kuerzere Weg gewaehlt.
    """
    entries = bandwidth_list(mode)
    cur = current if current in entries else entries[0]
    tgt = target if target in entries else entries[0]
    i_cur = entries.index(cur)
    i_tgt = entries.index(tgt)
    n = len(entries)
    fwd = (i_tgt - i_cur) % n
    rev = (i_cur - i_tgt) % n
    if rev < fwd:
        return CMD_BANDWIDTH_DOWN * rev
    return CMD_BANDWIDTH_UP * fwd


def bandwidth_for_step(step_khz: float, mode: str) -> str:
    """Passende Bandbreite zur Messpunktschrittweite waehlen.

    Die Breite soll etwa der Schrittweite entsprechen; die kleinste
    verfuegbare Breite >= Schrittweite wird gewaehlt. 'Auto' wird
    vermieden, damit der Sweep mit einem festen Filter misst.
    Reicht keine Bandbreite aus (Schrittweite groesser als alle
    Filter), wird die groesste genommen -- Signale zwischen den
    Messpunkten koennen dann zwar uebersehen werden, aber der
    Sweep misst mit dem breitesten verfuegbaren Filter.
    """
    fm = mode.upper() == "FM"
    entries = [t for t in bandwidth_list(mode) if t.lower() != "auto"]
    big = [t for t in entries if bandwidth_khz(t, fm) >= step_khz]
    if big:
        return min(big, key=lambda t: bandwidth_khz(t, fm))
    return max(entries, key=lambda t: bandwidth_khz(t, fm))


def band_entry(band_name: str, current_hz: int = 0,
               mode: str | None = None) -> tuple[str, str, int, int] | None:
    """Bandtabelleneintrag (Name, Modus, min_kHz, max_kHz) fuer ein Band.

    Bandnamen sind nicht eindeutig ('15M' ist Rundfunk- UND Amateurband):
    Bevorzugt wird der Eintrag, der die aktuelle Frequenz enthaelt, dann
    der mit passendem Modus, sonst der erste Treffer des Namens.
    """
    entries = [e for e in BANDS if e[0].upper() == band_name.upper()]
    if not entries:
        return None
    if current_hz > 0:
        for entry in entries:
            if entry[2] * 1000 <= current_hz <= entry[3] * 1000:
                return entry
    if mode:
        for entry in entries:
            if entry[1].upper() == mode.upper():
                return entry
    return entries[0]


def band_table_mode(band: str, current_hz: int = 0,
                    mode: str | None = None) -> str | None:
    """Modus des Bandes laut Bandtabelle (z. B. '80M' -> 'LSB')."""
    entry = band_entry(band, current_hz, mode)
    return entry[1] if entry else None


def suggested_sweep_points(band: str, mode: str | None = None,
                           current_hz: int = 0) -> int:
    """Sinnvolle Messpunktzahl, abhaengig nur vom Band (10..500).

    Das Raster richtet sich nach der Natur des Bandes laut Bandtabelle,
    nicht nach dem aktuell eingestellten Modus:
    - Amateurbaender (Bandtabelle: LSB/USB): ~1 kHz, damit SSB-
      Verbindungen (knapp 3 kHz breit) auch dann einzeln aufloesbar
      sind, wenn der Empfaenger gerade auf AM steht
    - VHF (FM): ~200 kHz Kanalabstand
    - Rundfunkbaender (AM): ~10 kHz Kanalabstand

    Bandnamen sind nicht eindeutig ('15M' ist Rundfunk- und Amateurband);
    mit current_hz wird der Eintrag gewaehlt, der die aktuelle Frequenz
    enthaelt, sonst der mit passendem Modus.
    """
    entry = band_entry(band, current_hz, mode)
    if entry is None:
        return 60
    _name, entry_mode, lo, hi = entry
    span_khz = hi - lo
    table_mode = entry_mode.upper()
    if table_mode in ("LSB", "USB"):
        spacing = 1
    elif table_mode == "FM":
        spacing = 200
    else:
        spacing = 10
    points = int(span_khz / spacing) + 1
    return max(10, min(500, points))


def sweep_points_for_band(band: str, mode: str,
                          current_hz: int = 0) -> tuple[int, int] | None:
    """Messbereich fuer einen Sweep: (min_kHz, max_kHz).

    Im Band 'ALL' wird das aktuelle MHz ganzzahlig ab- und aufgerundet:
    Der Sweep umfasst genau den MHz-Bereich, in dem die aktuelle
    Frequenz liegt (z. B. 15000-16000 kHz bei 15,2 MHz).
    """
    entry = band_entry(band, current_hz, mode)
    if entry is None:
        return None
    _name, _entry_mode, lo, hi = entry
    if band.upper() == "ALL":
        if current_hz <= 0:
            return None
        mhz_lo = max(lo, (current_hz // 1_000_000) * 1000)
        mhz_hi = min(hi, mhz_lo + 1000)
        return mhz_lo, mhz_hi
    return lo, hi





def volume_burst(current: int, target: int) -> bytes:
    """Befehlsfolge, um von 'current' auf 'target' zu kommen (ein Burst).

    Die Firmware kennt nur V/v (Lautstärke ±1). Die Differenz wird als
    ein einziger zusammenhängender Bytestrom übergeben, damit das Radio
    sie als zusammengehörige Folge verarbeitet.
    """
    if target == current:
        return b""
    command = CMD_VOLUME_UP if target > current else CMD_VOLUME_DOWN
    return command * abs(target - current)


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
