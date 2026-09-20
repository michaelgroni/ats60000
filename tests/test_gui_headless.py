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


if __name__ == "__main__":
    unittest.main()
