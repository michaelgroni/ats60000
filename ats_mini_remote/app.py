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
        self._sweep_active = False
        self._sweep_freqs: list[int] = []
        self._sweep_index = 0
        self._sweep_restore_freq: int | None = None
        self._sweep_timeout_id: str | None = None

        self._build_ui()
        root.after(50, self._poll_main_thread)

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
        self.rssi_var = tk.StringVar(value="–")
        self.smeter_var = tk.StringVar(value="–")
        self.snr_var = tk.StringVar(value="–")
        self.batt_var = tk.StringVar(value="–")
        for col, (label, var) in enumerate([
            ("Frequenz", self.freq_var),
            ("Band", self.band_var),
            ("Modus", self.mode_var),
            ("Signalstärke", self.rssi_var),
            ("S-Wert", self.smeter_var),
            ("SNR", self.snr_var),
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

        # Spektrum (Sweep)
        sweep = ttk.LabelFrame(outer, text="Spektrum")
        sweep.pack(fill=tk.X, **pad)
        self.sweep_points_var = tk.StringVar(value="60")
        ttk.Label(sweep, text="Messpunkte:").grid(row=0, column=0, padx=4, pady=2)
        ttk.Spinbox(sweep, from_=10, to=500, increment=10,
                    textvariable=self.sweep_points_var, width=6).grid(row=0, column=1)
        self.sweep_start_button = ttk.Button(sweep, text="Sweep starten",
                                             command=self.sweep_start)
        self.sweep_start_button.grid(row=0, column=2, padx=6)
        self.sweep_stop_button = ttk.Button(sweep, text="Abbrechen",
                                            command=self.sweep_stop, state=tk.DISABLED)
        self.sweep_stop_button.grid(row=0, column=3, padx=4)
        self.sweep_progress_var = tk.StringVar(value="")
        ttk.Label(sweep, textvariable=self.sweep_progress_var).grid(
            row=0, column=4, padx=8)
        self.sweep_canvas = tk.Canvas(sweep, height=120, bg="#000",
                                      highlightthickness=0)
        self.sweep_canvas.grid(row=1, column=0, columnspan=5, sticky="we",
                               padx=4, pady=(0, 4))
        self.sweep_canvas.bind("<Button-1>", self._sweep_click)
        self._sweep_data: list[tuple[int, int]] | None = None
        self._sweep_freq_range: tuple[int, int] | None = None

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
        self._sweep_points_pending = True
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

    # -------------------------------------------------- Spektrum (Sweep)

    def sweep_start(self):
        if not self.client.is_connected():
            self.log("Nicht verbunden – Sweep nicht möglich")
            return
        status = self._last_status
        if status is None:
            self.log("Kein Status – Sweep nicht möglich")
            return
        rng = protocol.sweep_points_for_band(
            status.band, status.mode, status.display_frequency_hz())
        if rng is None:
            self.log(f"Band '{status.band}' unbekannt – Sweep nicht möglich")
            return
        try:
            points = int(self.sweep_points_var.get())
        except ValueError:
            points = 60
        points = max(10, min(500, points))

        lo_khz, hi_khz = rng
        # Sweep-Modus: der Natur des Bandes laut Bandtabelle folgen, nicht
        # dem zufaellig eingestellten Modus (z. B. 80M trotz AM auf LSB).
        # FM-Baender laufen ohnehin nur in FM; mode_cmd ist dann leer.
        sweep_mode = protocol.band_table_mode(
            status.band, status.display_frequency_hz(),
            status.mode) or status.mode
        mode_cmd = protocol.mode_steps(status.mode, sweep_mode)
        self._sweep_mode = sweep_mode
        spacing_hz = (hi_khz - lo_khz) * 1000 / (points - 1)
        # Passende Schrittweite: Sweepraster = zugehoeriges Schrittweiten-Raster
        step_text = protocol.step_for_spacing(spacing_hz, sweep_mode)
        step = protocol.step_hz(step_text)
        self._sweep_freqs = protocol.aligned_sweep_freqs(
            int(lo_khz) * 1000, int(hi_khz) * 1000, step)
        if len(self._sweep_freqs) < 2:
            self.log("Band zu schmal für diese Schrittweite – Sweep nicht möglich")
            return
        self._sweep_index = 0
        self._sweep_data = []
        self._sweep_marker_hz = None
        self._sweep_freq_range = (self._sweep_freqs[0], self._sweep_freqs[-1])
        self._sweep_restore_freq = status.display_frequency_hz()
        # Bandbreite etwa auf die Messpunktschrittweite einstellen
        bw_target = protocol.bandwidth_for_step(step / 1000, sweep_mode)
        # Reihenfolge: Modus zuerst, denn doMode() der Firmware setzt
        # Schrittweite und Bandbreite auf die Modus-Defaults zurueck;
        # deshalb werden beide nach einem Moduswechsel immer gesetzt.
        self._sweep_setups = []   # (name, cmd_bytes, restore-Wert, ist-Wert)
        self._sweep_restore_setup = None
        if mode_cmd:
            self._sweep_setups.append((
                "Modus", mode_cmd, status.mode, sweep_mode))
            # Schrittweite/Bandbreite des Ausgangszustands nach dem
            # Modus-Rueckwechsel explizit wiederherstellen (doMode()
            # setzt beide auf die Modus-Defaults zurueck)
            restore = self._last_status
            if restore is not None:
                restore_step_cmd = protocol.step_steps(
                    protocol.default_step(restore.mode), restore.step,
                    restore.mode)
                restore_bw_cmd = protocol.bandwidth_steps(
                    protocol.default_bandwidth(restore.mode), restore.bandwidth,
                    restore.mode)
                self._sweep_restore_setup = (restore_step_cmd, restore_bw_cmd)
        if status.step != step_text or mode_cmd:
            self._sweep_setups.append((
                "Schrittweite",
                protocol.step_steps(status.step, step_text, sweep_mode),
                status.step, step_text))
        if status.bandwidth != bw_target or mode_cmd:
            self._sweep_setups.append((
                "Bandbreite",
                protocol.bandwidth_steps(status.bandwidth, bw_target,
                                        sweep_mode),
                status.bandwidth, bw_target))
        self._sweep_applied = []
        self._sweep_active = True
        self.sweep_start_button.config(state=tk.DISABLED)
        self.sweep_stop_button.config(state=tk.NORMAL)
        if sweep_mode != status.mode:
            self.log(f"Modus für Sweep: {sweep_mode} "
                     f"(vorher {status.mode}, wird zurückgestellt)")
        self.log(f"Sweep über {status.band}: {lo_khz}–{hi_khz} kHz, "
                 f"{len(self._sweep_freqs)} Punkte, Schrittweite {step_text}, "
                 f"Bandbreite {bw_target}")
        self._sweep_advance_setup()

    def sweep_stop(self):
        if not self._sweep_active:
            return
        self._sweep_active = False
        self._sweep_finish("Abgebrochen")

    def _sweep_next(self):
        if not self._sweep_active:
            return
        if self._sweep_index >= len(self._sweep_freqs):
            self._sweep_finish("Fertig")
            return
        hz = self._sweep_freqs[self._sweep_index]
        # waehrend des Sweeps gilt der Sweep-Modus, nicht der Originalmodus
        ssb = self._sweep_mode in ("LSB", "USB")
        try:
            self.send(protocol.format_frequency_command(hz, ssb))
        except ValueError:
            # Frequenz außerhalb des Bands (Rundung) → Punkt überspringen
            self._sweep_index += 1
            self.root.after(30, self._sweep_next)
            return
        self._sweep_arm_timeout()

    def _sweep_arm_timeout(self):
        """Punkt überspringen, wenn das Radio die Frequenz nicht bestätigt."""
        self._sweep_disarm_timeout()
        # 3 Monitortakte: sonst hat das Radio die Frequenz abgelehnt
        # (z. B. Rundung am Bandrand) oder der Status bleibt aus.
        self._sweep_timeout_id = self.root.after(1500, self._sweep_timeout)

    def _sweep_disarm_timeout(self):
        if self._sweep_timeout_id is not None:
            self.root.after_cancel(self._sweep_timeout_id)
            self._sweep_timeout_id = None

    def _sweep_timeout(self):
        self._sweep_timeout_id = None
        if not self._sweep_active:
            return
        if self._sweep_phase_setup is not None:
            name, _cmd, restore, target = self._sweep_phase_setup
            self.log(f"{name} nicht bestätigt ({target}) – Sweep trotzdem fortgesetzt")
            self._sweep_phase_setup = None
            self._sweep_advance_setup()
            return
        hz = self._sweep_freqs[self._sweep_index] \
            if self._sweep_index < len(self._sweep_freqs) else None
        self.log(f"Keine Bestätigung für {hz / 1000:.1f} kHz – Punkt übersprungen")
        self._sweep_index += 1
        self.sweep_progress_var.set(
            f"{self._sweep_index}/{len(self._sweep_freqs)}")
        self._sweep_next()

    def _sweep_on_status(self, status: protocol.ReceiverStatus):
        """Wird aus on_status gerufen: misst den Punkt, fährt fort."""
        if not self._sweep_active:
            return
        if self._sweep_phase_setup is not None:
            name, _cmd, _restore, target = self._sweep_phase_setup
            if name == "Modus":
                current = status.mode
            elif name == "Bandbreite":
                current = status.bandwidth
            else:
                current = status.step
            if current == target:
                self._sweep_disarm_timeout()
                self._sweep_phase_setup = None
                self._sweep_advance_setup()
            return
        expected_hz = self._sweep_freqs[self._sweep_index] if \
            self._sweep_index < len(self._sweep_freqs) else None
        actual_hz = status.display_frequency_hz()
        # Status bestätigt die Ziel Frequenz erst, wenn sie übernommen wurde
        if expected_hz is None or abs(actual_hz - expected_hz) > 1000:
            return
        self._sweep_disarm_timeout()
        self._sweep_data.append((expected_hz, status.rssi))
        self._sweep_index += 1
        done = self._sweep_index
        total = len(self._sweep_freqs)
        self.sweep_progress_var.set(f"{done}/{total}")
        self._sweep_draw()
        if done >= total:
            self._sweep_finish("Fertig")
        else:
            # Kein additional Delay: der nächste F-Befehl geht sofort raus,
            # der 500-ms-Monitor-Teakt liefert die zugehörige Messung.
            self._sweep_next()

    def _sweep_advance_setup(self):
        """Naechste Einstellung (Modus/Schrittweite/Bandbreite) setzen."""
        if not self._sweep_active:
            return
        if self._sweep_setups:
            name, cmd, restore, target = self._sweep_setups.pop(0)
            self._sweep_phase_setup = (name, cmd, restore, target)
            # Umkehrung merken (M<->m, S<->s, W<->w): kehrt die Bewegung auf
            # dem zyklischen Index immer korrekt zurueck, unabhaengig davon,
            # ob der Status die Aenderung schon gemeldet hat.
            inverse = cmd.translate(bytes.maketrans(b"MSWmsw", b"mswMSW"))
            self._sweep_applied.append((name, inverse, restore, target))
            self.send(cmd)
            self._sweep_arm_timeout()
        else:
            self._sweep_phase_setup = None
            self._sweep_next()

    def _sweep_finish(self, message: str):
        """Sweep beenden: Einstellungen zurueckstellen, dann aufräumen."""
        self._sweep_disarm_timeout()
        self._sweep_message = message
        self._sweep_active = False
        # Einstellungen per Umkehrbefehl zurueckstellen; die Firmware
        # verarbeitet Einzelzeichen-Befehle (M/m/S/s/W/w) sofort und in
        # Reihenfolge, sodass die Umkehrung den Ausgangszustand
        # wiederherstellt, unabhaengig vom Statusstand.
        while self._sweep_applied:
            _name, inverse, _restore, _target = self._sweep_applied.pop()
            if inverse:
                self.send(inverse)
        # Sonderfall Moduswechsel: doMode() der Firmware setzt nach dem
        # Rueckwechsel Schrittweite und Bandbreite auf die Modus-Defaults
        # zurueck, nicht auf die urspruenglichen Werte. Beide werden daher
        # nach dem Modus-Rueckwechsel gezielt auf den Ausgangszustand
        # gestellt (leerer Befehl, wenn sie bereits passen).
        self._sweep_setups = []
        if self._sweep_restore_setup is not None:
            step_cmd, bw_cmd = self._sweep_restore_setup
            self.send(step_cmd)
            self.send(bw_cmd)
            self._sweep_restore_setup = None
        self._sweep_really_finish()

    def _sweep_really_finish(self):
        self._sweep_active = False
        self._sweep_disarm_timeout()
        self._sweep_marker_hz = None
        self.sweep_start_button.config(state=tk.NORMAL)
        self.sweep_stop_button.config(state=tk.DISABLED)
        self.sweep_progress_var.set(self._sweep_message or "Fertig")
        restore = self._sweep_restore_freq
        if restore is not None:
            status = self._last_status
            # Der Modus wurde bereits zurueckgestellt; die Frequenz wird
            # im Originalmodus gesendet (BFO-Stellen unter 1 kHz)
            ssb = status.mode in ("LSB", "USB") if status else False
            try:
                self.send(protocol.format_frequency_command(restore, ssb))
            except ValueError:
                pass
        self.log(f"Sweep {self._sweep_message}: "
                 f"{len(self._sweep_data or [])} Punkte")

    def _sweep_draw(self):
        data = self._sweep_data
        if not data:
            return
        canvas = self.sweep_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 100)
        height = 120
        lo, hi = self._sweep_freq_range
        span = max(hi - lo, 1)
        rssi_max = 127
        for hz, rssi in data:
            x = (hz - lo) / span * width
            y = height - 4 - (rssi / rssi_max) * (height - 8)
            canvas.create_rectangle(x - 1, y, x + 1, height - 4,
                                   fill="#0f0", outline="")
        # Eingestellte Frequenz als vertikale Markierung; waehrend des
        # Sweeps ist das die Restore-Frequenz, da das Radio gerade das
        # Band durchfaehrt.
        if self._sweep_active and self._sweep_restore_freq is not None:
            current_hz = self._sweep_restore_freq
        else:
            status = self._last_status
            current_hz = status.display_frequency_hz() if status else None
        if current_hz is not None and lo <= current_hz <= hi:
            x = (current_hz - lo) / span * width
            canvas.create_line(x, 2, x, height - 4,
                               fill="#f80", width=2)

    def _sweep_click(self, event):
        """Klick im Diagramm: zur angeklickten Frequenz tunen."""
        data = self._sweep_data
        if not data or self._sweep_freq_range is None:
            return
        lo, hi = self._sweep_freq_range
        span = max(hi - lo, 1)
        canvas = self.sweep_canvas
        width = max(canvas.winfo_width(), 100)
        hz = lo + event.x / width * span
        hz = int(round((hz // 1000) * 1000))
        status = self._last_status
        ssb = status.mode in ("LSB", "USB") if status else False
        try:
            self.send(protocol.format_frequency_command(hz, ssb))
            self.log(f"Abgestimmt auf {hz / 1000:.1f} kHz")
        except ValueError:
            self.log("Frequenz außerhalb des Bands")

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
        # Nach Verbindung und Bandwechsel sinnvolle Messpunktzahl waehlen.
        # Die Empfehlung haengt nur vom Band ab (dessen Natur laut Bandtabelle),
        # nicht vom eingestellten Modus; ein Moduswechsel aendert sie nicht.
        if (self._sweep_points_pending
                or status.band != self._sweep_points_band):
            self._sweep_points_band = status.band
            points = protocol.suggested_sweep_points(
                status.band, status.mode, status.display_frequency_hz())
            self.sweep_points_var.set(str(points))
            self._sweep_points_pending = False
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
        if self._sweep_active:
            self.root.after(0, lambda: self._sweep_on_status(status))

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
            self.rssi_var.set(f"{status.rssi} dBµV")
            self.smeter_var.set(
                protocol.s_meter(status.rssi, status.mode.upper() == "FM"))
            self.snr_var.set(f"{status.snr} dB")
            self.batt_var.set(f"{status.voltage:.2f} V")
            self._set_row_values(status)
            # Frequenzmarke im Spektrum nachziehen, wenn die Frequenz
            # geaendert wurde (ausserhalb des Sweeps, der selbst zeichnet)
            if (not self._sweep_active and self._sweep_data
                    and hz != self._sweep_marker_hz):
                self._sweep_marker_hz = hz
                self._sweep_draw()

        shot = getattr(self, "_pending_screenshot", None)
        if shot is not None:
            self._pending_screenshot = None
            self._screenshot = shot
            self._show_screenshot(shot)

        self.root.after(50, self._poll_main_thread)

    def _show_screenshot(self, shot: protocol.Screenshot):
        ppm = shot.to_ppm()
        self._shot_photo = tk.PhotoImage(data=ppm, format="PPM")
        self.shot_label.config(image=self._shot_photo, text="")

    _pending_log: list[str] = []
    _pending_status: protocol.ReceiverStatus | None = None
    _pending_screenshot: protocol.Screenshot | None = None
    _sweep_active: bool = False
    _sweep_timeout_id: str | None = None
    _sweep_phase_setup: tuple | None = None
    _sweep_setups: list = []
    _sweep_applied: list = []
    _sweep_restore_setup: tuple[bytes, bytes] | None = None
    _sweep_message: str = ""
    _sweep_restore_freq: int | None = None
    _sweep_mode: str = ""
    _sweep_marker_hz: int | None = None
    _sweep_points_pending: bool = False
    _sweep_points_band: str = ""


def main():
    root = tk.Tk()
    RemoteApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
