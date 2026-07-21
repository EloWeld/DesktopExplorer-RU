# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for the one-file wizard.

Two things need saying out loud here. The lib/ modules are imported after a
sys.path.insert, which static analysis cannot follow, so they are listed as
hidden imports. And UnityPy resolves a good part of its class machinery at
runtime, so it is collected wholesale rather than by what the analyser sees.

    pyinstaller --clean --noconfirm build/deru.spec
"""
import os

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))

datas = [
    (os.path.join(ROOT, "data"), "data"),
    (os.path.join(ROOT, "art"), "art"),
]
binaries = []
hiddenimports = [
    # lib/, reached through sys.path at runtime
    "patcher", "steam", "state", "errors", "resources", "version",
    "unityfs", "writer", "glyphs", "prebake",
]

for package in ("UnityPy",):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

a = Analysis(
    [os.path.join(ROOT, "deru.py")],
    pathex=[os.path.join(ROOT, "lib")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=[
        # the CSVs are for the game's own localisation pipeline, not for runtime
        "tkinter", "unittest", "pydoc_data", "pytest",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="deru",
    debug=False,
    strip=False,
    upx=False,             # UPX-packed binaries trip antivirus heuristics
    console=True,          # it is a terminal wizard; a windowed build has no tty
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,      # whatever the build machine is; CI builds both
    codesign_identity=None,  # ad-hoc signed after the fact, see the workflow
    entitlements_file=None,
)
