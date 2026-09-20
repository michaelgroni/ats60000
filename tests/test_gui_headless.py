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
        if hasattr(parent, "children"):
            parent.children.append(self)

    def pack(self, **kw):
        self._register_manager("pack")

    def grid(self, **kw):
        self._register_manager("grid")

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
        pass

    def columnconfigure(self, *a, **kw):
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


def make_tkinter_mock():
    mod = types.ModuleType("tkinter")
    mod.Tk = lambda: FakeFrame(None)
    mod.Frame = FakeFrame
    mod.LabelFrame = FakeFrame
    mod.X = "x"
    mod.Y = "y"
    mod.BOTH = "both"
    tk_var = type("Var", (), {"__init__": lambda self, *a, **kw: None})
    mod.StringVar = tk_var
    mod.IntVar = tk_var
    mod.Text = FakeWidget
    mod.END = "end"
    mod.Canvas = FakeWidget
    mod.NORMAL = "normal"
    mod.DISABLED = "disabled"
    mod.PhotoImage = lambda **kw: None

    ttk = types.ModuleType("tkinter.ttk")
    setattr(ttk, "Frame", FakeFrame)
    setattr(ttk, "LabelFrame", FakeFrame)
    for name in ["Label", "Button", "Entry",
                 "Combobox", "Spinbox", "Scale", "Treeview"]:
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
        application._build_ui()
        # Kein Exception -> Aufbau ok
        self.assertTrue(True)


class FakeCanvas:
    """Zeichenoperationen mitzaehlen statt darstellen."""

    def __init__(self):
        self.lines = []
        self.rectangles = []
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


class FakeLogText:
    """Stub fuer das Log-Textfeld (config/insert/see/index/delete)."""

    def config(self, **kw):
        pass

    def insert(self, *a, **kw):
        pass

    def see(self, *a, **kw):
        pass

    def index(self, *a, **kw):
        return "1.0"

    def delete(self, *a, **kw):
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
        application._sweep_active = False
        application._sweep_points_pending = False
        application._sweep_points_band = "80M"
        application._current_mode = "LSB"
        application._current_volume = -1
        application._sweep_timeout_id = None
        application._last_status = None
        application._sweep_data = [(3_500_000, 10), (3_600_000, 20)]
        application._sweep_freqs = [3_500_000, 3_600_000]
        application._sweep_freq_range = (3_500_000, 4_000_000)
        application._sweep_marker_hz = None
        application._sweep_restore_freq = None
        application._sweep_mode = "LSB"
        application.sweep_canvas = FakeCanvas()
        application.volume_var = FakeVar()
        application.freq_var = FakeVar()
        application.band_var = FakeVar()
        application.mode_var = FakeVar()
        application.rssi_var = FakeVar()
        application.smeter_var = FakeVar()
        application.snr_var = FakeVar()
        application.batt_var = FakeVar()
        application.sweep_points_var = FakeVar()
        application.sweep_progress_var = FakeVar()
        application.log_text = FakeLogText()
        application.log = lambda msg: None
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
        # RSSI-Ticks 0..120 (alle 20 dB) vorhanden
        for tick in ("0", "40", "120"):
            self.assertIn(tick, texts)

    def test_missing_points_are_interpolated(self):
        app = self._make_app()
        # 3 Punkte geplant, mittlerer fehlt -> wird interpoliert (dunkel)
        app._sweep_data = [(3_500_000, 10), (3_700_000, 30)]
        app._sweep_freqs = [3_500_000, 3_600_000, 3_700_000]
        app._sweep_marker_hz = None
        app._pending_status = self._status(3_600)
        app._poll_main_thread()
        greens = [r for r in app.sweep_canvas.rectangles
                  if r[1].get("fill") == "#0f0"]
        darks = [r for r in app.sweep_canvas.rectangles
                 if r[1].get("fill") == "#060"]
        self.assertEqual(len(greens), 3)   # 2 gemessen + 1 interpoliert, gleiche Farbe
        self.assertEqual(len(darks), 0)
        # keine Kurvenlinie mehr -- nur Achsen
        curves = [ln for ln in app.sweep_canvas.lines
                  if ln[1].get("fill") == "#0a0"]
        self.assertEqual(len(curves), 0)

    def test_no_draw_without_spectrum_data(self):
        app = self._make_app()
        app._sweep_data = None
        app._pending_status = self._status(3_600)
        app._poll_main_thread()
        self.assertEqual(len(app.sweep_canvas.lines), 0)

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
