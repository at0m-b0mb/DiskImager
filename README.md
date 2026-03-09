# DiskImager

A cross-platform disk imaging, cloning, and flashing tool with both CLI and GUI interfaces.

## Features

- **Backup** – create raw `.img` images of any disk or partition with SHA-256 sidecar
- **Restore** – write an image back to a disk with optional post-write verification
- **Flash** – flash `.img` / `.iso` / `.zip` files to USB drives (bootable)
- **Verify** – compute and compare SHA-256 hashes of image files
- **GUI** – modern dark-theme CustomTkinter interface with live progress
- **Cross-platform** – Windows, macOS, and Linux from a single codebase

## Installation

```bash
pip install -r requirements.txt
```

## CLI Usage

```bash
# List physical drives
python main.py list

# Backup /dev/sdb to a file
python main.py backup /dev/sdb backup.img

# Restore image to /dev/sdc
python main.py restore backup.img /dev/sdc

# Flash an ISO to a USB drive
python main.py flash ubuntu-22.04.iso /dev/sdd

# Verify image integrity
python main.py verify backup.img
python main.py verify backup.img --hash <expected-sha256>

# Launch GUI
python main.py gui
```

## Project Structure

```
disktool/
├── __init__.py
├── cli.py              # Click CLI entrypoint
├── gui.py              # CustomTkinter GUI
├── core/
│   ├── disk.py         # drive enumeration
│   ├── imaging.py      # backup / restore / flash
│   └── verify.py       # SHA-256 hashing & verification
└── platform/
    ├── __init__.py
    ├── linux.py        # Linux /sys enumeration
    ├── darwin.py       # macOS diskutil
    └── windows.py      # Windows WMI/PowerShell
main.py                 # entry point
DiskImager.spec         # PyInstaller build spec
```

## Build Standalone Executable

```bash
pip install pyinstaller
pyinstaller DiskImager.spec
# Output: dist/disktool (or dist/disktool.exe on Windows)
```

## Safety Features

- System disk detection (requires `--dangerous` flag to override)
- Pre-wipe confirmation dialog (type `CONFIRM`)
- SHA-256 post-write verification
- Dry-run mode (`--dry-run`) for safe testing
- Read-only source protection

## Running Tests

```bash
pytest tests/
```

## License

MIT