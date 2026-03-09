# 💿 DiskImager

<p align="center">
  <strong>Cross-platform disk imaging, cloning, and flashing tool</strong><br>
  <em>A full-featured, production-ready solution for backup, restore, and USB flashing on Windows, macOS, and Linux.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?logo=github" alt="Cross-platform">
  <img src="https://img.shields.io/badge/GUI-CustomTkinter-purple" alt="CustomTkinter">
  <img src="https://img.shields.io/badge/CLI-Click%20%2B%20Rich-brightgreen" alt="Click + Rich">
  <img src="https://img.shields.io/badge/License-MIT-yellow" alt="MIT License">
  <img src="https://img.shields.io/badge/Tests-48%20passing-success" alt="Tests">
</p>

> **Repository description (GitHub *About* field):**
> *DiskImager — cross-platform disk imaging, backup, restore, USB flash & secure erase tool with a modern dark/light-mode GUI and a rich colour CLI. Supports Windows, macOS and Linux. Includes SHA-256 verification, dry-run mode, and multi-pass secure erase.*

> **Suggested GitHub topics:**
> `disk-imaging` · `backup` · `restore` · `usb-flash` · `iso-flash` · `disk-clone` · `secure-erase` · `python` · `customtkinter` · `gui` · `cli` · `cross-platform` · `sha256` · `storage` · `system-administration` · `linux` · `windows` · `macos` · `pyinstaller` · `dark-mode`

---

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [CLI Reference](#cli-reference)
  - [list](#list)
  - [backup](#backup)
  - [restore](#restore)
  - [flash](#flash)
  - [verify](#verify)
  - [info](#info)
  - [erase](#erase)
- [GUI Guide](#gui-guide)
- [Safety Features](#safety-features)
- [Project Structure](#project-structure)
- [Building a Standalone Executable](#building-a-standalone-executable)
- [Running Tests](#running-tests)
- [Contributing](#contributing)
- [License](#license)

---

## Features

| Feature | Description |
|---------|-------------|
| **Backup** | Raw byte-for-byte copy of any disk or partition to a `.img` file |
| **Restore** | Write an image back to a disk with SHA-256 post-write verification |
| **Flash** | Flash `.img`, `.iso`, or `.zip` archives to USB drives |
| **Verify** | Compute and compare SHA-256/SHA-512 hashes of image files |
| **Erase** | Securely overwrite a disk with zeros (multi-pass DoD-style wipe) |
| **Drive Info** | Detailed partition table and drive metadata |
| **GUI** | Modern dark/light-theme CustomTkinter interface with live progress |
| **CLI** | Beautiful Rich tables, progress bars, and colour output |
| **Cross-platform** | Windows, macOS, and Linux from a single Python codebase |

### GUI Highlights

- **Clickable drive table** – click any row to auto-fill device paths
- **Activity log** – timestamped record of every operation
- **Dark / Light theme** toggle
- **Custom CONFIRM dialog** – type CONFIRM before any destructive operation
- **Progress dialog** – live speed, percentage, ETA, and elapsed timer
- **Five tabs** – Backup · Restore · Flash · Verify · Activity
- **Status bar** – live operation status and Python version

### CLI Highlights

- Rich-coloured drive table with boot / USB / system indicators
- SHA-256 sidecar files (`.sha256`) and JSON metadata sidecars (`.json`) on every backup
- Dry-run mode (`--dry-run`) for all write operations
- System-disk safety lock (requires `--dangerous` to override)
- `CONFIRM` prompt before any destructive operation

---

## Installation

### Prerequisites

- Python **3.11** or newer
- `pip`

### Install dependencies

```bash
git clone https://github.com/at0m-b0mb/DiskImager.git
cd DiskImager
pip install -r requirements.txt
```

> **Windows only:** Install `pywin32` for full hardware enumeration:
> ```
> pip install pywin32
> ```

---

## Quick Start

```bash
# Launch the GUI
python main.py gui

# List all physical drives
python main.py list

# Backup a USB drive to an image file
python main.py backup /dev/sdb my-usb.img

# Flash an ISO to a USB drive
python main.py flash ubuntu-24.04.iso /dev/sdb
```

---

## CLI Reference

All commands share the global `--verbose / -v` flag which enables debug logging, and `--version`.

### list

List all detected physical drives.

```bash
python main.py list
```

**Example output:**

```
                               Physical Drives
 ┏━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┳━━━━━━━┓
 ┃   ID ┃ Device   ┃     Size ┃   Type   ┃ Boot?  ┃ Model             ┃ Parts ┃
 ┡━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━━┩
 │    0 │ /dev/sda │ 931.5 GB │ Internal │ ❌ YES │ Samsung SSD 990   │     4 │
 │    1 │ /dev/sdb │  31.9 GB │ 🔌 USB   │ ✅ NO  │ SanDisk Ultra     │     1 │
 └──────┴──────────┴──────────┴──────────┴────────┴───────────────────┴───────┘
```

---

### backup

Create a raw `.img` image of a disk with SHA-256 sidecar and JSON metadata.

```bash
python main.py backup <SOURCE> <DEST> [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--dry-run` | Simulate without writing |
| `--no-verify` | Skip post-backup hash hint |

```bash
# Backup USB drive
python main.py backup /dev/sdb backup.img

# Dry run (no data written)
python main.py backup /dev/sdb backup.img --dry-run
```

**Output files:**

| File | Description |
|------|-------------|
| `backup.img` | Raw disk image |
| `backup.img.sha256` | SHA-256 checksum sidecar |
| `backup.json` | JSON metadata (source, size, hash, timestamp, platform) |

---

### restore

Write an image file back to a disk (with post-write verification).

```bash
python main.py restore <IMAGE> <DEST> [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--dry-run` | Simulate without writing |
| `--no-verify` | Skip post-restore SHA-256 verification |
| `--dangerous` | Allow writing to system disks |

```bash
# Restore an image (prompts CONFIRM first)
python main.py restore backup.img /dev/sdc

# Skip verification for speed
python main.py restore backup.img /dev/sdc --no-verify
```

---

### flash

Flash an `.img`, `.iso`, or `.zip`-packaged image to a USB drive.

```bash
python main.py flash <IMAGE> <DEST> [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--dry-run` | Simulate without writing |
| `--no-verify` | Skip post-flash verification |
| `--dangerous` | Allow writing to system disks |

```bash
# Flash Ubuntu ISO to USB
python main.py flash ubuntu-24.04.iso /dev/sdb

# Flash a compressed image
python main.py flash raspios.img.zip /dev/sdb
```

---

### verify

Compute and optionally compare the SHA-256 hash of an image.

```bash
python main.py verify <IMAGE> [--hash <EXPECTED>]
```

```bash
# Compute hash only
python main.py verify backup.img

# Compare against a known hash
python main.py verify backup.img --hash abc123...

# Auto-detect from .sha256 sidecar
python main.py verify backup.img
```

---

### info

Show detailed information about a specific drive, including partition table.

```bash
python main.py info <DEVICE>
```

```bash
python main.py info /dev/sda
```

**Example output:**

```
─────────────── Drive Info: /dev/sda ───────────────
  Device    /dev/sda
  Model     Samsung SSD 990 PRO
  Size      931.5 GB  (1,000,204,886,016 bytes)
  Removable No
  System    Yes
  Partitions 4

──────────────── Partitions ──────────────────────
 Name    Path        Size       Mount Point   FS
 sda1    /dev/sda1   512.0 MB   /boot/efi     vfat
 sda2    /dev/sda2   931.0 GB   /             ext4
```

---

### erase

Securely overwrite a disk with zeros. Supports multi-pass DoD-style wiping.

```bash
python main.py erase <DEST> [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--passes N` | Number of overwrite passes (1–7). Passes > 1 use random data then zeros. |
| `--dry-run` | Simulate without writing |
| `--dangerous` | Allow erasing system disks |

```bash
# Single-pass zero fill
python main.py erase /dev/sdb

# 3-pass wipe (random, random, zeros)
python main.py erase /dev/sdb --passes 3
```

---

## GUI Guide

Launch the GUI:

```bash
python main.py gui
```

### Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│  DiskImager v1.0.0          │  Physical Drives                          │
│                             │  [table of detected drives]               │
│  Backup                     │  [selected drive info bar]                │
│  Restore                    ├───────────────────────────────────────────┤
│  Flash                      │ [Backup] [Restore] [Flash] [Verify] [Log] │
│  Verify                     │                                           │
│  Activity                   │  (tab content for active operation)       │
│                             │                                           │
│  Dark mode  [toggle]        │                                           │
│  [Scan Drives]              │                                           │
│  Linux x86_64               ├───────────────────────────────────────────┤
│                             │ Status bar: Ready  │  Python 3.12.3       │
└─────────────────────────────────────────────────────────────────────────┘
```

### Workflow

1. **Scan** – click **Scan Drives** to enumerate all physical drives
2. **Select** – click any drive row to select it; the device path auto-fills the active tab
3. **Configure** – browse for source/dest files and choose options
4. **Run** – click the operation button; a progress dialog shows speed, ETA, and elapsed time
5. **Confirm** – for destructive operations, type `CONFIRM` in the safety dialog
6. **Review** – check the **Activity** tab for a timestamped log of all operations

### Theme

Use the **Dark mode** toggle in the sidebar to switch between dark and light themes.

---

## Safety Features

| Feature | Description |
|---------|-------------|
| **System disk lock** | Restore, Flash, and Erase are blocked on system disks unless `--dangerous` is passed (CLI) |
| **CONFIRM prompt** | All destructive operations require the user to type `CONFIRM` (custom dialog in GUI, typed prompt in CLI) |
| **SHA-256 verification** | Post-write read-back verification for Restore and Flash |
| **Dry-run mode** | `--dry-run` / checkbox simulates the full operation without writing a single byte |
| **SHA-256 sidecar** | Every Backup creates a `.sha256` file for future integrity checking |
| **JSON metadata** | Every Backup creates a `.json` sidecar recording source path, size, hash, and timestamp |

---

## Project Structure

```
DiskImager/
├── main.py                   # Single entry point
├── pyproject.toml            # Project metadata (setuptools)
├── requirements.txt          # pip dependencies
├── DiskImager.spec           # PyInstaller build specification
├── disktool/
│   ├── __init__.py           # Package version
│   ├── cli.py                # Click CLI (list, backup, restore, flash, verify, info, erase)
│   ├── gui.py                # CustomTkinter GUI (dark/light, tabbed, live progress)
│   ├── core/
│   │   ├── disk.py           # Unified drive enumeration + psutil fallback
│   │   ├── imaging.py        # backup / restore / flash / erase (chunked I/O)
│   │   └── verify.py         # SHA-256/SHA-512 hashing and sidecar management
│   └── platform/
│       ├── __init__.py       # Auto-selects platform backend
│       ├── linux.py          # /sys/block enumeration
│       ├── darwin.py         # diskutil plist
│       └── windows.py        # WMI + PowerShell Get-Disk
└── tests/
    ├── test_cli.py           # CLI command tests
    ├── test_disk.py          # Drive enumeration tests
    ├── test_imaging.py       # Backup / restore / flash / erase tests
    └── test_verify.py        # Hash / sidecar tests
```

---

## Building a Standalone Executable

```bash
pip install pyinstaller
pyinstaller DiskImager.spec
```

Output: `dist/disktool` (Linux/macOS) or `dist/disktool.exe` (Windows).

The spec file includes all platform modules and hides the console window on Windows when using `--windowed`.

---

## Running Tests

```bash
# Install test dependencies
pip install pytest pytest-cov

# Run all 48 tests
pytest tests/

# Run with coverage report
pytest tests/ --cov=disktool --cov-report=term-missing
```

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes with tests
4. Run `pytest tests/` to ensure everything passes
5. Open a pull request

---

## License

MIT — see [LICENSE](LICENSE) for details.
