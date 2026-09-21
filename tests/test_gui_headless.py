"""Headless-Smoke-Test der GUI-Konstruktion mit Tkinter-Mock.

Prüft insbesondere den Geometrie-Manager-Fehler aus dem Feldreport
("cannot use geometry manager pack/grid" im selben Container).
"""

import sys
import types
import unittest


class FakeWidget:
    def __init__(self, parent, *args, **kwargs):
        self.parent = parent
        self.children = []
        self.kwargs = dict(kwargs)
        self.pack_kwargs = None
        self.config_kwargs = dict(kwargs)
        if hasattr(parent, "children"):
            parent.children.append(self)

    def pack(self, **kw):
        self._register_manager("pack")

    def grid(self, **kw):
        self._register_manager("grid")

    def set(self, *a, **kw):
        pass

    def _register_manager(self, manager):
        parent = self.parent
        while parent is not None and not hasattr(parent, "_managers"):
            parent = getattr(parent, "parent", None)
        if parent is not None:
            if manager not in parent._managers:
                parent._managers.add(manager)
            else:
                return
            if len(parent._managers) > 1:
                raise RuntimeError(
                    f'cannot use geometry manager "{manager}" inside '
                    f'"{parent._name}": '
                    f'"{list(parent._managers)[0]}" is already managing '
                    "its content windows")

    def config(self, **kw):
        if not hasattr(self, "config_kwargs"):
            self.config_kwargs = {}
        self.config_kwargs.update(kw)

    def configure(self, **kw):
        self.config(**kw)

    def pack(self, **kw):
        self.pack_kwargs = dict(kw)
        self._register_manager("pack")

    def pack_forget(self):
        self.pack_kwargs = None

    def columnconfigure(self, *a, **kw):
        pass

    def rowconfigure(self, *a, **kw):
        pass

    def bind(self, *a, **kw):
        pass

    def heading(self, *a, **kw):
        pass

    def column(self, *a, **kw):
        pass


class FakeFrame(FakeWidget):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self._managers = set()
        self._name = kwargs.get("text", "frame")
        self.children = []

    def title(self, *a, **kw):
        pass

    def update_idletasks(self):
        pass

    def minsize(self, *a, **kw):
        pass

    def geometry(self, *a, **kw):
        pass

    def bind_all(self, *a, **kw):
        pass

    def unbind_all(self, *a, **kw):
        pass


def make_tkinter_mock():
    mod = types.ModuleType("tkinter")
    mod.Tk = lambda: FakeFrame(None)
    mod.Frame = FakeFrame
    mod.LabelFrame = FakeFrame
    mod.X = "x"
    mod.Y = "y"
    mod.BOTH = "both"
    class FakeTkVar:
        def __init__(self, *a, **kw):
            self.value = a[0] if a else kw.get("value")

        def set(self, value):
            self.value = value

        def get(self):
            return self.value

    tk_var = FakeTkVar
    mod.StringVar = tk_var
    mod.IntVar = tk_var
    mod.BooleanVar = tk_var
    mod.Text = FakeWidget
    mod.END = "end"
    mod.VERTICAL = "vertical"
    mod.LEFT = "left"
    mod.RIGHT = "right"
    class FakeMenu(FakeWidget):
        def __init__(self, parent, *args, **kwargs):
            super().__init__(parent, *args, **kwargs)
            self.entries = []
            self.cascades = []
            self.config_calls = []

        def add_command(self, **kw):
            self.entries.append(kw)

        def add_radiobutton(self, **kw):
            self.entries.append(kw)

        def add_cascade(self, **kw):
            self.cascades.append(kw)

        def entryconfigure(self, index, **kw):
            self.config_calls.append((index, kw))

    mod.Menu = FakeMenu
    mod.Canvas = FakeScrollCanvas
    mod.Radiobutton = FakeWidget
    mod.NORMAL = "normal"
    mod.DISABLED = "disabled"
    mod.PhotoImage = lambda **kw: None

    ttk = types.ModuleType("tkinter.ttk")
    class FakeTreeview(FakeWidget):
        def heading(self, col, text=None, **kw):
            pass

        def column(self, *a, **kw):
            pass

        def tag_configure(self, *a, **kw):
            pass

        def insert(self, parent, end, values=(), tags=()):
            pass

        def get_children(self):
            return []

        def delete(self, *a, **kw):
            pass

        def see(self, *a, **kw):
            pass

        def yview(self, *a, **kw):
            pass

        def configure(self, *a, **kw):
            pass

    setattr(ttk, "Frame", FakeFrame)
    setattr(ttk, "LabelFrame", FakeFrame)
    setattr(ttk, "Treeview", FakeTreeview)
    for name in ["Label", "Button", "Entry",
                 "Combobox", "Spinbox", "Scale", "Radiobutton",
                 "Scrollbar", "Checkbutton"]:
        setattr(ttk, name, FakeWidget)
    mod.ttk = ttk

    sub = types.ModuleType("tkinter.filedialog")
    sub.asksaveasfilename = lambda **kw: ""
    mod.filedialog = sub

    mb = types.ModuleType("tkinter.messagebox")
    mb.showerror = lambda *a, **kw: None
    mod.messagebox = mb

    sys.modules["tkinter"] = mod
    sys.modules["tkinter.ttk"] = ttk
    sys.modules["tkinter.filedialog"] = sub
    sys.modules["tkinter.messagebox"] = mb
    web = types.ModuleType("webbrowser")
    web.open = lambda url: None
    sys.modules["webbrowser"] = web
    return mod


class GuiSmokeTest(unittest.TestCase):
    def test_build_ui_without_manager_conflict(self):
        make_tkinter_mock()
        # Import erst nach dem Mock-Einsetzen
        for name in list(sys.modules):
            if name.startswith("ats_mini_remote.app"):
                del sys.modules[name]
        from ats_mini_remote import app as app_mod

        root = FakeFrame(None)
        application = object.__new__(app_mod.RemoteApp)
        application.root = root
        # Nur GUI-Aufbau ohne echten Client
        application.client = None
        application._row_value_vars = {}
        application._pending_memory = []
        application._screenshot = None
        application._lang_var = FakeVar()
        application._i18n_labels = []
        application._squelch_sens = 5
        application._build_ui()
        # Kein Exception -> Aufbau ok
        self.assertTrue(True)

    def test_menus_and_log_toggle(self):
        make_tkinter_mock()
        for name in list(sys.modules):
            if name.startswith("ats_mini_remote.app"):
                del sys.modules[name]
        from ats_mini_remote import app as app_mod

        root = FakeFrame(None)
        application = object.__new__(app_mod.RemoteApp)
        application.root = root
        application.client = None
        application._row_value_vars = {}
        application._pending_memory = []
        application._screenshot = None
        application._lang_var = FakeVar()
        application._i18n_labels = []
        application._squelch_sens = 5
        application._build_ui()

        # Menueleiste: Ansicht und Hilfe mit den besprochenen Eintraegen
        menubar = root.config_kwargs.get("menu")
        self.assertIsNotNone(menubar)
        labels = [c["label"] for c in menubar.cascades]
        self.assertIn("Ansicht", labels)
        self.assertIn("Hilfe", labels)
        view = [c["menu"] for c in menubar.cascades
                if c["label"] == "Ansicht"][0]
        help_menu = [c["menu"] for c in menubar.cascades
                     if c["label"] == "Hilfe"][0]
        self.assertEqual([e["label"] for e in view.entries],
                         ["Log anzeigen"])
        self.assertEqual([e["label"] for e in help_menu.entries],
                         ["Website", "Über"])

        # Log ist bei Programmstart ausgeblendet
        self.assertFalse(application._log_visible)
        self.assertIsNone(application.logbox.pack_kwargs)
        # Ein-/Ausblenden schaltet Sichtbarkeit und Menueetikett
        view.entries[0]["command"]()
        self.assertTrue(application._log_visible)
        self.assertIsNotNone(application.logbox.pack_kwargs)
        self.assertEqual(view.config_calls[-1][1]["label"],
                         "Log ausblenden")
        view.entries[0]["command"]()
        self.assertFalse(application._log_visible)
        self.assertIsNone(application.logbox.pack_kwargs)

        # Ueber-Dialog enthaelt die Version, Website oeffnet die Projektseite
        from ats_mini_remote import app as app2
        shown = []
        app2.messagebox.showinfo = lambda title, text: shown.append((title, text))
        help_menu.entries[1]["command"]()
        self.assertEqual(shown[0][0], "Über")
        self.assertIn("Version", shown[0][1])
        self.assertIn(app2.PROJECT_URL, shown[0][1])

    def test_log_splits_status_line(self):
        """Statuszeilen des Radios werden in Spalten zerlegt."""
        from ats_mini_remote import protocol
        make_tkinter_mock()
        from ats_mini_remote import app as app_mod
        application = object.__new__(app_mod.RemoteApp)
        application._t = lambda key, **kw: {"col_message": "Nachricht"}.get(key, key)
        application._log_line_is_raw = lambda msg: False
        application.log_tree = FakeLogTree()
        line = "1,3600,0,0,80M,LSB,1k,2k,0,20,64,30,10,4.10,7"
        application._log_insert("radio", line)
        row = application.log_tree.rows[0]
        # freq, band, mode, vol, rssi, snr, spannung sind gefuellt
        self.assertIn("3600", row[0][3])
        self.assertEqual(row[0][4], "80M")
        self.assertEqual(row[0][5], "LSB")
        self.assertEqual(row[0][9], "20")
        self.assertIn("64", row[0][10])
        self.assertIn("30", row[0][11])
        self.assertIn("4", row[0][12])
        # Nachricht-Spalte bleibt leer
        self.assertEqual(row[0][13], "")
        # Kein Status: Nachricht erscheint unzerlegt in der Msg-Spalte
        application._log_insert("radio", "Error: bad format")
        row = application.log_tree.rows[1]
        self.assertEqual(row[0][13], "Error: bad format")

    def test_language_switch_updates_static_texts(self):
        """Sprachwechsel stellt alle registrierten Texte um."""
        make_tkinter_mock()
        from ats_mini_remote import app as app_mod
        from ats_mini_remote import i18n
        root = FakeFrame(None)
        application = object.__new__(app_mod.RemoteApp)
        application.root = root
        application.client = None
        application._row_value_vars = {}
        application._pending_memory = []
        application._screenshot = None
        application._lang_var = FakeVar()
        application._i18n_labels = []
        application._squelch_sens = 5
        application._build_ui()
        application.client = type("C", (), {"is_connected": lambda self: False})()
        application.root.title = lambda *a, **kw: None
        application.smeter_canvas = FakeCanvas()
        application.snr_canvas = FakeCanvas()
        application._last_status = None
        try:
            application.switch_language("English")
            texts = {w.config_kwargs.get("text")
                     for w, _key in application._i18n_labels}
            for expected in ("Memory slots", "Spectrum", "Display",
                             "Log", "Host:", "Slot:", "Points:"):
                self.assertIn(expected, texts, f"missing: {expected}")
            application.switch_language("Deutsch")
            texts = {w.config_kwargs.get("text")
                     for w, _key in application._i18n_labels}
            self.assertIn("Speicherplätze", texts)
        finally:
            from ats_mini_remote import i18n as _i18n
            _i18n.set_language("Deutsch")

    def test_app_version_format(self):
        make_tkinter_mock()
        from ats_mini_remote import app as app_mod
        version = app_mod.app_version()
        self.assertTrue(version)
        # Release '0.1' oder Dev-Kennung '0.1-<n>-g<hash>' oder Fallback
        self.assertRegex(version, r"^\d+\.\d+(-\d+-g[0-9a-f]+)?$")


class FakeScrollCanvas(FakeWidget):
    """Scroll- und Zeichen-Canvas: Aufrufe protokollieren statt
    darstellen; Scroll-Geometrie bleibt ohne Funktion."""

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.lines = []
        self.rectangles = []
        self.polygons = []
        self.ovals = []
        self.texts = []
        self.deleted = 0
        self.width = 300
        self.height = 140

    def create_window(self, *a, **kw):
        return 1

    def itemconfigure(self, *a, **kw):
        pass

    def bbox(self, *a, **kw):
        return (0, 0, 700, 500)

    def yview(self, *a, **kw):
        pass

    def yview_scroll(self, *a, **kw):
        pass

    def configure(self, **kw):
        self.config(**kw)

    def delete(self, *a, **kw):
        self.deleted += 1

    def winfo_width(self):
        return self.width

    def cget(self, key):
        return str(self.height) if key == "height" else ""

    def create_rectangle(self, *a, **kw):
        self.rectangles.append((a, kw))

    def create_polygon(self, *a, **kw):
        self.polygons.append((a, kw))

    def create_oval(self, *a, **kw):
        self.ovals.append((a, kw))

    def create_line(self, *a, **kw):
        self.lines.append((a, kw))

    def create_text(self, *a, **kw):
        self.texts.append((a, kw))


class FakeCanvas:
    """Zeichenoperationen mitzaehlen statt darstellen."""

    def __init__(self):
        self.lines = []
        self.rectangles = []
        self.polygons = []
        self.ovals = []
        self.texts = []
        self.deleted = 0
        self.width = 300
        self.height = 140

    def delete(self, *a, **kw):
        self.deleted += 1

    def winfo_width(self):
        return self.width

    def cget(self, key):
        return str(self.height) if key == "height" else ""

    def create_rectangle(self, *a, **kw):
        self.rectangles.append((a, kw))

    def create_polygon(self, *a, **kw):
        self.polygons.append((a, kw))

    def create_oval(self, *a, **kw):
        self.ovals.append((a, kw))

    def create_line(self, *a, **kw):
        self.lines.append((a, kw))

    def create_text(self, *a, **kw):
        self.texts.append((a, kw))


class FakeVar:
    def __init__(self, *a, **kw):
        self.value = None

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class FakeLogTree:
    """Stub fuer die Logtabelle (heading/column/tag_configure/insert/...)."""

    def __init__(self):
        self.rows = []
        self.headings = {}

    def heading(self, col, text=None):
        if text is not None:
            self.headings[col] = text
        return self.headings.get(col)

    def column(self, *a, **kw):
        pass

    def tag_configure(self, *a, **kw):
        pass

    def insert(self, parent, end, values=(), tags=()):
        self.rows.append((values, tags))
        return len(self.rows) - 1

    def get_children(self):
        return list(range(len(self.rows)))

    def delete(self, *a, **kw):
        pass

    def see(self, *a, **kw):
        pass

    def yview(self, *a, **kw):
        pass

    def configure(self, *a, **kw):
        pass


class SpectrumMarkerTest(unittest.TestCase):
    """Frequenzmarke muss Frequenzaenderungen nachziehen."""

    def _make_app(self):
        make_tkinter_mock()
        for name in list(sys.modules):
            if name.startswith("ats_mini_remote.app"):
                del sys.modules[name]
        from ats_mini_remote import app as app_mod
        application = object.__new__(app_mod.RemoteApp)
        application.root = FakeFrame(None)
        application.client = None
        application._row_value_vars = {}
        application._pending_memory = []
        application._screenshot = None
        application._pending_log = []
        application._pending_status = None
        application._pending_screenshot = None
        application._volume_dragging = False
        application._squelch_enabled = False
        application._squelch_muted = False
        application._squelch_sens = 5
        application._squelch_sens_state = "disabled"
        application.squelch_sens_scale = FakeWidget(None)
        application.squelch_check = FakeWidget(None)
        application._sweep_active = False
        application._sweep_points_pending = False
        application._sweep_points_band = "80M"
        application._current_mode = "LSB"
        application._current_volume = -1
        application._sweep_timeout_id = None
        application._sweep_peak = {}
        application._sweep_ema = {}
        application._sweep_prev = {}
        application._last_status = None
        application._memory_refresh_id = None
        application._lang_var = FakeVar()
        application._i18n_labels = []
        application._sweep_data = [(3_500_000, 10), (3_600_000, 20)]
        application._sweep_freqs = [3_500_000, 3_600_000]
        application._sweep_freq_range = (3_500_000, 4_000_000)
        application._sweep_marker_hz = None
        application._sweep_restore_freq = None
        application._sweep_mode = "LSB"
        application.sweep_canvas = FakeCanvas()
        application.smeter_canvas = FakeCanvas()
        application.smeter_metric_var = FakeVar()
        application.smeter_metric_var.value = "rssi"
        application.freq_display = FakeCanvas()
        application.batt_canvas = FakeCanvas()
        application.snr_canvas = FakeCanvas()
        application.volume_var = FakeVar()
        application.sweep_points_var = FakeVar()
        application.sweep_progress_var = FakeVar()
        application.log_tree = FakeLogTree()
        application.log = lambda msg, source="app": None
        application.root.after = lambda delay, fn=None: None
        application.root.after_cancel = lambda tid: None
        return application

    def _status(self, khz):
        from ats_mini_remote import protocol
        return protocol.ReceiverStatus(frequency=khz, mode="LSB", band="80M")

    @staticmethod
    def _markers(canvas):
        """Nur die orangen Frequenzmarken zaehlen (nicht Achsen/Ticks)."""
        return [ln for ln in canvas.lines if ln[1].get("fill") == "#f80"]

    def test_marker_follows_frequency_changes(self):
        app = self._make_app()
        # erster Status: Marke wird gezeichnet
        app._pending_status = self._status(3_600)
        app._poll_main_thread()
        self.assertEqual(len(self._markers(app.sweep_canvas)), 1)
        self.assertEqual(app._sweep_marker_hz, 3_600_000)
        # dieselbe Frequenz: kein Neuzeichnen
        app._pending_status = self._status(3_600)
        app._poll_main_thread()
        self.assertEqual(len(self._markers(app.sweep_canvas)), 1)
        # neue Frequenz: Marke wandert mit
        app._pending_status = self._status(3_700)
        app._poll_main_thread()
        self.assertEqual(len(self._markers(app.sweep_canvas)), 2)
        self.assertEqual(app._sweep_marker_hz, 3_700_000)

    def test_axes_are_labeled(self):
        app = self._make_app()
        app._pending_status = self._status(3_600)
        app._poll_main_thread()
        texts = [t[1].get("text") for t in app.sweep_canvas.texts]
        # dBuV-Skala links und Einheit der Frequenzachse
        self.assertIn("dBµV", texts)
        self.assertIn("kHz", texts)   # 3.5-4 MHz Spanne -> kHz-Beschriftung
        # Achsenmaximum dynamisch: Peak 20 dBuV -> Maximum 60 (Minimum)
        for tick in ("0", "40", "60"):
            self.assertIn(tick, texts)
        self.assertNotIn("80", texts)   # ueber Maximum hinaus keine Ticks

    def test_missing_points_are_interpolated(self):
        app = self._make_app()
        # 3 Punkte geplant, mittlerer fehlt -> die Trapeze zwischen den
        # Punkten fuellen die Luecke lueckenlos (lineare Interpolation)
        app._sweep_data = [(3_500_000, 10), (3_700_000, 30)]
        app._sweep_freqs = [3_500_000, 3_600_000, 3_700_000]
        app._sweep_marker_hz = None
        app._pending_status = self._status(3_600)
        app._poll_main_thread()
        fills = [p for p in app.sweep_canvas.polygons
                 if p[1].get("fill") == "#0f0"]
        self.assertEqual(len(fills), 2)   # Trapez 3.5->3.6 und 3.6->3.7
        self.assertEqual(len(app.sweep_canvas.rectangles), 0)
        # keine Kurvenlinie mehr -- nur Achsen
        curves = [ln for ln in app.sweep_canvas.lines
                  if ln[1].get("fill") == "#0a0"]
        self.assertEqual(len(curves), 0)

    def test_frequency_axis_has_nine_ticks_and_clear_unit(self):
        app = self._make_app()
        app._sweep_data = [(3_500_000, 30), (3_700_000, 40)]
        app._sweep_freqs = [3_500_000, 3_600_000, 3_700_000]
        app._sweep_freq_range = (3_500_000, 3_700_000)
        app._pending_status = self._status(3_600)
        app._poll_main_thread()
        canvas = app.sweep_canvas
        # unterhalb der Achse gezeichnete Ticks mit Zahl (anchor n)
        freq_ticks = [t for t in canvas.texts
                      if t[1].get("anchor") == "n"]
        self.assertEqual(len(freq_ticks), 9)
        # Einheit kHz steht rechts neben dem letzten Tick
        unit = [t for t in canvas.texts if t[1].get("text") == "kHz"][0]
        last_tick_x = max(t[0][0] for t in freq_ticks)
        self.assertGreater(unit[0][0], last_tick_x)

    def test_smeter_draws_needle_and_scale(self):
        import math
        from ats_mini_remote import protocol
        app = self._make_app()
        app._last_status = protocol.ReceiverStatus(
            frequency=3_600, mode="AM", band="80M",
            rssi=64, snr=30)
        # klassisches Zeigerinstrument: helle Flaeche, rotes Band am
        # Skalenende, schwarzer Zeiger, Drehpunkt, Ticks mit Labeln
        app._smeter_redraw()
        canvas = app.smeter_canvas
        faces = [rc for rc in canvas.rectangles
                 if rc[1].get("fill") == app._SMETER_FACE]
        self.assertEqual(len(faces), 0)   # kein Rahmen/Blatt mehr
        reds = [pg for pg in canvas.polygons
                if pg[1].get("fill") == app._SMETER_RED]
        self.assertEqual(len(reds), 1)   # rotes Uebersteuerungsband
        cx, cy = canvas.winfo_width() / 2, app._SMETER_PIVOT[1]
        needles = [ln for ln in canvas.lines
                   if ln[1].get("fill") == app._SMETER_NEEDLE
                   and abs(ln[0][0] - cx) < 1 and abs(ln[0][1] - cy) < 1]
        self.assertEqual(len(needles), 1)   # genau ein Zeiger vom Drehpunkt
        self.assertEqual(len(canvas.ovals), 1)   # Drehpunkt
        texts = [t[1].get("text") for t in canvas.texts]
        self.assertIn("64 dBµV", texts)
        # Skala: RSSI-Ticks 10..120 in 10er-Schritten vorhanden
        for tick in ("10", "30", "50", "70", "90", "110",
                     "20", "60", "120"):
            self.assertIn(tick, texts)
        # Zeigerwinkel: 64/127 der Halbkreisspanne, von links ueber oben
        (x1, y1), (x2, y2) = needles[0][0][:2], needles[0][0][2:4]
        angle = math.degrees(math.atan2(cy - y2, x2 - cx))
        expected = 180 - (64 / 127) * 180
        self.assertAlmostEqual(angle, expected, delta=2)

    def test_smeter_labels_outside_scale(self):
        import math
        from ats_mini_remote import protocol
        app = self._make_app()
        app._last_status = protocol.ReceiverStatus(
            frequency=3_600, mode="AM", band="80M",
            rssi=64, snr=30)
        app._smeter_redraw()
        cx, cy = app.smeter_canvas.winfo_width() / 2, app._SMETER_PIVOT[1]
        r = app._SMETER_R
        # Tick-Labels liegen ausserhalb des Skalenradius
        for coords, kw in app.smeter_canvas.texts:
            if kw.get("text") in ("10", "30", "50", "70", "90",
                                  "110", "20", "40", "60", "80",
                                  "100", "120"):
                d = math.hypot(coords[0] - cx, coords[1] - cy)
                self.assertGreaterEqual(d, r + 3)

    def test_smeter_needle_follows_metric(self):
        import math
        from ats_mini_remote import protocol
        app = self._make_app()
        app._last_status = protocol.ReceiverStatus(
            frequency=3_600, mode="AM", band="80M",
            rssi=64, snr=30)
        # S-Wert-Metrik: Skala S1..S9 plus Bereich +10..+60 ueber S9
        app.smeter_metric_var.value = "s"
        app._smeter_redraw()
        canvas = app.smeter_canvas
        texts = [t[1].get("text") for t in canvas.texts]
        self.assertIn("S9+20", texts)
        self.assertIn("9", texts)        # Tick-Label ohne S-Praefix
        self.assertNotIn("S9", texts)    # S9 nur noch an der Wertziffer
        # Labels nur auf jedem zweiten Haupttick
        for tick in ("1", "3", "5", "7", "9", "+20", "+40", "+60"):
            self.assertIn(tick, texts)
        for tick in ("2", "4", "6", "8", "+10", "+30", "+50"):
            self.assertNotIn(tick, texts)
        # Zeigerposition S9+20 = Position 11 von 15 muss rechts vom
        # S9-Tick (Position 9 von 15) liegen
        cx, cy = canvas.winfo_width() / 2, app._SMETER_PIVOT[1]
        r = app._SMETER_R
        s9_text = [t for t in canvas.texts if t[1].get("text") == "9"][0]
        s9_angle = math.degrees(
            math.atan2(cy - s9_text[0][1], s9_text[0][0] - cx))
        needles = [ln for ln in canvas.lines
                   if ln[1].get("fill") == app._SMETER_NEEDLE
                   and abs(ln[0][0] - cx) < 1 and abs(ln[0][1] - cy) < 1]
        (x1, y1), (x2, y2) = needles[0][0][:2], needles[0][0][2:4]
        needle_angle = math.degrees(
            math.atan2(cy - y2, x2 - cx))
        # Zeiger uebernimmt dieselbe Winkelskala wie die Ticks
        needle_pos = (180 - needle_angle) / 180
        self.assertGreater(needle_pos, 8 / 14)   # rechts vom S9-Tick
        self.assertLess(needle_pos, 1.0)
        self.assertAlmostEqual(needle_pos, 10 / 14, delta=0.02)
        # SNR-Instrument: eigene Anzeige mit Ticks 0..60, Text in dB
        app._snr_redraw()
        texts = [t[1].get("text") for t in app.snr_canvas.texts]
        self.assertIn("SNR 30 dB", texts)
        for tick in ("0", "10", "20", "30", "40", "50", "60"):
            self.assertIn(tick, texts)

    def test_squelch_mutes_and_opens(self):
        from ats_mini_remote import protocol
        app = self._make_app()
        app._squelch_enabled = True
        app._volume_target = 30
        app._current_volume = 30
        sent = []
        app.send = lambda cmd: sent.append(cmd)
        app.client = type("C", (), {"is_connected": lambda self: True})()
        # Rauschen: RSSI und SNR unter den Schwellen -> stumm
        app._squelch_eval(self._status_rssi(10, 5))
        self.assertTrue(app._squelch_muted)
        self.assertEqual(sent, [b"v" * 30])
        # Hysterese: knapp ueber den Schliessschwellen bleibt stumm
        app._squelch_eval(self._status_rssi(13, 8))
        self.assertTrue(app._squelch_muted)
        self.assertEqual(sent, [b"v" * 30])
        # Oeffnen: ueber beide Oeffnungsschwellen -> Lautstaerke zurueck
        app._squelch_eval(self._status_rssi(20, 15))
        self.assertFalse(app._squelch_muted)
        self.assertEqual(sent, [b"v" * 30, b"V" * 30])

    def test_squelch_ignores_ssb(self):
        from ats_mini_remote import protocol
        app = self._make_app()
        app._squelch_enabled = True
        app._volume_target = 30
        app._current_volume = 30
        sent = []
        app.send = lambda cmd: sent.append(cmd)
        # LSB: Sperre bleibt wirkungslos, nichts wird gesendet
        app._squelch_eval(protocol.ReceiverStatus(
            frequency=3_600, mode="LSB", band="80M", rssi=0, snr=0))
        self.assertFalse(app._squelch_muted)
        self.assertEqual(sent, [])

    def test_squelch_disable_unmutes(self):
        from ats_mini_remote import protocol
        app = self._make_app()
        app._squelch_enabled = True
        app._volume_target = 30
        app._current_volume = 30
        sent = []
        app.send = lambda cmd: sent.append(cmd)
        app.client = type("C", (), {"is_connected": lambda self: True})()
        app._squelch_eval(self._status_rssi(10, 5))
        self.assertTrue(app._squelch_muted)
        # Sperre ausschalten: Stummschaltung wird aufgehoben
        app._squelch_eval(self._status_rssi(10, 5))
        app._squelch_enabled = False
        app._squelch_eval(self._status_rssi(10, 5))
        self.assertFalse(app._squelch_muted)
        self.assertEqual(sent, [b"v" * 30, b"V" * 30])

    def _status_rssi(self, rssi, snr):
        from ats_mini_remote import protocol
        return protocol.ReceiverStatus(
            frequency=3_600, mode="AM", band="80M",
            rssi=rssi, snr=snr, volume=30)

    def test_freq_display_draws_segments(self):
        app = self._make_app()
        from ats_mini_remote import protocol
        app._freq_redraw(protocol.ReceiverStatus(
            frequency=3_600, mode="AM", band="80M"))
        # nur die leuchtenden Segmente, alle in LED-Farbe
        self.assertGreater(len(app.freq_display.polygons), 7)
        fills = {p[1].get("fill") for p in app.freq_display.polygons}
        self.assertEqual(fills, {app._7SEG_ON})
        texts = [t[1].get("text") for t in app.freq_display.texts]
        self.assertIn("kHz", texts)

    def test_freq_display_long_frequency_fits_into_canvas(self):
        app = self._make_app()
        from ats_mini_remote import protocol
        # 30000,000 kHz im KW-Band: die laengste moegliche Anzeige muss
        # mit der festen Segmentgroesse in die 240-px-Canvas passen
        app.freq_display.width = 240
        app._freq_redraw(protocol.ReceiverStatus(
            frequency=30_000, mode="AM", band="SW"))
        self.assertGreater(len(app.freq_display.polygons), 7)
        canvas_w = app.freq_display.width
        for args, _kw in app.freq_display.polygons:
            xs = [pt[0] for pt in args]
            self.assertLessEqual(max(xs), canvas_w,
                                 "Siebensegmentanzeige ragt ueber den Rand")
        text_args = app.freq_display.texts[0][0]
        self.assertLessEqual(text_args[0], canvas_w)
        self.assertIn("kHz", [t[1].get("text") for t in app.freq_display.texts])

    def test_freq_display_uses_fixed_segment_size(self):
        app = self._make_app()
        from ats_mini_remote import protocol
        # kurze und lange Anzeige verwenden dieselbe (feste) Geometrie
        app.freq_display.width = 240
        app._freq_redraw(protocol.ReceiverStatus(
            frequency=3_600, mode="AM", band="80M"))
        short_geometry = {tuple(a) for a, _kw in app.freq_display.polygons}
        app._freq_redraw(protocol.ReceiverStatus(
            frequency=30_000, mode="AM", band="SW"))
        long_geometry = {tuple(a) for a, _kw in app.freq_display.polygons}
        self.assertTrue(short_geometry & long_geometry,
                         "Segmentgeometrie weicht zwischen kurz und lang ab")

    def test_battery_display_draws_symbol_and_voltage(self):
        app = self._make_app()
        from ats_mini_remote import protocol
        app._battery_redraw(protocol.ReceiverStatus(
            frequency=3_600, mode="AM", band="80M", voltage=4.05))
        # Batteriesymbol: Gehaeuse, Nub und Fuellstand
        self.assertGreaterEqual(len(app.batt_canvas.rectangles), 3)
        texts = [t[1].get("text") for t in app.batt_canvas.texts]
        self.assertTrue(any(t.endswith("V") for t in texts))

    def test_squelch_sensitivity_shifts_threshold(self):
        app = self._make_app()
        app._squelch_enabled = True
        app._volume_target = 30
        app._current_volume = 30
        sent = []
        app.send = lambda cmd: sent.append(cmd)
        # Empfindlichkeit 10 (maximal): Oeffnungsschwelle AM sinkt auf 10
        app._squelch_sens = 10
        app._squelch_eval(self._status_rssi(12, 15))
        self.assertFalse(app._squelch_muted)   # Sperre bleibt offen
        # Empfindlichkeit 0 (minimal): Oeffnungsschwelle AM steigt auf 20
        app._squelch_sens = 0
        app._squelch_eval(self._status_rssi(12, 15))
        self.assertTrue(app._squelch_muted)     # jetzt wird gestummt

    def test_squelch_sens_callback_clamps(self):
        app = self._make_app()
        app.on_squelch_sens_changed("7.0")
        self.assertEqual(app._squelch_sens, 7)
        app.on_squelch_sens_changed("99")
        self.assertEqual(app._squelch_sens, 10)
        app.on_squelch_sens_changed("-3")
        self.assertEqual(app._squelch_sens, 0)

    def test_squelch_sens_slider_state_follows_mode(self):
        from ats_mini_remote import protocol
        app = self._make_app()
        app._volume_dragging = True   # Slider-Update im Poll abschalten
        # AM: Slider bedienbar
        app._pending_status = self._status_rssi(20, 15)
        app._poll_main_thread()
        self.assertEqual(app.squelch_sens_scale.config_kwargs.get("state"),
                         "normal")
        self.assertEqual(app._squelch_sens_state, "normal")
        # SSB: Slider und Checkbox ausgegraut
        app.squelch_sens_scale.config_kwargs.clear()
        app.squelch_check.config_kwargs.clear()
        app._pending_status = protocol.ReceiverStatus(
            frequency=3_600, mode="LSB", band="80M")
        app._poll_main_thread()
        self.assertEqual(app.squelch_sens_scale.config_kwargs.get("state"),
                         "disabled")
        self.assertEqual(app.squelch_check.config_kwargs.get("state"),
                         "disabled")
        self.assertEqual(app._squelch_sens_state, "disabled")

    def test_click_snaps_to_step(self):
        from ats_mini_remote import protocol
        app = self._make_app()
        app._sweep_data = [(3_500_000, 30), (3_700_000, 40)]
        app._sweep_freqs = [3_500_000, 3_600_000, 3_700_000]
        app._sweep_freq_range = (3_500_000, 3_700_000)
        app._last_status = protocol.ReceiverStatus(
            frequency=3_600, mode="AM", band="80M", step="5k")
        sent = []
        app.send = lambda cmd: sent.append(cmd)
        app.log = lambda msg: None
        # Klick irgendewo ins Diagramm
        class Ev:
            x = 150
        app._sweep_click(Ev())
        self.assertEqual(len(sent), 1)
        # Frequenz im Befehl muss durch 5 kHz teilbar sein
        cmd = sent[0].decode("latin1")
        hz = int(cmd[1:]) * 1000
        self.assertEqual(hz % 5000, 0, cmd)

    def test_incremental_draw_during_sweep(self):
        app = self._make_app()
        # 3 Punkte geplant, Reihenfolge wie beim Sweep von links nach rechts
        app._sweep_freqs = [3_500_000, 3_600_000, 3_700_000]
        app._sweep_data = []
        app._sweep_active = True
        canvas = app.sweep_canvas
        fills = lambda: [p for p in canvas.polygons
                         if p[1].get("fill") == "#0f0"]
        # erster Messpunkt (Randpunkt 3.5 MHz verpasst): Flaeche vom
        # linken Rand bis zum Messpunkt, kein Vollredraw
        app._sweep_data.append((3_600_000, 10))
        app._sweep_draw_incr(3_600_000)
        self.assertEqual(canvas.deleted, 0)
        self.assertEqual(len(fills()), 1)
        # dritter Punkt gemessen: das Trapez dazwischen deckt die
        # Luecke sofort ab -- Interpolation als Flaeche
        app._sweep_data.append((3_700_000, 30))
        app._sweep_draw_incr(3_700_000)
        self.assertEqual(canvas.deleted, 0)   # kein delete("all") pro Punkt
        self.assertEqual(len(fills()), 2)

    def test_axis_max_dynamic(self):
        app = self._make_app()
        # Maximum = groesster Wert, auf Vielfache von 10 aufgerundet,
        # aber nie kleiner als 60
        app._sweep_data = [(3_500_000, 20)]
        self.assertEqual(app._sweep_scale_max(), 60)   # Minimum
        app._sweep_data = [(3_500_000, 60)]
        self.assertEqual(app._sweep_scale_max(), 60)   # exakt 60 bleibt 60
        app._sweep_data = [(3_500_000, 61)]
        self.assertEqual(app._sweep_scale_max(), 70)
        app._sweep_data = [(3_500_000, 10), (3_600_000, 73)]
        self.assertEqual(app._sweep_scale_max(), 80)

    def test_axis_grows_during_sweep(self):
        app = self._make_app()
        app._sweep_freqs = [3_500_000, 3_600_000]
        app._sweep_data = []
        app._sweep_active = True
        canvas = app.sweep_canvas
        # kleiner Wert: kein Rescale
        app._sweep_data.append((3_500_000, 40))
        app._sweep_draw_incr(3_500_000)
        self.assertEqual(canvas.deleted, 0)
        self.assertEqual(app._sweep_axis_max, 60)
        # Wert ueber dem Achsenmaximum: kompletter Redraw mit neuer Skala
        app._sweep_data.append((3_600_000, 75))
        app._sweep_draw_incr(3_600_000)
        self.assertEqual(canvas.deleted, 1)
        self.assertEqual(app._sweep_axis_max, 80)
        texts = [t[1].get("text") for t in canvas.texts]
        self.assertIn("80", texts)   # neue Achse bis 80

    def test_peak_hold_follows_ema_and_previous(self):
        app = self._make_app()
        # pro Frequenz: EMA ohne Historie (alter/neuer Stand je halb),
        # gemerkt wird max(vorheriger Messwert, EMA)
        app._sweep_update_peak(3_500_000, 20)
        self.assertEqual(app._sweep_ema[3_500_000], 10)
        self.assertEqual(app._sweep_peak[3_500_000], 10)
        app._sweep_update_peak(3_500_000, 60)
        # EMA = (10+60)/2 = 35, Peak = max(20, 35) = 35
        self.assertEqual(app._sweep_ema[3_500_000], 35)
        self.assertEqual(app._sweep_peak[3_500_000], 35)
        # Rueckblick in der Zeit: sinkt der Wert, haelt der Peak den
        # frueheren Stand fest und klingt nur langsam ab
        app._sweep_update_peak(3_500_000, 5)
        self.assertEqual(app._sweep_ema[3_500_000], 20)
        self.assertEqual(app._sweep_peak[3_500_000], 60)

    def test_peak_hold_is_per_frequency(self):
        app = self._make_app()
        # Der Peak einer Frequenz darf nicht in Nachbarkanäle wandern
        # (fruehere Version verschob Werte nach rechts)
        app._sweep_update_peak(3_500_000, 80)
        app._sweep_update_peak(3_600_000, 10)
        self.assertEqual(app._sweep_peak[3_500_000], 40)
        self.assertEqual(app._sweep_peak[3_600_000], 5)
        self.assertNotIn(80, app._sweep_peak.values())

    def test_peak_drawn_as_pale_polygon(self):
        app = self._make_app()
        # Peak-Hold-Flaeche: blass Gruen (#060) unter der Hauptflaeche,
        # nur sichtbar, wo fruehere Werte groesser waren
        app._sweep_data = [(3_500_000, 40), (3_600_000, 20)]
        app._sweep_freqs = [3_500_000, 3_600_000]
        app._sweep_peak = {3_500_000: 40, 3_600_000: 30}
        app._pending_status = self._status(3_600)
        app._poll_main_thread()
        pale = [p for p in app.sweep_canvas.polygons
                if p[1].get("fill") == "#060"]
        main = [p for p in app.sweep_canvas.polygons
                if p[1].get("fill") == "#0f0"]
        self.assertEqual(len(pale), 1)   # ein Peak-Trapez
        self.assertEqual(len(main), 1)   # ein Haupt-Trapez
        # Peak-Trapez liegt im Voll-Draw unter dem Haupt-Trapez
        self.assertEqual(len(app.sweep_canvas.polygons), 2)

    def test_peak_drawn_incrementally(self):
        app = self._make_app()
        app._sweep_freqs = [3_500_000, 3_600_000, 3_700_000]
        app._sweep_data = []
        app._sweep_active = True
        canvas = app.sweep_canvas
        # erster Messpunkt (3.5 MHz verpasst): Peak- und Hauptflaeche
        # vom linken Rand bis zum Messpunkt
        app._sweep_data.append((3_600_000, 40))
        app._sweep_peak = {3_600_000: 40}
        app._sweep_draw_incr(3_600_000)
        pale = [p for p in canvas.polygons
                if p[1].get("fill") == "#060"]
        main = [p for p in canvas.polygons
                if p[1].get("fill") == "#0f0"]
        self.assertEqual(len(pale), 1)
        self.assertEqual(len(main), 1)

    def test_axis_unit_is_visible(self):
        app = self._make_app()
        app._sweep_data = [(3_500_000, 30), (3_700_000, 40)]
        app._sweep_freqs = [3_500_000, 3_600_000, 3_700_000]
        app._sweep_freq_range = (3_500_000, 3_700_000)
        app._pending_status = self._status(3_600)
        app._poll_main_thread()
    def test_smeter_canvas_bg_and_text_inside(self):
        make_tkinter_mock()
        for name in list(sys.modules):
            if name.startswith("ats_mini_remote.app"):
                del sys.modules[name]
        from ats_mini_remote import app as app_mod
        from ats_mini_remote import protocol
        root = FakeFrame(None)
        application = object.__new__(app_mod.RemoteApp)
        application.root = root
        application.client = None
        application._row_value_vars = {}
        application._pending_memory = []
        application._screenshot = None
        application._lang_var = FakeVar()
        application._i18n_labels = []
        application._squelch_sens = 5
        application._build_ui()
        # Canvas-Hintergrund ist ab Programmstart die Zifferblattfarbe
        self.assertEqual(application.smeter_canvas.kwargs.get("bg"),
                         app_mod.RemoteApp._SMETER_FACE)
        # Wertziffer liegt vollstaendig im Canvas (nicht abgeschnitten)
        application._last_status = protocol.ReceiverStatus(
            frequency=3_600, mode="AM", band="80M", rssi=64, snr=30)
        application.smeter_metric_var = FakeVar()
        application.smeter_metric_var.value = "rssi"
        application.smeter_canvas = FakeCanvas()
        application._smeter_redraw()
        h = application._SMETER_H
        for coords, kw in application.smeter_canvas.texts:
            if kw.get("text") == "64 dBµV":
                self.assertLessEqual(coords[1] + 6, h)

    def test_smeter_axis_labels_inside_canvas(self):
        app = self._make_app()
        app._sweep_data = [(3_500_000, 30), (3_700_000, 40)]
        app._sweep_freqs = [3_500_000, 3_600_000, 3_700_000]
        app._sweep_freq_range = (3_500_000, 3_700_000)
        app._pending_status = self._status(3_600)
        app._poll_main_thread()
        # Einheit "dBµV" liegt vollständig im Canvas (nicht abgeschnitten)
        unit = [t for t in app.sweep_canvas.texts
                if t[1].get("text") == "dBµV"]
        self.assertEqual(len(unit), 1)
        y = unit[0][0][1]
        self.assertGreaterEqual(y, 0)
        self.assertLess(y, 140)
        # oberster RSSI-Tick hat Abstand zum oberen Rand
        ticks = [t for t in app.sweep_canvas.texts
                 if t[1].get("text") == "60"]
        self.assertGreaterEqual(ticks[0][0][1], 0)
        # letzter Frequenz-Tick hat rechts Platz: rechte Kante + Textbreite
        # bleibt unter der Canvas-Breite (pad_r reserviert)
        last_x = max(t[0][0] for t in app.sweep_canvas.texts
                     if t[1].get("text") not in ("dBµV",))
        self.assertLessEqual(last_x, 300 - 10)

    def test_resize_redraws_spectrum(self):
        app = self._make_app()
        app._sweep_data = [(3_500_000, 30), (3_700_000, 40)]
        app._sweep_freqs = [3_500_000, 3_600_000, 3_700_000]
        app._sweep_freq_range = (3_500_000, 4_000_000)
        canvas = app.sweep_canvas
        # Resize: breiteres Canvas -> kompletter Redraw mit neuer Geometrie
        canvas.width = 600
        app._sweep_on_resize(None)
        self.assertEqual(canvas.deleted, 1)
        fills = [p for p in canvas.polygons
                 if p[1].get("fill") == "#0f0"]
        self.assertGreaterEqual(len(fills), 1)

    def test_axes_drawn_without_spectrum_data(self):
        app = self._make_app()
        app._sweep_data = None
        app._sweep_freq_range = None
        # ohne Daten: Achsen und Marke aus dem aktuellen Band (80M)
        app._pending_status = self._status(3_600)
        app._poll_main_thread()
        self.assertGreater(len(app.sweep_canvas.lines), 0)
        self.assertEqual(len(self._markers(app.sweep_canvas)), 1)
        texts = [t[1].get("text") for t in app.sweep_canvas.texts]
        self.assertIn("dBµV", texts)
        # keine Messflaechen ohne Daten
        self.assertEqual(len(app.sweep_canvas.polygons), 0)

    def test_no_draw_during_sweep(self):
        app = self._make_app()
        app._sweep_active = True
        app._pending_status = self._status(3_600)
        app._poll_main_thread()
        # waehrend des Sweeps zeichnet _sweep_on_status selbst
        self.assertEqual(self._markers(app.sweep_canvas), [])
        self.assertEqual(app._sweep_marker_hz, None)

    def test_marker_outside_range_is_not_drawn(self):
        app = self._make_app()
        app._pending_status = self._status(7_100)  # ausserhalb 3.5-4 MHz
        app._poll_main_thread()
        # kein Punkt im Diagrammbereich -> keine Marke, aber Marker merken
        self.assertEqual(self._markers(app.sweep_canvas), [])
        self.assertEqual(app._sweep_marker_hz, 7_100_000)
        # Rueckkehr in den Bereich zeichnet wieder
        app._pending_status = self._status(3_800)
        app._poll_main_thread()
        self.assertEqual(len(self._markers(app.sweep_canvas)), 1)


if __name__ == "__main__":
    unittest.main()
