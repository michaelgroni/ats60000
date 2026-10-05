/**
 * Tests des BLE-Transports (web/ble.js) mit einer nachgebauten
 * Web-Bluetooth-Umgebung; Ausfuehrung mit
 * node --test web/tests/ble.test.mjs
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { BleTransport, NUS_SERVICE } from "../ble.js";

/** Kleiner Ersatz fuer DataView/TextEncoder-Welt des Browsers. */
class FakeValue {
  constructor(text) {
    this.value = { text };
  }
}

class FakeChar {
  constructor(name) {
    this.name = name;
    this.listeners = [];
    this.written = [];
  }
  addEventListener(_type, fn) {
    this.listeners.push(fn);
  }
  removeEventListener(_type, fn) {
    this.listeners = this.listeners.filter((f) => f !== fn);
  }
  async startNotifications() {}
  async writeValue(bytes) {
    this.written.push(new TextDecoder().decode(bytes));
  }
  notify(text) {
    const event = { target: { value: new TextEncoder().encode(text) } };
    for (const fn of this.listeners) {
      fn(event);
    }
  }
}

class FakeService {
  constructor() {
    this.tx = new FakeChar("tx");
    this.rx = new FakeChar("rx");
  }
  async getCharacteristic(uuid) {
    return uuid.startsWith("6e400002") ? this.rx : this.tx;
  }
}

class FakeServer {
  constructor() {
    this.service = new FakeService();
    this.connected = false;
  }
  async connect() {
    this.connected = true;
    return this;
  }
  async getPrimaryService() {
    return this.service;
  }
  disconnect() {
    this.connected = false;
  }
}

function fakeEnv() {
  const server = new FakeServer();
  const device = {
    gatt: server,
    listeners: {},
    addEventListener(type, fn) {
      this.listeners[type] = fn;
    },
  };
  const nav = {
    bluetooth: {
      async requestDevice() {
        return device;
      },
    },
  };
  return { nav, device, server };
}

test("connect baut GATT auf und aktiviert TX-Notifications", async () => {
  const { nav } = fakeEnv();
  const lines = [];
  const states = [];
  const t = new BleTransport((l) => lines.push(l), (s) => states.push(s),
                            nav.bluetooth);
  await t.connect();
  assert.equal(t.connected, true);
  assert.deepEqual(states, ["connecting", "connected"]);
});

test("Zeilen werden ueber Chunk-Grenzen hinweg gesammelt", async () => {
  const { nav, server } = fakeEnv();
  const lines = [];
  const t = new BleTransport((l) => lines.push(l), null, nav.bluetooth);
  await t.connect();
  const tx = server.service.tx;
  tx.notify("201,3600,0,0,80M,LSB,");
  tx.notify("25,4,3,30,42,18,2");
  tx.notify("100,3.95,77\r\n");
  tx.notify("zweite Zeile\r\n");
  assert.equal(lines.length, 2);
  assert.ok(lines[0].startsWith("201,3600"));
  assert.ok(lines[0].endsWith("77"));
  assert.equal(lines[1], "zweite Zeile");
});

test("send schreibt auf die RX-Charakteristik", async () => {
  const { nav, server } = fakeEnv();
  const t = new BleTransport(null, null, nav.bluetooth);
  await t.connect();
  await t.send("F107900000\r\n");
  await t.send("V");
  assert.deepEqual(server.service.rx.written, ["F107900000\r\n", "V"]);
});

test("send ohne Verbindung wirft", async () => {
  const t = new BleTransport(null, null, {});
  await assert.rejects(() => t.send("V"), /Nicht verbunden/);
});

test("gattserverdisconnected triggert Reconnect", async () => {
  const { nav, device } = fakeEnv();
  const states = [];
  const t = new BleTransport(null, (s) => states.push(s), nav.bluetooth);
  await t.connect();
  device.listeners["gattserverdisconnected"]();
  assert.equal(t.connected, false);
  assert.ok(states.includes("disconnected"));
  t.disconnect();
});

test("disconnect stoppt Reconnect und raeumt auf", async () => {
  const { nav } = fakeEnv();
  const states = [];
  const t = new BleTransport(null, (s) => states.push(s), nav.bluetooth);
  await t.connect();
  t.disconnect();
  assert.equal(t.connected, false);
  assert.equal(t._reconnectTimer, null);
  assert.equal(states.at(-1), "disconnected");
});

test("NUS-Service-UUID wie Firmware-Dokumentation", () => {
  assert.equal(NUS_SERVICE,
    "6e400001-b5a3-f393-e0a9-e50e24dcca9e");
});

/* ---- Böswilliger Browser: manipulierte API-Objekte ---- */

test("Notification mit unbrauchbarem value crasht den Empfang nicht", async () => {
  const { nav, server } = fakeEnv();
  const lines = [];
  const t = new BleTransport((l) => lines.push(l), null, nav.bluetooth);
  await t.connect();
  const tx = server.service.tx;
  tx.notify("erste Zeile\r\n");
  for (const bad of [undefined, null, {}, 12345, "text", new Map()]) {
    const event = { target: { value: bad } };
    for (const fn of tx.listeners) {
      fn(event);
    }
  }
  tx.notify("zweite Zeile\r\n");
  assert.deepEqual(lines, ["erste Zeile", "zweite Zeile"]);
});

test("Notification mit craschendem target-Getter laeuft weiter", async () => {
  const { nav, server } = fakeEnv();
  const lines = [];
  const t = new BleTransport((l) => lines.push(l), null, nav.bluetooth);
  await t.connect();
  const tx = server.service.tx;
  const evilEvent = {
    get target() {
      throw new Error("boeser Browser");
    },
  };
  for (const fn of tx.listeners) {
    fn(evilEvent);
  }
  tx.notify("ok\r\n");
  assert.deepEqual(lines, ["ok"]);
});

test("onLine-Ausnahme blockiert nachfolgende Zeilen nicht", async () => {
  const { nav, server } = fakeEnv();
  let calls = 0;
  const t = new BleTransport(() => {
    calls += 1;
    if (calls === 1) {
      throw new Error("Absturz in der Anzeige");
    }
  }, null, nav.bluetooth);
  await t.connect();
  server.service.tx.notify("erste\r\nzweite\r\n");
  assert.equal(calls, 2);
});

test("Riesenzeilen ohne Zeilenende werden begrenzt, Rest bleibt lesbar", async () => {
  const { nav, server } = fakeEnv();
  const lines = [];
  const t = new BleTransport((l) => lines.push(l), null, nav.bluetooth);
  await t.connect();
  const tx = server.service.tx;
  tx.notify("x".repeat(5000));
  tx.notify("x".repeat(5000));
  // Resync: bis zum naechsten Zeilenende wird verworfen
  tx.notify("erste\r\n");
  tx.notify("zweite\r\n");
  assert.deepEqual(lines, ["zweite"]);
  assert.equal(t._buffer, "");
});

test("Einzelne ueberlange Zeile wird verworfen, Nachfolger verarbeitet", async () => {
  const { nav, server } = fakeEnv();
  const lines = [];
  const t = new BleTransport((l) => lines.push(l), null, nav.bluetooth);
  await t.connect();
  const tx = server.service.tx;
  tx.notify("a".repeat(600) + "\r\n");
  tx.notify("kurz\r\n");
  assert.deepEqual(lines, ["kurz"]);
});

test("requestDevice ohne brauchbares Geraet fuehrt zu Fehler", async () => {
  const nav = {
    bluetooth: {
      async requestDevice() {
        return {};
      },
    },
  };
  const t = new BleTransport(null, null, nav.bluetooth);
  await assert.rejects(() => t.connect(), /Ung.ltiges/);
  assert.equal(t._wantConnected, false);
});

test("connect mit craschender GATT-Schnittstelle wirft sauber", async () => {
  const nav = {
    bluetooth: {
      async requestDevice() {
        return {
          gatt: null,
          addEventListener() {},
        };
      },
    },
  };
  const t = new BleTransport(null, null, nav.bluetooth);
  await assert.rejects(() => t.connect(), /Ung.ltiges/);
});

test("available() verlangt requestDevice-Funktion", () => {
  assert.equal(BleTransport.available({}), false);
  assert.equal(BleTransport.available(null), false);
});

test("writeValue-Ausnahme wird an send() weitergereicht", async () => {
  const { nav, server } = fakeEnv();
  const t = new BleTransport(null, null, nav.bluetooth);
  await t.connect();
  server.service.rx.writeValue = async () => {
    throw new DOMException("GATT operation failed", "NetworkError");
  };
  await assert.rejects(() => t.send("V"), /GATT/);
});

test("Reconnect mit Backoff statt starrem Takt", async () => {
  const { nav, device } = fakeEnv();
  const t = new BleTransport(null, null, nav.bluetooth);
  await t.connect();
  // GATT-Verbindung scheitert dauerhaft: Backoff muss die
  // Verzoegerung jeweils vergroessern
  device.gatt.connect = async () => {
    throw new Error("GATT nicht erreichbar");
  };
  const realSetTimeout = globalThis.setTimeout;
  const delays = [];
  globalThis.setTimeout = (fn, delay) => {
    delays.push(delay);
    return realSetTimeout(fn, 0);
  };
  try {
    device.listeners["gattserverdisconnected"]();
    await new Promise((r) => realSetTimeout(r, 30));
    assert.equal(delays.length >= 2, true);
    assert.ok(delays[1] > delays[0], "Verzoegerung waechst");
    assert.ok(delays.every((d) => d <= 30000), "Backoff begrenzt");
  } finally {
    globalThis.setTimeout = realSetTimeout;
  }
  t.disconnect();
});

test("Wiederverbindung registriert den Notify-Listener nur einmal", async () => {
  const { nav, server } = fakeEnv();
  const lines = [];
  const t = new BleTransport((l) => lines.push(l), null, nav.bluetooth);
  await t.connect();
  const tx = server.service.tx;
  tx.notify("einmal\r\n");
  assert.deepEqual(lines, ["einmal"]);
  // Simuliert Reconnect: _connectGatt erneut mit gleichem Char-Objekt
  await t._connectGatt();
  tx.notify("einmal\r\n");
  assert.deepEqual(lines, ["einmal", "einmal"]);
});

test("disconnect raeumt Listener-Referenzen auf", async () => {
  const { nav } = fakeEnv();
  const t = new BleTransport(null, null, nav.bluetooth);
  await t.connect();
  assert.ok(t._txChar);
  assert.ok(t._notifyHandler);
  t.disconnect();
  assert.equal(t.rxChar, null);
  assert.equal(t._buffer, "");
});
