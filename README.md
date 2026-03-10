# 💿 DiskImager

<p align="center">
  <strong>Cross-platform disk imaging, cloning, flashing, and management tool</strong><br>
  <em>Back up, restore, flash, compress, benchmark, and manage drives with confidence – on Windows, macOS, and Linux.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?logo=github" alt="Cross-platform">
  <img src="https://img.shields.io/badge/GUI-CustomTkinter-purple" alt="CustomTkinter">
  <img src="https://img.shields.io/badge/CLI-Click%20%2B%20Rich-brightgreen" alt="Click + Rich">
  <img src="https://img.shields.io/badge/License-MIT-yellow" alt="MIT License">
  <img src="https://img.shields.io/badge/Tests-279%20passing-success" alt="Tests">
</p>

---

## 🚀 What is DiskImager?

DiskImager is a free, open-source tool for backing up, restoring, flashing, cloning, formatting, compressing, benchmarking, and mounting disk drives.  
Whether you want to clone a USB drive, save a bootable ISO onto a flash drive, compress a backup image, or benchmark storage performance — DiskImager has you covered.

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
  - [clone](#clone)
  - [verify](#verify)
  - [checksum](#checksum)
  - [info](#info)
  - [erase](#erase)
  - [format](#format)
  - [partition](#partition)
  - [compress](#compress)
  - [benchmark](#benchmark)
  - [mount](#mount)
  - [unmount](#unmount)
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
| **Clone** | Direct device-to-device copy with no intermediate file |
| **Verify** | Compute and compare SHA-256/SHA-512 hashes of image files |
| **Checksum** | Single-pass multi-algorithm checksum (MD5, SHA-1, SHA-256, SHA-512) with optional sidecar files |
| **Erase** | Securely overwrite a disk with zeros (multi-pass DoD-style wipe) |
| **Format** | Format a device or partition with FAT32, exFAT, NTFS, ext4, HFS+, or APFS |
| **Partition** | Create MBR or GPT partition tables and define partitions in one command |
| **Compress** | Compress or decompress disk images with gzip, lz4, or zstd – shows space savings |
| **Benchmark** | Measure sequential read and write throughput of any drive or directory |
| **Mount / Unmount** | Read-only mount of disk images using native OS tools (losetup, hdiutil, Mount-DiskImage) |
| **Drive Info** | Detailed partition table and drive metadata, in both GUI and CLI |
| **GUI** | Modern dark/light-theme interface with live progress bars and tabbed layout |
| **CLI** | Beautiful Rich tables, progress bars, and colour output |
| **Cross-platform** | Windows, macOS, and Linux from a single Python codebase |

### GUI Highlights

- **Clickable drive table** – click any row to auto-fill device paths in the active tab
- **Drive Info popup** – click the "Drive Info" button to see partition details for a selected drive
- **Thirteen tabs** – Backup · Restore · Flash · Clone · Verify · Format · Erase · Benchmark · Partition · Compress · Checksum · Mount · Activity
- **Activity log** – timestamped record of every operation
- **Dark / Light theme** toggle
- **Custom CONFIRM dialog** – type CONFIRM before any destructive operation
- **Progress dialog** – live speed, percentage, ETA, and elapsed timer
- **Copy Hash button** – copy the computed SHA-256 digest to clipboard after verification
- **Open Folder** – after a successful backup, jump straight to the output folder
- **Status bar** – live operation status and Python version

### CLI Highlights

- Rich-coloured drive table with boot / USB / system indicators
- SHA-256 sidecar files (`.sha256`) and JSON metadata sidecars (`.json`) on every backup
- Dry-run mode (`--dry-run`) for all write operations
- System-disk safety lock (requires `--dangerous` to override)
- `CONFIRM` prompt before any destructive operation
- Multi-algorithm checksum in a single read pass

### Optional Dependencies

Some features require third-party packages that are not included by default:

| Package | Feature unlocked | Install |
|---------|-----------------|---------|
| `lz4` | lz4 compression in `compress` | `pip install lz4` |
| `zstandard` | zstd compression in `compress` | `pip install zstandard` |
| `pywin32` | Full hardware enumeration on Windows | `pip install pywin32` |

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

# Compress a backup image (gzip by default)
python main.py compress my-usb.img

# Compute checksums (MD5, SHA-1, SHA-256, SHA-512)
python main.py checksum my-usb.img

# Benchmark drive speed
python main.py benchmark /dev/sdb --write
```

---

## GUI Guide

Launch the GUI with:

```bash
python main.py gui
```

### Layout

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  DiskImager v1.0.0  │  Physical Drives                          [Drive Info]     │
│                     │  [table of detected drives]                                │
│  Backup             │  [selected drive info bar]                                 │
│  Restore            ├────────────────────────────────────────────────────────────│
│  Flash              │ Backup│Restore│Flash│Clone│Verify│Format│Erase│…│Activity  │
│  Clone              │                                                            │
│  Verify             │  (tab content for active operation)                        │
│  Format             │                                                            │
│  Erase              │                                                            │
│  Benchmark          │                                                            │
│  Partition          │                                                            │
│  Compress           │                                                            │
│  Checksum           │                                                            │
│  Mount              ├────────────────────────────────────────────────────────────│
│  Activity           │ Status bar: Ready  │  Python 3.12.3                        │
│                     │                                                            │
│  Dark mode [toggle] │                                                            │
│  [Scan Drives]      │                                                            │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Step-by-Step Workflow

1. **Scan** – click **Scan Drives** in the sidebar to detect all physical drives
2. **Select** – click a drive row; the device path auto-fills the active tab's field
3. **Configure** – use Browse… to pick source/destination files; tick options as needed
4. **Run** – click the operation button (e.g. **Start Backup**); a progress dialog shows speed, ETA, and elapsed time
5. **Confirm** – for destructive operations (Restore, Flash, Erase, Format, Partition), type `CONFIRM` in the safety dialog
6. **Review** – check the **Activity** tab for a timestamped log of all operations

### Tips

| Tip | Detail |
|-----|--------|
| **Drive Info** | Select a drive, then click **Drive Info** in the header to see partition details |
| **Copy Hash** | After running Verify, click **Copy Hash** to copy the SHA-256 to your clipboard |
| **Open Folder** | After a successful Backup, DiskImager asks if you want to open the output folder |
| **Dry Run** | Tick **Dry run** in any tab to simulate the operation without writing any data |
| **Dark / Light** | Toggle the **Dark mode** switch in the sidebar |
| **Auto-fill path** | Clicking a drive in the list auto-fills the relevant field in the currently active tab |

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

### clone

Clone a source device directly to a destination device without creating an intermediate image file.

```bash
python main.py clone <SOURCE> <DEST> [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--dry-run` | Simulate without writing |
| `--no-verify` | Skip post-clone SHA-256 verification |
| `--dangerous` | Allow cloning to/from system disks |

```bash
# Clone one USB drive to another
python main.py clone /dev/sdb /dev/sdc

# Dry run
python main.py clone /dev/sdb /dev/sdc --dry-run
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

### checksum

Compute multiple hash digests of a file in a **single read pass** and display them in a table.

```bash
python main.py checksum <FILE> [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--algorithms TEXT` | Comma-separated list of algorithms (default: `md5,sha1,sha256,sha512`) |
| `--save` | Write a sidecar file for each algorithm (e.g. `backup.img.sha256`) |

```bash
# Compute all four default hashes
python main.py checksum backup.img

# Only SHA-256 and SHA-512
python main.py checksum backup.img --algorithms sha256,sha512

# Compute and save sidecar files
python main.py checksum backup.img --algorithms md5,sha256 --save
```

**Example output:**

```
                    Checksums: backup.img
┏━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Algorithm  ┃ Digest                                                           ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ MD5        │ d8e8fca2dc0f896fd7cb4cb0031ba249                                 │
│ SHA1       │ 4e1243bd22c66e76c2ba9eddc1f91394e57f9f83                         │
│ SHA256     │ b94f6f125c79e3a5ffaa826f584c10d52ada669e6762051b826b55776d05a8a   │
│ SHA512     │ 0cf9180a764aba863a67b6d72f0918bc131c6772642cb2dce5a34f0a702f9470 … │
└────────────┴──────────────────────────────────────────────────────────────────┘
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

### format

Format a device or partition with a specified file system.

```bash
python main.py format <DEVICE> <FILESYSTEM> [OPTIONS]
```

Supported file systems: `fat32`, `exfat`, `ntfs`, `ext4`, `hfs+`, `apfs` (platform-dependent).  
Run `python main.py format --list-fs` to see what is available on your system.

| Option | Description |
|--------|-------------|
| `--label TEXT` | Volume label (default: `DISK`) |
| `--dry-run` | Simulate without formatting |
| `--dangerous` | Allow formatting system disks |
| `--list-fs` | List supported file systems and exit |

```bash
# Format USB as FAT32 with a label
python main.py format /dev/sdb fat32 --label MYDRIVE

# Format a partition as ext4
python main.py format /dev/sdb1 ext4 --label DATA

# Format a Windows drive letter
python main.py format E: ntfs --label BACKUP

# See available file systems on this platform
python main.py format --list-fs
```

---

### partition

Create a new MBR or GPT partition table on a device and optionally add partitions in one step.

```bash
python main.py partition <DEVICE> <SCHEME> [OPTIONS]
```

`SCHEME` must be `mbr` or `gpt`.

Each `--add` value takes the form `SIZE[:FS[:LABEL]]`:
- `SIZE` is a percentage (`100%`) or a size with unit (`8G`, `512M`)
- `FS` is an optional file system type hint (`fat32`, `ext4`, `ntfs`, …)
- `LABEL` is an optional partition name

| Option | Description |
|--------|-------------|
| `--add SIZE[:FS[:LABEL]]` | Add a partition (repeatable) |
| `--dry-run` | Simulate without writing |
| `--dangerous` | Allow partitioning system disks |

```bash
# Create a GPT table (no partitions yet)
python main.py partition /dev/sdb gpt

# MBR with one full-disk FAT32 partition
python main.py partition /dev/sdb mbr --add 100%:fat32

# GPT with an EFI boot partition and a root partition
python main.py partition /dev/sdb gpt \
    --add 512M:fat32:EFI \
    --add 100%:ext4:ROOT
```

---

### compress

Compress or decompress a disk image. Reports input size, output size, and space savings.

```bash
python main.py compress <IMAGE> [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-a, --algorithm` | `gzip` (default), `lz4`, or `zstd` |
| `--level N` | Compression level (1–22, algorithm-specific). Default: algorithm default. |
| `-o, --output PATH` | Output path. Default: `IMAGE` with the algorithm extension appended. |
| `-d, --decompress` | Decompress instead of compress (algorithm is auto-detected from extension). |

```bash
# Compress with gzip (creates backup.img.gz)
python main.py compress backup.img

# Compress with zstd at level 3
python main.py compress backup.img --algorithm zstd --level 3

# Decompress (auto-detects algorithm from .gz extension)
python main.py compress backup.img.gz --decompress

# Decompress lz4 to a custom output path
python main.py compress backup.img.lz4 -d -o restored.img
```

> **Optional packages:** lz4 and zstd are not installed by default.  
> Install them with `pip install lz4` or `pip install zstandard`.

---

### benchmark

Measure sequential read and/or write throughput of a device or directory.

```bash
python main.py benchmark <DEVICE> [OPTIONS]
```

`DEVICE` can be a block device path (e.g. `/dev/sdb`) or a directory for write tests.

| Option | Description |
|--------|-------------|
| `--size MB` | Data to read/write per phase (default: 64, max: 4096) |
| `--block-size MB` | I/O block size in MiB (default: 4) |
| `--write` | Also run a sequential write benchmark |
| `--read-only` | Skip the read benchmark (use with `--write` to run write only) |

```bash
# Read-only benchmark with default settings
python main.py benchmark /dev/sdb

# 128 MB read + write benchmark
python main.py benchmark /dev/sdb --size 128 --write

# Write-only benchmark using a directory
python main.py benchmark /tmp --write --read-only
```

---

### mount

Mount a disk image read-only for browsing. Requires root/Administrator on most platforms.

```bash
python main.py mount <IMAGE> [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-m, --mountpoint PATH` | Directory to mount at. Linux: auto-creates a temp dir if omitted. macOS/Windows: OS picks automatically. |
| `--dry-run` | Simulate without mounting |

```bash
# Mount (Linux auto-creates /tmp/disktool_mount_XXXXX)
python main.py mount backup.img

# Mount at a specific directory
python main.py mount backup.img --mountpoint /mnt/img

# Simulate
python main.py mount backup.img --dry-run
```

After mounting, DiskImager prints the mountpoint path. Run `disktool unmount <mountpoint>` when done.

---

### unmount

Unmount a previously mounted disk image.

```bash
python main.py unmount <IMAGE_OR_MOUNTPOINT> [OPTIONS]
```

Pass either the original image path **or** the mountpoint directory.

| Option | Description |
|--------|-------------|
| `--dry-run` | Simulate without unmounting |

```bash
# Unmount by mountpoint
python main.py unmount /mnt/img

# Unmount by image path (Linux)
python main.py unmount backup.img

# Dry run
python main.py unmount /mnt/img --dry-run
```

---

## Safety Features

| Feature | Description |
|---------|-------------|
| **System disk lock** | Restore, Flash, Clone, Erase, Format, and Partition are blocked on system disks unless `--dangerous` is passed (CLI) or confirmed (GUI) |
| **CONFIRM prompt** | All destructive operations require the user to type `CONFIRM` (custom dialog in GUI, typed prompt in CLI) |
| **SHA-256 verification** | Post-write read-back verification for Restore, Flash, and Clone |
| **Dry-run mode** | `--dry-run` / checkbox simulates the full operation without writing a single byte |
| **SHA-256 sidecar** | Every Backup creates a `.sha256` file for future integrity checking |
| **JSON metadata** | Every Backup creates a `.json` sidecar recording source path, size, hash, and timestamp |
| **Read-only mounts** | `mount` always uses read-only mode to prevent accidental writes to mounted images |

---

## Project Structure

```
DiskImager/
├── main.py                      # Single entry point
├── pyproject.toml               # Project metadata (setuptools)
├── requirements.txt             # pip dependencies
├── DiskImager.spec              # PyInstaller build specification
├── disktool/
│   ├── __init__.py              # Package version
│   ├── cli.py                   # Click CLI (all 15 commands)
│   ├── gui.py                   # CustomTkinter GUI (dark/light, 13 tabs, live progress)
│   ├── settings.py              # Persistent user settings
│   ├── core/
│   │   ├── disk.py              # Unified drive enumeration + psutil fallback
│   │   ├── imaging.py           # backup / restore / flash / clone / erase (chunked I/O)
│   │   ├── verify.py            # SHA-256/SHA-512 hashing, multi_hash(), sidecar management
│   │   ├── format.py            # Cross-platform disk formatting
│   │   ├── partition.py         # MBR/GPT partition table management
│   │   ├── compress.py          # gzip / lz4 / zstd streaming compression
│   │   ├── benchmark.py         # Sequential read/write throughput measurement
│   │   └── mount.py             # Cross-platform image mount / unmount
│   └── platform/
│       ├── __init__.py          # Auto-selects platform backend
│       ├── linux.py             # /sys/block enumeration
│       ├── darwin.py            # diskutil plist
│       └── windows.py           # WMI + PowerShell Get-Disk
└── tests/
    ├── test_cli.py              # CLI command tests
    ├── test_disk.py             # Drive enumeration tests
    ├── test_imaging.py          # Backup / restore / flash / clone / erase tests
    ├── test_verify.py           # Hash / sidecar / multi_hash tests
    ├── test_format.py           # Format tests
    ├── test_partition.py        # Partition table tests
    ├── test_benchmark.py        # Benchmark tests
    ├── test_compress.py         # Compress / decompress tests
    ├── test_checksum_mount.py   # Checksum + mount / unmount tests
    └── test_settings.py         # Settings persistence tests
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

# Run all 279 tests
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

### "Algorithm not available" when compressing

lz4 and zstd are optional. Install the required package:

```bash
pip install lz4          # for --algorithm lz4
pip install zstandard    # for --algorithm zstd
```

### Mount fails on Linux

Mounting requires `losetup` and `mount` which need root privileges.  
Run with `sudo python main.py mount <image>`.  
If losetup is not available, install `util-linux` (`sudo apt install util-linux` on Debian/Ubuntu).

---

## FAQ

**Q: Can I use DiskImager to create a bootable USB drive from an ISO?**  
A: Yes – use the **Flash** tab (GUI) or `python main.py flash <image.iso> <device>` (CLI).

**Q: Will it work on Windows?**  
A: Yes. Device paths on Windows look like `\\.\PhysicalDrive0`. Run as Administrator.

**Q: Is the backup a 1:1 raw copy?**  
A: Yes. DiskImager reads every byte of the source device and writes them to the destination file. The result is a raw `.img` file usable with other tools (e.g. `dd`, Balena Etcher, Win32DiskImager).

**Q: How do I know if my backup is intact?**  
A: Every backup creates a `.sha256` sidecar file. Run `python main.py verify backup.img` (or use the Verify tab) to recompute and compare the hash at any time. For multiple algorithms at once, use `python main.py checksum backup.img`.

**Q: What does "erase" actually do?**  
A: With 1 pass it overwrites every byte with zeros. With 2+ passes it writes random data first, then zeros on the final pass, following a simplified DoD 5220.22-M approach.

**Q: Can I cancel an in-progress operation?**  
A: Yes – click the **Cancel** button in the progress dialog. The operation will stop at the next chunk boundary.

**Q: What compression format should I use?**  
A: `gzip` is the safest choice (no extra packages needed and widely compatible). `lz4` is faster with slightly lower compression. `zstd` offers the best compression ratio with good speed. All three support `--decompress` to restore the original image.

**Q: What is the difference between `clone` and `backup` + `restore`?**  
A: `clone` copies one device directly to another device without creating an intermediate file, saving disk space and time. `backup` + `restore` creates a file you can keep, compress, and restore later.

**Q: What does `checksum` do that `verify` doesn't?**  
A: `verify` computes a single SHA-256 hash and optionally compares it to an expected value. `checksum` computes up to four different algorithms (MD5, SHA-1, SHA-256, SHA-512) in **one read pass**, which is faster than running them individually. It also supports saving sidecar files for each algorithm.

**Q: Is the mounted image writable?**  
A: No. `mount` always uses read-only mode to protect your backup data. To modify the image, unmount it first and then work with the raw file.

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
