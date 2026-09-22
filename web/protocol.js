/**
 * Protokoll-Portierung des ATS-Mini Ad-hoc-Fernsteuerprotokolls.
 * Eins-zu-eins-Umsetzung von ats_mini_remote/protocol.py (Python) nach
 * JavaScript, damit beide Implementierungen dieselben Prüfungen gegen
 * eine manipulierte Gegenseite durchfuehren:
 *   - Zeilenbefehle: 'F<frequenz-hz>\r\n', '#<slot>,<band>,<freq>,<mode>\r\n'
 *   - Einzeltasten: 'R'/'r', 'V'/'v', 'B'/'b', 'M'/'m', 'S'/'s',
 *     'W'/'w', 'A'/'a', 't', '$', 'C', 'e'
 *   - Monitor: CSV-Zeile mit 15 Feldern
 */

export const DEFAULT_PORT = 60000;

export const STATUS_FIELDS = 15;

// Begrenzungen fuer Werte aus der Gegenstelle: Die Firmware druckt
// RSSI/SNR als uint8, Volume 0..63, AGC-Index 0..37, Kondensator als
// uint16, Sequenznummer mod 256. Alles darueber ist manipuliert oder
// defekt (gleiche Grenzen wie in protocol.py).
const TEXT_FIELD_MAX = 16;
const VOLUME_MAX = 63;
const UINT8_MAX = 255;
const UINT16_MAX = 65535;

const IDX_VERSION = 0;
const IDX_FREQUENCY = 1;
const IDX_BFO = 2;
const IDX_CAL = 3;
const IDX_BAND = 4;
const IDX_MODE = 5;
const IDX_STEP = 6;
const IDX_BANDWIDTH = 7;
const IDX_AGC = 8;
const IDX_VOLUME = 9;
const IDX_RSSI = 10;
const IDX_SNR = 11;
const IDX_CAPACITOR = 12;
const IDX_VOLTAGE = 13;
const IDX_SEQNUM = 14;

export class ProtocolError extends Error {}

export class ReceiverStatus {
  constructor() {
    this.version = 0;
    this.frequency = 0;      // FM: 10-kHz-Schritte, AM/SSB: kHz
    this.bfo = 0;            // SSB: Hz
    this.cal = 0;
    this.band = "";
    this.mode = "";          // FM / AM / LSB / USB
    this.step = "";
    this.bandwidth = "";
    this.agc = 0;
    this.volume = 0;         // 0..63, 0 = stumm
    this.rssi = 0;           // dBuV
    this.snr = 0;            // dB
    this.capacitor = 0;
    this.voltage = 0.0;      // V
    this.seqnum = 0;
  }

  /** Anzeigefrequenz in Hz; in SSB-Modi kHz*1000 + BFO. */
  displayFrequencyHz() {
    if (this.mode.toUpperCase() === "FM") {
      return this.frequency * 10000;
    }
    return this.frequency * 1000 + this.bfo;
  }
}

/** Monitor-CSV-Zeile in einen ReceiverStatus umwandeln; null bei Muell. */
export function parseStatus(line) {
  if (typeof line !== "string") {
    return null;
  }
  const fields = line.split(",").map((f) => f.trim());
  if (fields.length !== STATUS_FIELDS) {
    return null;
  }
  // Freitextfelder begrenzen: keine Riesentexte und keine Steuerzeichen
  for (const idx of [IDX_BAND, IDX_MODE, IDX_STEP, IDX_BANDWIDTH]) {
    const text = fields[idx];
    if (text.length > TEXT_FIELD_MAX) {
      return null;
    }
    for (const ch of text) {
      const code = ch.charCodeAt(0);
      if (code < 32 || code > 126) {
        return null;
      }
    }
  }
  const numbers = [IDX_VERSION, IDX_FREQUENCY, IDX_BFO, IDX_CAL, IDX_AGC,
                   IDX_VOLUME, IDX_RSSI, IDX_SNR, IDX_CAPACITOR, IDX_SEQNUM];
  const values = {};
  for (const idx of numbers) {
    const n = Number(fields[idx]);
    if (!Number.isInteger(n)) {
      return null;
    }
    values[idx] = n;
  }
  const voltage = Number(fields[IDX_VOLTAGE]);
  if (!Number.isFinite(voltage)) {
    return null;
  }
  // Werte auf firmware-plausible Bereiche begrenzen (siehe protocol.py)
  if (values[IDX_VERSION] < 0 || values[IDX_VERSION] > 1000000) return null;
  if (values[IDX_FREQUENCY] < 0 || values[IDX_FREQUENCY] > 100000) return null;
  if (values[IDX_BFO] < -1000000 || values[IDX_BFO] > 1000000) return null;
  if (values[IDX_CAL] < -1000000 || values[IDX_CAL] > 1000000) return null;
  if (values[IDX_AGC] < 0 || values[IDX_AGC] > UINT8_MAX) return null;
  if (values[IDX_VOLUME] < 0 || values[IDX_VOLUME] > VOLUME_MAX) return null;
  if (values[IDX_RSSI] < 0 || values[IDX_RSSI] > UINT8_MAX) return null;
  if (values[IDX_SNR] < 0 || values[IDX_SNR] > UINT8_MAX) return null;
  if (values[IDX_CAPACITOR] < 0 || values[IDX_CAPACITOR] > UINT16_MAX) return null;
  if (values[IDX_SEQNUM] < 0 || values[IDX_SEQNUM] > UINT16_MAX) return null;
  if (voltage < 0.0 || voltage > 20.0) return null;

  const s = new ReceiverStatus();
  s.version = values[IDX_VERSION];
  s.frequency = values[IDX_FREQUENCY];
  s.bfo = values[IDX_BFO];
  s.cal = values[IDX_CAL];
  s.band = fields[IDX_BAND];
  s.mode = fields[IDX_MODE];
  s.step = fields[IDX_STEP];
  s.bandwidth = fields[IDX_BANDWIDTH];
  s.agc = values[IDX_AGC];
  s.volume = values[IDX_VOLUME];
  s.rssi = values[IDX_RSSI];
  s.snr = values[IDX_SNR];
  s.capacitor = values[IDX_CAPACITOR];
  s.voltage = voltage;
  s.seqnum = values[IDX_SEQNUM];
  return s;
}

/** Zahlenformat mit dem Locale-Dezimaltrenner (wie fmt_num). */
export function decimalSeparator() {
  const probe = (1.5).toLocaleString(undefined, { minimumFractionDigits: 1 });
  return probe.includes(",") ? "," : ".";
}

export function fmtNum(value, decimals = 2) {
  return value.toFixed(decimals).replace(".", decimalSeparator());
}

/** Liest eine Zahl, akzeptiert Komma und Punkt als Trenner. */
export function parseFloatText(text) {
  return parseFloat(text.trim().replace(",", "."));
}

/** Schrittweiten-Text ('10k', '1M', '25') in Hz; robust gegen Muell. */
export function stepHz(text, fallback = 1000) {
  const value = String(text).trim().toLowerCase();
  try {
    let hz;
    if (value.endsWith("m")) {
      hz = Math.floor(parseFloat(value.slice(0, -1)) * 1000000);
    } else if (value.endsWith("k")) {
      hz = Math.floor(parseFloat(value.slice(0, -1)) * 1000);
    } else {
      hz = parseInt(value, 10);
    }
    if (!Number.isFinite(hz)) return fallback;
    if (hz < 1 || hz > 100000000) return fallback;
    return hz;
  } catch {
    return fallback;
  }
}

/** Erzeugt den Frequenzbefehl 'F<hz>\r\n'. */
export function formatFrequencyCommand(hz, ssb) {
  if (!Number.isInteger(hz) || hz <= 0) {
    throw new ProtocolError("Frequenz muss positiv sein");
  }
  const payload = ssb ? String(hz) : String(Math.floor(hz / 1000) * 1000);
  return `F${payload}\r\n`;
}

/** Erzeugt den Speicherbefehl '#<slot>,<band>,<freq>,<mode>\r\n'.
 * Frequenz 0 loescht den Slot. */
export function formatMemoryCommand(slot, band, hz, mode) {
  if (!Number.isInteger(slot) || slot < 1 || slot > 32) {
    throw new ProtocolError("Slot muss zwischen 1 und 32 liegen");
  }
  for (const text of [band, mode]) {
    if (typeof text !== "string" || text.length < 1 || text.length > 16) {
      throw new ProtocolError("Ung\u00fcltiger Band- oder Modustext");
    }
    for (const ch of text) {
      const code = ch.charCodeAt(0);
      if (code < 32 || code > 126) {
        throw new ProtocolError("Ung\u00fcltiger Band- oder Modustext");
      }
    }
  }
  if (!Number.isInteger(hz) || hz < 0 || hz > 1000000000) {
    throw new ProtocolError("Frequenz ausserhalb plausibler Grenzen");
  }
  const slotText = String(slot).padStart(2, "0");
  return `#${slotText},${band},${hz},${mode}\r\n`;
}

// Einzeltasten-Befehle
export const CMD = {
  ENCODER_UP: "R",
  ENCODER_DOWN: "r",
  ENCODER_CLICK: "e",
  VOLUME_UP: "V",
  VOLUME_DOWN: "v",
  BAND_UP: "B",
  BAND_DOWN: "b",
  MODE_UP: "M",
  MODE_DOWN: "m",
  STEP_UP: "S",
  STEP_DOWN: "s",
  BANDWIDTH_UP: "W",
  BANDWIDTH_DOWN: "w",
  AGC_UP: "A",
  AGC_DOWN: "a",
  TOGGLE_LOG: "t",
  SHOW_MEMORIES: "$",
  SCREENSHOT: "C",
};

/** Lautst\u00e4rke- Burst: 'V'/'v' so oft, dass von from nach to gewechselt wird. */
export function volumeBurst(from, to) {
  if (!Number.isInteger(from) || !Number.isInteger(to)) return "";
  if (from < 0 || to < 0 || from > VOLUME_MAX || to > VOLUME_MAX) return "";
  if (to === from) return "";
  if (to > from) {
    return CMD.VOLUME_UP.repeat(to - from);
  }
  return CMD.VOLUME_DOWN.repeat(from - to);
}

/**
 * S-Wert aus RSSI (wie s_meter in protocol.py); fm waehlt die
 * FM-Tabelle (dBuV) statt der AM-Tabelle.
 */
export function sMeter(rssi, fm) {
  if (rssi < 0 || rssi > UINT8_MAX) return "\u2013";
  if (rssi <= 1) return "S0";
  if (!fm) {
    if (rssi <= 2) return "S1";
    if (rssi <= 3) return "S2";
    if (rssi <= 4) return "S3";
    if (rssi <= 10) return "S4";
    if (rssi <= 16) return "S5";
    if (rssi <= 22) return "S6";
    if (rssi <= 28) return "S7";
    if (rssi <= 34) return "S8";
    if (rssi <= 44) return "S9";
    if (rssi <= 54) return "S9+10";
    if (rssi <= 64) return "S9+20";
    if (rssi <= 74) return "S9+30";
    if (rssi <= 84) return "S9+40";
    if (rssi <= 94) return "S9+50";
    if (rssi <= 95) return "S9+60";
    return ">S9+60";
  }
  if (rssi <= 2) return "S6";
  if (rssi <= 8) return "S7";
  if (rssi <= 14) return "S8";
  if (rssi <= 24) return "S9";
  if (rssi <= 34) return "S9+10";
  if (rssi <= 44) return "S9+20";
  if (rssi <= 54) return "S9+30";
  if (rssi <= 64) return "S9+40";
  if (rssi <= 74) return "S9+50";
  if (rssi <= 76) return "S9+60";
  return ">S9+60";
}
