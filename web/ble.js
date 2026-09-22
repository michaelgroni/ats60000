/**
 * BLE-Transport fuer das Ad-hoc-Protokoll ueber Web Bluetooth.
 *
 * Die Firmware stellt das Ad-hoc-Protokoll im Modus
 * Settings -> Bluetooth -> Ad hoc ueber den Nordic UART Service
 * (NUS) bereit; die UUIDs entstammen der Firmware-Dokumentation
 * (ble-scan -s 6E400001-B5A3-F393-E0A9-E50E24DCCA9E).
 *
 * Der Transport kapselt die GATT-Charakteristiken als Byte-Stream:
 * TX (Notify) liefert die Monitorzeilen des Radios, RX (Write)
 * nimmt die Befehle entgegen. Zeilen werden im Empfangspuffer
 * gesammelt und zeilenweise als Strings weitergereicht.
 */

export const NUS_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e";
export const NUS_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e";  // write
export const NUS_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e";  // notify

const MAX_LINE = 512;          // Pufferlimit gegen Riesenzeilen
const RECONNECT_DELAY_MS = 1500;

export class BleTransport {
  /** @param {(line: string) => void} onLine  vollstaendige Zeile */
  /** @param {(state: string) => void} onState  "connecting"|"connected"|"disconnected" */
  /** @param {object|undefined} bluetooth  Web-Bluetooth-API (Test-Ersatz) */
  constructor(onLine, onState, bluetooth) {
    this.onLine = onLine;
    this.onState = onState;
    this._bluetooth = bluetooth;
    this.device = null;
    this.rxChar = null;
    this.connected = false;
    this._buffer = "";
    this._reconnectTimer = null;
    this._wantConnected = false;
    this._decoder = new TextDecoder();
    this._encoder = new TextEncoder();
  }

  static available(bluetooth) {
    const api = bluetooth ||
      (typeof navigator !== "undefined" ? navigator.bluetooth : undefined);
    return !!api;
  }

  /** Geraet waehlen und verbinden (Benutzerdialog des Browsers). */
  async connect() {
    const api = this._bluetooth ||
      (typeof navigator !== "undefined" ? navigator.bluetooth : undefined);
    if (!api) {
      throw new Error("Web Bluetooth wird von diesem Browser nicht unterst\u00fctzt");
    }
    this._wantConnected = true;
    this._setState("connecting");
    this.device = await api.requestDevice({
      filters: [{ services: [NUS_SERVICE] }],
    });
    this.device.addEventListener("gattserverdisconnected", () => {
      this.connected = false;
      this._setState("disconnected");
      this._scheduleReconnect();
    });
    await this._connectGatt();
  }

  async _connectGatt() {
    const server = await this.device.gatt.connect();
    const service = await server.getPrimaryService(NUS_SERVICE);
    const tx = await service.getCharacteristic(NUS_TX);
    await tx.startNotifications();
    tx.addEventListener("characteristicvaluechanged", (event) => {
      this._onNotify(event.target.value);
    });
    this.rxChar = await service.getCharacteristic(NUS_RX);
    this.connected = true;
    this._buffer = "";
    this._setState("connected");
  }

  /** Automatischer Nachverbindungsversuch nach Abbruch der Gegenstelle. */
  _scheduleReconnect() {
    if (!this._wantConnected || this._reconnectTimer !== null) {
      return;
    }
    this._reconnectTimer = setTimeout(async () => {
      this._reconnectTimer = null;
      if (!this._wantConnected || this.connected) {
        return;
      }
      try {
        this._setState("connecting");
        await this._connectGatt();
      } catch {
        this._scheduleReconnect();
      }
    }, RECONNECT_DELAY_MS);
  }

  _setState(state) {
    if (this.onState) {
      this.onState(state);
    }
  }

  _onNotify(value) {
    const chunk = this._decoder.decode(value, { stream: true });
    this._buffer += chunk;
    // Zeilen sammeln; Puffer begrenzen, damit eine manipulierte
    // Gegenstelle den Speicher nicht auffuellt
    while (true) {
      const nl = this._buffer.indexOf("\n");
      if (nl === -1) {
        break;
      }
      const line = this._buffer.slice(0, nl).replace(/\r$/, "");
      this._buffer = this._buffer.slice(nl + 1);
      if (this.onLine) {
        this.onLine(line);
      }
    }
    if (this._buffer.length > MAX_LINE) {
      this._buffer = this._buffer.slice(-MAX_LINE);
    }
  }

  /** Befehl als String senden (z. B. 'F107900000\\r\\n' oder 'V'). */
  async send(text) {
    if (!this.connected || !this.rxChar) {
      throw new Error("Nicht verbunden");
    }
    await this.rxChar.writeValue(this._encoder.encode(text));
  }

  disconnect() {
    this._wantConnected = false;
    if (this._reconnectTimer !== null) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    this.connected = false;
    if (this.device && this.device.gatt) {
      try {
        this.device.gatt.disconnect();
      } catch {
        // bereits getrennt
      }
    }
    this._setState("disconnected");
  }
}
