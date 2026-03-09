# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for DiskImager standalone executable.

Build with:
    pyinstaller DiskImager.spec

Or for a directory distribution (faster startup):
    pyinstaller --onedir DiskImager.spec
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH)

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[
        # Platform modules (all three shipped in the binary)
        "disktool.platform.linux",
        "disktool.platform.darwin",
        "disktool.platform.windows",
        # CustomTkinter internals
        "customtkinter",
        "PIL",
        "PIL._tkinter_finder",
        # Rich internals
        "rich.progress",
        "rich.logging",
        "rich.table",
        "rich.panel",
        # psutil internals
        "psutil",
        "psutil._pslinux",
        "psutil._psosx",
        "psutil._pswindows",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "unittest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="disktool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
