"""DiskImager GUI – polished CustomTkinter interface (v3)."""

from __future__ import annotations

import logging
import platform
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy import guard
# ---------------------------------------------------------------------------
try:
    import customtkinter as ctk
    from tkinter import filedialog, messagebox
    import tkinter as tk
except ImportError as _e:  # pragma: no cover
    ctk = None  # type: ignore[assignment]
    _IMPORT_ERROR = _e
else:
    _IMPORT_ERROR = None


# ---------------------------------------------------------------------------
# Colour palette  (GitHub-inspired dark / light)
# ---------------------------------------------------------------------------
PALETTE: dict[str, dict[str, str]] = {
    "dark": {
        "bg":         "#0d1117",
        "sidebar":    "#161b22",
        "card":       "#21262d",
        "card2":      "#30363d",
        "border":     "#30363d",
        "accent":     "#238636",
        "accent2":    "#1f6feb",
        "warning":    "#d29922",
        "danger":     "#da3633",
        "success":    "#3fb950",
        "text":       "#e6edf3",
        "text_muted": "#8b949e",
        "hover":      "#2d333b",
        "selected":   "#1f2d3d",
        "warn_bg":    "#3d1e1a",
    },
    "light": {
        "bg":         "#f6f8fa",
        "sidebar":    "#ffffff",
        "card":       "#ffffff",
        "card2":      "#f0f2f5",
        "border":     "#d0d7de",
        "accent":     "#2da44e",
        "accent2":    "#0969da",
        "warning":    "#9a6700",
        "danger":     "#cf222e",
        "success":    "#1a7f37",
        "text":       "#1f2328",
        "text_muted": "#656d76",
        "hover":      "#eaeef2",
        "selected":   "#ddf4ff",
        "warn_bg":    "#fff8e1",
    },
}

_THEME = "dark"


def P(key: str) -> str:
    """Return palette colour for the current theme."""
    return PALETTE[_THEME][key]


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _human_size(size_bytes: int) -> str:
    val: float = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(val) < 1024.0:
            return f"{val:.1f} {unit}"
        val /= 1024.0
    return f"{val:.1f} PB"


def _human_speed(bps: float) -> str:
    return _human_size(int(bps)) + "/s"


def _human_eta(done: int, total: int, speed: float) -> str:
    if total <= 0 or speed <= 0:
        return "---"
    remaining = total - done
    secs = int(remaining / speed)
    if secs < 60:
        return f"{secs}s"
    m, s = divmod(secs, 60)
    return f"{m}m {s:02d}s"


# ---------------------------------------------------------------------------
# Custom CONFIRM dialog
# ---------------------------------------------------------------------------

class ConfirmDialog(ctk.CTkToplevel):  # type: ignore[misc]
    """Ask the user to type CONFIRM before a destructive operation."""

    def __init__(self, parent: Any, message: str) -> None:
        super().__init__(parent)
        self.title("Confirm Destructive Operation")
        self.geometry("480x290")
        self.resizable(False, False)
        self.grab_set()
        self.focus_set()
        self._result = False

        ctk.CTkLabel(
            self, text="WARNING  --  DESTRUCTIVE OPERATION",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=P("danger"),
        ).pack(pady=(20, 6), padx=24, anchor="w")

        ctk.CTkLabel(
            self, text=message,
            font=ctk.CTkFont(size=12), text_color=P("text"),
            wraplength=432, justify="left",
        ).pack(pady=(0, 12), padx=24, anchor="w")

        ctk.CTkLabel(
            self, text='Type  CONFIRM  to proceed:',
            font=ctk.CTkFont(size=12), text_color=P("text_muted"),
        ).pack(padx=24, anchor="w")

        self._entry = ctk.CTkEntry(self, width=432, font=ctk.CTkFont(size=13))
        self._entry.pack(pady=(4, 14), padx=24)
        self._entry.bind("<Return>", lambda _: self._ok())
        self._entry.bind("<Escape>", lambda _: self._cancel())
        self._entry.focus_set()

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=(0, 18))
        ctk.CTkButton(
            row, text="Cancel", width=110,
            fg_color=P("card2"), hover_color=P("hover"),
            text_color=P("text"), command=self._cancel,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            row, text="Proceed", width=110,
            fg_color=P("danger"), hover_color="#b91c1c",
            command=self._ok,
        ).pack(side="right")

    def _ok(self) -> None:
        if self._entry.get().strip() == "CONFIRM":
            self._result = True
            self.grab_release()
            self.destroy()
        else:
            self._entry.configure(border_color=P("danger"), border_width=2)

    def _cancel(self) -> None:
        self._result = False
        self.grab_release()
        self.destroy()

    @property
    def confirmed(self) -> bool:
        return self._result


def ask_confirm(parent: Any, message: str) -> bool:
    dlg = ConfirmDialog(parent, message)
    parent.wait_window(dlg)
    return dlg.confirmed


# ---------------------------------------------------------------------------
# Progress dialog
# ---------------------------------------------------------------------------

class ProgressDialog(ctk.CTkToplevel):  # type: ignore[misc]
    """Modal progress window for long-running operations."""

    def __init__(self, parent: Any, op_name: str = "Working") -> None:
        super().__init__(parent)
        self.title(op_name)
        self.geometry("520x250")
        self.resizable(False, False)
        self.grab_set()
        self._cancelled = False
        self._done = False
        self._start = time.monotonic()

        self._title_lbl = ctk.CTkLabel(
            self, text=op_name,
            font=ctk.CTkFont(size=14, weight="bold"), anchor="w",
        )
        self._title_lbl.pack(pady=(18, 6), padx=24, anchor="w")

        self._bar = ctk.CTkProgressBar(self, height=12)
        self._bar.set(0)
        self._bar.pack(padx=24, fill="x", pady=(0, 6))

        self._stat1 = ctk.CTkLabel(
            self, text="Starting...",
            font=ctk.CTkFont(size=12), text_color=P("text_muted"), anchor="w",
        )
        self._stat1.pack(padx=24, anchor="w")

        self._stat2 = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=12), text_color=P("text_muted"), anchor="w",
        )
        self._stat2.pack(padx=24, anchor="w", pady=(0, 6))

        self._elapsed_lbl = ctk.CTkLabel(
            self, text="Elapsed: 0s",
            font=ctk.CTkFont(size=11), text_color=P("text_muted"), anchor="w",
        )
        self._elapsed_lbl.pack(padx=24, anchor="w")

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=(14, 18))
        self._cancel_btn = ctk.CTkButton(
            row, text="Cancel", width=100,
            fg_color=P("danger"), hover_color="#b91c1c",
            command=self._cancel,
        )
        self._cancel_btn.pack(side="left")
        self._close_btn = ctk.CTkButton(
            row, text="Close", width=100,
            fg_color=P("card2"), hover_color=P("hover"),
            text_color=P("text"), command=self.destroy, state="disabled",
        )
        self._close_btn.pack(side="left", padx=(8, 0))
        self._tick()

    def _tick(self) -> None:
        if not self.winfo_exists():
            return
        elapsed = int(time.monotonic() - self._start)
        m, s = divmod(elapsed, 60)
        self._elapsed_lbl.configure(
            text=f"Elapsed: {m}m {s:02d}s" if m else f"Elapsed: {s}s"
        )
        if not self._done:
            self.after(500, self._tick)

    def _cancel(self) -> None:
        self._cancelled = True
        self._title_lbl.configure(text="Cancelling...", text_color=P("warning"))

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def update_progress(self, done: int, total: int, speed: float) -> None:
        if not self.winfo_exists():
            return
        if total > 0:
            ratio = min(done / total, 1.0)
            self._bar.set(ratio)
            eta = _human_eta(done, total, speed)
            self._stat1.configure(
                text=f"{int(ratio*100)}%   {_human_size(done)} / {_human_size(total)}"
            )
            self._stat2.configure(
                text=f"Speed: {_human_speed(speed)}   ETA: {eta}"
            )
        else:
            self._bar.configure(mode="indeterminate")
            self._bar.start()
            self._stat1.configure(text=f"{_human_size(done)} written")
            self._stat2.configure(text=f"Speed: {_human_speed(speed)}")

    def finish(self, message: str = "Done!", success: bool = True) -> None:
        self._done = True
        if not self.winfo_exists():
            return
        self._bar.stop()
        self._bar.set(1 if success else 0)
        colour = P("success") if success else P("danger")
        self._title_lbl.configure(text=message, text_color=colour)
        self._stat1.configure(text="")
        self._stat2.configure(text="")
        self._cancel_btn.configure(state="disabled")
        self._close_btn.configure(state="normal")
        self.grab_release()


# ---------------------------------------------------------------------------
# Clickable drive row
# ---------------------------------------------------------------------------

class _DriveRow(ctk.CTkFrame):  # type: ignore[misc]
    def __init__(
        self, parent: Any, drive: dict[str, Any],
        on_select: Callable[[dict[str, Any]], None],
    ) -> None:
        super().__init__(parent, fg_color="transparent", cursor="hand2")
        self._drive = drive
        self._on_select = on_select
        self._selected = False

        usb_text  = "USB"     if drive.get("is_removable") else "Internal"
        boot_text = "SYS"     if drive.get("is_system")    else "---"
        usb_col   = P("warning") if drive.get("is_removable") else P("text_muted")
        boot_col  = P("danger")  if drive.get("is_system")    else P("text_muted")
        sg        = drive.get("size_gb", 0)
        size_str  = f"{sg:.1f} GB" if sg >= 1 else f"{sg*1024:.0f} MB"

        cols = [
            (str(drive["index"]),                       P("text_muted"), 36,  "e"),
            (drive.get("path", ""),                     P("accent2"),    172, "w"),
            (size_str,                                  P("text"),        80, "e"),
            (usb_text,                                  usb_col,          80, "center"),
            (boot_text,                                 boot_col,         80, "center"),
            (drive.get("model", "")[:28],               P("text"),       224, "w"),
            (str(len(drive.get("partitions", []))),     P("text_muted"), 58,  "e"),
        ]
        for text, color, width, anchor in cols:
            lbl = ctk.CTkLabel(
                self, text=text, font=ctk.CTkFont(size=11),
                text_color=color, width=width, anchor=anchor,
            )
            lbl.pack(side="left", padx=2, pady=3)
            lbl.bind("<Button-1>", self._click)
            lbl.bind("<Enter>",    self._enter)
            lbl.bind("<Leave>",    self._leave)

        self.bind("<Button-1>", self._click)
        self.bind("<Enter>",    self._enter)
        self.bind("<Leave>",    self._leave)

    def _enter(self, _e: Any = None) -> None:
        if not self._selected:
            self.configure(fg_color=P("hover"))

    def _leave(self, _e: Any = None) -> None:
        if not self._selected:
            self.configure(fg_color="transparent")

    def _click(self, _e: Any = None) -> None:
        self._on_select(self._drive)

    def set_selected(self, val: bool) -> None:
        self._selected = val
        self.configure(fg_color=P("selected") if val else "transparent")

    @property
    def drive(self) -> dict[str, Any]:
        return self._drive


# ---------------------------------------------------------------------------
# Sidebar nav button
# ---------------------------------------------------------------------------

class _NavButton(ctk.CTkButton):  # type: ignore[misc]
    def __init__(self, parent: Any, text: str, tab: str,
                 cb: Callable[[str], None]) -> None:
        super().__init__(
            parent, text=text,
            command=lambda: cb(tab),
            fg_color="transparent",
            hover_color=P("hover"),
            anchor="w",
            font=ctk.CTkFont(size=13),
            corner_radius=6,
        )

    def set_active(self, active: bool) -> None:
        self.configure(
            fg_color=P("selected") if active else "transparent",
            text_color=P("accent2") if active else P("text"),
            font=ctk.CTkFont(size=13, weight="bold" if active else "normal"),
        )


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class DiskImagerApp(ctk.CTk):  # type: ignore[misc]
    """DiskImager main window."""

    VERSION = "1.0.0"

    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title(f"DiskImager  v{self.VERSION}")
        self.geometry("1020x700")
        self.minsize(860, 560)

        self._drives: list[dict[str, Any]] = []
        self._selected_drive: Optional[dict[str, Any]] = None
        self._drive_rows: list[_DriveRow] = []
        self._activity_log: list[str] = []

        self._build_ui()
        self.after(120, self._refresh_drives)

    # =========================================================================
    # Top-level layout
    # =========================================================================

    def _build_ui(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main()
        self._build_statusbar()

    # -- Sidebar --------------------------------------------------------------

    def _build_sidebar(self) -> None:
        sb = ctk.CTkFrame(self, width=192, corner_radius=0, fg_color=P("sidebar"))
        sb.grid(row=0, column=0, sticky="nsew", rowspan=2)
        sb.grid_propagate(False)
        self._sidebar = sb

        logo = ctk.CTkFrame(sb, fg_color="transparent")
        logo.pack(fill="x", padx=14, pady=(22, 2))
        ctk.CTkLabel(
            logo, text="DiskImager",
            font=ctk.CTkFont(size=17, weight="bold"), text_color=P("text"),
        ).pack(side="left")
        ctk.CTkLabel(
            logo, text=f"v{self.VERSION}",
            font=ctk.CTkFont(size=10), text_color=P("text_muted"),
        ).pack(side="left", padx=(6, 0), pady=(4, 0))

        ctk.CTkFrame(sb, height=1, fg_color=P("border")).pack(
            fill="x", padx=14, pady=(10, 12)
        )

        self._nav_btns: dict[str, _NavButton] = {}
        for label, tab in [
            ("Backup",   "backup"),
            ("Restore",  "restore"),
            ("Flash",    "flash"),
            ("Verify",   "verify"),
            ("Erase",    "erase"),
            ("Activity", "activity"),
        ]:
            btn = _NavButton(sb, label, tab, self._switch_tab)
            btn.pack(fill="x", padx=10, pady=2)
            self._nav_btns[tab] = btn

        ctk.CTkFrame(sb, height=1, fg_color=P("border")).pack(
            fill="x", padx=14, pady=12
        )

        tr = ctk.CTkFrame(sb, fg_color="transparent")
        tr.pack(fill="x", padx=14, pady=(0, 6))
        ctk.CTkLabel(
            tr, text="Dark mode",
            font=ctk.CTkFont(size=12), text_color=P("text_muted"),
        ).pack(side="left")
        self._theme_switch = ctk.CTkSwitch(
            tr, text="", width=40, onvalue=1, offvalue=0,
            command=self._toggle_theme,
        )
        self._theme_switch.pack(side="right")
        self._theme_switch.select()

        ctk.CTkLabel(
            sb,
            text=f"{platform.system()} {platform.machine()}",
            font=ctk.CTkFont(size=10), text_color=P("text_muted"),
        ).pack(side="bottom", pady=(0, 6))

        ctk.CTkButton(
            sb, text="Scan Drives",
            fg_color=P("accent"), hover_color="#196127",
            font=ctk.CTkFont(size=12),
            command=self._refresh_drives,
        ).pack(side="bottom", fill="x", padx=10, pady=(0, 8))

    # -- Main pane ------------------------------------------------------------

    def _build_main(self) -> None:
        main = ctk.CTkFrame(self, fg_color=P("bg"), corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_rowconfigure(1, weight=1)
        main.grid_columnconfigure(0, weight=1)
        self._main = main
        self._build_drive_panel(main)
        self._build_tabs(main)

    def _build_drive_panel(self, parent: Any) -> None:
        outer = ctk.CTkFrame(parent, fg_color=P("card"), corner_radius=8)
        outer.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))

        hdr = ctk.CTkFrame(outer, fg_color="transparent")
        hdr.pack(fill="x", padx=12, pady=(8, 2))
        ctk.CTkLabel(
            hdr, text="Physical Drives",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=P("text"),
        ).pack(side="left")
        self._drive_info_btn = ctk.CTkButton(
            hdr, text="Drive Info", width=88,
            font=ctk.CTkFont(size=11),
            fg_color=P("card2"), hover_color=P("hover"),
            text_color=P("text"), state="disabled",
            command=self._show_drive_info,
        )
        self._drive_info_btn.pack(side="right", padx=(0, 4))
        self._drive_status_lbl = ctk.CTkLabel(
            hdr, text="Scanning...",
            font=ctk.CTkFont(size=11), text_color=P("text_muted"),
        )
        self._drive_status_lbl.pack(side="right", padx=(0, 8))

        col_hdr = ctk.CTkFrame(outer, fg_color=P("card2"), corner_radius=4)
        col_hdr.pack(fill="x", padx=10, pady=(0, 2))
        for col, w, anchor in [
            ("ID",     36,  "e"),
            ("Device", 172, "w"),
            ("Size",    80, "e"),
            ("Type",    80, "center"),
            ("Boot?",   80, "center"),
            ("Model",  224, "w"),
            ("Parts",   58, "e"),
        ]:
            ctk.CTkLabel(
                col_hdr, text=col,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=P("text_muted"), width=w, anchor=anchor,
            ).pack(side="left", padx=2, pady=3)

        self._drive_scroll = ctk.CTkScrollableFrame(
            outer, height=118, fg_color="transparent",
        )
        self._drive_scroll.pack(fill="x", padx=10, pady=(0, 4))

        sel = ctk.CTkFrame(outer, fg_color=P("selected"), corner_radius=4)
        sel.pack(fill="x", padx=10, pady=(0, 8))
        self._sel_lbl = ctk.CTkLabel(
            sel,
            text="Click a drive row to select it -- auto-fills device path below.",
            font=ctk.CTkFont(size=11), text_color=P("accent2"),
        )
        self._sel_lbl.pack(padx=10, pady=4, anchor="w")

    def _build_tabs(self, parent: Any) -> None:
        tv = ctk.CTkTabview(
            parent,
            fg_color=P("card"),
            segmented_button_fg_color=P("card2"),
            segmented_button_selected_color=P("accent2"),
            segmented_button_selected_hover_color="#1a5fcc",
            segmented_button_unselected_color=P("card2"),
            text_color=P("text"),
            corner_radius=8,
            command=self._on_tabview_change,
        )
        tv.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 6))
        self._tabview = tv
        for tab in ("Backup", "Restore", "Flash", "Verify", "Erase", "Activity"):
            tv.add(tab)
        tv.set("Backup")
        self._build_backup_tab(tv.tab("Backup"))
        self._build_restore_tab(tv.tab("Restore"))
        self._build_flash_tab(tv.tab("Flash"))
        self._build_verify_tab(tv.tab("Verify"))
        self._build_erase_tab(tv.tab("Erase"))
        self._build_activity_tab(tv.tab("Activity"))

    def _build_statusbar(self) -> None:
        bar = ctk.CTkFrame(self, height=28, corner_radius=0, fg_color=P("sidebar"))
        bar.grid(row=1, column=1, sticky="ew")
        self._status_lbl = ctk.CTkLabel(
            bar, text="Ready",
            font=ctk.CTkFont(size=11), text_color=P("text_muted"), anchor="w",
        )
        self._status_lbl.pack(side="left", padx=10)
        ctk.CTkLabel(
            bar,
            text=f"Python {sys.version.split()[0]}",
            font=ctk.CTkFont(size=11), text_color=P("text_muted"),
        ).pack(side="right", padx=10)

    # =========================================================================
    # Tab builders
    # =========================================================================

    def _section_title(self, parent: Any, text: str) -> None:
        ctk.CTkLabel(
            parent, text=text,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=P("text"), anchor="w",
        ).pack(fill="x", padx=16, pady=(14, 4))

    def _divider(self, parent: Any) -> None:
        ctk.CTkFrame(parent, height=1, fg_color=P("border")).pack(
            fill="x", padx=16, pady=6
        )

    def _form_row(
        self, parent: Any, label: str, entry_attr: str,
        placeholder: str, browse_cmd: Optional[Callable] = None,
    ) -> ctk.CTkEntry:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(
            row, text=label, width=150, anchor="w",
            font=ctk.CTkFont(size=12), text_color=P("text"),
        ).pack(side="left")
        entry = ctk.CTkEntry(
            row, placeholder_text=placeholder,
            font=ctk.CTkFont(size=12), text_color=P("text"),
        )
        entry.pack(side="left", fill="x", expand=True,
                   padx=(4, 4 if browse_cmd else 0))
        if browse_cmd:
            ctk.CTkButton(
                row, text="Browse...", width=90,
                fg_color=P("card2"), hover_color=P("hover"),
                text_color=P("text"), command=browse_cmd,
            ).pack(side="left")
        setattr(self, entry_attr, entry)
        return entry

    def _info_box(self, parent: Any, text: str) -> None:
        f = ctk.CTkFrame(parent, fg_color=P("card2"), corner_radius=6)
        f.pack(fill="x", padx=16, pady=(2, 6))
        ctk.CTkLabel(
            f, text=text,
            font=ctk.CTkFont(size=11), text_color=P("text_muted"), anchor="w",
        ).pack(padx=10, pady=5)

    def _warn_box(self, parent: Any, text: str) -> None:
        f = ctk.CTkFrame(parent, fg_color=P("warn_bg"), corner_radius=6)
        f.pack(fill="x", padx=16, pady=(2, 6))
        ctk.CTkLabel(
            f, text=text,
            font=ctk.CTkFont(size=11), text_color=P("warning"), anchor="w",
        ).pack(padx=10, pady=5)

    def _build_backup_tab(self, tab: Any) -> None:
        self._section_title(tab, "Backup Drive to Image File")
        self._divider(tab)
        self._form_row(tab, "Source device:", "_backup_src",
                       "/dev/sdb  or  \\\\.\\PhysicalDrive1")
        self._form_row(tab, "Destination .img:", "_backup_dst",
                       "backup.img", self._backup_browse_dst)
        self._divider(tab)
        opt = ctk.CTkFrame(tab, fg_color="transparent")
        opt.pack(fill="x", padx=16, pady=2)
        self._backup_dry_run = ctk.CTkCheckBox(
            opt, text="Dry run (simulate, no write)",
            font=ctk.CTkFont(size=12), text_color=P("text"),
        )
        self._backup_dry_run.pack(side="left")
        self._divider(tab)
        self._info_box(tab, "Creates a raw .img file + SHA-256 sidecar + .json metadata.")
        ctk.CTkButton(
            tab, text="Start Backup",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=P("accent"), hover_color="#196127",
            height=38, command=self._start_backup,
        ).pack(padx=16, pady=(4, 14), anchor="w")

    def _build_restore_tab(self, tab: Any) -> None:
        self._section_title(tab, "Restore Image to Drive")
        self._divider(tab)
        self._form_row(tab, "Image file (.img):", "_restore_src",
                       "backup.img", self._restore_browse_src)
        self._form_row(tab, "Target device:", "_restore_dst", "/dev/sdc")
        self._divider(tab)
        opt = ctk.CTkFrame(tab, fg_color="transparent")
        opt.pack(fill="x", padx=16, pady=2)
        self._restore_dry_run = ctk.CTkCheckBox(
            opt, text="Dry run",
            font=ctk.CTkFont(size=12), text_color=P("text"),
        )
        self._restore_dry_run.pack(side="left", padx=(0, 20))
        self._restore_no_verify = ctk.CTkCheckBox(
            opt, text="Skip post-write verification",
            font=ctk.CTkFont(size=12), text_color=P("text"),
        )
        self._restore_no_verify.pack(side="left")
        self._divider(tab)
        self._warn_box(tab, "All data on the target device will be permanently destroyed.")
        ctk.CTkButton(
            tab, text="Start Restore",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=P("warning"), hover_color="#92690d",
            text_color="#000000", height=38, command=self._start_restore,
        ).pack(padx=16, pady=(4, 14), anchor="w")

    def _build_flash_tab(self, tab: Any) -> None:
        self._section_title(tab, "Flash Image / ISO to USB Drive")
        self._divider(tab)
        self._form_row(tab, "Image / ISO / ZIP:", "_flash_src",
                       "ubuntu-22.04.iso", self._flash_browse_src)
        self._form_row(tab, "Target USB drive:", "_flash_dst", "/dev/sdd")
        self._divider(tab)
        opt = ctk.CTkFrame(tab, fg_color="transparent")
        opt.pack(fill="x", padx=16, pady=2)
        self._flash_dry_run = ctk.CTkCheckBox(
            opt, text="Dry run",
            font=ctk.CTkFont(size=12), text_color=P("text"),
        )
        self._flash_dry_run.pack(side="left", padx=(0, 20))
        self._flash_no_verify = ctk.CTkCheckBox(
            opt, text="Skip post-flash verification",
            font=ctk.CTkFont(size=12), text_color=P("text"),
        )
        self._flash_no_verify.pack(side="left")
        self._divider(tab)
        self._info_box(tab, "Supports .img, .iso, and .zip archives containing a disk image.")
        self._warn_box(tab, "All data on the target USB drive will be permanently destroyed.")
        ctk.CTkButton(
            tab, text="Flash Drive",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=P("danger"), hover_color="#b91c1c",
            height=38, command=self._start_flash,
        ).pack(padx=16, pady=(4, 14), anchor="w")

    def _build_verify_tab(self, tab: Any) -> None:
        self._section_title(tab, "Verify Image Integrity (SHA-256)")
        self._divider(tab)
        self._form_row(tab, "Image file:", "_verify_src",
                       "backup.img", self._verify_browse_src)
        self._form_row(
            tab, "Expected hash (optional):", "_verify_hash",
            "Leave blank -- auto-detects .sha256 sidecar",
        )
        self._divider(tab)
        res_frame = ctk.CTkFrame(tab, fg_color=P("card2"), corner_radius=6)
        res_frame.pack(fill="x", padx=16, pady=(2, 4))
        self._verify_result_lbl = ctk.CTkLabel(
            res_frame, text="No verification run yet.",
            font=ctk.CTkFont(size=12), text_color=P("text_muted"),
            anchor="w", wraplength=620, justify="left",
        )
        self._verify_result_lbl.pack(padx=12, pady=8, anchor="w")
        self._info_box(
            tab,
            "If a .sha256 sidecar exists next to the image it is loaded automatically.",
        )
        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(4, 14))
        ctk.CTkButton(
            btn_row, text="Verify Hash",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=P("accent2"), hover_color="#1a5fcc",
            height=38, command=self._start_verify,
        ).pack(side="left")
        self._copy_hash_btn = ctk.CTkButton(
            btn_row, text="Copy Hash",
            font=ctk.CTkFont(size=12),
            fg_color=P("card2"), hover_color=P("hover"),
            text_color=P("text"), height=38, width=110,
            command=self._copy_hash_to_clipboard, state="disabled",
        )
        self._copy_hash_btn.pack(side="left", padx=(8, 0))
        self._last_digest: Optional[str] = None

    def _build_erase_tab(self, tab: Any) -> None:
        self._section_title(tab, "Securely Erase a Drive")
        self._divider(tab)
        self._form_row(tab, "Target device:", "_erase_dst", "/dev/sdb")
        self._divider(tab)
        opt = ctk.CTkFrame(tab, fg_color="transparent")
        opt.pack(fill="x", padx=16, pady=2)
        self._erase_dry_run = ctk.CTkCheckBox(
            opt, text="Dry run (simulate, no write)",
            font=ctk.CTkFont(size=12), text_color=P("text"),
        )
        self._erase_dry_run.pack(side="left", padx=(0, 20))
        self._divider(tab)
        passes_row = ctk.CTkFrame(tab, fg_color="transparent")
        passes_row.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(
            passes_row, text="Overwrite passes:", width=150, anchor="w",
            font=ctk.CTkFont(size=12), text_color=P("text"),
        ).pack(side="left")
        self._erase_passes_var = tk.StringVar(value="1")
        self._erase_passes_menu = ctk.CTkOptionMenu(
            passes_row,
            values=["1", "2", "3", "5", "7"],
            variable=self._erase_passes_var,
            font=ctk.CTkFont(size=12),
            width=80,
        )
        self._erase_passes_menu.pack(side="left", padx=(4, 8))
        ctk.CTkLabel(
            passes_row,
            text="(1 = zeros only; 2+ = random data then zeros)",
            font=ctk.CTkFont(size=11), text_color=P("text_muted"),
        ).pack(side="left")
        self._divider(tab)
        self._warn_box(tab, "⚠  All data on the target device will be permanently and irrecoverably destroyed.")
        ctk.CTkButton(
            tab, text="Erase Drive",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=P("danger"), hover_color="#b91c1c",
            height=38, command=self._start_erase,
        ).pack(padx=16, pady=(4, 14), anchor="w")

    def _build_activity_tab(self, tab: Any) -> None:
        self._section_title(tab, "Activity Log")
        self._divider(tab)
        self._log_text = ctk.CTkTextbox(
            tab,
            font=ctk.CTkFont(family="monospace", size=11),
            text_color=P("text"),
            fg_color=P("bg"),
            corner_radius=6,
        )
        self._log_text.pack(fill="both", expand=True, padx=16, pady=(0, 4))
        self._log_text.configure(state="disabled")
        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkButton(
            row, text="Clear Log", width=120,
            fg_color=P("card2"), hover_color=P("hover"),
            text_color=P("text"), command=self._clear_log,
        ).pack(side="right")

    # =========================================================================
    # Drive table / refresh
    # =========================================================================

    def _refresh_drives(self) -> None:
        from disktool.core.disk import get_drives
        self._set_status("Scanning drives...")
        self._drive_status_lbl.configure(text="Scanning...")

        def _fetch() -> None:
            try:
                drives = get_drives()
            except Exception as exc:
                logger.error("Drive scan failed: %s", exc)
                drives = []
            self.after(0, lambda: self._on_drives_loaded(drives))

        threading.Thread(target=_fetch, daemon=True).start()

    def _on_drives_loaded(self, drives: list[dict[str, Any]]) -> None:
        self._drives = drives
        n = len(drives)
        self._drive_status_lbl.configure(
            text=f"{n} drive{'s' if n != 1 else ''} found"
        )
        self._set_status(f"Found {n} drive{'s' if n != 1 else ''}")
        self._render_drives()

    def _render_drives(self) -> None:
        for row in self._drive_rows:
            row.destroy()
        self._drive_rows.clear()
        self._selected_drive = None
        self._drive_info_btn.configure(state="disabled")
        self._sel_lbl.configure(
            text="Click a drive row to select it -- auto-fills device path below."
        )
        if not self._drives:
            ctk.CTkLabel(
                self._drive_scroll,
                text="No physical drives detected. Run as Administrator/root for full access.",
                font=ctk.CTkFont(size=11), text_color=P("text_muted"),
            ).pack(pady=8)
            return
        for drive in self._drives:
            row = _DriveRow(self._drive_scroll, drive, self._on_drive_selected)
            row.pack(fill="x", pady=1)
            self._drive_rows.append(row)

    def _on_drive_selected(self, drive: dict[str, Any]) -> None:
        self._selected_drive = drive
        for row in self._drive_rows:
            row.set_selected(row.drive is drive)
        path  = drive.get("path", "")
        sg    = drive.get("size_gb", 0)
        model = drive.get("model", "Unknown")
        usb   = "USB" if drive.get("is_removable") else "Internal"
        sys_  = "  [SYSTEM DISK]" if drive.get("is_system") else ""
        self._sel_lbl.configure(
            text=f"Selected: {path}   {sg:.1f} GB   {model}   {usb}{sys_}"
        )
        self._drive_info_btn.configure(state="normal")
        current = self._tabview.get()
        if current == "Backup":
            self._backup_src.delete(0, "end")
            self._backup_src.insert(0, path)
        elif current == "Restore":
            self._restore_dst.delete(0, "end")
            self._restore_dst.insert(0, path)
        elif current == "Flash":
            self._flash_dst.delete(0, "end")
            self._flash_dst.insert(0, path)
        elif current == "Erase":
            self._erase_dst.delete(0, "end")
            self._erase_dst.insert(0, path)
        self._set_status(f"Selected: {path}  {sg:.1f} GB  {model}")
        self._log(f"Drive selected: {path}  ({sg:.1f} GB  {model}  {usb})")

    def _show_drive_info(self) -> None:
        drive = self._selected_drive
        if not drive:
            return
        dlg = ctk.CTkToplevel(self)
        dlg.title(f"Drive Info: {drive.get('path', '')}")
        dlg.geometry("480x420")
        dlg.resizable(False, False)
        dlg.grab_set()

        ctk.CTkLabel(
            dlg, text=f"Drive Info: {drive.get('path', '')}",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=P("text"),
        ).pack(pady=(18, 4), padx=20, anchor="w")

        card = ctk.CTkFrame(dlg, fg_color=P("card2"), corner_radius=6)
        card.pack(fill="x", padx=20, pady=(0, 8))

        def _row(key: str, val: str) -> None:
            r = ctk.CTkFrame(card, fg_color="transparent")
            r.pack(fill="x", padx=12, pady=2)
            ctk.CTkLabel(r, text=key, width=130, anchor="w",
                         font=ctk.CTkFont(size=12), text_color=P("text_muted"),
                         ).pack(side="left")
            ctk.CTkLabel(r, text=val, anchor="w",
                         font=ctk.CTkFont(size=12), text_color=P("text"),
                         ).pack(side="left")

        sg = drive.get("size_gb", 0)
        size_str = f"{sg:.2f} GB  ({drive.get('size_bytes', 0):,} bytes)"
        _row("Device:",     drive.get("path", "—"))
        _row("Model:",      drive.get("model", "Unknown"))
        _row("Size:",       size_str)
        _row("Type:",       "USB / Removable" if drive.get("is_removable") else "Internal")
        _row("System Disk:", "YES" if drive.get("is_system") else "No")
        _row("Partitions:", str(len(drive.get("partitions", []))))

        parts = drive.get("partitions", [])
        if parts:
            ctk.CTkLabel(
                dlg, text="Partitions",
                font=ctk.CTkFont(size=13, weight="bold"), text_color=P("text"),
            ).pack(pady=(4, 2), padx=20, anchor="w")
            pcard = ctk.CTkScrollableFrame(dlg, fg_color=P("card2"), corner_radius=6, height=140)
            pcard.pack(fill="x", padx=20, pady=(0, 8))
            for p in parts:
                pb = ctk.CTkFrame(pcard, fg_color="transparent")
                pb.pack(fill="x", padx=4, pady=2)
                from disktool.core.disk import format_size
                psize = format_size(p.get("size_bytes", 0)).strip()
                mount = p.get("mountpoint") or "—"
                fs    = p.get("filesystem") or "—"
                ctk.CTkLabel(
                    pb, text=p.get("path", p.get("name", "")),
                    font=ctk.CTkFont(size=11), text_color=P("accent2"), width=120, anchor="w",
                ).pack(side="left")
                ctk.CTkLabel(
                    pb, text=psize,
                    font=ctk.CTkFont(size=11), text_color=P("text"), width=80, anchor="e",
                ).pack(side="left")
                ctk.CTkLabel(
                    pb, text=mount,
                    font=ctk.CTkFont(size=11), text_color=P("text_muted"), width=100, anchor="w",
                ).pack(side="left", padx=(8, 0))
                ctk.CTkLabel(
                    pb, text=fs,
                    font=ctk.CTkFont(size=11), text_color=P("text_muted"), width=60, anchor="w",
                ).pack(side="left", padx=(4, 0))

        ctk.CTkButton(
            dlg, text="Close", width=100,
            fg_color=P("card2"), hover_color=P("hover"),
            text_color=P("text"), command=dlg.destroy,
        ).pack(pady=(0, 14))



    def _switch_tab(self, tab_name: str) -> None:
        tab_map = {
            "backup":   "Backup",
            "restore":  "Restore",
            "flash":    "Flash",
            "verify":   "Verify",
            "erase":    "Erase",
            "activity": "Activity",
        }
        if tab_name in tab_map:
            self._tabview.set(tab_map[tab_name])
            self._on_tabview_change()

    def _on_tabview_change(self) -> None:
        current = self._tabview.get().lower()
        for name, btn in self._nav_btns.items():
            btn.set_active(name == current)

    # =========================================================================
    # Theme toggle
    # =========================================================================

    def _toggle_theme(self) -> None:
        global _THEME
        _THEME = "dark" if self._theme_switch.get() == 1 else "light"
        ctk.set_appearance_mode(_THEME)

    # =========================================================================
    # File dialogs
    # =========================================================================

    def _backup_browse_dst(self) -> None:
        p = filedialog.asksaveasfilename(
            title="Save image as", defaultextension=".img",
            filetypes=[("Disk image", "*.img"), ("All files", "*.*")],
        )
        if p:
            self._backup_dst.delete(0, "end")
            self._backup_dst.insert(0, p)

    def _restore_browse_src(self) -> None:
        p = filedialog.askopenfilename(
            title="Select image",
            filetypes=[("Disk images", "*.img *.iso *.zip"), ("All files", "*.*")],
        )
        if p:
            self._restore_src.delete(0, "end")
            self._restore_src.insert(0, p)

    def _flash_browse_src(self) -> None:
        p = filedialog.askopenfilename(
            title="Select image / ISO",
            filetypes=[("Images & ISOs", "*.img *.iso *.zip"), ("All files", "*.*")],
        )
        if p:
            self._flash_src.delete(0, "end")
            self._flash_src.insert(0, p)

    def _verify_browse_src(self) -> None:
        p = filedialog.askopenfilename(
            title="Select image to verify",
            filetypes=[("Disk images", "*.img *.iso"), ("All files", "*.*")],
        )
        if p:
            self._verify_src.delete(0, "end")
            self._verify_src.insert(0, p)

    # =========================================================================
    # Activity log / status
    # =========================================================================

    def _log(self, message: str) -> None:
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}]  {message}\n"
        self._activity_log.append(line)
        try:
            self._log_text.configure(state="normal")
            self._log_text.insert("end", line)
            self._log_text.see("end")
            self._log_text.configure(state="disabled")
        except Exception:
            pass

    def _clear_log(self) -> None:
        self._activity_log.clear()
        try:
            self._log_text.configure(state="normal")
            self._log_text.delete("1.0", "end")
            self._log_text.configure(state="disabled")
        except Exception:
            pass

    def _set_status(self, text: str) -> None:
        try:
            self._status_lbl.configure(text=text)
        except Exception:
            pass

    # =========================================================================
    # Wipe confirmation
    # =========================================================================

    def _wipe_confirm(self, dest: str) -> bool:
        info  = next((d for d in self._drives if d.get("path") == dest), None)
        sg    = info.get("size_gb", "?") if info else "?"
        model = info.get("model", "unknown") if info else "unknown"
        return ask_confirm(
            self,
            f"You are about to WIPE  {sg} GB  {model}  ({dest}).\n\n"
            "All data on this device will be permanently and irrecoverably destroyed.",
        )

    # =========================================================================
    # Operation starters
    # =========================================================================

    def _start_backup(self) -> None:
        src = self._backup_src.get().strip()
        dst = self._backup_dst.get().strip()
        dry = self._backup_dry_run.get() == 1
        if not src or not dst:
            messagebox.showerror("Missing input",
                                 "Please fill in source device and destination file.")
            return
        self._log(f"Backup: {src} -> {dst}" + (" [dry-run]" if dry else ""))
        self._run_op("backup", f"Backup {Path(src).name}",
                     {"source": src, "dest": dst, "dry_run": dry})

    def _start_restore(self) -> None:
        src = self._restore_src.get().strip()
        dst = self._restore_dst.get().strip()
        dry = self._restore_dry_run.get() == 1
        skip_verify = self._restore_no_verify.get() == 1
        if not src or not dst:
            messagebox.showerror("Missing input",
                                 "Please fill in image file and target device.")
            return
        info = next((d for d in self._drives if d.get("path") == dst), None)
        if info and info.get("is_system"):
            messagebox.showerror("System Disk Blocked",
                f"{dst} is a system disk. Restore to system disks is blocked.")
            return
        if not dry and not self._wipe_confirm(dst):
            return
        self._log(f"Restore: {src} -> {dst}" + (" [dry-run]" if dry else ""))
        self._run_op("restore", f"Restore -> {Path(dst).name}",
                     {"image": src, "dest": dst, "dry_run": dry, "verify": not skip_verify})

    def _start_flash(self) -> None:
        src = self._flash_src.get().strip()
        dst = self._flash_dst.get().strip()
        dry = self._flash_dry_run.get() == 1
        skip_verify = self._flash_no_verify.get() == 1
        if not src or not dst:
            messagebox.showerror("Missing input",
                                 "Please fill in image / ISO and target USB drive.")
            return
        info = next((d for d in self._drives if d.get("path") == dst), None)
        if info and info.get("is_system"):
            messagebox.showerror("System Disk Blocked",
                f"{dst} is a system disk. Flash to system disks is blocked.")
            return
        if not dry and not self._wipe_confirm(dst):
            return
        self._log(f"Flash: {src} -> {dst}" + (" [dry-run]" if dry else ""))
        self._run_op("flash", f"Flash {Path(src).name}",
                     {"image": src, "dest": dst, "dry_run": dry, "verify": not skip_verify})

    def _start_verify(self) -> None:
        src      = self._verify_src.get().strip()
        expected = self._verify_hash.get().strip() or None
        if not src:
            messagebox.showerror("Missing input", "Please select an image file to verify.")
            return
        img_path = Path(src)
        if not img_path.exists():
            messagebox.showerror("File not found", f"Cannot find:\n{src}")
            return
        self._log(f"Verify: {src}")
        self._verify_result_lbl.configure(
            text="Computing SHA-256...", text_color=P("text_muted")
        )
        self._copy_hash_btn.configure(state="disabled")
        self._last_digest = None
        self._set_status("Verifying...")
        dlg = ProgressDialog(self, "Verifying")

        def _worker() -> None:
            from disktool.core.verify import hash_file, read_sidecar
            exp = expected
            if exp is None:
                sidecar = read_sidecar(img_path)
                if sidecar:
                    _algo, exp = sidecar
            total = img_path.stat().st_size
            verify_start = time.monotonic()

            def _prog(done: int) -> None:
                elapsed = time.monotonic() - verify_start
                speed = done / elapsed if elapsed > 0 else 0.0
                try:
                    self.after(0, lambda: dlg.update_progress(done, total, speed))
                except Exception:
                    pass

            try:
                digest = hash_file(img_path, progress_callback=_prog)
            except Exception as exc:
                err = str(exc)
                self.after(0, lambda: dlg.finish(f"Error: {err}", success=False))
                self.after(0, lambda: self._verify_result_lbl.configure(
                    text=f"Error: {err}", text_color=P("danger"),
                ))
                return

            if exp:
                ok = digest.lower() == exp.lower()
                if ok:
                    msg = f"PASS\n\nSHA-256: {digest}"
                    self.after(0, lambda: dlg.finish("Verification Passed", success=True))
                    self.after(0, lambda: self._verify_result_lbl.configure(
                        text=msg, text_color=P("success"),
                    ))
                    self.after(0, lambda: self._log(f"Verify PASSED: {src}"))
                else:
                    msg = f"FAIL -- Hash mismatch!\n  Expected: {exp}\n  Got:      {digest}"
                    self.after(0, lambda: dlg.finish("Verification FAILED", success=False))
                    self.after(0, lambda: self._verify_result_lbl.configure(
                        text=msg, text_color=P("danger"),
                    ))
                    self.after(0, lambda: self._log(f"Verify FAILED: {src}"))
            else:
                msg = f"SHA-256: {digest}\n\n(No expected hash -- file was hashed only.)"
                self.after(0, lambda: dlg.finish("Hash Complete", success=True))
                self.after(0, lambda: self._verify_result_lbl.configure(
                    text=msg, text_color=P("text"),
                ))
                self.after(0, lambda: self._log(f"Hash: {src} -> {digest[:16]}..."))
            self._last_digest = digest
            self.after(0, lambda: self._copy_hash_btn.configure(state="normal"))
            self.after(0, lambda: self._set_status("Verification complete."))

        threading.Thread(target=_worker, daemon=True).start()

    def _copy_hash_to_clipboard(self) -> None:
        if self._last_digest:
            self.clipboard_clear()
            self.clipboard_append(self._last_digest)
            self._set_status("Hash copied to clipboard.")

    def _start_erase(self) -> None:
        dst = self._erase_dst.get().strip()
        dry = self._erase_dry_run.get() == 1
        try:
            passes = int(self._erase_passes_var.get())
        except (ValueError, AttributeError):
            passes = 1
        if not dst:
            messagebox.showerror("Missing input", "Please enter the target device path.")
            return
        info = next((d for d in self._drives if d.get("path") == dst), None)
        if info and info.get("is_system"):
            messagebox.showerror(
                "System Disk Blocked",
                f"{dst} is a system disk. Erase of system disks is blocked for safety.",
            )
            return
        if not dry:
            sg    = info.get("size_gb", "?") if info else "?"
            model = info.get("model", "unknown") if info else "unknown"
            if not ask_confirm(
                self,
                f"You are about to SECURELY ERASE  {sg} GB  {model}  ({dst})\n"
                f"using {passes} overwrite pass(es).\n\n"
                "All data will be permanently and irrecoverably destroyed.",
            ):
                return
        self._log(f"Erase: {dst}  passes={passes}" + (" [dry-run]" if dry else ""))
        self._set_status("Erase in progress...")
        dlg = ProgressDialog(self, f"Erase {dst}")

        def _progress(done: int, total: int, speed: float) -> None:
            if dlg.cancelled:
                raise InterruptedError("Cancelled by user.")
            try:
                self.after(0, lambda: dlg.update_progress(done, total, speed))
            except Exception:
                pass

        def _worker() -> None:
            from disktool.core.imaging import erase
            try:
                erase(dst, passes=passes, dry_run=dry, progress_callback=_progress)
                def _ok() -> None:
                    dlg.finish("Erase complete!", success=True)
                    self._log("Erase finished OK.")
                    self._set_status("Erase complete.")
                self.after(0, _ok)
            except InterruptedError:
                self.after(0, lambda: dlg.finish("Cancelled.", success=False))
                self.after(0, lambda: self._log("Erase cancelled."))
                self.after(0, lambda: self._set_status("Cancelled."))
            except Exception as exc:
                err = str(exc)
                logger.error("erase error: %s", exc)
                def _err() -> None:
                    dlg.finish(f"Error: {err}", success=False)
                    messagebox.showerror("Erase Failed", err)
                    self._log(f"Erase ERROR: {err}")
                    self._set_status(f"Error: {err}")
                self.after(0, _err)

        threading.Thread(target=_worker, daemon=True).start()

    # =========================================================================
    # Generic operation runner
    # =========================================================================

    def _run_op(self, op: str, display_name: str, kwargs: dict[str, Any]) -> None:
        from disktool.core.imaging import backup, flash, restore
        fn = {"backup": backup, "restore": restore, "flash": flash}[op]
        dlg = ProgressDialog(self, display_name)
        self._set_status(f"{op.capitalize()} in progress...")

        def _progress(done: int, total: int, speed: float) -> None:
            if dlg.cancelled:
                raise InterruptedError("Cancelled by user.")
            try:
                self.after(0, lambda: dlg.update_progress(done, total, speed))
            except Exception:
                pass

        def _worker() -> None:
            try:
                result = fn(**kwargs, progress_callback=_progress)
                def _ok() -> None:
                    if op == "backup" and result:
                        dlg.finish(f"Backup complete! SHA-256: {str(result)[:16]}...", success=True)
                        # Offer to open containing folder
                        dest = kwargs.get("dest", "")
                        if dest:
                            dest_path = Path(dest)
                            if dest_path.exists():
                                self._offer_open_folder(dest_path.parent)
                    else:
                        dlg.finish(f"{op.capitalize()} complete!", success=True)
                    self._log(f"{op.capitalize()} finished OK.")
                    self._set_status(f"{op.capitalize()} complete.")
                self.after(0, _ok)
            except InterruptedError:
                self.after(0, lambda: dlg.finish("Cancelled.", success=False))
                self.after(0, lambda: self._log(f"{op.capitalize()} cancelled."))
                self.after(0, lambda: self._set_status("Cancelled."))
            except Exception as exc:
                err = str(exc)
                logger.error("%s error: %s", op, exc)
                def _err() -> None:
                    dlg.finish(f"Error: {err}", success=False)
                    messagebox.showerror("Operation Failed", err)
                    self._log(f"{op.capitalize()} ERROR: {err}")
                    self._set_status(f"Error: {err}")
                self.after(0, _err)

        threading.Thread(target=_worker, daemon=True).start()

    def _offer_open_folder(self, folder: Path) -> None:
        """Ask whether to open the folder containing the backup image."""
        if messagebox.askyesno(
            "Backup Complete",
            f"Backup finished successfully!\n\nOpen the output folder?\n{folder}",
        ):
            self._open_folder(folder)

    @staticmethod
    def _open_folder(folder: Path) -> None:
        """Open *folder* in the OS file manager."""
        import subprocess
        try:
            if sys.platform == "win32":
                import os as _os
                _os.startfile(str(folder))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:
            logger.warning("Could not open folder %s: %s", folder, exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_gui() -> None:
    """Launch the DiskImager GUI."""
    if ctk is None:
        raise ImportError(
            "customtkinter is not installed. Install with: pip install customtkinter"
        ) from _IMPORT_ERROR  # type: ignore[name-defined]
    app = DiskImagerApp()
    app.mainloop()


if __name__ == "__main__":  # pragma: no cover
    run_gui()
