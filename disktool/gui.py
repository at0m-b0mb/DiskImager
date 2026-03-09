"""CustomTkinter GUI for DiskImager."""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy import guard
# ---------------------------------------------------------------------------
try:
    import customtkinter as ctk
    from tkinter import filedialog, messagebox, simpledialog
    import tkinter as tk
except ImportError as _e:  # pragma: no cover
    ctk = None  # type: ignore[assignment]
    _IMPORT_ERROR = _e
else:
    _IMPORT_ERROR = None


# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
ACCENT = "#1f6feb"
DANGER = "#da3633"
SUCCESS = "#3fb950"
WARNING = "#d29922"
BG_DARK = "#0d1117"
BG_CARD = "#161b22"
TEXT = "#c9d1d9"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _human_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0  # type: ignore[assignment]
    return f"{size_bytes:.1f} PB"


def _human_speed(bps: float) -> str:
    return _human_size(int(bps)) + "/s"


# ---------------------------------------------------------------------------
# Progress dialog
# ---------------------------------------------------------------------------

class ProgressDialog(ctk.CTkToplevel):  # type: ignore[misc]
    """Modal progress window shown during long operations."""

    def __init__(self, parent: ctk.CTk, title: str = "Working…") -> None:
        super().__init__(parent)
        self.title(title)
        self.geometry("480x200")
        self.resizable(False, False)
        self.grab_set()
        self._cancelled = False

        self._label = ctk.CTkLabel(self, text="Preparing…", font=ctk.CTkFont(size=13))
        self._label.pack(pady=(20, 8), padx=20, anchor="w")

        self._bar = ctk.CTkProgressBar(self, width=440)
        self._bar.set(0)
        self._bar.pack(pady=4, padx=20)

        self._status = ctk.CTkLabel(self, text="", text_color=TEXT, font=ctk.CTkFont(size=11))
        self._status.pack(pady=4, padx=20, anchor="w")

        ctk.CTkButton(self, text="Cancel", fg_color=DANGER, command=self._cancel).pack(pady=10)

    def _cancel(self) -> None:
        self._cancelled = True
        self._label.configure(text="Cancelling…")

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def update_progress(self, done: int, total: int, speed: float) -> None:
        if total > 0:
            ratio = done / total
            self._bar.set(ratio)
            pct = int(ratio * 100)
            done_str = _human_size(done)
            total_str = _human_size(total)
            speed_str = _human_speed(speed)
            self._status.configure(
                text=f"{pct}%  –  {done_str} / {total_str}  –  {speed_str}"
            )
        else:
            self._bar.configure(mode="indeterminate")
            self._bar.start()
            self._status.configure(text=f"{_human_size(done)} written  –  {_human_speed(speed)}")

    def finish(self, message: str = "Done!", success: bool = True) -> None:
        self._bar.stop()
        self._bar.set(1 if success else 0)
        colour = SUCCESS if success else DANGER
        self._label.configure(text=message, text_color=colour)
        self._status.configure(text="")
        self.grab_release()


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------

class DiskImagerApp(ctk.CTk):  # type: ignore[misc]
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("DiskImager  –  v1.0.0")
        self.geometry("900x620")
        self.minsize(780, 520)

        # Drives cache
        self._drives: list[dict[str, Any]] = []

        self._build_ui()
        self.after(100, self._refresh_drives)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Sidebar
        self._sidebar = ctk.CTkFrame(self, width=180, corner_radius=0)
        self._sidebar.pack(side="left", fill="y")

        ctk.CTkLabel(
            self._sidebar,
            text="DiskImager",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(20, 4), padx=10)
        ctk.CTkLabel(
            self._sidebar,
            text="v1.0.0",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack(pady=(0, 20), padx=10)

        self._nav_buttons: list[ctk.CTkButton] = []
        for label, tab_name in [
            ("💾  Backup", "backup"),
            ("📥  Restore", "restore"),
            ("⚡  Flash", "flash"),
        ]:
            btn = ctk.CTkButton(
                self._sidebar,
                text=label,
                command=lambda t=tab_name: self._switch_tab(t),
                fg_color="transparent",
                hover_color=BG_CARD,
                anchor="w",
                font=ctk.CTkFont(size=13),
            )
            btn.pack(pady=4, padx=10, fill="x")
            self._nav_buttons.append(btn)

        # Refresh button
        ctk.CTkButton(
            self._sidebar,
            text="🔄  Refresh Drives",
            command=self._refresh_drives,
            font=ctk.CTkFont(size=12),
        ).pack(side="bottom", pady=20, padx=10, fill="x")

        # Main area
        self._main = ctk.CTkFrame(self)
        self._main.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        # Drive table header
        header = ctk.CTkFrame(self._main, fg_color=BG_CARD, corner_radius=8)
        header.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(
            header, text="Physical Drives", font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left", padx=12, pady=6)
        self._drive_status = ctk.CTkLabel(
            header, text="", font=ctk.CTkFont(size=11), text_color="gray"
        )
        self._drive_status.pack(side="right", padx=12)

        # Drive table
        self._table_frame = ctk.CTkScrollableFrame(self._main, height=180, fg_color=BG_CARD, corner_radius=8)
        self._table_frame.pack(fill="x", pady=(0, 10))
        self._render_table_header()

        # Tabs frame
        self._tab_frame = ctk.CTkFrame(self._main, fg_color="transparent")
        self._tab_frame.pack(fill="both", expand=True)

        self._tabs: dict[str, ctk.CTkFrame] = {}
        self._tabs["backup"] = self._build_backup_tab()
        self._tabs["restore"] = self._build_restore_tab()
        self._tabs["flash"] = self._build_flash_tab()

        self._current_tab = "backup"
        self._switch_tab("backup")

    def _render_table_header(self) -> None:
        cols = ["ID", "Device", "Size", "Type", "Boot?", "Model", "Partitions"]
        widths = [40, 180, 80, 80, 60, 240, 70]
        row = ctk.CTkFrame(self._table_frame, fg_color="transparent")
        row.pack(fill="x", padx=4, pady=(4, 0))
        for col, w in zip(cols, widths):
            ctk.CTkLabel(
                row, text=col, font=ctk.CTkFont(size=11, weight="bold"),
                width=w, anchor="w", text_color="gray",
            ).pack(side="left", padx=2)
        self._table_rows: list[ctk.CTkFrame] = []

    def _render_drives(self) -> None:
        for r in self._table_rows:
            r.destroy()
        self._table_rows.clear()

        for drive in self._drives:
            row = ctk.CTkFrame(self._table_frame, fg_color="transparent")
            row.pack(fill="x", padx=4, pady=1)

            usb = "🔌 USB" if drive.get("is_removable") else "Internal"
            boot = "❌ YES" if drive.get("is_system") else "✅ NO"
            usb_color = WARNING if drive.get("is_removable") else TEXT
            boot_color = DANGER if drive.get("is_system") else SUCCESS

            values = [
                (str(drive["index"]), TEXT, 40),
                (drive.get("path", ""), ACCENT, 180),
                (f"{drive.get('size_gb', 0):.1f} GB", TEXT, 80),
                (usb, usb_color, 80),
                (boot, boot_color, 60),
                (drive.get("model", "")[:30], TEXT, 240),
                (str(len(drive.get("partitions", []))), TEXT, 70),
            ]
            for val, color, w in values:
                ctk.CTkLabel(
                    row, text=val, font=ctk.CTkFont(size=11),
                    text_color=color, width=w, anchor="w",
                ).pack(side="left", padx=2)
            self._table_rows.append(row)

    # ------------------------------------------------------------------
    # Backup tab
    # ------------------------------------------------------------------

    def _build_backup_tab(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self._tab_frame, fg_color=BG_CARD, corner_radius=8)
        ctk.CTkLabel(frame, text="Backup Drive to Image", font=ctk.CTkFont(size=15, weight="bold")).pack(
            pady=(14, 8), padx=16, anchor="w"
        )

        # Source
        r1 = ctk.CTkFrame(frame, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(r1, text="Source device:", width=130, anchor="w").pack(side="left")
        self._backup_src = ctk.CTkEntry(r1, placeholder_text="/dev/sdb  or  \\\\.\\PhysicalDrive1")
        self._backup_src.pack(side="left", fill="x", expand=True, padx=(4, 0))

        # Destination
        r2 = ctk.CTkFrame(frame, fg_color="transparent")
        r2.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(r2, text="Destination file:", width=130, anchor="w").pack(side="left")
        self._backup_dst = ctk.CTkEntry(r2, placeholder_text="backup.img")
        self._backup_dst.pack(side="left", fill="x", expand=True, padx=(4, 4))
        ctk.CTkButton(r2, text="Browse…", width=80, command=self._backup_browse_dst).pack(side="left")

        # Options
        r3 = ctk.CTkFrame(frame, fg_color="transparent")
        r3.pack(fill="x", padx=16, pady=4)
        self._backup_dry_run = ctk.CTkCheckBox(r3, text="Dry run (simulate)")
        self._backup_dry_run.pack(side="left", padx=(0, 16))

        ctk.CTkButton(
            frame, text="▶  Start Backup", fg_color=ACCENT,
            command=self._start_backup, font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(pady=(8, 14), padx=16, anchor="w")

        return frame

    # ------------------------------------------------------------------
    # Restore tab
    # ------------------------------------------------------------------

    def _build_restore_tab(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self._tab_frame, fg_color=BG_CARD, corner_radius=8)
        ctk.CTkLabel(frame, text="Restore Image to Drive", font=ctk.CTkFont(size=15, weight="bold")).pack(
            pady=(14, 8), padx=16, anchor="w"
        )

        r1 = ctk.CTkFrame(frame, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(r1, text="Image file:", width=130, anchor="w").pack(side="left")
        self._restore_src = ctk.CTkEntry(r1, placeholder_text="backup.img")
        self._restore_src.pack(side="left", fill="x", expand=True, padx=(4, 4))
        ctk.CTkButton(r1, text="Browse…", width=80, command=self._restore_browse_src).pack(side="left")

        r2 = ctk.CTkFrame(frame, fg_color="transparent")
        r2.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(r2, text="Target device:", width=130, anchor="w").pack(side="left")
        self._restore_dst = ctk.CTkEntry(r2, placeholder_text="/dev/sdc")
        self._restore_dst.pack(side="left", fill="x", expand=True, padx=(4, 0))

        r3 = ctk.CTkFrame(frame, fg_color="transparent")
        r3.pack(fill="x", padx=16, pady=4)
        self._restore_dry_run = ctk.CTkCheckBox(r3, text="Dry run")
        self._restore_dry_run.pack(side="left", padx=(0, 16))
        self._restore_no_verify = ctk.CTkCheckBox(r3, text="Skip verification")
        self._restore_no_verify.pack(side="left")

        ctk.CTkButton(
            frame, text="▶  Start Restore", fg_color=WARNING,
            command=self._start_restore, font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(pady=(8, 14), padx=16, anchor="w")

        return frame

    # ------------------------------------------------------------------
    # Flash tab
    # ------------------------------------------------------------------

    def _build_flash_tab(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self._tab_frame, fg_color=BG_CARD, corner_radius=8)
        ctk.CTkLabel(frame, text="Flash Image / ISO to USB", font=ctk.CTkFont(size=15, weight="bold")).pack(
            pady=(14, 8), padx=16, anchor="w"
        )

        r1 = ctk.CTkFrame(frame, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(r1, text="Image / ISO file:", width=130, anchor="w").pack(side="left")
        self._flash_src = ctk.CTkEntry(r1, placeholder_text="ubuntu-22.04.iso")
        self._flash_src.pack(side="left", fill="x", expand=True, padx=(4, 4))
        ctk.CTkButton(r1, text="Browse…", width=80, command=self._flash_browse_src).pack(side="left")

        r2 = ctk.CTkFrame(frame, fg_color="transparent")
        r2.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(r2, text="Target USB drive:", width=130, anchor="w").pack(side="left")
        self._flash_dst = ctk.CTkEntry(r2, placeholder_text="/dev/sdd")
        self._flash_dst.pack(side="left", fill="x", expand=True, padx=(4, 0))

        r3 = ctk.CTkFrame(frame, fg_color="transparent")
        r3.pack(fill="x", padx=16, pady=4)
        self._flash_dry_run = ctk.CTkCheckBox(r3, text="Dry run")
        self._flash_dry_run.pack(side="left", padx=(0, 16))
        self._flash_no_verify = ctk.CTkCheckBox(r3, text="Skip verification")
        self._flash_no_verify.pack(side="left")

        ctk.CTkButton(
            frame, text="⚡  Flash Drive", fg_color=DANGER,
            command=self._start_flash, font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(pady=(8, 14), padx=16, anchor="w")

        return frame

    # ------------------------------------------------------------------
    # Tab switching
    # ------------------------------------------------------------------

    def _switch_tab(self, tab_name: str) -> None:
        for frame in self._tabs.values():
            frame.pack_forget()
        self._tabs[tab_name].pack(fill="both", expand=True)
        self._current_tab = tab_name

    # ------------------------------------------------------------------
    # Drive refresh
    # ------------------------------------------------------------------

    def _refresh_drives(self) -> None:
        from disktool.core.disk import get_drives

        self._drive_status.configure(text="Scanning…")

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
        self._drive_status.configure(text=f"{len(drives)} drive(s) found")
        self._render_drives()

    # ------------------------------------------------------------------
    # File browsers
    # ------------------------------------------------------------------

    def _backup_browse_dst(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save image as",
            defaultextension=".img",
            filetypes=[("Disk image", "*.img"), ("All files", "*.*")],
        )
        if path:
            self._backup_dst.delete(0, "end")
            self._backup_dst.insert(0, path)

    def _restore_browse_src(self) -> None:
        path = filedialog.askopenfilename(
            title="Select image",
            filetypes=[("Disk images", "*.img *.iso *.zip"), ("All files", "*.*")],
        )
        if path:
            self._restore_src.delete(0, "end")
            self._restore_src.insert(0, path)

    def _flash_browse_src(self) -> None:
        path = filedialog.askopenfilename(
            title="Select image / ISO",
            filetypes=[("Images & ISOs", "*.img *.iso *.zip"), ("All files", "*.*")],
        )
        if path:
            self._flash_src.delete(0, "end")
            self._flash_src.insert(0, path)

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def _confirm_wipe(self, dest: str) -> bool:
        """Show a safety confirmation dialog. Returns True if user confirmed."""
        dest_info = next((d for d in self._drives if d.get("path") == dest), None)
        size_gb = dest_info.get("size_gb", "?") if dest_info else "?"
        model = dest_info.get("model", "unknown") if dest_info else "unknown"

        answer = simpledialog.askstring(
            "Confirm",
            f"⚠ You are about to WIPE {size_gb} GB {model} ({dest}).\n\n"
            "All data will be permanently destroyed.\n\n"
            "Type CONFIRM to proceed:",
            parent=self,
        )
        return answer == "CONFIRM"

    def _start_backup(self) -> None:
        src = self._backup_src.get().strip()
        dst = self._backup_dst.get().strip()
        dry = self._backup_dry_run.get() == 1

        if not src or not dst:
            messagebox.showerror("Missing input", "Please fill in source and destination.")
            return

        self._run_operation(
            op="backup",
            kwargs={"source": src, "dest": dst, "dry_run": dry},
        )

    def _start_restore(self) -> None:
        src = self._restore_src.get().strip()
        dst = self._restore_dst.get().strip()
        dry = self._restore_dry_run.get() == 1
        no_verify = self._restore_no_verify.get() == 1

        if not src or not dst:
            messagebox.showerror("Missing input", "Please fill in image and target.")
            return

        if not dry and not self._confirm_wipe(dst):
            return

        self._run_operation(
            op="restore",
            kwargs={"image": src, "dest": dst, "dry_run": dry, "verify": not no_verify},
        )

    def _start_flash(self) -> None:
        src = self._flash_src.get().strip()
        dst = self._flash_dst.get().strip()
        dry = self._flash_dry_run.get() == 1
        no_verify = self._flash_no_verify.get() == 1

        if not src or not dst:
            messagebox.showerror("Missing input", "Please fill in image and target.")
            return

        if not dry and not self._confirm_wipe(dst):
            return

        self._run_operation(
            op="flash",
            kwargs={"image": src, "dest": dst, "dry_run": dry, "verify": not no_verify},
        )

    def _run_operation(self, op: str, kwargs: dict[str, Any]) -> None:
        from disktool.core.imaging import backup, flash, restore

        dlg = ProgressDialog(self, title=op.capitalize() + "…")
        op_map = {"backup": backup, "restore": restore, "flash": flash}
        fn = op_map[op]

        def _progress(bytes_done: int, total: int, speed: float) -> None:
            if dlg.cancelled:
                raise InterruptedError("Operation cancelled by user.")
            self.after(0, lambda: dlg.update_progress(bytes_done, total, speed))

        def _worker() -> None:
            try:
                result = fn(**kwargs, progress_callback=_progress)
                self.after(0, lambda: dlg.finish("Complete!", success=True))
                self.after(
                    500,
                    lambda: messagebox.showinfo(
                        "Success",
                        f"{op.capitalize()} finished successfully!"
                        + (f"\nResult: {result}" if result else ""),
                    ),
                )
            except InterruptedError:
                self.after(0, lambda: dlg.finish("Cancelled.", success=False))
            except Exception as exc:
                logger.error("%s failed: %s", op, exc)
                self.after(0, lambda: dlg.finish(f"Error: {exc}", success=False))
                self.after(
                    500,
                    lambda: messagebox.showerror("Error", str(exc)),
                )

        threading.Thread(target=_worker, daemon=True).start()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_gui() -> None:
    """Launch the DiskImager GUI application."""
    if ctk is None:
        raise ImportError(
            "customtkinter is not installed. "
            "Install it with: pip install customtkinter"
        ) from _IMPORT_ERROR  # type: ignore[name-defined]

    app = DiskImagerApp()
    app.mainloop()


if __name__ == "__main__":  # pragma: no cover
    run_gui()
