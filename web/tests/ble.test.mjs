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
