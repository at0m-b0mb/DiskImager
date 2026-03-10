"""CLI entry point for DiskImager using Click + Rich."""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

console = Console()


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_confirmation(message: str) -> None:
    """Ask the user to type CONFIRM or abort."""
    console.print(
        Panel(
            f"[bold red]⚠  WARNING[/bold red]\n{message}\n\n"
            "[yellow]Type [bold]CONFIRM[/bold] to proceed, or anything else to abort.[/yellow]",
            border_style="red",
        )
    )
    answer = input("> ").strip()
    if answer != "CONFIRM":
        console.print("[bold red]Aborted.[/bold red]")
        sys.exit(1)


def _make_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False,
    )


# ---------------------------------------------------------------------------
# CLI root
# ---------------------------------------------------------------------------

@click.group()
@click.option("--verbose", "-v", is_flag=True, default=False, help="Enable debug logging.")
@click.version_option("1.0.0", prog_name="disktool")
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    """DiskImager – cross-platform disk imaging, cloning, and flashing tool."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    _configure_logging(verbose)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@main.command("list")
@click.pass_context
def cmd_list(ctx: click.Context) -> None:
    """List all detected physical drives."""
    from disktool.core.disk import get_drives

    with console.status("[bold green]Scanning drives…[/bold green]"):
        drives = get_drives()

    if not drives:
        console.print("[yellow]No physical drives detected.[/yellow]")
        return

    table = Table(title="Physical Drives", show_header=True, header_style="bold cyan", border_style="bright_black")
    table.add_column("ID", style="bold", width=4, justify="right")
    table.add_column("Device", style="cyan")
    table.add_column("Size", justify="right")
    table.add_column("Type", justify="center")
    table.add_column("Boot?", justify="center")
    table.add_column("Model")
    table.add_column("Parts", justify="right")

    for drive in drives:
        size_gb = drive.get("size_gb", 0)
        size_str = f"{size_gb:.1f} GB" if size_gb >= 1 else f"{size_gb * 1024:.0f} MB"

        if drive.get("is_removable"):
            dtype = Text("🔌 USB", style="yellow")
        else:
            dtype = Text("Internal", style="blue")

        if drive.get("is_system"):
            boot = Text("❌ YES", style="bold red")
        else:
            boot = Text("✅ NO", style="green")

        table.add_row(
            str(drive["index"]),
            drive.get("path", ""),
            size_str,
            dtype,
            boot,
            drive.get("model", "Unknown"),
            str(len(drive.get("partitions", []))),
        )

    console.print(table)


# ---------------------------------------------------------------------------
# backup
# ---------------------------------------------------------------------------

@main.command("backup")
@click.argument("source")
@click.argument("dest")
@click.option("--dry-run", is_flag=True, default=False, help="Simulate without writing.")
@click.option("--no-verify", is_flag=True, default=False, help="Skip post-backup hash verification.")
@click.pass_context
def cmd_backup(ctx: click.Context, source: str, dest: str, dry_run: bool, no_verify: bool) -> None:
    """Backup SOURCE device to DEST image file.

    Example:
        disktool backup /dev/sdb backup.img
    """
    from disktool.core.disk import get_drives
    from disktool.core.imaging import backup

    # Safety check
    drives = get_drives()
    for drive in drives:
        if drive.get("path") == source and drive.get("is_system"):
            _require_confirmation(
                f"[bold]{source}[/bold] appears to be your [red]system disk[/red]. "
                "Imaging a live system disk may produce an inconsistent image."
            )
            break

    if not dry_run:
        dest_path = Path(dest)
        if dest_path.exists():
            _require_confirmation(
                f"[bold]{dest}[/bold] already exists and will be [red]overwritten[/red]."
            )

    task_id = None
    with _make_progress() as progress:
        task_id = progress.add_task(f"Backup {source}", total=None)

        def _progress(bytes_done: int, total: int, speed: float) -> None:
            progress.update(task_id, completed=bytes_done, total=total if total else None)

        try:
            digest = backup(source, dest, dry_run=dry_run, progress_callback=_progress)
        except PermissionError:
            console.print(f"\n[bold red]Permission denied.[/bold red] Try running as root/Administrator.")
            sys.exit(1)
        except FileNotFoundError as exc:
            console.print(f"\n[bold red]Error:[/bold red] {exc}")
            sys.exit(1)

    if dry_run:
        console.print("[yellow][DRY RUN] No data written.[/yellow]")
    else:
        console.print(f"\n[bold green]✓ Backup complete![/bold green]")
        console.print(f"  Image : [cyan]{dest}[/cyan]")
        console.print(f"  SHA-256: [dim]{digest}[/dim]")
        if not no_verify:
            console.print("[dim]Hint: run [bold]disktool verify[/bold] to re-check the image.[/dim]")


# ---------------------------------------------------------------------------
# restore
# ---------------------------------------------------------------------------

@main.command("restore")
@click.argument("image")
@click.argument("dest")
@click.option("--dry-run", is_flag=True, default=False, help="Simulate without writing.")
@click.option("--dangerous", is_flag=True, default=False, help="Allow writing to system disks.")
@click.option("--no-verify", is_flag=True, default=False, help="Skip post-restore verification.")
@click.pass_context
def cmd_restore(
    ctx: click.Context,
    image: str,
    dest: str,
    dry_run: bool,
    dangerous: bool,
    no_verify: bool,
) -> None:
    """Restore IMAGE file to DEST device.

    Example:
        disktool restore backup.img /dev/sdc
    """
    from disktool.core.disk import get_drives
    from disktool.core.imaging import restore

    drives = get_drives()
    dest_info = next((d for d in drives if d.get("path") == dest), None)

    if dest_info and dest_info.get("is_system") and not dangerous:
        console.print(
            f"[bold red]Error:[/bold red] {dest} is a system disk. "
            "Use [bold]--dangerous[/bold] to override this safety check."
        )
        sys.exit(1)

    size_gb = dest_info.get("size_gb", "?") if dest_info else "?"
    model = dest_info.get("model", "unknown device") if dest_info else "unknown device"

    if not dry_run:
        _require_confirmation(
            f"About to [red]WIPE[/red] [bold]{size_gb} GB {model}[/bold] ({dest}).\n"
            "All data on the target will be permanently destroyed."
        )

    with _make_progress() as progress:
        task_id = progress.add_task(f"Restore -> {dest}", total=None)

        def _progress(bytes_done: int, total: int, speed: float) -> None:
            progress.update(task_id, completed=bytes_done, total=total if total else None)

        try:
            ok = restore(image, dest, dry_run=dry_run, verify=not no_verify, progress_callback=_progress)
        except (FileNotFoundError, ValueError) as exc:
            console.print(f"\n[bold red]Error:[/bold red] {exc}")
            sys.exit(1)
        except PermissionError:
            console.print(f"\n[bold red]Permission denied.[/bold red] Try running as root/Administrator.")
            sys.exit(1)

    if dry_run:
        console.print("[yellow][DRY RUN] No data written.[/yellow]")
    elif ok:
        console.print(f"\n[bold green]✓ Restore complete![/bold green]")
    else:
        console.print(f"\n[bold red]✗ Restore failed or verification mismatch.[/bold red]")
        sys.exit(2)


# ---------------------------------------------------------------------------
# flash
# ---------------------------------------------------------------------------

@main.command("flash")
@click.argument("image")
@click.argument("dest")
@click.option("--dry-run", is_flag=True, default=False, help="Simulate without writing.")
@click.option("--dangerous", is_flag=True, default=False, help="Allow writing to system disks.")
@click.option("--no-verify", is_flag=True, default=False, help="Skip post-flash verification.")
@click.pass_context
def cmd_flash(
    ctx: click.Context,
    image: str,
    dest: str,
    dry_run: bool,
    dangerous: bool,
    no_verify: bool,
) -> None:
    """Flash IMAGE (.img/.iso/.zip) to DEST USB drive.

    Example:
        disktool flash ubuntu-22.04.iso /dev/sdd --verify
    """
    from disktool.core.disk import get_drives
    from disktool.core.imaging import flash

    drives = get_drives()
    dest_info = next((d for d in drives if d.get("path") == dest), None)

    if dest_info and dest_info.get("is_system") and not dangerous:
        console.print(
            f"[bold red]Error:[/bold red] {dest} is a system disk. "
            "Use [bold]--dangerous[/bold] to override."
        )
        sys.exit(1)

    size_gb = dest_info.get("size_gb", "?") if dest_info else "?"
    model = dest_info.get("model", "unknown device") if dest_info else "unknown device"

    if not dry_run:
        _require_confirmation(
            f"About to flash [cyan]{Path(image).name}[/cyan] onto "
            f"[bold]{size_gb} GB {model}[/bold] ({dest}).\n"
            "All data on the target will be permanently destroyed."
        )

    with _make_progress() as progress:
        task_id = progress.add_task(f"Flash {Path(image).name} -> {dest}", total=None)

        def _progress(bytes_done: int, total: int, speed: float) -> None:
            progress.update(task_id, completed=bytes_done, total=total if total else None)

        try:
            ok = flash(image, dest, dry_run=dry_run, verify=not no_verify, progress_callback=_progress)
        except (FileNotFoundError, ValueError) as exc:
            console.print(f"\n[bold red]Error:[/bold red] {exc}")
            sys.exit(1)
        except PermissionError:
            console.print(f"\n[bold red]Permission denied.[/bold red] Try running as root/Administrator.")
            sys.exit(1)

    if dry_run:
        console.print("[yellow][DRY RUN] No data written.[/yellow]")
    elif ok:
        console.print(f"\n[bold green]✓ Flash complete![/bold green]")
    else:
        console.print(f"\n[bold red]✗ Flash failed or verification mismatch.[/bold red]")
        sys.exit(2)


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

@main.command("verify")
@click.argument("image")
@click.option("--hash", "expected_hash", default=None, help="Expected SHA-256 digest to compare against.")
@click.pass_context
def cmd_verify(ctx: click.Context, image: str, expected_hash: Optional[str]) -> None:
    """Compute and optionally verify the SHA-256 hash of IMAGE.

    Example:
        disktool verify backup.img
        disktool verify backup.img --hash abc123...
    """
    from disktool.core.verify import hash_file, read_sidecar

    image_path = Path(image)
    if not image_path.exists():
        console.print(f"[bold red]Error:[/bold red] File not found: {image}")
        sys.exit(1)

    # Try loading sidecar hash
    if expected_hash is None:
        sidecar = read_sidecar(image_path)
        if sidecar:
            algo, expected_hash = sidecar
            console.print(f"[dim]Using sidecar hash ({algo}): {expected_hash}[/dim]")

    total_bytes = image_path.stat().st_size

    with _make_progress() as progress:
        task_id = progress.add_task(f"Hashing {image_path.name}", total=total_bytes)

        def _progress(done: int) -> None:
            progress.update(task_id, completed=done)

        digest = hash_file(image_path, progress_callback=_progress)

    console.print(f"\n  SHA-256: [cyan]{digest}[/cyan]")

    if expected_hash:
        if digest.lower() == expected_hash.lower():
            console.print("[bold green]✓ Hash match – image is intact.[/bold green]")
        else:
            console.print(f"[bold red]✗ Hash mismatch![/bold red]")
            console.print(f"  Expected: [red]{expected_hash.lower()}[/red]")
            console.print(f"  Got:      [red]{digest}[/red]")
            sys.exit(2)


# ---------------------------------------------------------------------------
# gui launcher (convenience)
# ---------------------------------------------------------------------------

@main.command("gui")
def cmd_gui() -> None:
    """Launch the graphical user interface."""
    try:
        from disktool.gui import run_gui

        run_gui()
    except ImportError as exc:
        console.print(f"[bold red]GUI dependencies not installed:[/bold red] {exc}")
        console.print("Install with: [bold]pip install customtkinter[/bold]")
        sys.exit(1)
    except Exception as exc:  # e.g. tkinter.TclError on a headless server
        console.print(f"[bold red]Failed to launch GUI:[/bold red] {exc}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# clone
# ---------------------------------------------------------------------------

@main.command("clone")
@click.argument("source")
@click.argument("dest")
@click.option("--dry-run", is_flag=True, default=False, help="Simulate without writing.")
@click.option("--dangerous", is_flag=True, default=False, help="Allow cloning to/from system disks.")
@click.option("--no-verify", is_flag=True, default=False, help="Skip post-clone SHA-256 verification.")
@click.pass_context
def cmd_clone(
    ctx: click.Context,
    source: str,
    dest: str,
    dry_run: bool,
    dangerous: bool,
    no_verify: bool,
) -> None:
    """Clone SOURCE device directly to DEST device (no intermediate file).

    Both SOURCE and DEST must be accessible block devices or files.
    All data on DEST will be overwritten.

    Example:
        disktool clone /dev/sdb /dev/sdc
    """
    from disktool.core.disk import get_drives
    from disktool.core.imaging import clone

    drives = get_drives()
    dest_info = next((d for d in drives if d.get("path") == dest), None)

    if dest_info and dest_info.get("is_system") and not dangerous:
        console.print(
            f"[bold red]Error:[/bold red] {dest} is a system disk. "
            "Use [bold]--dangerous[/bold] to override this safety check."
        )
        sys.exit(1)

    size_gb = dest_info.get("size_gb", "?") if dest_info else "?"
    model = dest_info.get("model", "unknown device") if dest_info else "unknown device"

    if not dry_run:
        _require_confirmation(
            f"About to clone [cyan]{source}[/cyan] directly onto "
            f"[bold]{size_gb} GB {model}[/bold] ({dest}).\n"
            "All data on the target will be permanently destroyed."
        )

    with _make_progress() as progress:
        task_id = progress.add_task(f"Clone {source} -> {dest}", total=None)

        def _progress(bytes_done: int, total: int, speed: float) -> None:
            progress.update(task_id, completed=bytes_done, total=total if total else None)

        try:
            digest = clone(
                source, dest, dry_run=dry_run, verify=not no_verify,
                progress_callback=_progress,
            )
        except (FileNotFoundError, ValueError) as exc:
            console.print(f"\n[bold red]Error:[/bold red] {exc}")
            sys.exit(1)
        except PermissionError:
            console.print(f"\n[bold red]Permission denied.[/bold red] Try running as root/Administrator.")
            sys.exit(1)

    if dry_run:
        console.print("[yellow][DRY RUN] No data written.[/yellow]")
    elif digest:
        console.print(f"\n[bold green]✓ Clone complete![/bold green]")
        console.print(f"  SHA-256: [dim]{digest}[/dim]")
    else:
        console.print(f"\n[bold red]✗ Clone failed.[/bold red]")
        sys.exit(2)


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------

@main.command("info")
@click.argument("device")
@click.pass_context
def cmd_info(ctx: click.Context, device: str) -> None:
    """Show detailed information about DEVICE.

    Example:
        disktool info /dev/sda
    """
    from disktool.core.disk import format_size, get_drives

    with console.status("[bold green]Scanning drives…[/bold green]"):
        drives = get_drives()

    drive = next((d for d in drives if d.get("path") == device), None)
    if not drive:
        console.print(f"[bold red]Error:[/bold red] Device [cyan]{device}[/cyan] not found in drive list.")
        console.print("[dim]Run [bold]disktool list[/bold] to see available devices.[/dim]")
        sys.exit(1)

    console.print()
    console.print(Rule(f"[bold cyan]Drive Info: {device}[/bold cyan]"))

    # Main info table
    info_table = Table(show_header=False, box=None, padding=(0, 2))
    info_table.add_column("Key", style="dim", width=18)
    info_table.add_column("Value", style="bold")

    def yn(val: bool) -> Text:
        return Text("Yes", style="bold red") if val else Text("No", style="green")

    info_table.add_row("Device", f"[cyan]{drive.get('path', '')}[/cyan]")
    info_table.add_row("Model", drive.get("model", "Unknown"))
    size_bytes = drive.get("size_bytes", 0)
    info_table.add_row("Size", f"{format_size(size_bytes).strip()}  ([dim]{size_bytes:,} bytes[/dim])")
    info_table.add_row("Removable", yn(drive.get("is_removable", False)))
    info_table.add_row("System Disk", yn(drive.get("is_system", False)))
    info_table.add_row("Partitions", str(len(drive.get("partitions", []))))

    console.print(info_table)

    partitions = drive.get("partitions", [])
    if partitions:
        console.print()
        console.print(Rule("[dim]Partitions[/dim]"))
        part_table = Table(
            show_header=True,
            header_style="bold cyan",
            border_style="bright_black",
        )
        part_table.add_column("Name")
        part_table.add_column("Path", style="cyan")
        part_table.add_column("Size", justify="right")
        part_table.add_column("Mount Point")
        part_table.add_column("Filesystem")

        for part in partitions:
            psize = part.get("size_bytes", 0)
            part_table.add_row(
                part.get("name", ""),
                part.get("path", ""),
                format_size(psize).strip(),
                part.get("mountpoint", "—") or "—",
                part.get("filesystem", "—") or "—",
            )
        console.print(part_table)
    console.print()


# ---------------------------------------------------------------------------
# format
# ---------------------------------------------------------------------------

@main.command("format")
@click.argument("device")
@click.argument("filesystem")
@click.option("--label", default="DISK", show_default=True,
              help="Volume label written to the new file system.")
@click.option("--dry-run", is_flag=True, default=False, help="Simulate without formatting.")
@click.option("--dangerous", is_flag=True, default=False, help="Allow formatting system disks.")
@click.option("--list-fs", is_flag=True, default=False,
              help="List supported file systems on this platform and exit.")
@click.pass_context
def cmd_format(
    ctx: click.Context,
    device: str,
    filesystem: str,
    label: str,
    dry_run: bool,
    dangerous: bool,
    list_fs: bool,
) -> None:
    """Format DEVICE with FILESYSTEM.

    DEVICE is the path to a block device or partition (e.g. /dev/disk4,
    /dev/sdb, \\\\.\\PhysicalDrive1, or a Windows drive letter like E:).

    FILESYSTEM is the target file system.  Common values:

    \b
        fat32   – FAT32 (SD cards, USB sticks, cross-platform)
        exfat   – exFAT (large files, cross-platform)
        ntfs    – NTFS  (Windows)
        ext4    – ext4  (Linux)
        hfs+    – HFS+  (macOS, journaled)
        apfs    – APFS  (macOS 10.13+)

    Run with --list-fs to see all file systems supported on this platform.

    Example:

        disktool format /dev/disk4 fat32 --label MIYOO

        disktool format /dev/sdb ext4 --label DATA

        disktool format E: ntfs --label BACKUP
    """
    from disktool.core.format import (
        filesystem_label,
        format_disk,
        list_supported_filesystems,
    )

    if list_fs:
        supported = list_supported_filesystems()
        console.print("\n[bold cyan]Supported file systems on this platform:[/bold cyan]\n")
        for fs in supported:
            console.print(f"  [green]•[/green] [bold]{fs}[/bold]  ([dim]{filesystem_label(fs)}[/dim])")
        console.print()
        return

    from disktool.core.disk import get_drives

    drives = get_drives()
    dest_info = next((d for d in drives if d.get("path") == device), None)

    if dest_info and dest_info.get("is_system") and not dangerous:
        console.print(
            f"[bold red]Error:[/bold red] {device} is a system disk. "
            "Use [bold]--dangerous[/bold] to override this safety check."
        )
        sys.exit(1)

    size_gb = dest_info.get("size_gb", "?") if dest_info else "?"
    model = dest_info.get("model", "unknown device") if dest_info else "unknown device"
    fs_display = filesystem_label(filesystem)

    if not dry_run:
        _require_confirmation(
            f"About to [red]FORMAT[/red] [bold]{size_gb} GB {model}[/bold] ({device})\n"
            f"as [bold cyan]{fs_display}[/bold cyan] with label [bold]{label!r}[/bold].\n\n"
            "All data on the target will be permanently destroyed."
        )

    try:
        ok = format_disk(device, filesystem, label=label, dry_run=dry_run)
    except ValueError as exc:
        console.print(f"\n[bold red]Error:[/bold red] {exc}")
        sys.exit(1)
    except FileNotFoundError as exc:
        console.print(f"\n[bold red]Formatting tool not found:[/bold red] {exc}")
        sys.exit(1)
    except OSError as exc:
        console.print(f"\n[bold red]Format failed:[/bold red] {exc}")
        sys.exit(1)
    except PermissionError:
        console.print("\n[bold red]Permission denied.[/bold red] Try running as root/Administrator.")
        sys.exit(1)

    if dry_run:
        console.print("[yellow][DRY RUN] No changes made.[/yellow]")
    elif ok:
        console.print(
            f"\n[bold green]✓ Format complete![/bold green]  "
            f"[cyan]{device}[/cyan] is now [bold]{fs_display}[/bold]"
            + (f" (label: [bold]{label}[/bold])" if label else "")
            + "."
        )
    else:
        console.print(f"\n[bold red]✗ Format failed.[/bold red]")
        sys.exit(2)


# ---------------------------------------------------------------------------
# erase
# ---------------------------------------------------------------------------

@main.command("erase")
@click.argument("dest")
@click.option("--passes", default=1, show_default=True, type=click.IntRange(1, 7),
              help="Number of overwrite passes (1=zeros, 2+=random+zeros).")
@click.option("--dry-run", is_flag=True, default=False, help="Simulate without writing.")
@click.option("--dangerous", is_flag=True, default=False, help="Allow erasing system disks.")
@click.pass_context
def cmd_erase(
    ctx: click.Context,
    dest: str,
    passes: int,
    dry_run: bool,
    dangerous: bool,
) -> None:
    """Securely erase DEST by overwriting with zeros.

    Use --passes 3 for a DoD-style multi-pass wipe (random data then zeros).

    Example:
        disktool erase /dev/sdb
        disktool erase /dev/sdb --passes 3
    """
    from disktool.core.disk import get_drives
    from disktool.core.imaging import erase

    drives = get_drives()
    dest_info = next((d for d in drives if d.get("path") == dest), None)

    if dest_info and dest_info.get("is_system") and not dangerous:
        console.print(
            f"[bold red]Error:[/bold red] {dest} is a system disk. "
            "Use [bold]--dangerous[/bold] to override this safety check."
        )
        sys.exit(1)

    size_gb = dest_info.get("size_gb", "?") if dest_info else "?"
    model = dest_info.get("model", "unknown device") if dest_info else "unknown device"

    if not dry_run:
        _require_confirmation(
            f"About to [red]SECURELY ERASE[/red] [bold]{size_gb} GB {model}[/bold] ({dest})\n"
            f"using [bold]{passes}[/bold] pass(es).\n\n"
            "All data will be permanently and irrecoverably destroyed."
        )

    with _make_progress() as progress:
        task_id = progress.add_task(
            f"Erase {dest} ({passes} {'passes' if passes != 1 else 'pass'})", total=None
        )

        def _progress(bytes_done: int, total: int, speed: float) -> None:
            progress.update(task_id, completed=bytes_done, total=total if total else None)

        try:
            ok = erase(dest, passes=passes, dry_run=dry_run, progress_callback=_progress)
        except (FileNotFoundError, ValueError) as exc:
            console.print(f"\n[bold red]Error:[/bold red] {exc}")
            sys.exit(1)
        except PermissionError:
            console.print(f"\n[bold red]Permission denied.[/bold red] Try running as root/Administrator.")
            sys.exit(1)

    if dry_run:
        console.print("[yellow][DRY RUN] No data erased.[/yellow]")
    elif ok:
        console.print(f"\n[bold green]✓ Erase complete![/bold green]")
    else:
        console.print(f"\n[bold red]✗ Erase failed.[/bold red]")
        sys.exit(2)


# ---------------------------------------------------------------------------
# benchmark
# ---------------------------------------------------------------------------

@main.command("benchmark")
@click.argument("device")
@click.option("--size", "size_mb", default=64, show_default=True, type=click.IntRange(1, 4096),
              help="Amount of data to read/write per test phase (MB).")
@click.option("--block-size", "block_size_mb", default=4, show_default=True,
              type=click.IntRange(1, 64),
              help="I/O block size in megabytes.")
@click.option("--write", "do_write", is_flag=True, default=False,
              help="Also run a sequential write benchmark.")
@click.option("--read-only", "read_only", is_flag=True, default=False,
              help="Skip the read benchmark (only meaningful with --write).")
@click.pass_context
def cmd_benchmark(
    ctx: click.Context,
    device: str,
    size_mb: int,
    block_size_mb: int,
    do_write: bool,
    read_only: bool,
) -> None:
    """Measure sequential read (and optionally write) throughput of DEVICE.

    DEVICE can be a block device path or a directory (for write tests).

    Examples:

        disktool benchmark /dev/sdb

        disktool benchmark /dev/sdb --size 128 --write

        disktool benchmark /tmp --write --read-only
    """
    from disktool.core.benchmark import benchmark_read, benchmark_write

    do_read = not read_only

    if not do_read and not do_write:
        console.print("[bold red]Error:[/bold red] Nothing to do. "
                      "Pass [bold]--write[/bold] or remove [bold]--read-only[/bold].")
        sys.exit(1)

    console.print(
        f"\n[bold cyan]Disk Benchmark[/bold cyan]  "
        f"[dim]{device}[/dim]  "
        f"size=[bold]{size_mb} MB[/bold]  block=[bold]{block_size_mb} MB[/bold]\n"
    )

    results: dict[str, dict] = {}

    if do_read:
        with _make_progress() as progress:
            task_id = progress.add_task(f"Read  {device}", total=size_mb * 1024 * 1024)

            def _read_progress(done: int, total: int, speed: float) -> None:
                progress.update(task_id, completed=done, total=total)

            try:
                results["read"] = benchmark_read(
                    device,
                    size_mb=size_mb,
                    block_size_mb=block_size_mb,
                    progress_callback=_read_progress,
                )
            except FileNotFoundError as exc:
                console.print(f"\n[bold red]Error:[/bold red] {exc}")
                sys.exit(1)
            except PermissionError:
                console.print("\n[bold red]Permission denied.[/bold red] Try running as root/Administrator.")
                sys.exit(1)
            except OSError as exc:
                console.print(f"\n[bold red]Read error:[/bold red] {exc}")
                sys.exit(1)

    if do_write:
        with _make_progress() as progress:
            task_id = progress.add_task(f"Write {device}", total=size_mb * 1024 * 1024)

            def _write_progress(done: int, total: int, speed: float) -> None:
                progress.update(task_id, completed=done, total=total)

            try:
                results["write"] = benchmark_write(
                    device,
                    size_mb=size_mb,
                    block_size_mb=block_size_mb,
                    progress_callback=_write_progress,
                )
            except PermissionError:
                console.print("\n[bold red]Permission denied.[/bold red] Try running as root/Administrator.")
                sys.exit(1)
            except OSError as exc:
                console.print(f"\n[bold red]Write error:[/bold red] {exc}")
                sys.exit(1)

    # Summary table
    table = Table(
        title="Benchmark Results",
        show_header=True,
        header_style="bold cyan",
        border_style="bright_black",
    )
    table.add_column("Operation", style="bold", width=10)
    table.add_column("Size (MB)", justify="right")
    table.add_column("Duration (s)", justify="right")
    table.add_column("Speed (MB/s)", justify="right", style="bold green")

    for op, r in results.items():
        table.add_row(
            op.capitalize(),
            f"{r['size_mb']:.1f}",
            f"{r['duration_s']:.3f}",
            f"{r['speed_mb_s']:.2f}",
        )

    console.print()
    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# partition
# ---------------------------------------------------------------------------

@main.command("partition")
@click.argument("device")
@click.argument("scheme", metavar="SCHEME")
@click.option(
    "--add", "partitions", multiple=True, metavar="SIZE[:FS[:LABEL]]",
    help=(
        "Add a partition after creating the table. "
        "SIZE is a percentage (50%) or size with unit (8G, 512M). "
        "Optional FS sets the partition type hint (fat32, ext4, ntfs, …). "
        "Optional LABEL sets the partition name. "
        "Repeat to add multiple partitions."
    ),
)
@click.option("--dry-run", is_flag=True, default=False, help="Simulate without writing.")
@click.option("--dangerous", is_flag=True, default=False, help="Allow partitioning system disks.")
@click.pass_context
def cmd_partition(
    ctx: click.Context,
    device: str,
    scheme: str,
    partitions: tuple[str, ...],
    dry_run: bool,
    dangerous: bool,
) -> None:
    """Create a new MBR or GPT partition table on DEVICE.

    SCHEME must be 'mbr' or 'gpt'.

    Use --add to define partitions immediately after creating the table.
    Each --add value is SIZE[:FS[:LABEL]], for example:

    \b
        --add 100%                      full-disk, no type hint
        --add 8G:fat32:BOOT             8 GB FAT32 partition named BOOT
        --add 50%:ext4 --add 50%:ext4   two equal ext4 partitions

    After partitioning, use [bold]disktool format[/bold] to write a file system.

    Examples:

        disktool partition /dev/sdb gpt

        disktool partition /dev/sdb mbr --add 100%:fat32

        disktool partition /dev/sdb gpt --add 512M:fat32:EFI --add 100%:ext4:ROOT
    """
    from disktool.core.disk import get_drives
    from disktool.core.partition import (
        add_partition,
        create_partition_table,
        list_partition_schemes,
    )

    supported = list_partition_schemes()
    if scheme.lower() not in supported:
        console.print(
            f"[bold red]Error:[/bold red] Unsupported scheme {scheme!r}. "
            f"Supported: {', '.join(supported)}"
        )
        sys.exit(1)

    drives = get_drives()
    dest_info = next((d for d in drives if d.get("path") == device), None)

    if dest_info and dest_info.get("is_system") and not dangerous:
        console.print(
            f"[bold red]Error:[/bold red] {device} is a system disk. "
            "Use [bold]--dangerous[/bold] to override this safety check."
        )
        sys.exit(1)

    size_gb = dest_info.get("size_gb", "?") if dest_info else "?"
    model = dest_info.get("model", "unknown device") if dest_info else "unknown device"

    if not dry_run:
        part_desc = ""
        if partitions:
            part_desc = "\n  Partitions: " + "  |  ".join(partitions)
        _require_confirmation(
            f"About to [red]REPARTITION[/red] [bold]{size_gb} GB {model}[/bold] ({device})\n"
            f"as [bold cyan]{scheme.upper()}[/bold cyan].{part_desc}\n\n"
            "All data on the target will be permanently destroyed."
        )

    try:
        create_partition_table(device, scheme, dry_run=dry_run)
    except ValueError as exc:
        console.print(f"\n[bold red]Error:[/bold red] {exc}")
        sys.exit(1)
    except FileNotFoundError as exc:
        console.print(f"\n[bold red]Partitioning tool not found:[/bold red] {exc}")
        sys.exit(1)
    except OSError as exc:
        console.print(f"\n[bold red]Partition failed:[/bold red] {exc}")
        sys.exit(1)
    except PermissionError:
        console.print("\n[bold red]Permission denied.[/bold red] Try running as root/Administrator.")
        sys.exit(1)

    if dry_run:
        console.print(f"[yellow][DRY RUN] Would create {scheme.upper()} table on {device}.[/yellow]")
    else:
        console.print(
            f"\n[bold green]✓ {scheme.upper()} partition table created on {device}.[/bold green]"
        )

    # Add any requested partitions
    for spec in partitions:
        parts = spec.split(":", 2)
        p_size = parts[0].strip()
        p_fs = parts[1].strip() if len(parts) > 1 else None
        p_label = parts[2].strip() if len(parts) > 2 else None

        try:
            add_partition(device, size=p_size, filesystem=p_fs, label=p_label, dry_run=dry_run)
        except (FileNotFoundError, OSError, ValueError) as exc:
            console.print(f"[bold red]Failed to add partition {spec!r}:[/bold red] {exc}")
            sys.exit(1)
        except PermissionError:
            console.print("\n[bold red]Permission denied.[/bold red] Try running as root/Administrator.")
            sys.exit(1)

        if dry_run:
            label_str = f" label={p_label!r}" if p_label else ""
            fs_str = f" type={p_fs}" if p_fs else ""
            console.print(
                f"[yellow][DRY RUN] Would add partition: size={p_size}{fs_str}{label_str}[/yellow]"
            )
        else:
            fs_str = f" ({p_fs})" if p_fs else ""
            console.print(
                f"  [green]•[/green] Partition added: [bold]{p_size}[/bold]{fs_str}"
                + (f"  label=[bold]{p_label}[/bold]" if p_label else "")
            )

    if not dry_run and partitions:
        console.print(
            "\n[dim]Tip: run [bold]disktool format[/bold] to write a file system to each partition.[/dim]"
        )


# ---------------------------------------------------------------------------
# compress / decompress
# ---------------------------------------------------------------------------

@main.command("compress")
@click.argument("image")
@click.option(
    "--algorithm", "-a",
    default="gzip", show_default=True,
    type=click.Choice(["gzip", "lz4", "zstd"], case_sensitive=False),
    help="Compression algorithm.",
)
@click.option("--level", default=None, type=click.IntRange(1, 22),
              help="Compression level (algorithm-specific).  Default: algorithm default.")
@click.option("--output", "-o", default=None,
              help="Output path.  Default: IMAGE with algorithm extension appended.")
@click.option("--decompress", "-d", is_flag=True, default=False,
              help="Decompress instead of compress.")
@click.pass_context
def cmd_compress(
    ctx: click.Context,
    image: str,
    algorithm: str,
    level: Optional[int],
    output: Optional[str],
    decompress: bool,
) -> None:
    """Compress or decompress a disk IMAGE.

    Supported algorithms: gzip (always), lz4 (pip install lz4),
    zstd (pip install zstandard).

    Examples:

        disktool compress backup.img

        disktool compress backup.img --algorithm zstd --level 3

        disktool compress backup.img.gz --decompress

        disktool compress backup.img.lz4 -d -o restored.img
    """
    from disktool.core.compress import (
        compress_image,
        decompress_image,
        detect_algorithm,
        list_supported_algorithms,
    )

    supported = list_supported_algorithms()

    if decompress:
        # Auto-detect algorithm from extension
        detected = detect_algorithm(image)
        if detected and detected not in supported:
            console.print(
                f"[bold red]Error:[/bold red] Algorithm {detected!r} is not available. "
                f"Install the required package first."
            )
            sys.exit(1)
        if detected is None:
            console.print(
                f"[bold red]Error:[/bold red] Cannot detect compression algorithm from "
                f"extension {Path(image).suffix!r}."
            )
            sys.exit(1)

        image_path = Path(image)
        total_bytes = image_path.stat().st_size if image_path.exists() else 0

        with _make_progress() as progress:
            task_id = progress.add_task(f"Decompress {image_path.name}", total=total_bytes)

            def _dprogress(done: int, total: int, speed: float) -> None:
                progress.update(task_id, completed=done, total=total or None)

            try:
                result_path = decompress_image(image, output=output, progress_callback=_dprogress)
            except (FileNotFoundError, ValueError, RuntimeError) as exc:
                console.print(f"\n[bold red]Error:[/bold red] {exc}")
                sys.exit(1)

        console.print(f"\n[bold green]✓ Decompressed![/bold green]  → [cyan]{result_path}[/cyan]")
        return

    # Compress
    algorithm = algorithm.lower()
    if algorithm not in supported:
        console.print(
            f"[bold red]Error:[/bold red] Algorithm {algorithm!r} is not available.\n"
            f"Available: {', '.join(supported)}\n"
            f"Install with: pip install {'lz4' if algorithm == 'lz4' else 'zstandard'}"
        )
        sys.exit(1)

    image_path = Path(image)
    if not image_path.exists():
        console.print(f"[bold red]Error:[/bold red] File not found: {image}")
        sys.exit(1)
    total_bytes = image_path.stat().st_size

    with _make_progress() as progress:
        task_id = progress.add_task(f"Compress {image_path.name} ({algorithm})", total=total_bytes)

        def _cprogress(done: int, total: int, speed: float) -> None:
            progress.update(task_id, completed=done, total=total or None)

        try:
            result_path = compress_image(
                image, algorithm=algorithm, level=level, output=output,
                progress_callback=_cprogress,
            )
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            console.print(f"\n[bold red]Error:[/bold red] {exc}")
            sys.exit(1)

    in_size = total_bytes
    out_size = result_path.stat().st_size
    ratio = (1 - out_size / in_size) * 100 if in_size > 0 else 0
    console.print(f"\n[bold green]✓ Compressed![/bold green]  → [cyan]{result_path}[/cyan]")
    console.print(
        f"  Input:  [dim]{in_size:,} bytes[/dim]\n"
        f"  Output: [dim]{out_size:,} bytes[/dim]\n"
        f"  Saving: [bold green]{ratio:.1f}%[/bold green]"
    )


# ---------------------------------------------------------------------------
# checksum
# ---------------------------------------------------------------------------

@main.command("checksum")
@click.argument("file")
@click.option(
    "--algorithms", "-a",
    default="md5,sha1,sha256,sha512", show_default=True,
    help="Comma-separated list of hash algorithms to compute.",
)
@click.option("--save", is_flag=True, default=False,
              help="Write a <FILE>.<algo> sidecar for each algorithm.")
@click.pass_context
def cmd_checksum(ctx: click.Context, file: str, algorithms: str, save: bool) -> None:
    """Compute multiple checksums of FILE in a single read pass.

    Examples:

        disktool checksum backup.img

        disktool checksum backup.img --algorithms sha256,sha512

        disktool checksum backup.img --algorithms md5,sha256 --save
    """
    from disktool.core.verify import multi_hash, write_sidecar

    file_path = Path(file)
    if not file_path.exists():
        console.print(f"[bold red]Error:[/bold red] File not found: {file}")
        sys.exit(1)

    algo_list = [a.strip().lower() for a in algorithms.split(",") if a.strip()]
    if not algo_list:
        console.print("[bold red]Error:[/bold red] No algorithms specified.")
        sys.exit(1)

    total_bytes = file_path.stat().st_size

    with _make_progress() as progress:
        task_id = progress.add_task(f"Checksumming {file_path.name}", total=total_bytes)

        def _progress(done: int) -> None:
            progress.update(task_id, completed=done)

        try:
            digests = multi_hash(file_path, algorithms=algo_list, progress_callback=_progress)
        except (FileNotFoundError, ValueError) as exc:
            console.print(f"\n[bold red]Error:[/bold red] {exc}")
            sys.exit(1)

    table = Table(
        title=f"Checksums: {file_path.name}",
        show_header=True,
        header_style="bold cyan",
        border_style="bright_black",
    )
    table.add_column("Algorithm", style="bold", width=10)
    table.add_column("Digest", style="cyan")

    for algo, digest in digests.items():
        table.add_row(algo.upper(), digest)

    console.print()
    console.print(table)

    if save:
        for algo, digest in digests.items():
            sidecar = write_sidecar(file_path, digest, algorithm=algo)
            console.print(f"  [dim]Saved sidecar: {sidecar.name}[/dim]")

    console.print()


# ---------------------------------------------------------------------------
# mount / unmount
# ---------------------------------------------------------------------------

@main.command("mount")
@click.argument("image")
@click.option(
    "--mountpoint", "-m", default=None,
    help=(
        "Directory to mount at.  "
        "Linux: defaults to a new temp directory.  "
        "macOS/Windows: OS picks the mountpoint automatically when omitted."
    ),
)
@click.option("--dry-run", is_flag=True, default=False, help="Simulate without mounting.")
@click.pass_context
def cmd_mount(
    ctx: click.Context,
    image: str,
    mountpoint: Optional[str],
    dry_run: bool,
) -> None:
    """Mount a disk IMAGE for read-only browsing.

    Requires root/Administrator on most platforms.

    Examples:

        disktool mount backup.img

        disktool mount backup.img --mountpoint /mnt/img

        disktool mount backup.img --dry-run
    """
    from disktool.core.mount import mount_image

    try:
        info = mount_image(image, mountpoint=mountpoint, dry_run=dry_run)
    except FileNotFoundError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)
    except ValueError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)
    except OSError as exc:
        console.print(f"[bold red]Mount failed:[/bold red] {exc}")
        console.print("[dim]Hint: mounting requires root/Administrator privileges.[/dim]")
        sys.exit(1)
    except PermissionError:
        console.print("[bold red]Permission denied.[/bold red] Try running as root/Administrator.")
        sys.exit(1)

    if dry_run:
        console.print(f"[yellow][DRY RUN] Would mount {image}.[/yellow]")
    else:
        mp = info.get("mountpoint") or "(OS-assigned)"
        loop = info.get("loop_device")
        console.print(f"\n[bold green]✓ Mounted![/bold green]")
        console.print(f"  Image:      [cyan]{image}[/cyan]")
        console.print(f"  Mountpoint: [cyan]{mp}[/cyan]")
        if loop:
            console.print(f"  Loop dev:   [dim]{loop}[/dim]")
        console.print(f"\n[dim]Run [bold]disktool unmount {mp}[/bold] when done.[/dim]")


@main.command("unmount")
@click.argument("image_or_mountpoint")
@click.option("--dry-run", is_flag=True, default=False, help="Simulate without unmounting.")
@click.pass_context
def cmd_unmount(
    ctx: click.Context,
    image_or_mountpoint: str,
    dry_run: bool,
) -> None:
    """Unmount a previously mounted disk image.

    Pass either the original IMAGE path or the MOUNTPOINT directory.

    Examples:

        disktool unmount /mnt/img

        disktool unmount backup.img --dry-run
    """
    from disktool.core.mount import unmount_image

    try:
        ok = unmount_image(image_or_mountpoint, dry_run=dry_run)
    except ValueError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)
    except OSError as exc:
        console.print(f"[bold red]Unmount failed:[/bold red] {exc}")
        sys.exit(1)
    except PermissionError:
        console.print("[bold red]Permission denied.[/bold red] Try running as root/Administrator.")
        sys.exit(1)

    if dry_run:
        console.print(f"[yellow][DRY RUN] Would unmount {image_or_mountpoint}.[/yellow]")
    elif ok:
        console.print(f"\n[bold green]✓ Unmounted {image_or_mountpoint}.[/bold green]")
    else:
        console.print(f"\n[bold red]✗ Unmount failed.[/bold red]")
        sys.exit(2)


if __name__ == "__main__":
    main()
