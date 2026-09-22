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
 *
 * Sicherheitsmodell: Sämtliche Objekte der Web-Bluetooth-API und
 * alle Notification-Daten gelten als untraeglich (böswilliger
 * Browser, böswillige Gegenstelle). Deshalb:
 *   - Event- und GATT-Objekte werden vor jedem Zugriff geprueft
 *   - Decode-Fehler setzen Decoder und Puffer zurueck, statt den
 *     Empfang dauerhaft zu blockieren
 *   - Empfangspuffer und Zeilenlaenge sind hart begrenzt (MAX_LINE)
 *   - ausgelieferte Zeilen duergen Fehler in onLine nicht werfen
 *   - Reconnect-Versuche mit exponentiellem Backoff
 */

export const NUS_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e";
export const NUS_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e";  // write
export const NUS_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e";  // notify

const MAX_LINE = 512;          // Pufferlimit gegen Riesenzeilen
const RECONNECT_DELAY_MS = 1500;
const RECONNECT_MAX_DELAY_MS = 30000;

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
    this._overlong = false;
    this._reconnectTimer = null;
    this._reconnectDelayMs = RECONNECT_DELAY_MS;
    this._wantConnected = false;
    this._txChar = null;
    this._notifyHandler = null;
    this._decoder = new TextDecoder();
    this._encoder = new TextEncoder();
  }

  static available(bluetooth) {
    try {
      const api = bluetooth ||
        (typeof navigator !== "undefined" ? navigator.bluetooth : undefined);
      return !!api && typeof api.requestDevice === "function";
    } catch {
      return false;
    }
  }

  _api() {
    const api = this._bluetooth ||
      (typeof navigator !== "undefined" ? navigator.bluetooth : undefined);
    if (!api || typeof api.requestDevice !== "function") {
      return null;
    }
    return api;
  }

  /** Geraet waehlen und verbinden (Benutzerdialog des Browsers). */
  async connect() {
    const api = this._api();
    if (!api) {
      throw new Error("Web Bluetooth wird von diesem Browser nicht unterst\u00fctzt");
    }
    this._wantConnected = true;
    this._setState("connecting");
    this.device = await api.requestDevice({
      filters: [{ services: [NUS_SERVICE] }],
    });
    if (!this.device || !this.device.gatt ||
        typeof this.device.addEventListener !== "function" ||
        typeof this.device.gatt.connect !== "function") {
      this._wantConnected = false;
      this._setState("disconnected");
      throw new Error("Ung\u00fcltiges Bluetooth-Ger\u00e4t-Objekt");
    }
    this.device.addEventListener("gattserverdisconnected", () => {
      this.connected = false;
      this._setState("disconnected");
      this._scheduleReconnect();
    });
    await this._connectGatt();
  }

  async _connectGatt() {
    if (!this.device || !this.device.gatt ||
        typeof this.device.gatt.connect !== "function") {
      throw new Error("Ung\u00fcltige GATT-Schnittstelle");
    }
    const server = await this.device.gatt.connect();
    const service = await server.getPrimaryService(NUS_SERVICE);
    const tx = await service.getCharacteristic(NUS_TX);
    if (typeof tx.startNotifications !== "function" ||
        typeof tx.addEventListener !== "function") {
      throw new Error("Ung\u00fcltige TX-Charakteristik");
    }
    await tx.startNotifications();
    // Bei wiederholtem Verbindungsaufbau liefert der Browser dieselben
    // Charakteristik-Objekte; ein zweiter Listener wuerde jede Zeile
    // doppelt ausliefern.
    if (this._txChar && this._notifyHandler &&
        typeof this._txChar.removeEventListener === "function") {
      this._txChar.removeEventListener(
        "characteristicvaluechanged", this._notifyHandler);
    }
    this._txChar = tx;
    this._notifyHandler = (event) => this._onNotifyEvent(event);
    tx.addEventListener("characteristicvaluechanged", this._notifyHandler);
    const rx = await service.getCharacteristic(NUS_RX);
    if (typeof rx.writeValue !== "function") {
      throw new Error("Ung\u00fcltige RX-Charakteristik");
    }
    this.rxChar = rx;
    this.connected = true;
    this._buffer = "";
    this._overlong = false;
    this._reconnectDelayMs = RECONNECT_DELAY_MS;
    this._setState("connected");
  }

  /** Automatischer Nachverbindungsversuch nach Abbruch der Gegenstelle. */
  _scheduleReconnect() {
    if (!this._wantConnected || this._reconnectTimer !== null) {
      return;
    }
    const delay = this._reconnectDelayMs;
    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null;
      this._reconnectAttempt();
    }, delay);
  }

  async _reconnectAttempt() {
    if (!this._wantConnected || this.connected) {
      return;
    }
    try {
      this._setState("connecting");
      await this._connectGatt();
    } catch {
      // Böswillige oder defekte Gegenstelle: Backoff statt
      // endlosem 1,5-s-Takt, der Radio und Browser beschaeftigt.
      this._reconnectDelayMs = Math.min(this._reconnectDelayMs * 2,
                                        RECONNECT_MAX_DELAY_MS);
      this._scheduleReconnect();
    }
  }

  _setState(state) {
    if (this.onState) {
      this.onState(state);
    }
  }

  _onNotifyEvent(event) {
    let value = null;
    try {
      if (event && event.target) {
        value = event.target.value;
      }
    } catch {
      value = null;
    }
    this._onNotify(value);
  }

  _onNotify(value) {
    let chunk;
    try {
      chunk = this._decoder.decode(value, { stream: true });
    } catch {
      // Unbrauchbares value-Objekt: Decoder und Puffer zuruecksetzen,
      // damit der Empfang laeuft, sobald wieder gueltige Daten kommen.
      this._decoder = new TextDecoder();
      this._buffer = "";
      return;
    }
    if (typeof chunk !== "string") {
      return;
    }
    // Zeilen sammeln; Puffer begrenzen, damit eine manipulierte
    // Gegenstelle den Speicher nicht auffuellt. Eine Zeile ohne
    // Zeilenende, die MAX_LINE ueberschreitet, wird verworfen und
    // bis zum naechsten Zeilenende uebersprungen.
    if (this._overlong) {
      const nl = chunk.indexOf("\n");
      if (nl === -1) {
        return;
      }
      this._overlong = false;
      chunk = chunk.slice(nl + 1);
    }
    this._buffer += chunk;
    while (true) {
      const nl = this._buffer.indexOf("\n");
      if (nl === -1) {
        break;
      }
      const line = this._buffer.slice(0, nl).replace(/\r$/, "");
      this._buffer = this._buffer.slice(nl + 1);
      if (line.length > MAX_LINE) {
        continue;
      }
      if (this.onLine) {
        try {
          this.onLine(line);
        } catch {
          // Fehler der Anzeige darf den Empfang nicht blockieren
        }
      }
    }
    if (this._buffer.length > MAX_LINE) {
      this._overlong = true;
      this._buffer = "";
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
    this.rxChar = null;
    this._buffer = "";
    this._overlong = false;
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
