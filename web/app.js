/**
 * Anwendungslogik der PWA: verbindet BLE-Transport und Protokoll
 * mit der Oberflaeche. Der Monitor des Radios wird nach dem
 * Verbinden automatisch aktiviert (Befehl 't'), die CSV-Zeilen
 * werden geparst und die Anzeigen aktualisiert.
 */

import {
  parseStatus, formatFrequencyCommand, formatMemoryCommand,
  volumeBurst, sMeter, stepHz, CMD,
} from "./protocol.js";
import { BleTransport } from "./ble.js";

const $ = (id) => document.getElementById(id);

const state = {
  transport: null,
  status: null,
  volumeTarget: 0,
  logVisible: false,
  logLines: [],
};

/* ---------- Siebensegment-Frequenzanzeige (feste Zellen) ---------- */

const SEG_W = 15, SEG_H = 28, SEG_T = 3, SEG_GAP = 8, SEG_INT_CELLS = 5;
const SEG_MAP = {
  0: "abcdef", 1: "bc", 2: "abdeg", 3: "abcdg",
  4: "bcfg", 5: "acdfg", 6: "acdefg", 7: "abc",
  8: "abcdefg", 9: "abcdfg",
};

function segPoints(x, w, h, t, seg) {
  const y0 = t, y1 = t + h, ym = Math.floor((y0 + y1) / 2);
  if (["a", "g", "d"].includes(seg)) {
    const y = { a: y0, g: ym, d: y1 }[seg];
    return [[x, y], [x + t, y + t], [x + w - t, y + t], [x + w, y],
            [x + w - t, y - t], [x + t, y - t]];
  }
  const [xa, ya, yb] = {
    f: [x, y0, ym], b: [x + w, y0, ym],
    e: [x, ym, y1], c: [x + w, ym, y1],
  }[seg];
  return [[xa, ya], [xa + t, ya + t], [xa + t, yb - t], [xa, yb],
          [xa - t, yb - t], [xa - t, ya + t]];
}

function drawFrequency(status) {
  const canvas = $("freq-display");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!status) return;
  const hz = status.displayFrequencyHz();
  const fm = status.mode.toUpperCase() === "FM";
  const text = fm ? (hz / 1e6).toFixed(2) : (hz / 1e3).toFixed(3);
  const unit = fm ? "MHz" : "kHz";
  const sep = text.includes(",") ? "," : ".";
  const [head, frac = ""] = text.split(sep);
  // Fester Aufbau: fuenf Zellen vor dem Dezimalpunkt, fuehrende dunkel
  const intDigits = head.padStart(SEG_INT_CELLS, "0");
  const litLen = intDigits.replace(/^0+/, "").length || 1;
  const x0 = SEG_T + 1;
  let x = x0;
  ctx.fillStyle = "#000";
  intDigits.split("").forEach((ch, i) => {
    if (i >= SEG_INT_CELLS - litLen) {
      for (const seg of SEG_MAP[ch]) {
        const pts = segPoints(x, SEG_W, SEG_H, SEG_T, seg);
        ctx.beginPath();
        pts.forEach(([px, py], j) => (j ? ctx.lineTo(px, py)
                                       : ctx.moveTo(px, py)));
        ctx.closePath();
        ctx.fill();
      }
    }
    x += SEG_W + SEG_GAP;
  });
  // Dezimalpunkt an fester Position
  const y1 = SEG_T + SEG_H;
  ctx.beginPath();
  ctx.ellipse(x - SEG_GAP / 2, y1 - 1, 2.5, 2.5, 0, 0, Math.PI * 2);
  ctx.fill();
  x += SEG_GAP;
  for (const ch of frac) {
    for (const seg of SEG_MAP[ch]) {
      const pts = segPoints(x, SEG_W, SEG_H, SEG_T, seg);
      ctx.beginPath();
      pts.forEach(([px, py], j) => (j ? ctx.lineTo(px, py)
                                     : ctx.moveTo(px, py)));
      ctx.closePath();
      ctx.fill();
    }
    x += SEG_W + SEG_GAP;
  }
  ctx.fillStyle = "#333";
  ctx.font = "bold 10px sans-serif";
  ctx.textBaseline = "middle";
  ctx.fillText(unit, x + 3, SEG_T + SEG_H / 2);
}

/* ---------- Statusanzeige ---------- */

function updateStatus(status) {
  state.status = status;
  drawFrequency(status);
  const fm = status.mode.toUpperCase() === "FM";
  $("s-value").textContent = sMeter(status.rssi, fm);
  $("rssi-value").textContent = String(status.rssi);
  $("snr-value").textContent = String(status.snr);
  $("band-value").textContent = status.band || "–";
  $("mode-value").textContent = status.mode || "–";
  $("step-value").textContent = status.step || "–";
  $("bw-value").textContent = status.bandwidth || "–";
  $("agc-value").textContent = String(status.agc);
  $("vol-value").textContent = String(status.volume);
  $("volume").value = String(status.volume);
  state.volumeTarget = status.volume;
  $("status-line").textContent =
    `${status.band} · ${status.mode} · ` +
    `${status.voltage.toFixed(2).replace(".", ",")} V`;
}

function clearStatus() {
  state.status = null;
  drawFrequency(null);
  for (const id of ["s-value", "rssi-value", "snr-value", "band-value",
                    "mode-value", "step-value", "bw-value", "agc-value",
                    "vol-value"]) {
    $(id).textContent = "–";
  }
  $("status-line").textContent = "–";
}

/* ---------- Log ---------- */

function appendLog(source, message) {
  const time = new Date().toLocaleTimeString();
  state.logLines.push(`${time} ${source} ${message}`);
  if (state.logLines.length > 200) {
    state.logLines.shift();
  }
  if (state.logVisible) {
    $("log").textContent = state.logLines.join("\n");
    $("log").scrollTop = $("log").scrollHeight;
  }
}

$("log-toggle").addEventListener("click", () => {
  state.logVisible = !state.logVisible;
  $("log").hidden = !state.logVisible;
  $("log-toggle").textContent =
    state.logVisible ? "Log ausblenden" : "Log anzeigen";
  if (state.logVisible) {
    $("log").textContent = state.logLines.join("\n");
  }
});

/* ---------- Verbindung ---------- */

function setStateLabel(stateName) {
  const el = $("state");
  el.className = stateName;
  el.textContent = {
    connecting: "Verbinde…",
    connected: "Verbunden",
    disconnected: "Nicht verbunden",
  }[stateName] || stateName;
  $("connect-btn").textContent =
    stateName === "connected" ? "Trennen" : "Verbinden";
}

async function connect() {
  if (state.transport && state.transport.connected) {
    state.transport.disconnect();
    clearStatus();
    return;
  }
  if (!BleTransport.available()) {
    alert("Dieser Browser unterst\u00fctzt Web Bluetooth nicht. " +
          "Auf iOS die Seite im Browser Bluefy \u00f6ffnen.");
    return;
  }
  state.transport = new BleTransport((line) => onLine(line), setStateLabel);
  try {
    await state.transport.connect();
    // Monitor aktivieren: Statusmeldungen des Radios anfordern
    await state.transport.send(CMD.TOGGLE_LOG);
    appendLog("App", "Verbunden, Monitor aktiviert");
  } catch (err) {
    if (err.name === "NotFoundError") {
      appendLog("App", "Kein Ger\u00e4t ausgew\u00e4hlt");
      setStateLabel("disconnected");
    } else {
      appendLog("App", `Verbindung fehlgeschlagen: ${err.message}`);
      setStateLabel("disconnected");
    }
  }
}

$("connect-btn").addEventListener("click", connect);

function onLine(line) {
  const status = parseStatus(line);
  if (status) {
    updateStatus(status);
    return;
  }
  appendLog("Radio", line);
}

/* ---------- Steuerung ---------- */

document.querySelectorAll("button[data-cmd]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    await sendRaw(btn.dataset.cmd);
  });
});

async function sendRaw(text) {
  if (!state.transport || !state.transport.connected) {
    appendLog("App", "Nicht verbunden – Befehl ignoriert");
    return;
  }
  try {
    await state.transport.send(text);
  } catch (err) {
    appendLog("App", `Senden fehlgeschlagen: ${err.message}`);
  }
}

$("freq-set").addEventListener("click", async () => {
  const text = $("freq-input").value.trim();
  if (!text) return;
  const unit = $("freq-unit").value;
  let value = Number.parseFloat(text.replace(",", "."));
  if (!Number.isFinite(value) || value <= 0) {
    appendLog("App", "Ung\u00fcltige Frequenzangabe");
    return;
  }
  let hz = Math.round(unit === "MHz" ? value * 1e6 : value * 1e3);
  if (!state.status) {
    appendLog("App", "Kein Status – Frequenzsetzung nicht m\u00f6glich");
    return;
  }
  // Auf das Schrittweiten-Raster runden, wie die Desktop-Fernbedienung
  const step = stepHz(state.status.step, 1000);
  hz = Math.round(hz / step) * step;
  const ssb = ["LSB", "USB"].includes(state.status.mode.toUpperCase());
  try {
    const cmd = formatFrequencyCommand(hz, ssb);
    await state.transport.send(cmd);
    appendLog("App", `Abgestimmt auf ${(hz / 1000).toFixed(1)} kHz`);
  } catch (err) {
    appendLog("App", err.message);
  }
});

/* Lautstaerke: Slider sendet erst beim Loslassen den Burst */
$("volume").addEventListener("change", async () => {
  const target = Number.parseInt($("volume").value, 10);
  const burst = volumeBurst(state.volumeTarget, target);
  state.volumeTarget = target;
  if (burst) {
    await sendRaw(burst);
  }
});

/* Erste Statusinitialisierung */
clearStatus();
setStateLabel("disconnected");

/* Service Worker registrieren (PWA-Offline-Start) */
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => {
    // Offline-Start ohne Service Worker: App funktioniert trotzdem
  });
}
