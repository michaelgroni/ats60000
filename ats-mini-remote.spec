# -*- mode: python ; coding: utf-8 -*-
# PyInstaller-Spec: eine einzige fensterlose Windows-EXE bauen
#   pip install pyinstaller
#   pyinstaller ats-mini-remote.spec
# Ergebnis: dist/ATS-Mini-Remote.exe

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='ATS-Mini-Remote',
    debug=False,
    strip=False,
    upx=False,
    console=False,
)
