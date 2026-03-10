# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for DiskImager standalone executable.

Produces a single self-contained binary (--onefile) that embeds Python and
every dependency so end-users don't need to install anything.

Build (from the repo root):
    pip install pyinstaller
    pyinstaller DiskImager.spec

Output:
    dist/disktool          (Linux / macOS)
    dist/disktool.exe      (Windows)

For a directory build (faster startup, easier debugging):
    pyinstaller --onedir DiskImager.spec
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH)

# ---------------------------------------------------------------------------
# Collect customtkinter theme/image assets so the GUI works when bundled.
# ---------------------------------------------------------------------------
try:
    import customtkinter as _ctk
    _ctk_dir = Path(_ctk.__file__).parent
    _ctk_datas = [
        (str(_ctk_dir / "assets"), "customtkinter/assets"),
    ]
except Exception:
    _ctk_datas = []

# Collect Pillow/tkinter helper data if present
try:
    import PIL as _pil
    _pil_dir = Path(_pil.__file__).parent
    _pil_datas = [(str(_pil_dir), "PIL")]
except Exception:
    _pil_datas = []

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=_ctk_datas + _pil_datas,
    hiddenimports=[
        # ---- DiskImager core ----
        "disktool",
        "disktool.cli",
        "disktool.gui",
        "disktool.settings",
        "disktool.core.disk",
        "disktool.core.imaging",
        "disktool.core.verify",
        "disktool.core.compress",
        "disktool.core.benchmark",
        "disktool.core.format",
        "disktool.core.mount",
        "disktool.core.partition",
        # ---- Platform backends (all three bundled) ----
        "disktool.platform",
        "disktool.platform.linux",
        "disktool.platform.darwin",
        "disktool.platform.windows",
        # ---- CustomTkinter / Pillow ----
        "customtkinter",
        "customtkinter.windows",
        "customtkinter.windows.widgets",
        "customtkinter.windows.widgets.utility",
        "PIL",
        "PIL.Image",
        "PIL.ImageTk",
        "PIL._tkinter_finder",
        # ---- Rich ----
        "rich",
        "rich.progress",
        "rich.logging",
        "rich.table",
        "rich.panel",
        "rich.rule",
        "rich.text",
        "rich.console",
        "rich.prompt",
        "rich.markup",
        "rich.columns",
        # ---- psutil (platform sub-modules) ----
        "psutil",
        "psutil._pslinux",
        "psutil._psosx",
        "psutil._psposix",
        "psutil._pswindows",
        "psutil._psaix",
        "psutil._psbsd",
        "psutil._pssunos",
        # ---- Optional compression back-ends ----
        "lz4",
        "lz4.frame",
        "zstandard",
        # ---- Click / tqdm ----
        "click",
        "tqdm",
        "tqdm.auto",
        # ---- cryptography ----
        "cryptography",
        "cryptography.hazmat.primitives.hashes",
        # ---- Windows-specific helpers (no-op on other platforms) ----
        "win32api",
        "win32con",
        "win32com",
        "win32com.client",
        "winreg",
        "ctypes.wintypes",
        # ---- stdlib modules sometimes missed by the hook ----
        "zipfile",
        "gzip",
        "hashlib",
        "json",
        "shutil",
        "subprocess",
        "tempfile",
        "threading",
        "queue",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "unittest", "_pytest"],
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
    # Keep console=True so the CLI works; the GUI opens its own Tk window.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
