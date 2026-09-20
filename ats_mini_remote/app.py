"""Tkinter-Oberfläche der WLAN-Fernbedienung für das ATS-Miniradio V1."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import protocol
from .client import RemoteClient


class RemoteApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("ATS-Miniradio V1 – WLAN-Fernbedienung")
        root.minsize(560, 520)

        self.client = RemoteClient(
            on_status=self.on_status,
            on_memory=self.on_memory,
            on_line=self.log,
            on_disconnect=self.on_disconnect,
            on_screenshot=self.on_screenshot,
        )
        self._pending_memory: list[tuple[int, str, int, str]] = []
        self._screenshot: protocol.Screenshot | None = None
        self._volume_target = 0
        self._row_value_vars: dict[str, tk.StringVar] = {}

        self._build_ui()
        root.after(200, self._poll_main_thread)

    # ----------------------------------------------------------- Oberfläche

    def _build_ui(self):
        pad = {"padx": 6, "pady": 3}
        outer = ttk.Frame(self.root)
        outer.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Verbindungsleiste
        conn = ttk.LabelFrame(outer, text="Verbindung")
        conn.pack(fill=tk.X, **pad)
        ttk.Label(conn, text="Host:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.host_var = tk.StringVar(value="atsmini.local")
        ttk.Entry(conn, textvariable=self.host_var, width=20).grid(row=0, column=1, padx=2)
        ttk.Label(conn, text="Port:").grid(row=0, column=2, sticky="w", padx=4)
        self.port_var = tk.StringVar(value=str(protocol.DEFAULT_PORT))
        ttk.Entry(conn, textvariable=self.port_var, width=7).grid(row=0, column=3, padx=2)
        self.connect_button = ttk.Button(conn, text="Verbinden", command=self.connect)
        self.connect_button.grid(row=0, column=4, padx=6)
        self.state_label = ttk.Label(conn, text="Getrennt", foreground="#a00")
        self.state_label.grid(row=0, column=5, sticky="w", padx=6)

        # Status
        status = ttk.LabelFrame(outer, text="Empfänger")
        status.pack(fill=tk.X, **pad)
        self.freq_var = tk.StringVar(value="–")
        self.band_var = tk.StringVar(value="–")
        self.mode_var = tk.StringVar(value="–")
        self.sigm_var = tk.StringVar(value="–")
        self.batt_var = tk.StringVar(value="–")
        for col, (label, var) in enumerate([
            ("Frequenz", self.freq_var),
            ("Band", self.band_var),
            ("Modus", self.mode_var),
            ("Signal", self.sigm_var),
            ("Batterie", self.batt_var),
        ]):
            ttk.Label(status, text=label, font=("", 8, "bold")).grid(
                row=0, column=col, sticky="w", padx=8, pady=(6, 0))
            ttk.Label(status, textvariable=var, font=("", 12, "bold")).grid(
                row=1, column=col, sticky="w", padx=8, pady=(0, 6))

        # Steuerung
        ctrl = ttk.LabelFrame(outer, text="Steuerung")
        ctrl.pack(fill=tk.X, **pad)

        ttk.Label(ctrl, text="Frequenz:").grid(row=0, column=0, sticky="w", padx=4)
        self.freq_entry_var = tk.StringVar()
        ttk.Entry(ctrl, textvariable=self.freq_entry_var, width=14).grid(
            row=0, column=1, padx=2)
        self.freq_unit_var = tk.StringVar(value="MHz")
        unit_box = ttk.Combobox(ctrl, textvariable=self.freq_unit_var,
                                values=["kHz", "MHz"], width=5, state="readonly")
        unit_box.grid(row=0, column=2, padx=2)
        ttk.Button(ctrl, text="Setzen", command=self.set_frequency).grid(
            row=0, column=3, padx=4)

        self.volume_var = tk.IntVar(value=0)
        self._volume_dragging = False
        self.volume_scale = ttk.Scale(ctrl, from_=0, to=63, variable=self.volume_var,
                                       command=self.on_volume_changed)
        self.volume_scale.grid(row=0, column=4, columnspan=4, sticky="we", padx=8, pady=4)
        self.volume_scale.bind("<ButtonPress-1>", lambda _e: self._volume_drag(True))
        self.volume_scale.bind("<ButtonRelease-1>", lambda _e: self._volume_drag(False))

        rows = [
            ("Frequenz", None, None),
            ("Schrittweite", protocol.CMD_STEP_UP, protocol.CMD_STEP_DOWN),
            ("Band", protocol.CMD_BAND_UP, protocol.CMD_BAND_DOWN),
            ("Modus", protocol.CMD_MODE_UP, protocol.CMD_MODE_DOWN),
            ("Bandbreite", protocol.CMD_BANDWIDTH_UP, protocol.CMD_BANDWIDTH_DOWN),
            ("AGC/Attn", protocol.CMD_AGC_UP, protocol.CMD_AGC_DOWN),
        ]
        for row, (label, up, down) in enumerate(rows, start=1):
            if label == "Frequenz":
                down_cmd = lambda _l=None: self.tune(-1)
                up_cmd = lambda _l=None: self.tune(+1)
            else:
                down_cmd = (lambda c=down: lambda: self.send(c))()
                up_cmd = (lambda c=up: lambda: self.send(c))()
            ttk.Button(ctrl, text="◀", width=3,
                       command=down_cmd).grid(row=row, column=0, sticky="w", padx=4, pady=2)
            value_var = tk.StringVar(value="–")
            self._row_value_vars[label] = value_var
            ttk.Label(ctrl, text=label, width=12).grid(row=row, column=1, sticky="w", padx=4)
            ttk.Label(ctrl, textvariable=value_var, width=12,
                      font=("", 9, "bold")).grid(row=row, column=2, sticky="w", padx=8)
            ttk.Button(ctrl, text="▶", width=3,
                       command=up_cmd).grid(row=row, column=3, sticky="w")

        # Speicher
        mem = ttk.LabelFrame(outer, text="Speicherplätze")
        mem.pack(fill=tk.X, **pad)
        ttk.Button(mem, text="Anzeigen ($)",
                   command=self.show_memories).grid(row=0, column=0, padx=4, pady=2)
        ttk.Label(mem, text="Slot:").grid(row=0, column=1, padx=4)
        self.slot_var = tk.StringVar(value="1")
        slot_spin = ttk.Spinbox(mem, from_=1, to=32, textvariable=self.slot_var, width=4)
        slot_spin.grid(row=0, column=2)
        ttk.Button(mem, text="Aktuellen Sender speichern (#)",
                   command=self.save_memory).grid(row=0, column=3, padx=4)
        ttk.Button(mem, text="Slot löschen",
                   command=self.clear_memory).grid(row=0, column=4, padx=4)
        self.memory_tree = ttk.Treeview(mem, columns=("Slot", "Band", "Frequenz", "Modus"),
                                        show="headings", height=4)
        for col_name, width in [("Slot", 50), ("Band", 80), ("Frequenz", 140), ("Modus", 60)]:
            self.memory_tree.heading(col_name, text=col_name)
            self.memory_tree.column(col_name, width=width)
        self.memory_tree.grid(row=1, column=0, columnspan=5, sticky="we", padx=4, pady=4)
        mem.columnconfigure(0, weight=1)

        # Screenshot
        shot = ttk.LabelFrame(outer, text="Display")
        shot.pack(fill=tk.X, **pad)
        ttk.Button(shot, text="Screenshot (C)",
                   command=self.take_screenshot).grid(row=0, column=0, padx=4, pady=2)
        ttk.Button(shot, text="Speichern…",
                   command=self.save_screenshot).grid(row=0, column=1, padx=4)
        self.shot_label = ttk.Label(shot, text="Kein Screenshot")
        self.shot_label.grid(row=0, column=2, padx=8)

        # Log
        logbox = ttk.LabelFrame(outer, text="Log")
        logbox.pack(fill=tk.BOTH, expand=True, **pad)
        self.log_text = tk.Text(logbox, height=6, state=tk.DISABLED, font=("Courier", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.root.bind("<Return>", lambda _e: self.set_frequency())

    # ------------------------------------------------------ Aktionen am Radio

    def connect(self):
        host = self.host_var.get().strip()
        if not host:
            messagebox.showerror("Fehler", "Bitte Host angeben")
            return
        try:
            port = int(self.port_var.get())
        except ValueError:
            messagebox.showerror("Fehler", "Ungültiger Port")
            return
        try:
            self.client.connect(host, port)
        except OSError as exc:
            messagebox.showerror("Verbindung fehlgeschlagen", str(exc))
            return
        self.set_state(True)
        self.send(protocol.CMD_TOGGLE_LOG)
        self.log(f"Verbunden mit {host}:{port}, Monitor aktiviert")

    def disconnect(self):
        self.client.disconnect()
        self.set_state(False)
        self.log("Getrennt")

    def send(self, command: bytes):
        if not self.client.is_connected():
            self.log("Nicht verbunden – Befehl ignoriert")
            return
        self.client.send(command)

    def tune(self, direction: int):
        """Frequenz um eine Schrittweite ändern — über den F-Befehl.

        Kein R/r (Encoder-Emulation): In der Firmware dreht R/r je nach
        aktuellem Bildschirm den MENÜEINTRAG (z. B. den Wi-Fi-Modus) statt
        die Frequenz und speichert das ab. Der F-Befehl wirkt immer und
        ausschließlich auf die Frequenz.
        """
        status = self._last_status
        if status is None:
            self.log("Kein Status – Frequenzschritt nicht möglich")
            return
        hz = status.display_frequency_hz()
        step_hz = protocol.step_size_hz(status)
        target = hz + direction * step_hz
        ssb = status.mode in ("LSB", "USB")
        try:
            self.send(protocol.format_frequency_command(target, ssb))
        except ValueError:
            self.log("Frequenz außerhalb des Bands – Schritt ignoriert")

    def _set_row_values(self, status: protocol.ReceiverStatus):
        """Wertanzeige zwischen den ◀/▶-Buttons aktualisieren."""
        vars_ = self._row_value_vars
        if "Frequenz" in vars_:
            hz = status.display_frequency_hz()
            if status.mode.upper() == "FM":
                vars_["Frequenz"].set(f"{hz / 1e6:.2f} MHz")
            else:
                vars_["Frequenz"].set(f"{hz / 1e3:.3f} kHz")
        if "Band" in vars_:
            vars_["Band"].set(status.band)
        if "Modus" in vars_:
            vars_["Modus"].set(status.mode)
        if "Schrittweite" in vars_:
            vars_["Schrittweite"].set(status.step)
        if "Bandbreite" in vars_:
            vars_["Bandbreite"].set(status.bandwidth)
        if "AGC/Attn" in vars_:
            # Firmware: 0 = AGC ein, >0 = Attenuation (Wert = Index - 1)
            vars_["AGC/Attn"].set("AGC ein" if status.agc == 0
                                  else f"ATTN {status.agc - 1}")

    def set_frequency(self):
        raw = self.freq_entry_var.get().strip().replace(",", ".")
        if not raw:
            return
        try:
            value = float(raw)
        except ValueError:
            messagebox.showerror("Fehler", "Ungültige Frequenzeingabe")
            return
        unit = self.freq_unit_var.get()
        ssb = self._current_mode in ("LSB", "USB")
        if unit == "MHz":
            hz = int(round(value * 1_000_000))
        else:
            hz = int(round(value * 1000))
        if not ssb:
            hz = (hz // 1000) * 1000
        self.send(protocol.format_frequency_command(hz, ssb))

    def _volume_drag(self, active: bool):
        self._volume_dragging = active
        if not active:
            # Beim Loslassen einmalig gegen den letzten bekannten Radio-Wert
            self._send_volume()

    def on_volume_changed(self, value: str):
        # Ziel nur merken; gesendet wird beim Loslassen des Reglers als
        # ein einziger Burst. Während des Ziehens wird nichts gesendet,
        # und Statusupdates überschreiben den Regler nicht.
        self._volume_target = int(float(value))

    def _send_volume(self):
        if not self.client.is_connected():
            return
        target = self._volume_target
        burst = protocol.volume_burst(self._current_volume, target)
        if burst:
            self.send(burst)

    def show_memories(self):
        self._pending_memory = []
        self.send(protocol.CMD_SHOW_MEMORIES)
        self.root.after(800, self._flush_memories)

    def save_memory(self):
        status = self._last_status
        if status is None:
            messagebox.showerror("Fehler", "Kein Status vom Empfänger")
            return
        try:
            slot = int(self.slot_var.get())
        except ValueError:
            messagebox.showerror("Fehler", "Ungültiger Slot")
            return
        band = status.band
        mode = status.mode
        if mode.upper() == "FM":
            freq_hz = status.frequency * 10_000
        else:
            freq_hz = status.frequency * 1000
        self.send(protocol.format_memory_command(slot, band, freq_hz, mode))
        self.root.after(400, self.show_memories)

    def clear_memory(self):
        try:
            slot = int(self.slot_var.get())
        except ValueError:
            messagebox.showerror("Fehler", "Ungültiger Slot")
            return
        status = self._last_status
        band = status.band if status else "MW"
        mode = status.mode if status else "AM"
        self.send(protocol.format_memory_command(slot, band, 0, mode))
        self.root.after(400, self.show_memories)

    def _flush_memories(self):
        rows = self._pending_memory
        self._pending_memory = []
        for iid in self.memory_tree.get_children():
            self.memory_tree.delete(iid)
        for slot, band, freq, mode in sorted(rows):
            display = f"{freq / 1_000_000:.3f} MHz" if freq >= 10_000_000 else f"{freq / 1000:.0f} kHz"
            self.memory_tree.insert("", tk.END, values=(slot, band, display, mode))

    def take_screenshot(self):
        if not self.client.is_connected():
            self.log("Nicht verbunden – Screenshot nicht möglich")
            return
        self.client.request_screenshot()

    def save_screenshot(self):
        if self._screenshot is None:
            messagebox.showerror("Fehler", "Kein Screenshot vorhanden")
            return
        filename = filedialog.asksaveasfilename(
            defaultextension=".bmp", filetypes=[("BMP-Bild", "*.bmp")])
        if not filename:
            return
        with open(filename, "wb") as fh:
            fh.write(self._screenshot.to_bmp())
        self.log(f"Screenshot gespeichert: {filename}")

    # ----------------------------------------------------------- Rückrufe

    _last_status: protocol.ReceiverStatus | None = None
    _current_mode: str = ""
    _current_volume: int = -1

    def on_status(self, status: protocol.ReceiverStatus):
        self._pending_status = status

    def on_memory(self, mem: tuple[int, str, int, str]):
        self._pending_memory.append(mem)

    def on_disconnect(self, reason: str):
        self.root.after(0, lambda: self._handle_disconnect(reason))

    def _handle_disconnect(self, reason: str):
        self.set_state(False)
        self.log(f"Verbindung getrennt: {reason}")

    def on_screenshot(self, shot: protocol.Screenshot):
        self._pending_screenshot = shot

    # ----------------------------------------------------------- Hilfsfunktionen

    def set_state(self, connected: bool):
        if connected:
            self.connect_button.config(text="Trennen", command=self.disconnect)
            self.state_label.config(text="Verbunden", foreground="#070")
        else:
            self.connect_button.config(text="Verbinden", command=self.connect)
            self.state_label.config(text="Getrennt", foreground="#a00")

    def log(self, message: str):
        self._pending_log.append(message)

    def _poll_main_thread(self):
        for message in self._pending_log:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
            if float(self.log_text.index("end-1c").split(".")[0]) > 400:
                self.log_text.delete("1.0", "200.0")
            self.log_text.config(state=tk.DISABLED)
        self._pending_log = []

        status = getattr(self, "_pending_status", None)
        if status is not None:
            self._pending_status = None
            self._last_status = status
            self._current_mode = status.mode
            self._current_volume = status.volume
            # Regler nur aktualisieren, wenn der Nutzer ihn nicht gerade zieht
            if not self._volume_dragging:
                self.volume_var.set(status.volume)
            hz = status.display_frequency_hz()
            if status.mode.upper() == "FM":
                self.freq_var.set(f"{hz / 1e6:.2f} MHz")
            else:
                self.freq_var.set(f"{hz / 1e3:.3f} kHz")
            self.band_var.set(status.band)
            self.mode_var.set(status.mode)
            self.sigm_var.set(f"{status.rssi} dBµV / {status.snr} dB")
            self.batt_var.set(f"{status.voltage:.2f} V")
            self._set_row_values(status)

        shot = getattr(self, "_pending_screenshot", None)
        if shot is not None:
            self._pending_screenshot = None
            self._screenshot = shot
            self._show_screenshot(shot)

        self.root.after(100, self._poll_main_thread)

    def _show_screenshot(self, shot: protocol.Screenshot):
        ppm = shot.to_ppm()
        self._shot_photo = tk.PhotoImage(data=ppm, format="PPM")
        self.shot_label.config(image=self._shot_photo, text="")

    _pending_log: list[str] = []
    _pending_status: protocol.ReceiverStatus | None = None
    _pending_screenshot: protocol.Screenshot | None = None


def main():
    root = tk.Tk()
    RemoteApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
