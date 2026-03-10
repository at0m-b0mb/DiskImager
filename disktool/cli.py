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


if __name__ == "__main__":
    main()
