"""Tkinter-Oberfläche der WLAN-Fernbedienung für das ATS-Miniradio V1."""

from __future__ import annotations

import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__
from . import i18n
from . import protocol
from .client import RemoteClient

PROJECT_URL = "https://github.com/michaelgroni/ats60000"


def app_version() -> str:
    """Versionsanzeige: Release-Tag wenn moeglich, sonst Dev-Kennung.

    Bei einem Checkout mit Git-Tags (z. B. dem Release-Build) ergibt
    'git describe' den Release; Development-Builds ohne passenden
    Tag zeigen Abstand und Kurz-Hash ('0.1-14-g1a2b3c4'), damit der
    exakte Build identifizierbar bleibt. Ohne Git-Zugriff (z. B. EXE
    ausserhalb eines Repos) bleibt die Paketversion.
    """
    try:
        out = subprocess.run(
            ["git", "describe", "--tags", "--long", "--match", "v[0-9]*"],
            capture_output=True, text=True, timeout=2, check=True)
        described = out.stdout.strip().lstrip("v")
        distance, _, _hash = described.rpartition("-g")
        if distance.endswith("-0"):
            return distance[:-2]  # exakt am Tag: reiner Release
        return described
    except (OSError, subprocess.SubprocessError):
        return __version__


def _interp_rssi(freqs: list[int], measured: dict[int, int],
                 hz: int) -> int | None:
    """RSSI eines fehlenden Punkts linear zwischen Nachbarn interpolieren.

    Gesucht sind die naechsten gemessenen Punkte links und rechts der
    Frequenz; liegt nur einer davon vor (Randbereich), wird dessen Wert
    uebernommen. Ohne jeden Messwert: None (nicht zeichenbar).
    """
    idx = freqs.index(hz)
    left = None
    for j in range(idx - 1, -1, -1):
        if freqs[j] in measured:
            left = j
            break
    right = None
    for j in range(idx + 1, len(freqs)):
        if freqs[j] in measured:
            right = j
            break
    if left is None and right is None:
        return None
    if left is None:
        return measured[freqs[right]]
    if right is None:
        return measured[freqs[left]]
    lo_rssi = measured[freqs[left]]
    hi_rssi = measured[freqs[right]]
    frac = (hz - freqs[left]) / (freqs[right] - freqs[left])
    return round(lo_rssi + (hi_rssi - lo_rssi) * frac)


class _SweepPlot:
    """Geometrie des Spektrum-Canvas: Frequenz/RSSI in Pixel umrechnen."""

    def __init__(self, canvas, freq_range, pad_l, pad_r, pad_b, pad_t,
                 rssi_max):
        cw = max(canvas.winfo_width(), 100)
        ch = max(int(canvas.cget("height")), 100)
        self.pad_l = pad_l
        self.pad_t = pad_t
        self.plot_w = max(cw - pad_l - pad_r, 10)
        self.plot_h = max(ch - pad_b - pad_t - 2, 10)
        self.base_y = pad_t + self.plot_h
        lo, hi = freq_range
        self.lo = lo
        self.hi = hi
        self.span = max(hi - lo, 1)
        self.rssi_max = rssi_max

    def fx(self, hz):
        return self.pad_l + (hz - self.lo) / self.span * self.plot_w

    def fy(self, rssi):
        return self.base_y - (rssi / self.rssi_max) * self.plot_h


class RemoteApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(self._t("app_title"))
        root.minsize(560, 520)

        self.client = RemoteClient(
            on_status=self.on_status,
            on_memory=self.on_memory,
            on_line=self._on_radio_line,
            on_disconnect=self.on_disconnect,
            on_screenshot=self.on_screenshot,
            on_screenshot_progress=self.on_screenshot_progress,
        )
        self._pending_memory: list[tuple[int, str, int, str]] = []
        self._screenshot: protocol.Screenshot | None = None
        self._volume_target = 0
        self._row_value_vars: dict[str, tk.StringVar] = {}
        self._i18n_labels: list = []
        self._lang_var = tk.StringVar(value=i18n.current() or "Deutsch")
        self._memory_refresh_id: str | None = None
        self._squelch_enabled = False
        self._squelch_muted = False
        self._sweep_active = False
        self._sweep_freqs: list[int] = []
        self._sweep_index = 0
        self._sweep_restore_freq: int | None = None
        self._sweep_timeout_id: str | None = None
        self._sweep_peak: dict[int, int] = {}
        self._sweep_ema: dict[int, int] = {}
        self._sweep_prev: dict[int, int] = {}
        self._sweep_axes_band: str = ""

        self._build_ui()
        root.after(50, self._poll_main_thread)

    # ----------------------------------------------------------- Oberfläche

    def _t(self, key: str, **kwargs) -> str:
        return i18n.get_translator()(key, **kwargs)

    def _tr(self, widget, key: str):
        """Statisches Textwidget registrieren: Sprachwechsel erneuert Text."""
        self._i18n_labels.append((widget, key))
        return widget

    def _build_ui(self):
        pad = {"padx": 6, "pady": 3}
        self._build_menu()
        outer = ttk.Frame(self.root)
        outer.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Verbindungsleiste
        conn = ttk.LabelFrame(outer, text=self._t("connection"))
        self._tr(conn, "connection")
        conn.pack(fill=tk.X, **pad)
        self._tr(ttk.Label(conn, text=self._t("host")), "host").grid(
            row=0, column=0, sticky="w", padx=4, pady=4)
        self.host_var = tk.StringVar(value="atsmini.local")
        ttk.Entry(conn, textvariable=self.host_var, width=20).grid(row=0, column=1, padx=2)
        self._tr(ttk.Label(conn, text=self._t("port")), "port").grid(
            row=0, column=2, sticky="w", padx=4)
        self.port_var = tk.StringVar(value=str(protocol.DEFAULT_PORT))
        ttk.Entry(conn, textvariable=self.port_var, width=7).grid(row=0, column=3, padx=2)
        self.connect_button = ttk.Button(conn, text=self._t("connect"), command=self.connect)
        self.connect_button.grid(row=0, column=4, padx=6)
        self.state_label = ttk.Label(conn, text=self._t("disconnected"), foreground="#a00")
        self.state_label.grid(row=0, column=5, sticky="w", padx=6)

        # Status
        status = ttk.LabelFrame(outer, text=self._t("receiver"))
        self._tr(status, "receiver")
        status.pack(fill=tk.X, **pad)
        self.freq_var = tk.StringVar(value="–")
        self.band_var = tk.StringVar(value="–")
        self.mode_var = tk.StringVar(value="–")
        self.rssi_var = tk.StringVar(value="–")
        self.smeter_var = tk.StringVar(value="–")
        self.snr_var = tk.StringVar(value="–")
        self.batt_var = tk.StringVar(value="–")
        for col, (label, var) in enumerate([
            ("frequency", self.freq_var),
            ("band", self.band_var),
            ("mode", self.mode_var),
            ("signal_strength", self.rssi_var),
            ("s_value", self.smeter_var),
            ("snr", self.snr_var),
            ("battery", self.batt_var),
        ]):
            self._tr(ttk.Label(status, text=self._t(label),
                               font=("", 8, "bold")),
                     label).grid(row=0, column=col, sticky="w",
                                 padx=8, pady=(6, 0))
            ttk.Label(status, textvariable=var, font=("", 12, "bold")).grid(
                row=1, column=col, sticky="w", padx=8, pady=(0, 6))

        # Steuerung
        ctrl = ttk.LabelFrame(outer, text=self._t("controls"))
        self._tr(ctrl, "controls")
        ctrl.pack(fill=tk.X, **pad)

        self._tr(ttk.Label(ctrl, text=self._t("frequency")),
                 "frequency").grid(row=0, column=0, sticky="w", padx=4)
        self.freq_entry_var = tk.StringVar()
        ttk.Entry(ctrl, textvariable=self.freq_entry_var, width=14).grid(
            row=0, column=1, padx=2)
        self.freq_unit_var = tk.StringVar(value="MHz")
        unit_box = ttk.Combobox(ctrl, textvariable=self.freq_unit_var,
                                values=["kHz", "MHz"], width=5, state="readonly")
        unit_box.grid(row=0, column=2, padx=2)
        self._tr(ttk.Button(ctrl, text=self._t("set"), command=self.set_frequency),
                 "set").grid(row=0, column=3, padx=4)

        self.volume_var = tk.IntVar(value=0)
        self._volume_dragging = False
        self.volume_scale = ttk.Scale(ctrl, from_=0, to=63, variable=self.volume_var,
                                       command=self.on_volume_changed)
        self.volume_scale.bind("<ButtonPress-1>", lambda _e: self._volume_drag(True))
        self.volume_scale.bind("<ButtonRelease-1>", lambda _e: self._volume_drag(False))

        rows = [
            ("frequency", None, None),
            ("step_size", protocol.CMD_STEP_UP, protocol.CMD_STEP_DOWN),
            ("volume", None, None),
            ("band", protocol.CMD_BAND_UP, protocol.CMD_BAND_DOWN),
            ("mode", protocol.CMD_MODE_UP, protocol.CMD_MODE_DOWN),
            ("bandwidth", protocol.CMD_BANDWIDTH_UP, protocol.CMD_BANDWIDTH_DOWN),
            ("agc_attn", protocol.CMD_AGC_UP, protocol.CMD_AGC_DOWN),
        ]
        for row, (label, up, down) in enumerate(rows, start=1):
            if label == "frequency":
                down_cmd = lambda _l=None: self.tune(-1)
                up_cmd = lambda _l=None: self.tune(+1)
            elif label == "volume":
                self._tr(ttk.Label(ctrl, text=self._t(label), width=12), label).grid(
                    row=row, column=0, sticky="w", padx=4)
                self.volume_scale.grid(row=row, column=1, columnspan=3,
                                       sticky="we", padx=2, pady=6)
                continue
            else:
                down_cmd = (lambda c=down: lambda: self.send(c))()
                up_cmd = (lambda c=up: lambda: self.send(c))()
            self._tr(ttk.Label(ctrl, text=self._t(label), width=12), label).grid(
                row=row, column=0, sticky="w", padx=4)
            ttk.Button(ctrl, text="◀", width=3,
                       command=down_cmd).grid(row=row, column=1, sticky="w", padx=2, pady=2)
            value_var = tk.StringVar(value="–")
            self._row_value_vars[label] = value_var
            ttk.Label(ctrl, textvariable=value_var, width=12,
                      font=("", 9, "bold")).grid(row=row, column=2, sticky="w", padx=8)
            ttk.Button(ctrl, text="▶", width=3,
                       command=up_cmd).grid(row=row, column=3, sticky="w")

        self.squelch_var = tk.BooleanVar(value=False)
        self._tr(ttk.Checkbutton(ctrl, text=self._t("squelch"),
                                 variable=self.squelch_var,
                                 command=self.toggle_squelch),
                 "squelch").grid(row=row, column=1, columnspan=2,
                                 sticky="w", padx=2, pady=(2, 0))

        # Quasianaloges S-Meter rechts neben den Steuerelementen;
# Metrik per Radiobutton: RSSI, S-Wert oder SNR
        meter = ttk.Frame(ctrl)
        meter.grid(row=1, column=4, rowspan=len(rows), sticky="nsew",
                   padx=(16, 4), pady=2)
        self.smeter_metric_var = tk.StringVar(value="rssi")
        for i, (key, val) in enumerate((("metric_rssi", "rssi"),
                                        ("metric_s", "s"),
                                        ("metric_snr", "snr"))):
            self._tr(ttk.Radiobutton(meter, text=self._t(key), value=val,
                                     variable=self.smeter_metric_var,
                                     command=self._smeter_redraw),
                     key).grid(row=0, column=i, sticky="w", padx=2)
        self.smeter_canvas = tk.Canvas(meter, width=self._SMETER_W,
                                       height=self._SMETER_H,
                                       bg=self._SMETER_FACE,
                                       highlightthickness=0)
        self.smeter_canvas.grid(row=1, column=0, columnspan=3,
                               sticky="we", pady=(4, 2))
        ctrl.columnconfigure(4, weight=1)

        # Speicher
        mem = ttk.LabelFrame(outer, text=self._t("memories"))
        self._tr(mem, "memories")
        mem.pack(fill=tk.X, **pad)
        self._tr(ttk.Label(mem, text=self._t("slot")), "slot").grid(
            row=0, column=0, padx=4)
        self.slot_var = tk.StringVar(value="1")
        slot_spin = ttk.Spinbox(mem, from_=1, to=32, textvariable=self.slot_var, width=4)
        slot_spin.grid(row=0, column=1)
        self._tr(ttk.Button(mem, text=self._t("save_current"),
                            command=self.save_memory),
                 "save_current").grid(row=0, column=2, padx=4)
        self._tr(ttk.Button(mem, text=self._t("clear_slot"),
                            command=self.clear_memory),
                 "clear_slot").grid(row=0, column=3, padx=4)
        self._memory_cols = (("slot", "col_slot", 50),
                             ("band", "col_band", 80),
                             ("freq", "col_frequency", 140),
                             ("mode", "col_mode", 60))
        self.memory_tree = ttk.Treeview(mem,
                                        columns=[c[0] for c in self._memory_cols],
                                        show="headings", height=4)
        for col, key, width in self._memory_cols:
            self.memory_tree.heading(col, text=self._t(key))
            self.memory_tree.column(col, width=width)
        self.memory_tree.grid(row=1, column=0, columnspan=4, sticky="we", padx=4, pady=4)
        mem.columnconfigure(0, weight=1)

        # Spektrum (Sweep)
        sweep = ttk.LabelFrame(outer, text=self._t("spectrum"))
        self._tr(sweep, "spectrum")
        sweep.pack(fill=tk.X, **pad)
        self.sweep_points_var = tk.StringVar(value="60")
        self._tr(ttk.Label(sweep, text=self._t("points")),
                 "points").grid(row=0, column=0, padx=4, pady=2)
        ttk.Spinbox(sweep, from_=10, to=500, increment=10,
                    textvariable=self.sweep_points_var, width=6).grid(row=0, column=1)
        self.sweep_start_button = ttk.Button(sweep, text=self._t("sweep_start"),
                                             command=self.sweep_start)
        self._tr(self.sweep_start_button, "sweep_start")
        self.sweep_start_button.grid(row=0, column=2, padx=6)
        self.sweep_stop_button = ttk.Button(sweep, text=self._t("sweep_stop"),
                                            command=self.sweep_stop, state=tk.DISABLED)
        self._tr(self.sweep_stop_button, "sweep_stop")
        self.sweep_stop_button.grid(row=0, column=3, padx=4)
        self.sweep_progress_var = tk.StringVar(value="")
        ttk.Label(sweep, textvariable=self.sweep_progress_var).grid(
            row=0, column=4, padx=8)
        self.sweep_canvas = tk.Canvas(sweep, height=140, bg="#000",
                                      highlightthickness=0)
        self.sweep_canvas.grid(row=1, column=0, columnspan=5, sticky="we",
                               padx=4, pady=(0, 4))
        # Spalte 0 nimmt die ganze zusaetzliche Breite auf: das Spektrum
        # fuellt das Fenster abzueglich Rand und waechst mit dem Fenster
        sweep.columnconfigure(0, weight=1)
        self.sweep_canvas.bind("<Button-1>", self._sweep_click)
        self.sweep_canvas.bind("<Configure>", self._sweep_on_resize)
        self._sweep_data: list[tuple[int, int]] | None = None
        self._sweep_freq_range: tuple[int, int] | None = None

        # Screenshot
        shot = ttk.LabelFrame(outer, text=self._t("display"))
        self._tr(shot, "display")
        shot.pack(fill=tk.X, **pad)
        self._tr(ttk.Button(shot, text=self._t("screenshot"),
                            command=self.take_screenshot),
                 "screenshot").grid(row=0, column=0, padx=4, pady=2)
        self._tr(ttk.Button(shot, text=self._t("save_as"),
                            command=self.save_screenshot),
                 "save_as").grid(row=0, column=1, padx=4)
        self.shot_label = ttk.Label(shot, text=self._t("no_screenshot"))
        self.shot_label.grid(row=0, column=2, padx=8)

        # Log (per Menue Ansicht ein-/ausblendbar; Programmstart: aus):
        # Tabellenansicht mit Spaltenueberschriften und Rollbalken
        self.logbox = ttk.LabelFrame(outer, text=self._t("log"))
        self._tr(self.logbox, "log")
        self._log_visible = False
        self._log_cols = (
            ("time", "col_time", 62),
            ("source", "col_source", 62),
            ("kind", "col_kind", 70),
            ("freq", "col_frequency", 92),
            ("band", "col_band", 55),
            ("mode", "col_mode", 46),
            ("step", "col_step", 48),
            ("bw", "col_bw", 56),
            ("agc", "col_agc", 38),
            ("vol", "col_vol", 44),
            ("rssi", "col_rssi", 46),
            ("snr", "col_snr", 42),
            ("volt", "col_volt", 48),
            ("msg", "col_message", 280),
        )
        self.log_tree = ttk.Treeview(self.logbox,
                                     columns=[c[0] for c in self._log_cols],
                                     show="headings", height=8)
        for col, key, width in self._log_cols:
            self.log_tree.heading(col, text=self._t(key))
            self.log_tree.column(col, width=width, stretch=(col == "msg"))
        self.log_tree.tag_configure("raw", foreground="#b50")
        log_scroll = ttk.Scrollbar(self.logbox, orient=tk.VERTICAL,
                                   command=self.log_tree.yview)
        self.log_tree.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 4), pady=4)
        self.log_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True,
                           padx=(4, 0), pady=4)

        self.root.bind("<Return>", lambda _e: self.set_frequency())

    def _build_menu(self):
        """Menueleiste: Ansicht (Log) und Hilfe (Website, Ueber)."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label=self._t("show_log"), command=self.toggle_log)
        # Sprache: Radiobuttons je verfuegbarer Sprache; fehlende
        # Schluessel fallen im Translator auf Deutsch zurueck
        lang_menu = tk.Menu(view_menu, tearoff=0)
        current_lang = i18n.current() or "Deutsch"
        for name in i18n.available():
            lang_menu.add_radiobutton(
                label=name, value=name, variable=self._lang_var,
                command=lambda n=name: self.switch_language(n))
        view_menu.add_cascade(label=self._t("menu_language"), menu=lang_menu)
        menubar.add_cascade(label=self._t("menu_view"), menu=view_menu)
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label=self._t("menu_website"), command=self.open_website)
        help_menu.add_command(label=self._t("menu_about"), command=self.show_about)
        menubar.add_cascade(label=self._t("menu_help"), menu=help_menu)
        self._view_menu = view_menu

    def switch_language(self, name: str):
        """Sprache umschalten: statische Texte der Fenster aktualisieren.
        Dynamische Werte (Status, Speicherliste, Log) uebernehmen die neue
        Sprache mit dem naechsten Update von selbst.
        """
        i18n.set_language(name)
        self.root.title(self._t("app_title"))
        self._apply_language()

    def _apply_language(self):
        """Statische Widget-Texte auf die aktive Sprache umstellen."""
        t = self._t
        for widget, key in self._i18n_labels:
            widget.config(text=t(key))
        self.connect_button.config(
            text=t("disconnect") if self.client.is_connected() else t("connect"))
        self.state_label.config(
            text=t("connected") if self.client.is_connected()
            else t("disconnected"))
        # Log-Menueetikett und Spaltenueberschriften
        self._view_menu.entryconfigure(
            0, label=t("hide_log" if self._log_visible else "show_log"))
        for col, key, _w in self._log_cols:
            self.log_tree.heading(col, text=t(key))
        for col, key, _w in self._memory_cols:
            self.memory_tree.heading(col, text=t(key))
        self.shot_label.config(
            image="", text=t("no_screenshot")
            if getattr(self, "_shot_photo", None) is None else "")
        self._smeter_redraw()

    def toggle_log(self):
        """Log-Anzeige ein-/ausblenden (Startzustand: ausgeblendet)."""
        self._log_visible = not self._log_visible
        if self._log_visible:
            self.logbox.pack(fill=tk.BOTH, expand=True,
                             padx=6, pady=3)
        else:
            self.logbox.pack_forget()
        self._view_menu.entryconfigure(
            0, label=self._t("hide_log" if self._log_visible
                             else "show_log"))

    def _log_insert(self, source: str, message: str):
        """Zeile in die Logtabelle einfuegen und auf 400 Zeilen begrenzen.

        Radio-Statuszeilen (CSV mit 15 Feldern) werden in ihre
        Bestandteile zerlegt; alles andere erscheint in der Spalte
        Nachricht, unformatierte Zeilen zusaetzlich farbig markiert.
        """
        import time as _time
        stamp = _time.strftime("%H:%M:%S")
        src = self._t("log_source_app" if source == "app" else "log_source_radio")
        tags = ("raw",) if self._log_line_is_raw(message) else ()
        values: tuple = (stamp, src) + ("",) * 11 + (message,)
        if source == "radio":
            status = protocol.parse_status(message)
            if status is not None:
                tags = ()
                hz = status.display_frequency_hz()
                if status.mode.upper() == "FM":
                    freq = f"{protocol.fmt_num(hz / 1e6, 2)} MHz"
                else:
                    freq = f"{protocol.fmt_num(hz / 1e3, 3)} kHz"
                values = (stamp, src,
                          self._t("log_kind_status"),
                          freq,
                          status.band,
                          status.mode,
                          status.step,
                          status.bandwidth,
                          str(status.agc),
                          str(status.volume),
                          f"{status.rssi} dBµV",
                          f"{status.snr} dB",
                          protocol.fmt_num(status.voltage, 2),
                          "")
        item = self.log_tree.insert("", tk.END, values=values, tags=tags)
        children = self.log_tree.get_children()
        if len(children) > 400:
            self.log_tree.delete(*children[:len(children) - 400])
        self.log_tree.see(item)

    def open_website(self):
        import webbrowser
        webbrowser.open(PROJECT_URL)

    def show_about(self):
        messagebox.showinfo(
            self._t("menu_about"),
            f"{self._t('app_title')}\n{self._t('menu_about_version')} {app_version()}\n\n"
            f"{self._t('menu_about_project')}:\n{PROJECT_URL}")

    # ------------------------------------------------------ Aktionen am Radio

    def connect(self):
        host = self.host_var.get().strip()
        if not host:
            messagebox.showerror(self._t("error"), self._t("err_no_host"))
            return
        try:
            port = int(self.port_var.get())
        except ValueError:
            messagebox.showerror(self._t("error"), self._t("err_invalid_port"))
            return
        try:
            self.client.connect(host, port)
        except OSError as exc:
            messagebox.showerror(self._t("err_connect_failed"), str(exc))
            return
        self.set_state(True)
        self.send(protocol.CMD_TOGGLE_LOG)
        self._sweep_points_pending = True
        self.show_memories()
        self._schedule_memory_refresh()
        self.log(self._t("connected_with", host=host, port=port))

    def disconnect(self):
        self.client.disconnect()
        self.set_state(False)
        self.log(self._t("disconnected_log"))

    def send(self, command: bytes):
        if not self.client.is_connected():
            self.log(self._t("not_connected_cmd"))
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
            self.log(self._t("no_status_tune"))
            return
        hz = status.display_frequency_hz()
        step_hz = protocol.step_size_hz(status)
        # Ziel muss durch die Schrittweite teilbar sein: Liegt die aktuelle
        # Frequenz daneben (z. B. nach SSB-BFO-Feinabstimmung oder manueller
        # Eingabe), springt der Schritt auf das naechste Vielfache in
        # Klickrichtung, statt das Raster weiter zu verfehlen.
        if hz % step_hz == 0:
            target = hz + direction * step_hz
        else:
            lower = (hz // step_hz) * step_hz
            target = lower + step_hz if direction > 0 else lower
        ssb = status.mode in ("LSB", "USB")
        try:
            self.send(protocol.format_frequency_command(target, ssb))
        except ValueError:
            self.log(self._t("freq_out_of_band_step"))

    # -------------------------------------------------- Spektrum (Sweep)

    def sweep_start(self):
        if not self.client.is_connected():
            self.log(self._t("not_connected_sweep"))
            return
        status = self._last_status
        if status is None:
            self.log(self._t("no_status_sweep"))
            return
        rng = protocol.sweep_points_for_band(
            status.band, status.mode, status.display_frequency_hz())
        if rng is None:
            self.log(self._t("band_unknown_sweep", band=status.band))
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
        # Punkte gleichmaessig verteilen, jede einzeln aufs feinste
        # Schrittweitenraster runden: Punktzahl bleibt erhalten, jede
        # Messfrequenz liegt nah an ihrer Idealposition. Das Raster legt
        # nur die firmwarekonformen Frequenzen fest, nicht den Abstand.
        self._sweep_freqs, step_text, spacing_hz = protocol.sweep_plan(
            int(lo_khz) * 1000, int(hi_khz) * 1000, points, sweep_mode)
        step = protocol.step_hz(step_text)
        if len(self._sweep_freqs) < 2:
            self.log(self._t("band_too_narrow"))
            return
        self._sweep_index = 0
        self._sweep_data = []
        self._sweep_marker_hz = None
        self._sweep_freq_range = (self._sweep_freqs[0], self._sweep_freqs[-1])
        self._sweep_restore_freq = status.display_frequency_hz()
        # Bandbreite nach dem Punktabstand waehlen (nicht nach dem Raster):
        # kleinste Breite >= Punktabstand, sonst die groesste
        bw_target = protocol.bandwidth_for_step(spacing_hz / 1000, sweep_mode)
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
            self.log(self._t("log_sweep_mode", mode=sweep_mode, old=status.mode))
        self.log(self._t("log_sweep_over", band=status.band, lo=lo_khz, hi=hi_khz,
                         points=len(self._sweep_freqs), step=step_text,
                         bw=bw_target))
        # Achsengeruest einmalig zeichnen; die Messpunkte werden danach
        # inkrementell hinzugefuegt (kein Vollredraw pro Punkt)
        self._sweep_axis_max = self._SWEEP_AXIS_MIN
        self.sweep_canvas.delete("all")
        plot = self._sweep_plot()
        self._sweep_draw_frame(plot)
        self._sweep_draw_marker(plot)
        self._sweep_advance_setup()

    def sweep_stop(self):
        if not self._sweep_active:
            return
        self._sweep_active = False
        self._sweep_finish(self._t("sweep_cancelled"))

    def _sweep_next(self):
        if not self._sweep_active:
            return
        if self._sweep_index >= len(self._sweep_freqs):
            self._sweep_finish(self._t("sweep_done"))
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

    def _sweep_update_peak(self, hz: int, rssi: int):
        """Peak-Hold je Frequenz: Rueckblick in der Zeit, nicht auf der
        Frequenzachse.

        Vorheriger Wert und gleitender Mittelwert werden pro Frequenz
        gehalten und ueber Sweeps hinweg weitergefuehrt. Der Mittelwert
        ist ein EMA ohne Historie (alter und neuer Stand gehen je zur
        Haelfte ein) und decayt mit jeder erneuten Messung derselben
        Frequenz; gemerkt wird das Maximum beider. Ein Signal, das in
        frueheren Sweeps da war, bleibt so als blasse Flaeche an
        seiner Frequenz sichtbar und klingt mit der Zeit ab.
        """
        prev = self._sweep_prev.get(hz, 0)
        ema = (self._sweep_ema.get(hz, 0) + rssi) // 2
        self._sweep_ema[hz] = ema
        self._sweep_peak[hz] = max(prev, ema)
        self._sweep_prev[hz] = rssi

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
            self.log(self._t("log_sweep_setup_conflict", name=name, target=target))
            self._sweep_phase_setup = None
            self._sweep_advance_setup()
            return
        hz = self._sweep_freqs[self._sweep_index] \
            if self._sweep_index < len(self._sweep_freqs) else None
        self.log(self._t("log_point_skipped",
                             freq=protocol.fmt_num(hz / 1000, 1)))
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
        self._sweep_update_peak(expected_hz, status.rssi)
        self._sweep_index += 1
        done = self._sweep_index
        total = len(self._sweep_freqs)
        self.sweep_progress_var.set(f"{done}/{total}")
        self._sweep_draw_incr(expected_hz)
        if done >= total:
            self._sweep_finish(self._t("sweep_done"))
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
        self.sweep_progress_var.set(
            self._sweep_message or self._t("sweep_done"))
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
        self.log(self._t("log_sweep_summary", message=self._sweep_message,
                         points=len(self._sweep_data or [])))
        # Abschlusszeichnung: fuellt die letzten Luecken (am rechten Rand
        # fehlt der rechte Nachbar) und setzt die Frequenzmarke neu
        self._sweep_draw()

    _SWEEP_AXIS_MIN = 60       # dBuV: kleineres Achsenmaximum nie sinnvoll
    _sweep_axis_max = 60       # aktuell gezeichnetes Achsenmaximum
    _SWEEP_PAD_L = 32         # Platz fuer die dBuV-Achse links
    _SWEEP_PAD_R = 46         # Platz rechts: Frequenz und Einheit ohne Ueberschneidung
    _SWEEP_PAD_B = 16         # Platz fuer die Frequenzachse unten
    _SWEEP_PAD_T = 22         # Platz oben: Einheit ueber der Achsenspitze
    _SWEEP_TICK_FONT = ("", 7)

    def _sweep_scale_max(self) -> int:
        """Achsenmaximum: groesster Messwert oder Peak-Hold-Wert, auf
        Vielfache von 10 aufgerundet, aber nie kleiner als 60 dBuV."""
        data = self._sweep_data or []
        peak = max((rssi for _hz, rssi in data), default=0)
        hold = max(self._sweep_peak.values(), default=0)
        peak = max(peak, hold)
        return max(self._SWEEP_AXIS_MIN, ((peak + 9) // 10) * 10)

    def _sweep_plot(self) -> _SweepPlot:
        """Aktuelles Layout des Spektrum-Canvas als _SweepPlot."""
        return _SweepPlot(self.sweep_canvas, self._sweep_freq_range,
                          self._SWEEP_PAD_L, self._SWEEP_PAD_R,
                          self._SWEEP_PAD_B, self._SWEEP_PAD_T,
                          self._sweep_axis_max)

    def _sweep_draw_frame(self, plot: _SweepPlot):
        """Achsen und Beschriftung zeichnen (einmalig pro Sweep/Redraw)."""
        canvas = self.sweep_canvas
        pad_l = plot.pad_l
        pad_t = plot.pad_t
        base_y = plot.base_y
        fx = plot.fx
        fy = plot.fy

        # dBuV-Achse links: Ticks alle 20 dB bis zum Achsenmaximum
        for rssi in range(0, plot.rssi_max + 1, 20):
            y = fy(rssi)
            canvas.create_line(pad_l - 3, y, pad_l, y, fill="#888")
            canvas.create_text(pad_l - 5, y, text=str(rssi), anchor="e",
                               font=self._SWEEP_TICK_FONT, fill="#ccc")
        canvas.create_line(pad_l, pad_t, pad_l, base_y, fill="#888")
        # Einheit links oberhalb der Achsenspitze
        canvas.create_text(pad_l - 5, pad_t - 7, text="dBµV",
                           anchor="se", font=self._SWEEP_TICK_FONT, fill="#ccc")

        # Frequenzachse unten: 9 Ticks mit Zahl, Einheit nach Spanne (MHz/kHz)
        span = plot.span
        unit = "MHz" if span >= 2_000_000 else "kHz"
        scale = 1_000_000 if unit == "MHz" else 1_000
        canvas.create_line(pad_l, base_y, pad_l + plot.plot_w, base_y, fill="#888")
        for i in range(9):
            hz = plot.lo + i * span / 8
            x = fx(hz)
            canvas.create_line(x, base_y, x, base_y + 3, fill="#888")
            value = hz / scale
            text = (protocol.fmt_num(value, 2) if value < 100
                    else protocol.fmt_num(value, 1))
            canvas.create_text(x, base_y + 5, text=text, anchor="n",
                               font=self._SWEEP_TICK_FONT, fill="#ccc")
        # Einheit rechts unterhalb der Achsenspitze, mit Abstand zur
        # hoechsten Frequenz (nicht ueberschneidend)
        canvas.create_text(pad_l + plot.plot_w + 18, base_y + 5, text=unit,
                           anchor="nw", font=self._SWEEP_TICK_FONT, fill="#ccc")

    def _sweep_draw_marker(self, plot: _SweepPlot):
        """Eingestellte Frequenz als vertikale Markierung; waehrend des
        Sweeps ist das die Restore-Frequenz, da das Radio gerade das
        Band durchfaehrt."""
        if self._sweep_active and self._sweep_restore_freq is not None:
            current_hz = self._sweep_restore_freq
        else:
            status = self._last_status
            current_hz = status.display_frequency_hz() if status else None
        if current_hz is not None and plot.lo <= current_hz <= plot.hi:
            x = plot.fx(current_hz)
            self.sweep_canvas.create_line(x, plot.pad_t, x, plot.base_y,
                                          fill=self.MARKER_COLOR, width=2)

    _SWEEP_PEAK_FILL = "#060"   # Peak-Hold: blasseres Gruen

    def _sweep_fill(self, plot: _SweepPlot, hz1: int, rssi1: int,
                    hz2: int, rssi2: int, color: str = "#0f0"):
        """Flaeche zwischen zwei Punkten bis zur Basislinie fuellen.

        Das Trapez ist die grafische lineare Interpolation: alle
        Frequenzen zwischen hz1 und hz2 liegen auf der Verbindungsgeraden,
        es entstehen keine schwarzen Luecken zwischen den Messpunkten.
        """
        x1, x2 = plot.fx(hz1), plot.fx(hz2)
        if x2 <= x1:
            return
        y1, y2 = plot.fy(rssi1), plot.fy(rssi2)
        self.sweep_canvas.create_polygon(
            x1, y1, x2, y2, x2, plot.base_y, x1, plot.base_y,
            fill=color, outline="")

    def _sweep_range_or_band(self) -> tuple[int, int] | None:
        """Frequenzbereich fuer die Achsen: Sweep-Bereich, sonst aktuelles
        Band laut letztem Status -- Achsen sind damit auch ohne
        Spektrumdaten sichtbar."""
        if self._sweep_freq_range is not None:
            return self._sweep_freq_range
        status = self._last_status
        if status is None:
            return None
        rng = protocol.sweep_points_for_band(
            status.band, status.mode, status.display_frequency_hz())
        if rng is None:
            return None
        return int(rng[0]) * 1000, int(rng[1]) * 1000

    def _sweep_draw(self):
        """Alles zeichnen: nach Sweep-Ende, Band- oder Frequenzwechsel.

        Ohne Spektrumdaten werden nur Achsen und Frequenzmarke gezeigt
        (Bereich aus dem aktuellen Band). Mit Daten: Achsenmaximum
        dynamisch aus den Messwerten, dann durchgehende Flaeche --
        zwischen allen Punkten (gemessen oder interpoliert) wird je ein
        Trapez bis zur Basislinie gefuellt.
        """
        data = self._sweep_data
        canvas = self.sweep_canvas
        canvas.delete("all")
        rng = self._sweep_range_or_band()
        if rng is None:
            return
        if data:
            self._sweep_axis_max = self._sweep_scale_max()
        plot = _SweepPlot(self.sweep_canvas, rng,
                          self._SWEEP_PAD_L, self._SWEEP_PAD_R,
                          self._SWEEP_PAD_B, self._SWEEP_PAD_T,
                          self._sweep_axis_max)
        self._sweep_draw_frame(plot)
        if not data:
            self._sweep_draw_marker(plot)
            return
        measured = dict(data)
        freqs_all = self._sweep_freqs or [hz for hz, _ in data]
        values: list[tuple[int, int]] = []
        for hz in freqs_all:
            if hz in measured:
                values.append((hz, measured[hz]))
            else:
                rssi = _interp_rssi(freqs_all, measured, hz)
                if rssi is not None:
                    values.append((hz, rssi))
        # Peak-Hold-Flaeche (blass) unter der Hauptflaeche: sichtbar bleibt
        # sie nur, wo fruehere Werte ueber dem aktuellen Spektrum lagen
        peaks = [(hz, self._sweep_peak.get(hz, rssi))
                 for hz, rssi in values]
        for (hz1, rssi1), (hz2, rssi2) in zip(peaks, peaks[1:]):
            self._sweep_fill(plot, hz1, rssi1, hz2, rssi2,
                             color=self._SWEEP_PEAK_FILL)
        for (hz1, rssi1), (hz2, rssi2) in zip(values, values[1:]):
            self._sweep_fill(plot, hz1, rssi1, hz2, rssi2)
        self._sweep_draw_marker(plot)

    def _sweep_draw_incr(self, hz: int):
        """Nach einem Messpunkt inkrementell weiterzeichnen.

        Es wird nur das Trapez vom letzten gemessenen Punkt bis zum
        neuen Messpunkt gefuellt -- es deckt alle Luecken davor ab, denn
        die Flaeche zwischen zwei Messpunkten ist deren Interpolation.
        Uebersteigt der Messwert das aktuelle Achsenmaximum, wird einmal
        komplett neu gezeichnet (Achse hoher skaliert).
        """
        if self._sweep_freq_range is None or not self._sweep_freqs:
            return
        if self._sweep_scale_max() != self._sweep_axis_max:
            self._sweep_draw()
            return
        freqs = self._sweep_freqs
        measured = dict(self._sweep_data or [])
        idx = freqs.index(hz)
        plot = self._sweep_plot()
        prev = None
        for j in range(idx - 1, -1, -1):
            if freqs[j] in measured:
                prev = j
                break
        rssi = measured[hz]
        peak = self._sweep_peak.get(hz, rssi)
        if prev is None:
            # kein linker Nachbar: einseitige Interpolation, die
            # Flaeche links davon liegt flach auf dem Messwert
            self._sweep_fill(plot, plot.lo, peak, hz, peak,
                             color=self._SWEEP_PEAK_FILL)
            self._sweep_fill(plot, plot.lo, rssi, hz, rssi)
        else:
            hz_p = freqs[prev]
            peak_p = self._sweep_peak.get(hz_p, measured[hz_p])
            self._sweep_fill(plot, hz_p, peak_p, hz, peak,
                             color=self._SWEEP_PEAK_FILL)
            self._sweep_fill(plot, hz_p, measured[hz_p], hz, rssi)

    def _sweep_on_resize(self, event):
        """Bei Groessenaenderung neu zeichnen: das Spektrum passt sich
        der neuen Canvas-Breite an (Achsen, Flaechen, Marke)."""
        self._sweep_draw()

    def _sweep_click(self, event):
        """Klick im Diagramm: zur angeklickten Frequenz tunen."""
        data = self._sweep_data
        if not data or self._sweep_freq_range is None:
            return
        lo, hi = self._sweep_freq_range
        span = max(hi - lo, 1)
        canvas = self.sweep_canvas
        cw = max(canvas.winfo_width(), 100)
        pad_l = self._SWEEP_PAD_L
        plot_w = max(cw - pad_l - self._SWEEP_PAD_R, 10)
        hz = lo + (event.x - pad_l) / plot_w * span
        status = self._last_status
        # Klickfrequenz auf ein Vielfaches der eingestellten Schrittweite
        # runden: das Radio springt dann exakt auf eine Rasterfrequenz
        step = protocol.step_hz(status.step) if status else 1000
        step = max(step, 1)
        hz = int(round(round(hz / step) * step))
        ssb = status.mode in ("LSB", "USB") if status else False
        try:
            self.send(protocol.format_frequency_command(hz, ssb))
            self.log(self._t("log_tuned",
                             freq=protocol.fmt_num(hz / 1000, 1)))
        except ValueError:
            self.log(self._t("freq_out_of_band"))

    _SMETER_W = 260
    _SMETER_H = 122
    _SMETER_BG = "#f4eedd"     # Hintergrund = Zifferblattfarbe, ab Start hell
    _SMETER_FACE = "#f4eedd"   # helles Zifferblatt
    _SMETER_TXT = "#111"
    _SMETER_TICK = "#000"
    _SMETER_RED = "#c00"       # roter Bereich am Skalenende
    MARKER_COLOR = "#f80"        # Farbe der Frequenzmarke im Spektrum
    _SMETER_NEEDLE = MARKER_COLOR
    _SMETER_PIVOT = (130, 86)   # Drehpunkt des Zeigers
    _SMETER_R = 60              # Skalenradius
    _SMETER_ARC = 180            # Zeichenauslenkung links->rechts (Grad)
    _SMETER_RED_FROM = 0.85     # ab hier Skalenbereich rot

    def _smeter_value(self, status) -> tuple[float, str, list[str]]:
        """Metrik-abhaengiger Anzeigewert: (0..1, Text, Tick-Labels)."""
        metric = self.smeter_metric_var.get()
        if metric == "s":
            # Skala S1..S9 mit Bereich darueber (+10..+60 dB ueber S9);
            # Zeigerwert und Ticks verwenden dieselbe Positionsskala:
            # 15 Schritte = S1..S9 (9) + 10..60 dB (6)
            s = protocol.s_meter(status.rssi, status.mode.upper() == "FM")
            # 15 Positionen: 1..9 und +10..+60; Labels nur auf jeder
            # zweiten Position (1, 3, 5, 7, 9, +20, +40, +60)
            ticks = []
            for pos in range(15):
                if pos < 9:
                    label = str(pos + 1)
                else:
                    label = f"+{(pos - 8) * 10}"
                ticks.append(label if pos % 2 == 0 else None)
            pos = 14   # ">S9+60" -> Skalenende
            if s.startswith("S"):
                body, _, over = s[1:].partition("+")
                try:
                    pos = int(body) - 1
                except ValueError:
                    pos = 8
                if over:
                    try:
                        pos += int(over) // 10
                    except ValueError:
                        pass
            pos = max(0, min(pos, 14))
            return pos / 14, s, ticks
        if metric == "snr":
            # SNR 0..60 dB -> 0..1; Ticks alle 15 dB
            v = max(0.0, min(status.snr, 60.0)) / 60.0
            text = f"{status.snr:.0f} dB"
            return v, text, ["0", "10", "20", "30", "40", "50", "60"]
        # Signalstaerke: RSSI 0..127 dBuV -> 0..1; Ticks alle 20 dB
        v = max(0.0, min(status.rssi, 127.0)) / 127.0
        return v, f"{status.rssi} dBµV", [str(t) for t in range(10, 128, 10)]

    def _smeter_redraw(self):
        """S-Meter neu zeichnen: analoges Zeigerinstrument im klassischen
        Look mit hellem Zifferblatt, Skala ausserhalb des Halbkreises
        beschriftet, rotem Uebersteuerungsbereich und Zeiger."""
        import math as _math
        canvas = self.smeter_canvas
        canvas.delete("all")
        status = self._last_status
        value, text, ticks = 0.0, "–", []
        if status is not None:
            value, text, ticks = self._smeter_value(status)
        value = max(0.0, min(value, 1.0))
        w = self._SMETER_W
        h = self._SMETER_H
        cx, cy = self._SMETER_PIVOT
        r = self._SMETER_R
        arc = self._SMETER_ARC

        def polar(angle_deg: float, radius: float) -> tuple[float, float]:
            # Winkel 0 = linke Skalenendung, arc = rechte Skalenendung,
            # Bogen verlaeuft oberhalb des Drehpunkts
            a = _math.radians(180 - angle_deg)
            return cx + radius * _math.cos(a), cy - radius * _math.sin(a)

        # helles Zifferblatt im dunklen Gehaeuse, mit Blende als Rahmen
        canvas.create_rectangle(4, 4, w - 4, h - 4,
                                fill=self._SMETER_FACE,
                                outline="#999", width=2)

        # roter Uebersteuerungsbereich am Skalenende als Bogenband
        a0 = self._SMETER_RED_FROM * arc
        band = []
        steps = 12
        for i in range(steps + 1):
            band.append(polar(a0 + (arc - a0) * i / steps, r + 2))
        for i in range(steps, -1, -1):
            band.append(polar(a0 + (arc - a0) * i / steps, r - 3))
        canvas.create_polygon(*band, fill=self._SMETER_RED, outline="")

        # Skala: Hauptticks mit Label ausserhalb des Bogens, Zwischenticks
        n = max(len(ticks) - 1, 1)
        for i in range(n + 1 if ticks else 0):
            angle = i * arc / n
            x_out, y_out = polar(angle, r)
            x_in, y_in = polar(angle, r - 10)
            canvas.create_line(x_out, y_out, x_in, y_in,
                               fill=self._SMETER_TICK, width=2)
            if ticks[i] is not None:
                lx, ly = polar(angle, r + 13)
                canvas.create_text(lx, ly, text=ticks[i], anchor="c",
                                   font=("", 8), fill=self._SMETER_TXT)
            if i < n:
                for sub in (1/2,):
                    a_sub = angle + arc / n * sub
                    xs_out, ys_out = polar(a_sub, r)
                    xs_in, ys_in = polar(a_sub, r - 6)
                    canvas.create_line(xs_out, ys_out, xs_in, ys_in,
                                       fill=self._SMETER_TICK, width=1)

        # Zeiger vom Drehpunkt zum Skalenwert, Drehpunkt als Nabe
        nx, ny = polar(value * arc, r - 6)
        canvas.create_line(cx, cy, nx, ny,
                           fill=self._SMETER_NEEDLE, width=2)
        canvas.create_oval(cx - 4, cy - 4, cx + 4, cy + 4,
                           fill=self._SMETER_TICK, outline="")

        # Wertziffer unter dem Drehpunkt, rot im Uebersteuerungsbereich
        canvas.create_text(cx, cy + 9, text=text, anchor="n",
                           font=("", 9, "bold"),
                           fill=self._SMETER_RED if value >= self._SMETER_RED_FROM
                           else self._SMETER_TXT)

    def _set_row_values(self, status: protocol.ReceiverStatus):
        """Wertanzeige zwischen den ◀/▶-Buttons aktualisieren."""
        vars_ = self._row_value_vars
        if "frequency" in vars_:
            hz = status.display_frequency_hz()
            if status.mode.upper() == "FM":
                vars_["frequency"].set(
                    f"{protocol.fmt_num(hz / 1e6, 2)} MHz")
            else:
                vars_["frequency"].set(
                    f"{protocol.fmt_num(hz / 1e3, 3)} kHz")
        if "band" in vars_:
            vars_["band"].set(status.band)
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
        if "mode" in vars_:
            vars_["mode"].set(status.mode)
        if "step_size" in vars_:
            vars_["step_size"].set(status.step)
        if "bandwidth" in vars_:
            vars_["bandwidth"].set(status.bandwidth)
        if "agc_attn" in vars_:
            # Firmware: 0 = AGC ein, >0 = Attenuation (Wert = Index - 1)
            vars_["agc_attn"].set(self._t("agc_on") if status.agc == 0
                                  else f"ATTN {status.agc - 1}")

    def set_frequency(self):
        raw = self.freq_entry_var.get().strip()
        if not raw:
            return
        try:
            value = protocol.parse_float(raw)
        except ValueError:
            messagebox.showerror(self._t("error"), self._t("err_invalid_frequency"))
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
        burst = protocol.volume_burst(self._current_volume, self._volume_target)
        if burst:
            self.send(burst)

    def toggle_squelch(self):
        """Rauschsperre ein-/ausschalten."""
        self._squelch_enabled = bool(self.squelch_var.get())
        if not self._squelch_enabled and self._squelch_muted:
            self._squelch_unmute()

    def _squelch_unmute(self):
        """Stummschaltung aufheben: das Radio steht auf 0, also von 0
        zurueck zum vom Nutzer eingestellten Wert."""
        self._squelch_muted = False
        if not self.client.is_connected():
            return
        burst = protocol.volume_burst(0, self._volume_target)
        if burst:
            self.send(burst)

    def _squelch_eval(self, status: protocol.ReceiverStatus):
        """Rauschsperre fuer AM/FM: unterhalb der Schwellen stumm schalten.

        Das Radio hat keine Mute-Funktion; die Sperre setzt daher die
        Lautstaerke voruebergehend auf 0 und stellt beim Oeffnen den
        vom Nutzer eingestellten Wert wieder her. Hysterese verhindert
        Flattern bei Werten um die Schwelle; nur AM und FM werden
        betrachtet, in SSB-Modi bleibt die Sperre wirkungslos.
        """
        if not self._squelch_enabled:
            if self._squelch_muted:
                self._squelch_unmute()
            return
        mode = status.mode.upper()
        if mode not in ("AM", "FM"):
            if self._squelch_muted:
                self._squelch_unmute()
            return
        open_rssi = 15 if mode == "AM" else 20
        close_rssi = open_rssi - 5
        open_snr = 10
        close_snr = 7
        signal = status.rssi >= open_rssi and status.snr >= open_snr
        noise = status.rssi <= close_rssi or status.snr <= close_snr
        if self._squelch_muted:
            if signal:
                self._squelch_unmute()
        elif noise:
            if self._volume_target > 0 and self._current_volume > 0:
                self._squelch_muted = True
                self.send(protocol.volume_burst(self._current_volume, 0))

    def show_memories(self):
        self._pending_memory = []
        self.send(protocol.CMD_SHOW_MEMORIES)
        self.root.after(800, self._flush_memories)

    def _schedule_memory_refresh(self):
        """Speicherliste selten auffrischen (alle 60 s), solange verbunden."""
        if self._memory_refresh_id is not None:
            self.root.after_cancel(self._memory_refresh_id)
        if not self.client.is_connected():
            self._memory_refresh_id = None
            return
        self._memory_refresh_id = self.root.after(
            60_000, self._memory_refresh_tick)

    def _memory_refresh_tick(self):
        self._memory_refresh_id = None
        if self.client.is_connected():
            self.show_memories()
            self._schedule_memory_refresh()

    def save_memory(self):
        status = self._last_status
        if status is None:
            messagebox.showerror(self._t("error"), self._t("err_no_status"))
            return
        try:
            slot = int(self.slot_var.get())
        except ValueError:
            messagebox.showerror(self._t("error"), self._t("err_invalid_slot"))
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
            messagebox.showerror(self._t("error"), self._t("err_invalid_slot"))
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
            display = (f"{protocol.fmt_num(freq / 1_000_000, 3)} MHz"
                   if freq >= 10_000_000
                   else f"{freq / 1000:.0f} kHz")
            self.memory_tree.insert("", tk.END, values=(slot, band, display, mode))

    def take_screenshot(self):
        if not self.client.is_connected():
            self.log(self._t("not_connected_shot"))
            return
        self.shot_label.config(image="")
        self.shot_label.config(text=self._t("receiving", percent=0))
        self.client.request_screenshot()

    def save_screenshot(self):
        if self._screenshot is None:
            messagebox.showerror(self._t("error"), self._t("err_no_screenshot"))
            return
        filename = filedialog.asksaveasfilename(
            defaultextension=".bmp", filetypes=[("BMP-Bild", "*.bmp")])
        if not filename:
            return
        with open(filename, "wb") as fh:
            fh.write(self._screenshot.to_bmp())
        self.log(self._t("screenshot_saved", filename=filename))

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

    def _on_radio_line(self, line: str):
        self.log(line, source="radio")

    def on_disconnect(self, reason: str):
        self.root.after(0, lambda: self._handle_disconnect(reason))

    def _handle_disconnect(self, reason: str):
        self.set_state(False)
        if self._memory_refresh_id is not None:
            self.root.after_cancel(self._memory_refresh_id)
            self._memory_refresh_id = None
        self.log(self._t("connection_lost", reason=reason))

    def on_screenshot(self, shot: protocol.Screenshot):
        self._pending_screenshot = shot

    def on_screenshot_progress(self, received: int, total: int):
        """Fortschritt des Screenshot-Empfangs (aus dem Leser-Thread).

        total = 0: Uebertragung laeuft noch ohne bekannte Zeilenzahl
        (Header fehlt noch). Sonst: received von total Zeilen.
        """
        self._pending_screenshot_progress = (received, total)

    # ----------------------------------------------------------- Hilfsfunktionen

    def set_state(self, connected: bool):
        if connected:
            self.connect_button.config(text=self._t("disconnect"), command=self.disconnect)
            self.state_label.config(text=self._t("connected"), foreground="#070")
        else:
            self.connect_button.config(text=self._t("connect"), command=self.connect)
            self.state_label.config(text=self._t("disconnected"), foreground="#a00")

    def log(self, message: str, source: str = "app"):
        """Meldung im Log vormerken; source: 'app' oder 'radio'."""
        self._pending_log.append((source, message))

    def _log_line_is_raw(self, message: str) -> bool:
        """True, wenn eine Radio-Zeile keinem erwarteten Format entspricht.

        Erwartete Formate (Firmware Remote.cpp): leere Zeilen als
        Bestaetigung, 'Error: ...'-Meldungen, '#..'-Speicherzeilen und
        CSV-Statuszeilen. Alles andere (z. B. Hex-Daten) wird als
        unformatierte Rohzeile farbig hervorgehoben.
        """
        text = message.strip()
        if not text:
            return False
        if text.startswith("Error:"):
            return False
        if protocol.parse_status(text) is not None:
            return False
        if protocol.parse_memory_line(text) is not None:
            return False
        return True

    def _poll_main_thread(self):
        for source, message in self._pending_log:
            self._log_insert(source, message)
        self._pending_log = []

        status = getattr(self, "_pending_status", None)
        if status is not None:
            self._pending_status = None
            self._last_status = status
            self._current_mode = status.mode
            self._current_volume = status.volume
            # Regler nur aktualisieren, wenn der Nutzer ihn nicht gerade
            # zieht und die Rauschsperre nicht gerade stummschaltet
            if not self._volume_dragging and not self._squelch_muted:
                self.volume_var.set(status.volume)
            hz = status.display_frequency_hz()
            if status.mode.upper() == "FM":
                self.freq_var.set(f"{protocol.fmt_num(hz / 1e6, 2)} MHz")
            else:
                self.freq_var.set(f"{protocol.fmt_num(hz / 1e3, 3)} kHz")
            self.band_var.set(status.band)
            self.mode_var.set(status.mode)
            self.rssi_var.set(f"{status.rssi} dBµV")
            self.smeter_var.set(
                protocol.s_meter(status.rssi, status.mode.upper() == "FM"))
            self.snr_var.set(f"{status.snr} dB")
            self.batt_var.set(f"{protocol.fmt_num(status.voltage, 2)} V")
            self._set_row_values(status)
            self._squelch_eval(status)
            self._smeter_redraw()
            # Frequenzmarke im Spektrum nachziehen, wenn die Frequenz
            # geaendert wurde (ausserhalb des Sweeps, der selbst zeichnet).
            # Ohne Spektrumdaten werden Achsen und Marke aus dem aktuellen
            # Band gezeichnet (initial und nach Band-/Frequenzwechsel).
            if not self._sweep_active:
                redraw = False
                if self._sweep_data:
                    redraw = hz != self._sweep_marker_hz
                else:
                    redraw = (hz != self._sweep_marker_hz
                              or status.band != self._sweep_axes_band)
                    self._sweep_axes_band = status.band
                if redraw:
                    self._sweep_marker_hz = hz
                    self._sweep_draw()

        shot = getattr(self, "_pending_screenshot", None)
        if shot is not None:
            self._pending_screenshot = None
            self._screenshot = shot
            self._show_screenshot(shot)

        progress = getattr(self, "_pending_screenshot_progress", None)
        if progress is not None:
            self._pending_screenshot_progress = None
            received, total = progress
            if total > 0:
                percent = min(99, received * 100 // total)
                self.shot_label.config(text=self._t("receiving", percent=percent))

        self.root.after(50, self._poll_main_thread)

    def _show_screenshot(self, shot: protocol.Screenshot):
        ppm = shot.to_ppm()
        self._shot_photo = tk.PhotoImage(data=ppm, format="PPM")
        self.shot_label.config(image=self._shot_photo, text="")

    _pending_log: list[str] = []
    _pending_status: protocol.ReceiverStatus | None = None
    _pending_screenshot: protocol.Screenshot | None = None
    _pending_screenshot_progress: tuple[int, int] | None = None
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
    _sweep_axes_band: str = ""
    _sweep_peak: dict[int, int] = {}
    _sweep_ema: dict[int, int] = {}
    _sweep_prev: dict[int, int] = {}
    _sweep_points_pending: bool = False
    _sweep_points_band: str = ""


def main():
    protocol.apply_system_locale()
    root = tk.Tk()
    RemoteApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
