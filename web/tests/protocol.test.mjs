/**
 * Tests der Protokoll-Portierung (web/protocol.js) als
 * Gegenstueck zu tests/test_protocol.py; Ausfuehrung mit
 * node --test web/tests/protocol.test.mjs
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  parseStatus, formatFrequencyCommand, formatMemoryCommand,
  volumeBurst, sMeter, stepHz, STATUS_FIELDS,
} from "../protocol.js";

const VALID_LINE =
  "201,3600,0,0,80M,LSB,25,4,3,30,42,18,2100,3.95,77";

test("gueltige Monitorzeile wird geparst", () => {
  const s = parseStatus(VALID_LINE);
  assert.ok(s);
  assert.equal(s.frequency, 3600);
  assert.equal(s.band, "80M");
  assert.equal(s.mode, "LSB");
  assert.equal(s.volume, 30);
  assert.equal(s.rssi, 42);
  assert.equal(s.snr, 18);
  assert.equal(s.voltage, 3.95);
});

test("Anzeigefrequenz: FM in 10-kHz-Schritten, SSB mit BFO", () => {
  const fm = parseStatus("201,10790,0,0,VHF,FM,10k,0,5,30,42,18,2100,3.95,77");
  assert.equal(fm.displayFrequencyHz(), 107900000);
  const ssb = parseStatus(VALID_LINE);
  assert.equal(ssb.displayFrequencyHz(), 3600000);
  const bfo = parseStatus("201,7100,1500,0,40M,USB,25,4,3,30,42,18,2100,3.95,77");
  assert.equal(bfo.displayFrequencyHz(), 7101500);
});

test("falsche Feldzahl und Muell werden abgelehnt", () => {
  assert.equal(parseStatus("201,3600"), null);
  assert.equal(parseStatus(""), null);
  assert.equal(parseStatus("a,b,c"), null);
  assert.equal(parseStatus(null), null);
  assert.equal(parseStatus(undefined), null);
});

test("JavaScript-typische Zahlentrueke werden abgelehnt", () => {
  // Leere Felder (Number('') === 0), Hex-, Exponenten- und
  // Dezimalbruch-Schreibweisen in Ganzzahl-Feldern, Overflow
  const over = (idx, value) => {
    const fields = VALID_LINE.split(",");
    fields[idx] = value;
    return parseStatus(fields.join(","));
  };
  assert.equal(over(0, ""), null, "leeres Feld");
  assert.equal(over(0, " 201 ").version, 201, "whitespace wie float()/int()");
  assert.equal(over(0, "0x10"), null, "hex");
  assert.equal(over(1, "1e2"), null, "exponent");
  assert.equal(over(1, "3600.5"), null, "dezimalbruch");
  assert.equal(over(1, "99999999999999999999"), null, "ueber safe integer");
  assert.equal(over(13, "0x10"), null, "hex-spannung");
  assert.equal(over(13, "1.5e1").voltage, 15, "exponent wie float()");
});

test("Manipulierte Werte werden abgelehnt (Grenzen der Firmware)", () => {
  const over = (idx, value) => {
    const fields = VALID_LINE.split(",");
    fields[idx] = String(value);
    return parseStatus(fields.join(","));
  };
  assert.equal(parseStatus(VALID_LINE) !== null, true);
  // Volume > 63, RSSI > 255, Frequenz > 100000, Spannung > 20 V
  assert.equal(over(9, 64), null, "volume");
  assert.equal(over(10, 256), null, "rssi");
  assert.equal(over(1, 100001), null, "frequency");
  assert.equal(over(13, 21.5), null, "voltage");
  assert.equal(over(13, -1.0), null, "negative spannung");
  assert.equal(over(2, 2000000), null, "bfo");
});

test("Steuerzeichen und Riesentexte in Freitextfeldern werden abgelehnt", () => {
  const fields = VALID_LINE.split(",");
  fields[4] = "B\x03and";
  assert.equal(parseStatus(fields.join(",")), null);
  fields[4] = "x".repeat(17);
  assert.equal(parseStatus(fields.join(",")), null);
});

test("Frequenzbefehl mit und ohne SSB", () => {
  assert.equal(formatFrequencyCommand(7100000, false), "F7100000\r\n");
  assert.equal(formatFrequencyCommand(7100500, false), "F7100000\r\n");
  assert.equal(formatFrequencyCommand(7100500, true), "F7100500\r\n");
  assert.throws(() => formatFrequencyCommand(0, false));
  assert.throws(() => formatFrequencyCommand(-5, false));
});

test("Speicherbefehl und Validierung", () => {
  assert.equal(formatMemoryCommand(1, "VHF", 107900000, "FM"),
               "#01,VHF,107900000,FM\r\n");
  // Frequenz 0 loescht den Slot
  assert.equal(formatMemoryCommand(32, "VHF", 0, "FM"),
               "#32,VHF,0,FM\r\n");
  assert.throws(() => formatMemoryCommand(0, "VHF", 1000000, "FM"));
  assert.throws(() => formatMemoryCommand(33, "VHF", 1000000, "FM"));
  assert.throws(() => formatMemoryCommand(1, "V\x7fHF", 1000000, "FM"));
  assert.throws(() => formatMemoryCommand(1, "", 1000000, "FM"));
  assert.throws(() => formatMemoryCommand(1, "VHF", -1, "FM"));
  assert.throws(() => formatMemoryCommand(1, "VHF", 1000000001, "FM"));
});

test("Lautstaerke-Burst", () => {
  assert.equal(volumeBurst(10, 13), "VVV");
  assert.equal(volumeBurst(13, 10), "vvv");
  assert.equal(volumeBurst(5, 5), "");
  assert.equal(volumeBurst(-1, 5), "V".repeat(5), "clamp wie protocol.py");
  assert.equal(volumeBurst(0, 64), "V".repeat(63), "clamp wie protocol.py");
  assert.equal(volumeBurst(10, 1e9), "V".repeat(53), "clamp wie protocol.py");
  assert.equal(volumeBurst(1e9, 0), "v".repeat(63), "clamp wie protocol.py");
});

test("S-Wert-Tabelle wie Firmware (AM- und FM-Skala)", () => {
  assert.equal(sMeter(0, false), "S0");
  assert.equal(sMeter(2, false), "S1");
  assert.equal(sMeter(10, false), "S4");
  assert.equal(sMeter(44, false), "S9");
  assert.equal(sMeter(54, false), "S9+10");
  assert.equal(sMeter(95, false), "S9+60");
  assert.equal(sMeter(96, false), ">S9+60");
  assert.equal(sMeter(24, true), "S9");
  assert.equal(sMeter(34, true), "S9+10");
  assert.equal(sMeter(76, true), "S9+60");
  assert.equal(sMeter(300, false), "\u2013");
});

test("Schrittweiten-Text in Hz", () => {
  assert.equal(stepHz("10k"), 10000);
  assert.equal(stepHz("1M"), 1000000);
  assert.equal(stepHz("25"), 25);
  assert.equal(stepHz("muell"), 1000);
  assert.equal(stepHz("", 500), 500, "leerer text mit fallback");
  assert.equal(stepHz(""), 1000, "leerer text");
  assert.equal(stepHz("25abc"), 1000, "zahl mit muell-suffix");
  assert.equal(stepHz("abc25"), 1000);
  assert.equal(stepHz("0x10"), 1000, "hex");
  assert.equal(stepHz("10 k"), 1000, "leerzeichen im text");
});

test("STATUS_FIELDS betraegt 15", () => {
  assert.equal(STATUS_FIELDS, 15);
});
