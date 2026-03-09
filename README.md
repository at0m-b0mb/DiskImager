# 💿 DiskImager

<p align="center">
  <strong>Cross-platform disk imaging, cloning, and flashing tool</strong><br>
  <em>Back up, restore, and flash drives with confidence – on Windows, macOS, and Linux.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?logo=github" alt="Cross-platform">
  <img src="https://img.shields.io/badge/GUI-CustomTkinter-purple" alt="CustomTkinter">
  <img src="https://img.shields.io/badge/CLI-Click%20%2B%20Rich-brightgreen" alt="Click + Rich">
  <img src="https://img.shields.io/badge/License-MIT-yellow" alt="MIT License">
  <img src="https://img.shields.io/badge/Tests-48%20passing-success" alt="Tests">
</p>

---

## 🚀 What is DiskImager?

DiskImager is a free, open-source tool for backing up, restoring, and flashing disk drives.  
Whether you want to clone a USB drive, save a bootable ISO onto a flash drive, or create a full byte-for-byte image of a hard disk, DiskImager has you covered.

**It is designed to be safe by default:**

- 🔒 Destructive operations require typing `CONFIRM` before anything happens
- 🛡️ System disks are automatically locked from writes unless you explicitly allow it
- ✅ SHA-256 verification after every restore and flash to catch errors
- 🧪 Dry-run mode lets you preview what *would* happen without touching any data

---

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [GUI Guide](#gui-guide)
- [CLI Reference](#cli-reference)
  - [list](#list)
  - [backup](#backup)
  - [restore](#restore)
  - [flash](#flash)
  - [verify](#verify)
  - [info](#info)
  - [erase](#erase)
- [Safety Features](#safety-features)
- [Project Structure](#project-structure)
- [Building a Standalone Executable](#building-a-standalone-executable)
- [Running Tests](#running-tests)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)
- [Contributing](#contributing)
- [License](#license)

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **Backup** | Raw byte-for-byte copy of any disk or partition to a `.img` file |
| **Restore** | Write an image back to a disk with SHA-256 post-write verification |
| **Flash** | Flash `.img`, `.iso`, or `.zip` archives to USB drives |
| **Verify** | Compute and compare SHA-256/SHA-512 hashes of image files |
| **Erase** | Securely overwrite a disk with zeros (multi-pass DoD-style wipe) |
| **Drive Info** | Detailed partition table and drive metadata, in both GUI and CLI |
| **GUI** | Modern dark/light-theme interface with live progress bars and tabbed layout |
| **CLI** | Beautiful Rich tables, progress bars, and colour output |
| **Cross-platform** | Windows, macOS, and Linux from a single Python codebase |

### GUI Highlights

- **Clickable drive table** – click any row to auto-fill device paths in the active tab
- **Drive Info popup** – click the "Drive Info" button to see partition details for a selected drive
- **Erase tab** – securely wipe a drive with configurable overwrite passes, directly from the GUI
- **Activity log** – timestamped record of every operation
- **Dark / Light theme** toggle
- **Custom CONFIRM dialog** – type CONFIRM before any destructive operation
- **Progress dialog** – live speed, percentage, ETA, and elapsed timer
- **Copy Hash button** – copy the computed SHA-256 digest to clipboard after verification
- **Open Folder** – after a successful backup, jump straight to the output folder
- **Six tabs** – Backup · Restore · Flash · Verify · Erase · Activity
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

> **Linux/macOS:** You may need to run with `sudo` to access raw block devices.

---

## Quick Start

```bash
# Launch the GUI (recommended for most users)
python main.py gui

# List all physical drives
python main.py list

# Backup a USB drive to an image file
python main.py backup /dev/sdb my-usb.img

# Flash an ISO to a USB drive
python main.py flash ubuntu-24.04.iso /dev/sdb
```

---

## GUI Guide

Launch the GUI with:

```bash
python main.py gui
```

### Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  DiskImager v1.0.0        │  Physical Drives          [Drive Info]           │
│                           │  [table of detected drives]                      │
│  Backup                   │  [selected drive info bar]                       │
│  Restore                  ├──────────────────────────────────────────────────│
│  Flash                    │ [Backup][Restore][Flash][Verify][Erase][Activity]│
│  Verify                   │                                                  │
│  Erase                    │  (tab content for active operation)              │
│  Activity                 │                                                  │
│                           │                                                  │
│  Dark mode  [toggle]      │                                                  │
│  [Scan Drives]            │                                                  │
│  Linux x86_64             ├──────────────────────────────────────────────────│
│                           │ Status bar: Ready  │  Python 3.12.3              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Step-by-Step Workflow

1. **Scan** – click **Scan Drives** in the sidebar to detect all physical drives
2. **Select** – click a drive row; the device path auto-fills the active tab's field
3. **Configure** – use Browse… to pick source/destination files; tick options as needed
4. **Run** – click the operation button (e.g. **Start Backup**); a progress dialog shows speed, ETA, and elapsed time
5. **Confirm** – for destructive operations (Restore, Flash, Erase), type `CONFIRM` in the safety dialog
6. **Review** – check the **Activity** tab for a timestamped log of all operations

### Tips

| Tip | Detail |
|-----|--------|
| **Drive Info** | Select a drive, then click **Drive Info** in the header to see partition details |
| **Copy Hash** | After running Verify, click **Copy Hash** to copy the SHA-256 to your clipboard |
| **Open Folder** | After a successful Backup, DiskImager asks if you want to open the output folder |
| **Dry Run** | Tick **Dry run** in any tab to simulate the operation without writing any data |
| **Dark / Light** | Toggle the **Dark mode** switch in the sidebar |

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

# Auto-detect from .sha256 sidecar (created automatically by backup)
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

## Safety Features

| Feature | Description |
|---------|-------------|
| **System disk lock** | Restore, Flash, and Erase are blocked on system disks unless `--dangerous` is passed (CLI) or confirmed (GUI) |
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

## Troubleshooting

### "Permission denied" when accessing a drive

You need elevated privileges to read/write raw block devices.

- **Linux/macOS:** run with `sudo python main.py ...`
- **Windows:** right-click your terminal and choose **Run as Administrator**

### No drives appear in the list

- Run as root/Administrator (see above).
- On Windows, make sure `pywin32` is installed (`pip install pywin32`).
- Try clicking **Scan Drives** again after granting permissions.

### GUI won't start – "customtkinter not installed"

Install the GUI dependency:

```bash
pip install customtkinter
```

### Verification failed after restore/flash

This can indicate a hardware problem (faulty USB cable or drive) or that the source image is corrupt.  
Try a different USB port or cable, or re-download the image and verify its hash.

### ZIP archive not recognised during Flash

Make sure the `.zip` contains exactly one `.img` or `.iso` file at the root level.

---

## FAQ

**Q: Can I use DiskImager to create a bootable USB drive from an ISO?**  
A: Yes – use the **Flash** tab (GUI) or `python main.py flash <image.iso> <device>` (CLI).

**Q: Will it work on Windows?**  
A: Yes. Device paths on Windows look like `\\.\PhysicalDrive0`. Run as Administrator.

**Q: Is the backup a 1:1 raw copy?**  
A: Yes. DiskImager reads every byte of the source device and writes them to the destination file. The result is a raw `.img` file usable with other tools (e.g. `dd`, Balena Etcher, Win32DiskImager).

**Q: How do I know if my backup is intact?**  
A: Every backup creates a `.sha256` sidecar file. Run `python main.py verify backup.img` (or use the Verify tab) to recompute and compare the hash at any time.

**Q: What does "erase" actually do?**  
A: With 1 pass it overwrites every byte with zeros. With 2+ passes it writes random data first, then zeros on the final pass, following a simplified DoD 5220.22-M approach.

**Q: Can I cancel an in-progress operation?**  
A: Yes – click the **Cancel** button in the progress dialog. The operation will stop at the next chunk boundary.

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
